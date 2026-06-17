import sys
import time
import signal
import datetime
import numpy as np
import atomize.general_modules.general_functions as general
import atomize.device_modules.Insys_FPGA as pb_pro
import atomize.device_modules.Micran_X_band_MW_bridge_v2 as mwBridge
import atomize.device_modules.Lakeshore_335 as ls
import atomize.device_modules.BH_15 as bh
import atomize.general_modules.csv_opener_saver as openfile

# initialization of the devices
file_handler = openfile.Saver_Opener()
ls335 = ls.Lakeshore_335()
mw = mwBridge.Micran_X_band_MW_bridge_v2()
pb = pb_pro.Insys_FPGA()
bh15 = bh.BH_15()

def cleanup(*args):
    pb.pulser_close()
    # save whatever of the decay curve has been acquired so far
    file_handler.save_data(file_data, echo, header = header, mode = 'w')
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)

### Experimental parameters
# CPMG (Carr-Purcell-Meiboom-Gill), AWG version, universal in the number of pi pulses:
#
#   pi/2_x - tau - [ pi_y - 2*tau - (echo) ]  x NPI
#
# The pi/2 sits at t = 0, the n-th refocusing pi pulse at (2n-1)*tau, and the
# n-th echo forms at 2n*tau (n = 1 .. NPI). The pi pulses are all phased +y
# (Meiboom-Gill) so pulse-length errors do not accumulate; the pi/2 and the
# detection are cycled +x/-x to remove receiver offset / unwanted FIDs.
#
# The whole CPMG train is generated once. The indirect dimension is the echo
# index k (0 .. NPI-1): for every k only the DETECTION trigger is moved onto
# echo k+1, so the spin system always sees the identical train and we sample a
# different echo each time. digitizer_iq( integral = True ) collapses every
# captured echo to a single complex value, so the acquired row is directly the
# T2 (CPMG) decay - echo amplitude vs time - which is what we plot live.
NPI = 100                   # number of refocusing pi pulses = number of echoes
POINTS = NPI                # one indirect point per echo
FIELD = 3340.0
AVERAGES = 20
SCANS = 1
PHASES = 2                  # 2-step phase cycle (pi/2 and detection +x/-x)
DEC_COEF = 1                # must match 'Decimation' in digitizer_insys.param
process = 'None'

# PULSES
REP_RATE = '2000 Hz'
# pi/2 and pi share the length; the pi pulse is driven at twice the amplitude
# (AMPL_180 = 2 * AMPL_90), the usual AWG way to keep both pulses short.
PULSE_90_LENGTH = '44.8 ns'         # pi/2  excitation pulse
PULSE_180_LENGTH = '44.8 ns'        # pi    refocusing pulses, same length, 2x amplitude
PULSE_DETECTION_LENGTH = '512 ns'

# Fixed timing (ns). tau and all derived positions are multiples of the 3.2 ns
# pulser timebase so nothing is silently re-rounded.
TAU = 320.0                         # fixed pulse spacing; first echo at 2*tau
P90_START = 0.0                     # pi/2, fixed at t = 0
ECHO_SPACING = 2 * TAU             # echo-to-echo (and pi-to-pi) spacing
# detection window centered on the first echo (2*tau); moved by ECHO_SPACING/echo
ECHO_1 = 2 * TAU
DET_START = ECHO_1 - float(PULSE_DETECTION_LENGTH.split(' ')[0]) / 2

SHAPE = 'SINE'
FREQ = '50 MHz'

AMPL_90 = 20
AMPL_180 = 40

# IQ demodulation / phase correction (digitizer_iq).
# The AWG pulses sit at a digital IF (FREQ), so the detected signal must be
# digitally down-converted before integration. The demodulation frequency is the
# NEGATIVE of the AWG frequency, exactly as awg_phasing_insys computes it.
IQ_FREQ = -float(FREQ.split(' ')[0])    # MHz

