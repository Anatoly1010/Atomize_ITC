# Raw HDF5 file is ~2 * N1 * N2 * points_window * 4 bytes (about 170 MB for 128 x 128 and a 512 ns window)
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

def full_map():
    mi, mq = pb.digitizer_demodulate(
        data[0], data[1], IQ_FREQ,
        zero_order, first_order, second_order, integral = True )
    hyscore[0] = mi.reshape( N2, N1 ).T
    hyscore[1] = mq.reshape( N2, N1 ).T

def save_all():
    file_handler.save_data(file_data, data, header = header, mode = 'w',
                           axes = (time_axis, None), dtype = 'float32', axes_units = ('s', None))
    if file_data not in ('None', '', None):
        file_handler.save_data(file_data.rsplit('.', 1)[0] + '_map.h5', hyscore, header = header_map, mode = 'w')

def cleanup(*args):
    data[0], data[1] = pb.digitizer_at_exit()
    pb.pulser_close()
    full_map()
    save_all()
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)

### Experimental parameters
# HYSCORE pi/2 - tau - pi/2 - t1 - pi - t2 - pi/2 - tau - echo; flat index idx = i2 * N1 + i1 (t1 fastest)
N1 = 128                    # number of t1 points (inner / fast delay)
N2 = 128                    # number of t2 points (outer / slow delay)
POINTS = N1 * N2            # total points of the flattened indirect dimension
STEP = 16.0                 # t1 / t2 increment in ns
FIELD = 3478.0
AVERAGES = 20
SCANS = 1
DEC_COEF = 1                # must match 'Decimation' in digitizer_insys.param
process = 'None'

# PULSES
REP_RATE = '1000 Hz'
# pi/2 and pi share the length; the pi pulse is driven at twice the amplitude
# (AMPL_180 = 2 * AMPL_90), the usual AWG way to keep both pulses short.
PULSE_90_LENGTH = '16 ns'           # pi/2 pulses (P0, P1, P3)
PULSE_180_LENGTH = '16 ns'          # pi pulse  (P2), same length, double amplitude
# long enough that the captured window (points_window = LEN / (0.4*dec)) covers
# the integration window read from digitizer_insys.param (win_right); 512 ns ->
# 1280 samples >= win_right.
PULSE_DETECTION_LENGTH = '512 ns'

# Fixed timing (ns). All values are multiples of the 3.2 ns timebase so nothing
# is silently re-rounded. t1/t2 start just past the pulse length + ring-down so
# the inversion pulse never overlaps the flanking pi/2 pulses.
TAU = 128.0                         # tau, fixed
T1_START = 96.0                     # initial t1 (fast / inner delay)
T2_START = 96.0                     # initial t2 (slow / outer delay)

# Initial pulse starts (ns); positions are recomputed each indirect point
P0_START = 0.0                                          # pi/2,  fixed
P1_START = TAU                                          # pi/2,  fixed at tau
P2_START = TAU + T1_START                               # pi,    moves with t1
P3_START = TAU + T1_START + T2_START                    # pi/2,  moves with t1 + t2
# echo at 2*tau + t1 + t2. Open the detection window right after the last pi/2
# (not centered on the echo) so the long 512 ns window never opens during the
# refocusing pulse; the GUI integration window (win_left/win_right) brackets the
# echo inside the captured trace.
ECHO = 2 * TAU + T1_START + T2_START
DETECTION_START = P3_START + float(PULSE_90_LENGTH.split(' ')[0])   # after last pi/2; moves with t1 + t2

SHAPE = 'SINE'
FREQ = '100 MHz'

AMPL_90 = 50
AMPL_180 = 100

# IQ demodulation / phase correction (digitizer_demodulate).
# The AWG pulses sit at a digital IF (FREQ), so the detected signal must be
# digitally down-converted before integration. The demodulation frequency is the
# NEGATIVE of the AWG frequency, exactly as awg_phasing_insys computes it
# (iq_freq = -FREQ in MHz).
IQ_FREQ = -float(FREQ.split(' ')[0])    # MHz

# Phase corrections passed to digitizer_demodulate (worker units: rad, rad/s, rad/s^2).
# By default they are read from digitizer_insys.param via digitizer_read_settings()
# below, so they follow the phasing GUI even when no preset was saved. Set any of
# these to a number to override the value coming from the file.
ZERO_ORDER = None       # rad      ; None -> use digitizer_insys.param
FIRST_ORDER = None      # rad/s    ; None -> use digitizer_insys.param
SECOND_ORDER = None     # rad/s^2  ; None -> use digitizer_insys.param

# NAMES
EXP_NAME_2D = 'hyscore'            # real (t1, t2) HYSCORE map (the only live view)

