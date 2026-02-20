import sys
import signal
import datetime
import numpy as np
import atomize.general_modules.general_functions as general
import atomize.device_modules.Insys_FPGA as pb_pro
import atomize.device_modules.Micran_X_band_MW_bridge_v2 as mwBridge
import atomize.device_modules.Lakeshore_335 as ls
import atomize.device_modules.BH_15 as bh
import atomize.general_modules.csv_opener_saver as openfile

### Nonlinear axis
POINTS = 250
T_start = 3
T_end = 7.88

nonlinear_time_raw = 10 ** np.linspace( T_start, T_end, POINTS )
nonlinear_time = np.unique( general.numpy_round( nonlinear_time_raw, 3.2 ) )
POINTS = len( nonlinear_time )
x_axis = (np.insert(nonlinear_time , 0, 0))[:-1]


# initialization of the devices
file_handler = openfile.Saver_Opener()
ls335 = ls.Lakeshore_335()
mw = mwBridge.Micran_X_band_MW_bridge_v2()
pb = pb_pro.Insys_FPGA()
bh15 = bh.BH_15()

def cleanup(*args):
    pb.pulser_close()
    data[0], data[1] = pb.digitizer_at_exit(integral = True)
    file_handler.save_data(
        file_data, 
        np.c_[x_axis, data[0], data[1]], 
        header = header, 
        mode = 'w'
    )
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)

FIELD = 6500.0
AVERAGES = 10
SCANS = 1
PHASES = 2
DEC_COEF = 1
process = 'None'

# PULSES
REP_RATE = '12 Hz'
PULSE_LASER_LENGTH = '1024 ns'
PULSE_2_LENGTH = '22.4 ns'
PULSE_3_LENGTH = '44.8 ns'
PULSE_DETECTION_LENGTH = '512.0 ns'

PULSE_1_START = '0 ns'
PULSE_2_START = '0 ns'
PULSE_3_START = '300.8 ns'
PULSE_DETECTION = '576.0 ns'

# NAMES
EXP_NAME = 'kin'
CURVE_NAME = '6500'


# Setting magnetic field
bh15.magnet_setup(FIELD, 1)
bh15.magnet_field(FIELD)
general.wait('4000 ms')

# Setting pulses
pb.pulser_pulse(
    name ='P0', 
    channel = 'LASER', 
    start = PULSE_1_START, 
    length = PULSE_LASER_LENGTH
)

pb.pulser_pulse(
    name = 'P1', 
    channel = 'MW', 
    start = PULSE_2_START, 
    length = PULSE_2_LENGTH, 
    delta_start = f"{nonlinear_time[0]} ns", 
    phase_list = ['+x', '-x']
)

pb.pulser_pulse(
    name = 'P2', 
    channel = 'MW', 
    start = PULSE_3_START, 
    length = PULSE_3_LENGTH, 
    delta_start = f"{nonlinear_time[0]} ns", 
    phase_list = ['+x', '+x']
)

pb.pulser_pulse(
    name = 'P3', 
    channel = 'DETECTION', 
    start = PULSE_DETECTION, 
    length = PULSE_DETECTION_LENGTH, 
    delta_start = f"{nonlinear_time[0]} ns", 
    phase_list = ['+x', '-x']
)

pb.digitizer_decimation(DEC_COEF)
points_window = pb.digitizer_window_points()

pb.pulser_repetition_rate( REP_RATE )
pb.pulser_default_synt(1)

pb.pulser_open()
pb.digitizer_number_of_averages(AVERAGES)
data = np.zeros( ( 2, POINTS ) )

# Data saving
now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
w = 30

header = (
    f"{'Date:':<{w}} {now}\n"
    f"{'Experiment:':<{w}} THz Pump - 2 Pulse Echo; Log\n"
    f"{'Field:':<{w}} {FIELD} G\n"
    f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
    f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
    f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
    f"{general.fmt(mw.mw_bridge_att2_prd(), w)}\n"
    f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
    f"{'Repetition Rate:':<{w}} {pb.pulser_repetition_rate()}\n"
    f"{'Number of Scans:':<{w}} {SCANS}\n"
    f"{'Averages:':<{w}} {AVERAGES}\n"
    f"{'Points:':<{w}} {POINTS}\n"
    f"{'Window:':<{w}} {points_window * 0.4:.1f} ns\n"
    f"{'Window Left:':<{w}} {pb.win_left * 0.4:.1f} ns\n"
    f"{'Window Right:':<{w}} {pb.win_right * 0.4:.1f} ns\n"    
    f"{'Horizontal Resolution, Log[T Start]:':<{w}} {T_start}\n"
    f"{'Horizontal Resolution, Log[T End]:':<{w}} {T_end}\n"
    f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
    f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
    f"{'-'*50}\n"
    f"Pulse List:\n{pb.pulser_pulse_list()}"
    f"{'-'*50}\n"
    f"T (ns), I (A.U.), Q (A.U.)"
)

file_data = file_handler.create_file_dialog()

# Data acquisition
for k in general.scans(SCANS):

    for j in range(POINTS):

        # phase cycle
        for i in range(PHASES):

            process = general.plot_1d(
                EXP_NAME, 
                x_axis / 1e9, 
                ( data[0], data[1] ), 
                xname = 'T', 
                xscale = 's', 
                yname = 'Area', 
                yscale = 'A.U.', 
                label = CURVE_NAME, 
                text = f'Scan / Point: {k} / {j}', 
                pr = process
                )

            pb.pulser_next_phase()
            data[0], data[1] = pb.digitizer_get_curve( 
                POINTS, 
                PHASES, 
                integral = True 
            )

        # nonlinear_time_shift is calculated from the initial position of the pulses
        if j > 0:
            new_delta_start = f"{nonlinear_time[j] - nonlinear_time[j-1]:.1f} ns"

            pb.pulser_redefine_delta_start(name = 'P1', delta_start = new_delta_start)
            pb.pulser_redefine_delta_start(name = 'P2', delta_start = new_delta_start)
            pb.pulser_redefine_delta_start(name = 'P3', delta_start = new_delta_start)

        pb.pulser_shift()

    pb.pulser_pulse_reset()

pb.pulser_close()

general.plot_1d(
    EXP_NAME, 
    x_axis / 1e9, 
    ( data[0], data[1] ), 
    xname = 'T', 
    xscale = 's', 
    yname = 'Area', 
    yscale = 'A.U.', 
    label = CURVE_NAME, 
    text = f'Scan / Point: {k} / {j}', 
    pr = 'None'
)

file_handler.save_data(
    file_data, 
    np.c_[x_axis, data[0], data[1]], 
    header = header, 
    mode = 'w'
)