# Phase corrections passed to digitizer_iq (worker units: rad, rad/s, rad/s^2).
# By default they are read from digitizer_insys.param via digitizer_read_settings()
# below, so they follow the phasing GUI even when no preset was saved. Set any of
# these to a number to override the value coming from the file.
ZERO_ORDER = None       # rad      ; None -> use digitizer_insys.param
FIRST_ORDER = None      # rad/s    ; None -> use digitizer_insys.param
SECOND_ORDER = None     # rad/s^2  ; None -> use digitizer_insys.param

# NAMES
EXP_NAME = 'CPMG'       # T2 (CPMG) decay: echo amplitude vs time

# 2-step phase cycle. pi pulses fixed at +y (Meiboom-Gill); pi/2 and detection
# cycled +x/-x and combined with the +/- acquisition sign by the digitizer.
PH_90  = ['+x', '-x']
PH_180 = ['+y', '+y']
PH_DET = ['+x', '-x']

# Setting magnetic field
bh15.magnet_setup(FIELD, 1)
bh15.magnet_field(FIELD)

# Setting pulses (TRIGGER_AWG triggers carry the timing; AWG pulses carry the phase)
# pi/2 excitation
pb.pulser_pulse(name = 'P0', channel = 'TRIGGER_AWG', start = f"{P90_START} ns",
            length = PULSE_90_LENGTH)
pb.awg_pulse(name = 'A0', channel = 'CH0', func = SHAPE, frequency = FREQ, phase = 0,
            length = PULSE_90_LENGTH, sigma = PULSE_90_LENGTH, start = f"{P90_START} ns",
            phase_list = PH_90, amplitude = AMPL_90)

# NPI refocusing pi pulses at (2n-1)*tau, n = 1 .. NPI
for n in range(1, NPI + 1):
    pos = (2 * n - 1) * TAU
    pb.pulser_pulse(name = f'P{n}', channel = 'TRIGGER_AWG', start = f"{pos} ns",
                length = PULSE_180_LENGTH)
    pb.awg_pulse(name = f'A{n}', channel = 'CH0', func = SHAPE, frequency = FREQ, phase = 0,
                length = PULSE_180_LENGTH, sigma = PULSE_180_LENGTH, start = f"{pos} ns",
                phase_list = PH_180, amplitude = AMPL_180)

# single detection trigger, repositioned onto each echo during acquisition
pb.pulser_pulse(name = 'PDET', channel = 'DETECTION', start = f"{DET_START} ns",
            length = PULSE_DETECTION_LENGTH, phase_list = PH_DET)

pb.digitizer_decimation(DEC_COEF)

pb.pulser_repetition_rate( REP_RATE )
pb.pulser_default_synt(1)

pb.pulser_open()
pb.digitizer_number_of_averages(AVERAGES)

# Integration window (win_left / win_right), decimation and phase corrections are
# taken from the live digitizer_insys.param written by the phasing GUI, so the
# script integrates exactly the window the user phased on. digitizer_iq( integral
# = True ) uses win_left / win_right internally.
pb.digitizer_read_settings()
points_window = pb.digitizer_window_points()

# phase corrections: take the file value (set by the phasing GUI) unless the
# corresponding constant above was set to override it
zero_order   = pb.zero_order   if ZERO_ORDER   is None else ZERO_ORDER
first_order  = pb.first_order  if FIRST_ORDER  is None else FIRST_ORDER
second_order = pb.second_order if SECOND_ORDER is None else SECOND_ORDER

# raw single-echo transient kept only for the live IQ demodulation; echo is the
# integrated CPMG decay (I, Q) we build and plot at every phase step.
data = np.zeros( ( 2, points_window, POINTS ) )
echo = np.zeros( ( 2, POINTS ) )

# x axis of the decay: echo time = 2*tau * (k + 1), in seconds
echo_time = ( np.arange( 1, NPI + 1 ) * ECHO_SPACING ) / 1e9

# Data saving
now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
w = 30