# 16-step phase cycle for P0..P3; receiver -P0 + P1 + P3 selects the +00- pathway
ph = pb.digitizer_expand_phase_cycling('-1,1,0,1', 'x', '[x]', '(x)', '(x)')
PHASES = len(ph['receiver'])

# Setting magnetic field
bh15.magnet_setup(FIELD, 1)
bh15.magnet_field(FIELD)

# Setting pulses (TRIGGER_AWG triggers carry the timing; AWG pulses carry the phase)
pb.pulser_pulse(name = 'P0', channel = 'TRIGGER_AWG', start = f"{P0_START} ns",
            length = PULSE_90_LENGTH)
pb.pulser_pulse(name = 'P1', channel = 'TRIGGER_AWG', start = f"{P1_START} ns",
            length = PULSE_90_LENGTH)
pb.pulser_pulse(name = 'P2', channel = 'TRIGGER_AWG', start = f"{P2_START} ns",
            length = PULSE_180_LENGTH)
pb.pulser_pulse(name = 'P3', channel = 'TRIGGER_AWG', start = f"{P3_START} ns",
            length = PULSE_90_LENGTH)

pb.awg_pulse(name = 'A0', channel = 'CH0', func = SHAPE, frequency = FREQ, phase = 0,
            length = PULSE_90_LENGTH, sigma = PULSE_90_LENGTH, start = f"{P0_START} ns",
            phase_list = ph['pulses'][0], amplitude = AMPL_90)
pb.awg_pulse(name = 'A1', channel = 'CH0', func = SHAPE, frequency = FREQ, phase = 0,
            length = PULSE_90_LENGTH, sigma = PULSE_90_LENGTH, start = f"{P1_START} ns",
            phase_list = ph['pulses'][1], amplitude = AMPL_90)
pb.awg_pulse(name = 'A2', channel = 'CH0', func = SHAPE, frequency = FREQ, phase = 0,
            length = PULSE_180_LENGTH, sigma = PULSE_180_LENGTH, start = f"{P2_START} ns",
            phase_list = ph['pulses'][2], amplitude = AMPL_180)
pb.awg_pulse(name = 'A3', channel = 'CH0', func = SHAPE, frequency = FREQ, phase = 0,
            length = PULSE_90_LENGTH, sigma = PULSE_90_LENGTH, start = f"{P3_START} ns",
            phase_list = ph['pulses'][3], amplitude = AMPL_90)

pb.pulser_pulse(name = 'P4', channel = 'DETECTION', start = f"{DETECTION_START} ns",
            length = PULSE_DETECTION_LENGTH, phase_list = ph['receiver'])

pb.digitizer_decimation(DEC_COEF)

pb.pulser_repetition_rate( REP_RATE )
pb.pulser_default_synt(1)

pb.pulser_open()
pb.digitizer_number_of_averages(AVERAGES)

# Integration window (win_left / win_right) and decimation are taken from the
# live digitizer_insys.param file written by the phasing GUI, so the script
# integrates exactly the window the user phased on. digitizer_demodulate( integral = True )
# uses these internally.
pb.digitizer_read_settings()
points_window = pb.digitizer_window_points()

# phase corrections: take the file value (set by the phasing GUI) unless the
# corresponding constant above was set to override it
zero_order   = pb.zero_order   if ZERO_ORDER   is None else ZERO_ORDER
first_order  = pb.first_order  if FIRST_ORDER  is None else FIRST_ORDER
second_order = pb.second_order if SECOND_ORDER is None else SECOND_ORDER

# raw (ADC time x flattened delays) array and the integrated (t1 x t2) map
data = np.zeros( ( 2, points_window, POINTS ) )
hyscore = np.zeros( ( 2, N1, N2 ) )
time_axis = np.arange( points_window ) * 0.4 * DEC_COEF / 1e9

# Data saving
now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
w = 30

