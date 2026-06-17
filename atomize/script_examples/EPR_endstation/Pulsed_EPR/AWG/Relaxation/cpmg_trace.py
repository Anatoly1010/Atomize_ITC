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
    # store whatever raw trace is available
    data[0], data[1] = pb.digitizer_at_exit()
    file_handler.save_data(file_data, data[:, :, 0], header = header, mode = 'w')
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)

### Experimental parameters
# CPMG (Carr-Purcell-Meiboom-Gill), AWG, SINGLE-SEQUENCE / FULL-TRACE version.
#
#   pi/2_x - tau - [ pi_y - 2*tau - (echo) ]  x NPI
#
# Unlike cpmg.py (which re-runs the train and moves the detection window onto
# each echo), here the WHOLE train is fired once per shot and a single LARGE
# detection window captures the entire echo train in one go. The acquisition
# loop only phase-cycles and averages - NO integration is done on the raw data.
# We keep / save the full 1D transient obtained after phase cycling; integrating
# the individual echoes into a T2 decay is done AFTER the experiment (see the
# post-processing block at the end), so the raw trace stays untouched.
#
# The captured window equals the DETECTION pulse length set below (the digitizer
# acquires exactly the detection gate), so the whole train is captured straight
# from the script - no GUI 'Points' setting needed. The hardware caps the
# detection window at 12800 ns (adc_window <= 4000 pulser counts), so the train
# 2*NPI*tau (+margins) must fit in 12.8 us: keep NPI*tau small, or use the
# per-echo cpmg.py for long trains. Raise DEC_COEF to thin the sample count.
NPI = 16                    # number of refocusing pi pulses = number of echoes
POINTS = 1                  # single indirect point (whole train in one window)
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

# Fixed timing (ns). tau and all derived positions are multiples of the 3.2 ns
# pulser timebase so nothing is silently re-rounded.
TAU = 320.0                         # fixed pulse spacing; first echo at 2*tau
P90_START = 0.0                     # pi/2, fixed at t = 0
ECHO_SPACING = 2 * TAU             # echo-to-echo (and pi-to-pi) spacing
ECHO_1 = 2 * TAU                   # first echo
WINDOW_MARGIN = TAU                # open the window this much before/after the train

# single large detection window covering the whole echo train
DET_START = ECHO_1 - WINDOW_MARGIN
DET_LENGTH = ECHO_SPACING * NPI + 2 * WINDOW_MARGIN - ECHO_1     # spans first->last echo + margins
PULSE_DETECTION_LENGTH = f"{DET_LENGTH} ns"

# hardware limit: the detection window must be <= 12800 ns (adc_window <= 4000
# pulser counts of 3.2 ns). Fail early with a clear message rather than tripping
# the device assert inside pulser_pulse.
MAX_DET_NS = 12800.0
assert DET_LENGTH <= MAX_DET_NS, (
    f"Detection window {DET_LENGTH} ns exceeds the {MAX_DET_NS} ns hardware limit; "
    f"reduce NPI or TAU, or use the per-echo cpmg.py for long trains." )

SHAPE = 'SINE'
FREQ = '50 MHz'

AMPL_90 = 20
AMPL_180 = 40

# IQ demodulation / phase correction (digitizer_iq); used only to DISPLAY and to
# post-process the trace - the raw saved data is never integrated.
IQ_FREQ = -float(FREQ.split(' ')[0])    # MHz
ZERO_ORDER = None       # rad      ; None -> use digitizer_insys.param
FIRST_ORDER = None      # rad/s    ; None -> use digitizer_insys.param
SECOND_ORDER = None     # rad/s^2  ; None -> use digitizer_insys.param

# post-experiment echo integration half-width (ns) around each echo center
ECHO_INT_HALF = 64.0

# NAMES
EXP_NAME = 'CPMG trace'        # full echo-train transient
EXP_NAME_DECAY = 'CPMG decay'  # T2 decay built from the trace afterwards

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

# single large detection window spanning the whole train (fixed, never moved)
pb.pulser_pulse(name = 'PDET', channel = 'DETECTION', start = f"{DET_START} ns",
            length = PULSE_DETECTION_LENGTH, phase_list = PH_DET)

pb.digitizer_decimation(DEC_COEF)

pb.pulser_repetition_rate( REP_RATE )
pb.pulser_default_synt(1)

pb.pulser_open()
pb.digitizer_number_of_averages(AVERAGES)

# Decimation and phase corrections come from the live digitizer_insys.param
# (written by the phasing GUI). The integration window stored there is for the
# single-echo workflow and is NOT used here; we integrate per-echo afterwards.
pb.digitizer_read_settings()
points_window = pb.digitizer_window_points()

zero_order   = pb.zero_order   if ZERO_ORDER   is None else ZERO_ORDER
first_order  = pb.first_order  if FIRST_ORDER  is None else FIRST_ORDER
second_order = pb.second_order if SECOND_ORDER is None else SECOND_ORDER