header = (
    f"{'Date:':<{w}} {now}\n"
    f"{'Experiment:':<{w}} CPMG\n"
    f"{'Field:':<{w}} {FIELD} G\n"
    f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
    f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
    f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
    f"{general.fmt(mw.mw_bridge_att2_prd(), w)}\n"
    f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
    f"{'Repetition Rate:':<{w}} {pb.pulser_repetition_rate()}\n"
    f"{'Number of Scans:':<{w}} {SCANS}\n"
    f"{'Averages:':<{w}} {AVERAGES}\n"
    f"{'Phases:':<{w}} {PHASES}\n"
    f"{'Number of pi pulses:':<{w}} {NPI}\n"
    f"{'Tau:':<{w}} {TAU} ns\n"
    f"{'Echo Spacing (2*tau):':<{w}} {ECHO_SPACING} ns\n"
    f"{'Train Length (2*NPI*tau):':<{w}} {ECHO_SPACING * NPI} ns\n"
    f"{'Window:':<{w}} {PULSE_DETECTION_LENGTH}\n"
    f"{'Integration Window:':<{w}} {pb.win_left * 0.4 * DEC_COEF:.1f} - {pb.win_right * 0.4 * DEC_COEF:.1f} ns\n"
    f"{'IQ Frequency:':<{w}} {IQ_FREQ} MHz\n"
    f"{'Phase (0 / 1 / 2):':<{w}} {zero_order:.4g} rad / {first_order:.4g} rad/s / {second_order:.4g} rad/s2\n"
    f"{'Horizontal Resolution:':<{w}} {0.4 * DEC_COEF:.1g} ns\n"
    f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
    f"{'-'*50}\n"
    f"Pulse List:\n{pb.pulser_pulse_list()}"
    f"{'-'*50}\n"
    f"AWG Pulse List:\n{pb.awg_pulse_list()}"
    f"{'-'*50}\n"
    f"CPMG Decay (I, Q) vs echo time"
)

file_data = file_handler.create_file_dialog()

# Data acquisition
for k in general.scans(SCANS):

    for idx in range(POINTS):

        # move the detection window onto echo idx (echo idx+1 at 2*tau*(idx+1)).
        # pulser_redefine_start does NOT reset the indirect-point counter (unlike
        # pulser_pulse_reset); the pi train stays put.
        pb.pulser_redefine_start( name = 'PDET', start = f"{DET_START + idx * ECHO_SPACING} ns" )

        # phase cycle
        for i in range(PHASES):

            pb.awg_next_phase()
            pb.pulser_update()

            a, b = pb.digitizer_get_curve( POINTS, PHASES, current_scan = k, total_scan = SCANS )

            if a is not None:
                data[0], data[1] = a, b
                # IQ demodulate + integrate the echo -> one complex value per echo,
                # i.e. the whole CPMG decay curve at once.
                integral_i, integral_q = pb.digitizer_iq(
                    data[0], data[1], IQ_FREQ,
                    zero_order, first_order, second_order, integral = True )
                echo[0] = integral_i
                echo[1] = integral_q

            # plot the live decay (real part)
            process = general.plot_1d(
                EXP_NAME,
                echo_time, (echo[0], echo[1]),
                label = 'CPMG',
                xname = 'Time', xscale = 's',
                yname = 'Intensity', yscale = 'mV',
                text = f"Scan / Echo: {k} / {idx + 1}",
                pr = process
            )

        # reset the AWG phase index for the next echo
        pb.awg_shift()

    pb.pulser_pulse_reset()
    pb.awg_pulse_reset()

pb.pulser_close()

# Final view of the CPMG decay
general.plot_1d(
    EXP_NAME,
    echo_time, (echo[0], echo[1]),
    label = 'CPMG',
    xname = 'Time', xscale = 's',
    yname = 'Intensity', yscale = 'mV',
    pr = 'None'
)

# Save the integrated CPMG decay (I, Q) vs echo time
file_handler.save_data(file_data, echo, header = header, mode = 'w')

