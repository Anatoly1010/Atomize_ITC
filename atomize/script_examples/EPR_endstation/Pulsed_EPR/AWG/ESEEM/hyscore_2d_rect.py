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
    # store whatever is available as the integrated (flattened delays) row
    data[0], data[1] = pb.digitizer_at_exit(integral = True)
    file_handler.save_data(file_data, data, header = header, mode = 'w')
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)

### Experimental parameters
# Rectangular (non-AWG) HYSCORE. Same 2D experiment as hyscore_2d.py, but the
# MW pulses are plain rectangular pulses on the 'MW' channel: the phase cycle is
# carried directly by phase_list on each pulser_pulse (no awg_pulse / TRIGGER_AWG),
# and the pi pulse is realized by doubling its LENGTH (no amplitude control here).
# Rectangular pulses are detected at baseband through the analog quadrature
# bridge, so no IQ demodulation is needed: digitizer_get_curve( integral = True )
# returns the echo already integrated over the window (one value per delay point).
# That row is reshaped into the real (t1, t2) HYSCORE map and plotted live.
#
# HYSCORE is a 2D experiment: pi/2 - tau - pi/2 - t1 - pi - t2 - pi/2 - tau - echo
# t1 is the fast (inner) delay, t2 is the slow (outer) delay.
N1 = 128                    # number of t1 points (inner / fast delay)
N2 = 128                    # number of t2 points (outer / slow delay)
POINTS = N1 * N2            # total points of the flattened indirect dimension
STEP = 16.0                 # t1 / t2 increment in ns
FIELD = 3478.0
AVERAGES = 20
SCANS = 1
PHASES = 16                 # 16-step phase cycle (see 08_hyscore.py)
DEC_COEF = 1                # must match 'Decimation' in digitizer_insys.param
process = 'None'

# PULSES
REP_RATE = '1000 Hz'
# Rectangular pulses: the pi pulse has TWICE the length of the pi/2 pulse
# (no amplitude control on the MW channel, so the area is doubled via length).
PULSE_90_LENGTH = '16 ns'           # pi/2 pulses (P0, P1, P3)
PULSE_180_LENGTH = '32 ns'          # pi pulse  (P2), length-doubled
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

# NAMES
EXP_NAME_2D = 'hyscore'            # real (t1, t2) HYSCORE map (the only live view)

# 16-step phase cycle (translated from 08_hyscore.py)
PH_P0 = ['+x', '+x', '+x', '+x', '+x', '+x', '+x', '+x', '+x', '+x', '+x', '+x', '+x', '+x', '+x', '+x']
PH_P1 = ['+x', '+y', '-x', '-y', '+x', '+y', '-x', '-y', '+x', '+y', '-x', '-y', '+x', '+y', '-x', '-y']
PH_P2 = ['+x', '+y', '-x', '-y', '+x', '+y', '-x', '-y', '-x', '-y', '+x', '+y', '-x', '-y', '+x', '+y']
PH_P3 = ['+x', '+y', '-x', '-y', '-x', '-y', '+x', '+y', '+x', '+y', '-x', '-y', '-x', '-y', '+x', '+y']
# acquisition cycle ['+','-','+','-','-','+','-','+','+','-','+','-','-','+','-','+'] -> detection phases
PH_DET = ['+x', '-x', '+x', '-x', '-x', '+x', '-x', '+x', '+x', '-x', '+x', '-x', '-x', '+x', '-x', '+x']

# Setting magnetic field
bh15.magnet_setup(FIELD, 1)
bh15.magnet_field(FIELD)

# Setting pulses (rectangular MW pulses carry both the timing and the phase)
pb.pulser_pulse(name = 'P0', channel = 'MW', start = f"{P0_START} ns",
            length = PULSE_90_LENGTH, phase_list = PH_P0)
pb.pulser_pulse(name = 'P1', channel = 'MW', start = f"{P1_START} ns",
            length = PULSE_90_LENGTH, phase_list = PH_P1)
pb.pulser_pulse(name = 'P2', channel = 'MW', start = f"{P2_START} ns",
            length = PULSE_180_LENGTH, phase_list = PH_P2)
pb.pulser_pulse(name = 'P3', channel = 'MW', start = f"{P3_START} ns",
            length = PULSE_90_LENGTH, phase_list = PH_P3)