header_head = (
    f"{'Date:':<{w}} {now}\n"
    f"{'Experiment:':<{w}} HYSCORE\n"
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
    f"{'Points t1 / t2:':<{w}} {N1} / {N2}\n"
    f"{'Window:':<{w}} {PULSE_DETECTION_LENGTH}\n"
    f"{'Integration Window:':<{w}} {pb.win_left * 0.4 * DEC_COEF:.1f} - {pb.win_right * 0.4 * DEC_COEF:.1f} ns\n"
    f"{'IQ Frequency:':<{w}} {IQ_FREQ} MHz\n"
    f"{'Phase (0 / 1 / 2):':<{w}} {zero_order:.4g} rad / {first_order:.4g} rad/s / {second_order:.4g} rad/s2\n"
    f"{'Tau:':<{w}} {TAU} ns\n"
)
header_tail = (
    f"{'t1 / t2 Step:':<{w}} {STEP} ns\n"
    f"{'N1:':<{w}} {N1}\n"
    f"{'N2:':<{w}} {N2}\n"
    f"{'t1 Start:':<{w}} {T1_START} ns\n"
    f"{'t2 Start:':<{w}} {T2_START} ns\n"
    f"{'Flat Index:':<{w}} idx = i2*N1 + i1, t1 fastest; raw I, Q stored as (N1*N2, window points)\n"
    f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
    f"{'-'*50}\n"
    f"Pulse List:\n{pb.pulser_pulse_list()}"
    f"{'-'*50}\n"
    f"AWG Pulse List:\n{pb.awg_pulse_list()}"
    f"{'-'*50}\n"
    f"Raw I/Q (flat index x window) in this file; 2D HYSCORE map (t1 x t2) in *_map.h5"
)
header = (
    f"{header_head}"
    f"{'Horizontal Resolution:':<{w}} {0.4 * DEC_COEF:.1g} ns\n"
    f"Y (Point/): start 0 step 1\n"
    f"{header_tail}"
)
header_map = (
    f"{header_head}"
    f"X (t1/ns): start {T1_START} step {STEP}\n"
    f"Y (t2/ns): start {T2_START} step {STEP}\n"
    f"{header_tail}"
)

file_data = file_handler.create_file_dialog(fmt = 'h5')

# Data acquisition
for k in general.scans(SCANS):

    for idx in range(POINTS):

        # flattened indirect index -> (t1, t2); t1 is the fast (inner) delay
        i1 = idx % N1
        i2 = idx // N1

        # absolute positions for this (t1, t2) point.
        # t1 moves the pi pulse, the last pi/2 and the detection;
        # t2 moves only the last pi/2 and the detection.
        # pulser_redefine_start keeps the AWG companion pulses in sync and does
        # NOT reset the indirect-point counter (unlike pulser_pulse_reset).
        pb.pulser_redefine_start( name = 'P2', start = f"{P2_START + i1 * STEP} ns" )
        pb.pulser_redefine_start( name = 'P3', start = f"{P3_START + (i1 + i2) * STEP} ns" )
        pb.pulser_redefine_start( name = 'P4', start = f"{DETECTION_START + (i1 + i2) * STEP} ns" )

        # test mode checks the full phase cycle at the first and last point only
        n_ph = PHASES if general.test_flag != 'test' or idx in (0, POINTS - 1) else 1
        for i in range(n_ph):

            pb.awg_next_phase()
            pb.pulser_update()

            a, b, rng = pb.digitizer_get_curve( POINTS, PHASES, current_scan = k, total_scan = SCANS, partial = True )

            if a is not None:
                j0, j1 = rng
                data[0][:, j0:j1] = a
                data[1][:, j0:j1] = b
                dx, dy = pb.digitizer_demodulate(
                    a, b, IQ_FREQ,
                    zero_order, first_order, second_order, integral = True )
                flat = np.arange( j0, j1 )
                hyscore[0, flat % N1, flat // N1] = dx
                hyscore[1, flat % N1, flat // N1] = dy

                # update_2d redraws only the touched t2 columns (last axis)
                process = general.update_2d(
                    EXP_NAME_2D,
                    hyscore, j0 // N1, (j1 - 1) // N1 + 1,
                    start_step = ( (T1_START / 1e9, STEP / 1e9), (T2_START / 1e9, STEP / 1e9) ),
                    xname = 't1', xscale = 's',
                    yname = 't2', yscale = 's',
                    zname = 'Intensity', zscale = 'mV',
                    text = f"Scan / t1 / t2: {k} / {i1 * STEP:.1f} / {i2 * STEP:.1f}",
                    pr = process
                )

        # reset the AWG phase index for the next indirect point
        pb.awg_shift()

    pb.pulser_pulse_reset()
    pb.awg_pulse_reset()

data[0], data[1] = pb.digitizer_at_exit()
pb.pulser_close()
full_map()

# Final view of the real 2D HYSCORE map (t1 x t2)
general.plot_2d(
    EXP_NAME_2D,
    hyscore,
    start_step = ( (T1_START / 1e9, STEP / 1e9), (T2_START / 1e9, STEP / 1e9) ),
    xname = 't1', xscale = 's',
    yname = 't2', yscale = 's',
    zname = 'Intensity', zscale = 'mV',
    pr = 'None'
)

# Save the raw I/Q and the 2D HYSCORE map (t1 x t2)
save_all()
