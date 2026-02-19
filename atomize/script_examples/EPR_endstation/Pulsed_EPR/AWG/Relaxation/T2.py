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

# initialization of the devices
file_handler = openfile.Saver_Opener()
ls335 = ls.Lakeshore_335()
mw = mwBridge.Micran_X_band_MW_bridge_v2()
pb = pb_pro.Insys_FPGA()
bh15 = bh.BH_15()

def cleanup(*args):
    pb.pulser_close()
    data[0], data[1] = pb.digitizer_at_exit()
    file_handler.save_data(
        file_data, 
        data, 
        header = header, 
        mode = 'w'
    )
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)

### Experimental parameters
POINTS = 500
STEP = 6.4
FIELD = 3340.0
AVERAGES = 20
SCANS = 1
PHASES = 2
DEC_COEF = 1
process = 'None'

# PULSES
REP_RATE = '2000 Hz'
PULSE_1_LENGTH = '44.8 ns'
PULSE_2_LENGTH = '44.8 ns'
PULSE_DETECTION_LENGTH = '512 ns'

PULSE_1_START = '0 ns'
PULSE_2_START = '288 ns'
#+320 ns constant shift
PULSE_DETECTION = '896 ns'

SHAPE = 'SINE'
FREQ = '50 MHz'

AMPL_1 = 20
AMPL_2 = 40

# NAMES
EXP_NAME = 'T2'


# Setting magnetic field
bh15.magnet_setup(FIELD, 1)
bh15.magnet_field(FIELD)
general.wait('4000 ms')

# Setting pulses
pb.pulser_pulse(
    name = 'P0', 
    channel = 'TRIGGER_AWG', 
    start = PULSE_1_START, 
    length = PULSE_1_LENGTH
)
pb.pulser_pulse(
    name = 'P1', 
    channel = 'TRIGGER_AWG', 
    start = PULSE_2_START, 
    length = PULSE_2_LENGTH, 
    delta_start = f"{STEP} ns"
)

pb.awg_pulse(
    name = 'A0', 
    channel = 'CH0', 
    func = SHAPE, 
    frequency = FREQ, 
    phase = 0, 
    length = PULSE_1_LENGTH, 
    sigma = PULSE_1_LENGTH, 
    start = PULSE_1_START, 
    phase_list = ['+x', '-x'], 
    amplitude = AMPL_1
)


pb.awg_pulse(
    name = 'A1', 
    channel = 'CH0', 
    func = SHAPE, 
    frequency = FREQ, 
    phase = 0, 
    length = PULSE_2_LENGTH, 
    sigma = PULSE_2_LENGTH, 
    start = PULSE_2_START, 
    phase_list = ['+x', '+x'], 
    amplitude = AMPL_2,
)

pb.pulser_pulse(
    name = 'P3', 
    channel = 'DETECTION', 
    start = PULSE_DETECTION, 
    length = PULSE_DETECTION_LENGTH,
    phase_list = ['+x', '-x'],
    delta_start = f"{2 * STEP:.1f} ns"
)


pb.digitizer_decimation(DEC_COEF)
points_window = pb.digitizer_window_points()


pb.pulser_repetition_rate( REP_RATE )
pb.pulser_default_synt(1)

pb.pulser_open()
pb.digitizer_number_of_averages(AVERAGES)
data = np.zeros( ( 2, points_window, POINTS ) )


# Data saving
now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
w = 30

header = (
    f"{'Date:':<{w}} {now}\n"
    f"{'Experiment:':<{w}} T2\n"
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
    f"{'Window:':<{w}} {PULSE_DETECTION_LENGTH}\n"
    f"{'Horizontal Resolution:':<{w}} {0.4 * DEC_COEF:.1g} ns\n"
    f"{'Vertical Resolution, Tau:':<{w}} {STEP} ns\n"
    f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
    f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
    f"{'-'*50}\n"
    f"Pulse List:\n{pb.pulser_pulse_list()}"
    f"{'-'*50}\n"
    f"AWG Pulse List:\n{pb.awg_pulse_list()}"
    f"{'-'*50}\n"
    f"2D Data"
)


file_data = file_handler.create_file_dialog()

# Data acquisition
for k in general.scans(SCANS):


    for j in range(POINTS):

        # phase cycle
        for i in range(PHASES):

            process = general.plot_2d(
                EXP_NAME, 
                data, 
                start_step = ((0, 0.4 * DEC_COEF / 1e9), (0, STEP / 1e9)), 
                xname = 'Time', 
                xscale = 's', 
                yname = 'Delay', 
                yscale = 's', 
                zname = 'Intensity', 
                zscale = 'mV', 
                text = f"Scan / Time: {k} / {j * STEP:.1f}", 
                pr = process
            )

            pb.awg_next_phase()
            pb.pulser_update()

            data[0], data[1] = pb.digitizer_get_curve( 
                POINTS, 
                PHASES, 
                current_scan = k, 
                total_scan = SCANS ) 

        pb.pulser_shift()
        pb.awg_pulse_reset()

    pb.pulser_pulse_reset()


pb.pulser_close()


general.plot_2d(
    EXP_NAME, 
    data, 
    start_step = ((0, 0.4 * DEC_COEF / 1e9), (0, STEP / 1e9)), 
    xname = 'Time', 
    xscale = 's', 
    yname = 'Delay', 
    yscale = 's', 
    zname = 'Intensity', 
    zscale = 'mV', 
    text = f"Scan / Time: {k} / {j * STEP:.1f}", 
    pr = 'None'
)


file_handler.save_data(
    file_data, 
    data, 
    header = header, 
    mode = 'w'
)