pb.pulser_pulse(name = 'P4', channel = 'DETECTION', start = f"{DETECTION_START} ns",
            length = PULSE_DETECTION_LENGTH, phase_list = PH_DET)

pb.digitizer_decimation(DEC_COEF)

pb.pulser_repetition_rate( REP_RATE )
pb.pulser_default_synt(1)

pb.pulser_open()
pb.digitizer_number_of_averages(AVERAGES)

# Integration window (win_left / win_right) and decimation are taken from the
# live digitizer_insys.param file written by the phasing GUI, so the script
# integrates exactly the window the user phased on. digitizer_get_curve(
# integral = True ) uses these internally.
pb.digitizer_read_settings()

# integrated row (one value per flattened delay point) kept for the abort dump;
# hyscore is the reshaped (t1 x t2) map we build and plot every phase step.
data = np.zeros( ( 2, POINTS ) )
hyscore = np.zeros( ( 2, N1, N2 ) )

# Data saving
now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
w = 30

header = (
    f"{'Date:':<{w}} {now}\n"
    f"{'Experiment:':<{w}} HYSCORE (rectangular)\n"
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
    f"{'Tau:':<{w}} {TAU} ns\n"
    f"{'Horizontal Resolution:':<{w}} {0.4 * DEC_COEF:.1g} ns\n"
    f"{'t1 / t2 Step:':<{w}} {STEP} ns\n"
    f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
    f"{'-'*50}\n"
    f"Pulse List:\n{pb.pulser_pulse_list()}"
    f"{'-'*50}\n"
    f"2D HYSCORE Data (t1 x t2)"
)

file_data = file_handler.create_file_dialog()

# Data acquisition
for k in general.scans(SCANS):

    for idx in range(POINTS):

        # flattened indirect index -> (t1, t2); t1 is the fast (inner) delay
        i1 = idx % N1
        i2 = idx // N1

        # absolute positions for this (t1, t2) point.
        # t1 moves the pi pulse, the last pi/2 and the detection;
        # t2 moves only the last pi/2 and the detection.
        # pulser_redefine_start does NOT reset the indirect-point counter
        # (unlike pulser_pulse_reset).
        pb.pulser_redefine_start( name = 'P2', start = f"{P2_START + i1 * STEP} ns" )
        pb.pulser_redefine_start( name = 'P3', start = f"{P3_START + (i1 + i2) * STEP} ns" )
        pb.pulser_redefine_start( name = 'P4', start = f"{DETECTION_START + (i1 + i2) * STEP} ns" )

        # phase cycle
        for i in range(PHASES):

            # rectangular phase cycling: advances the phase index AND immediately
            # pushes the new pulse array to the pulser (no separate pulser_update)
            pb.pulser_next_phase()

            # integral = True -> echo already integrated over the window;
            # one value per flattened delay point (length POINTS)
            a, b = pb.digitizer_get_curve( POINTS, PHASES, current_scan = k,
                                           total_scan = SCANS, integral = True )

            if a is not None:
                data[0], data[1] = a, b
                # refactor the integrated row into the real (t1, t2) HYSCORE map
                # (idx = i2 * N1 + i1)
                hyscore[0] = data[0].reshape( N2, N1 ).T
                hyscore[1] = data[1].reshape( N2, N1 ).T

            # plot only the reshaped 2D map - the result is visible immediately
            process = general.plot_2d(
                EXP_NAME_2D,
                hyscore,
                start_step = ( (T1_START / 1e9, STEP / 1e9), (T2_START / 1e9, STEP / 1e9) ),
                xname = 't1', xscale = 's',
                yname = 't2', yscale = 's',
                zname = 'Intensity', zscale = 'mV',
                text = f"Scan / t1 / t2: {k} / {i1 * STEP:.1f} / {i2 * STEP:.1f}",
                pr = process
            )

        # reset the phase index for the next indirect point (all delta_start = 0,
        # so nothing is shifted; absolute positioning is done by redefine_start)
        pb.pulser_shift()

    pb.pulser_pulse_reset()

pb.pulser_close()

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

# Save the real 2D HYSCORE array (t1 x t2)
file_handler.save_data(file_data, hyscore, header = header, mode = 'w')