# raw transient (I, Q) over the whole window; POINTS = 1 keeps it compatible with
# digitizer_get_curve / digitizer_at_exit. disp is the demodulated trace we plot.
data = np.zeros( ( 2, points_window, POINTS ) )
disp = np.zeros( ( 2, points_window ) )

# relative time axis of the window (window starts at the detection trigger)
res = 0.4 * DEC_COEF                                 # ns per sample
time_axis = ( np.arange( points_window ) * res ) / 1e9   # seconds

# Data saving
now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
w = 30

header = (
    f"{'Date:':<{w}} {now}\n"
    f"{'Experiment:':<{w}} CPMG (full trace)\n"
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
    f"{'Detection Window:':<{w}} {PULSE_DETECTION_LENGTH}\n"
    f"{'Captured Window:':<{w}} {points_window * res:.1f} ns ({points_window} pts)\n"
    f"{'Window Start (rel. seq.):':<{w}} {DET_START} ns\n"
    f"{'IQ Frequency:':<{w}} {IQ_FREQ} MHz\n"
    f"{'Phase (0 / 1 / 2):':<{w}} {zero_order:.4g} rad / {first_order:.4g} rad/s / {second_order:.4g} rad/s2\n"
    f"{'Horizontal Resolution:':<{w}} {res:.1g} ns\n"
    f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
    f"{'-'*50}\n"
    f"Pulse List:\n{pb.pulser_pulse_list()}"
    f"{'-'*50}\n"
    f"AWG Pulse List:\n{pb.awg_pulse_list()}"
    f"{'-'*50}\n"
    f"Raw CPMG echo-train transient (I, Q); no integration applied"
)

file_data = file_handler.create_file_dialog()

st_time = time.time()
# Data acquisition: one sequence, phase-cycled and averaged. No integration.
for k in general.scans(SCANS):

    # phase cycle
    for i in range(PHASES):

        pb.awg_next_phase()
        pb.pulser_update()

        a, b = pb.digitizer_get_curve( POINTS, PHASES, current_scan = k, total_scan = SCANS )

        if a is not None:
            data[0], data[1] = a, b
            # demodulate the WHOLE trace for display only (integral = False, i.e.
            # no integration) - echoes show up as a decaying train of peaks.
            di, dq = pb.digitizer_iq(
                data[0], data[1], IQ_FREQ,
                zero_order, first_order, second_order, integral = False )
            disp[0], disp[1] = di[:, 0], dq[:, 0]

        # plot the whole 1D trace (demodulated real part)
        process = general.plot_1d(
            EXP_NAME,
            time_axis, disp[0],
            label = 'CPMG',
            xname = 'Time', xscale = 's',
            yname = 'Intensity', yscale = 'mV',
            text = f"Scan / Phase: {k} / {i}",
            pr = process
        )

    # reset the AWG phase index for the next scan
    pb.awg_shift()

    pb.pulser_pulse_reset()
    pb.awg_pulse_reset()

pb.pulser_close()

general.message( f'FULL TIME: {round(1000*(time.time() - st_time), 1)} ms' )

# Save the raw, un-integrated echo-train transient (I, Q) over the whole window
file_handler.save_data(file_data, data[:, :, 0], header = header, mode = 'w')

# ---------------------------------------------------------------------------
# Post-experiment processing (NOT applied to the raw data above): demodulate the
# trace and integrate each echo window into the CPMG (T2) decay. Echo n is at
# 2*n*tau in sequence time, i.e. at (2*n*tau - DET_START) inside the window.
# Adjust ECHO_INT_HALF (and, if the hardware pre-trigger shifts the window, a
# constant offset) if the echoes do not line up.
# ---------------------------------------------------------------------------
demod_i, demod_q = pb.digitizer_iq(
    data[0], data[1], IQ_FREQ, zero_order, first_order, second_order, integral = False )
demod_i, demod_q = demod_i[:, 0], demod_q[:, 0]

half = int(round(ECHO_INT_HALF / res))
echo_time = ( np.arange( 1, NPI + 1 ) * ECHO_SPACING ) / 1e9    # seconds
decay = np.zeros( ( 2, NPI ) )
for n in range(1, NPI + 1):
    center = int(round((2 * n * TAU - DET_START) / res))
    lo, hi = max(0, center - half), min(points_window, center + half)
    if hi > lo:
        decay[0, n - 1] = np.sum( demod_i[lo:hi] )
        decay[1, n - 1] = np.sum( demod_q[lo:hi] )

general.plot_1d(
    EXP_NAME_DECAY,
    echo_time, decay[0],
    label = 'CPMG decay',
    xname = 'Time', xscale = 's',
    yname = 'Intensity', yscale = 'mV',
    pr = 'None'
)

# save the post-integrated decay next to the raw trace (…_decay.csv)
if file_data not in ('None', '', None):
    decay_path = file_data.rsplit('.', 1)[0] + '_decay.csv'
    file_handler.save_data(decay_path, decay, header = header, mode = 'w')

cip = pb.count_ip(PHASES)
general.message( f"Counts: {cip}" )
general.message( f"TC: {np.sum(cip)}" )
