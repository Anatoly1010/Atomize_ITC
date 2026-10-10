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

# Initialization of the devices
file_handler = openfile.Saver_Opener()
ls335 = ls.Lakeshore_335()
mw = mwBridge.Micran_X_band_MW_bridge_v2()
bh15 = bh.BH_15()
pb = pb_pro.Insys_FPGA()
data = None
file_data = 'None'
readout_ready = False


def full_map():
    mi, mq = pb.digitizer_demodulate(
        data[0], data[1], IQ_FREQ,
        zero_order, first_order, second_order, integral = True)
    integral_map[0] = mi.reshape(FIELD_POINTS, POINTS).T
    integral_map[1] = mq.reshape(FIELD_POINTS, POINTS).T


def save_all():
    if general.test_flag == 'test':
        return
    file_handler.save_data(file_data, data, header = header, mode = 'w',
                           axes = (time_axis, None), dtype = 'float32', axes_units = ('s', None))
    if file_data not in ('None', '', None):
        file_handler.save_data(file_data.rsplit('.', 1)[0] + '_map.h5', integral_map,
                               header = header_map, mode = 'w', axes = (sweep_axis / 1e9, field_axis),
                               dtype = 'float32', axes_units = ('s', 'G'))


def cleanup(*args):
    if readout_ready:
        data[0], data[1] = pb.digitizer_at_exit()
    pb.pulser_close()
    if data is not None:
        full_map()
        save_all()
    sys.exit(0)


signal.signal(signal.SIGTERM, cleanup)

# Experimental parameters
POINTS = 500               # delay/length points at each field
START_FIELD = 3300.0
END_FIELD = 3380.0
FIELD_STEP = 2.0
FIELD_WAIT = '4000 ms'
AVERAGES = 20
SCANS = 1
DEC_COEF = 1               # must match digitizer_insys.param
EXP_NAME = 'T2 vs field'

# Pulse parameters
STEP = 6.4
TAU_START = 288.0
P0_START = 0.0
P1_START = TAU_START
DETECTION_START = 896.0
PULSE_1_LENGTH = '44.8 ns'
PULSE_2_LENGTH = '44.8 ns'
AMPL_1 = 20
AMPL_2 = 40
REP_RATE = '2000 Hz'
PULSE_DETECTION_LENGTH = '512 ns'
SHAPE = 'SINE'
FREQ = '50 MHz'
IQ_FREQ = -float(FREQ.split()[0])

# None uses the phase corrections saved by the phasing GUI.
ZERO_ORDER = None
FIRST_ORDER = None
SECOND_ORDER = None

# Sweep axes
sweep_axis = TAU_START + np.arange(POINTS) * STEP
field_intervals = (END_FIELD - START_FIELD) / FIELD_STEP
FIELD_POINTS = round(field_intervals) + 1
field_axis = START_FIELD + np.arange(FIELD_POINTS) * FIELD_STEP
TOTAL_POINTS = POINTS * FIELD_POINTS
process = 'None'

# Setting magnetic field
bh15.magnet_setup(START_FIELD, abs(FIELD_STEP))

# Setting pulses
ph = pb.digitizer_expand_phase_cycling('-1,2', '+x,-x', '+x,+x')
PHASES = len(ph['receiver'])
pb.pulser_pulse(name = 'P0', channel = 'TRIGGER_AWG', start = f'{P0_START:.1f} ns',
                length = PULSE_1_LENGTH)
pb.pulser_pulse(name = 'P1', channel = 'TRIGGER_AWG', start = f'{P1_START:.1f} ns',
                length = PULSE_2_LENGTH, delta_start = f'{STEP} ns')
pb.awg_pulse(name = 'A0', channel = 'CH0', func = SHAPE, frequency = FREQ, phase = 0,
             length = PULSE_1_LENGTH, sigma = PULSE_1_LENGTH, start = f'{P0_START:.1f} ns',
             phase_list = ph['pulses'][0], amplitude = AMPL_1)
pb.awg_pulse(name = 'A1', channel = 'CH0', func = SHAPE, frequency = FREQ, phase = 0,
             length = PULSE_2_LENGTH, sigma = PULSE_2_LENGTH, start = f'{P1_START:.1f} ns',
             phase_list = ph['pulses'][1], amplitude = AMPL_2)
pb.pulser_pulse(name = 'D', channel = 'DETECTION', start = f'{DETECTION_START:.1f} ns',
                length = PULSE_DETECTION_LENGTH, delta_start = f'{2 * STEP} ns', phase_list = ph['receiver'])
pb.pulser_repetition_rate(REP_RATE)
pb.pulser_default_synt(1)
pb.digitizer_number_of_averages(AVERAGES)

pb.digitizer_read_settings()
pb.digitizer_decimation(DEC_COEF)
points_window = pb.digitizer_window_points()
zero_order = pb.zero_order if ZERO_ORDER is None else ZERO_ORDER
first_order = pb.first_order if FIRST_ORDER is None else FIRST_ORDER
second_order = pb.second_order if SECOND_ORDER is None else SECOND_ORDER

# Data arrays and saving headers
time_axis = np.arange(points_window) * 0.4 * DEC_COEF / 1e9
now = datetime.datetime.now().strftime('%d-%m-%Y %H-%M-%S')
w = 30
header_head = (
    f"{'Date:':<{w}} {now}\n"
    f"{'Experiment:':<{w}} {EXP_NAME}\n"
    f"{'Start Field:':<{w}} {START_FIELD} G\n"
    f"{'End Field:':<{w}} {END_FIELD} G\n"
    f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
    f"{'Field Wait:':<{w}} {FIELD_WAIT}\n"
    f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
    f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
    f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
    f"{general.fmt(mw.mw_bridge_att2_prd(), w)}\n"
    f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
    f"{'Repetition Rate:':<{w}} {REP_RATE}\n"
    f"{'Number of Scans:':<{w}} {SCANS}\n"
    f"{'Averages:':<{w}} {AVERAGES}\n"
    f"{'Phases:':<{w}} {PHASES}\n"
    f"{'Delay / Field Points:':<{w}} {POINTS} / {FIELD_POINTS}\n"
    f"{'Window:':<{w}} {PULSE_DETECTION_LENGTH}\n"
    f"{'Integration Window:':<{w}} {pb.win_left * 0.4 * DEC_COEF:.1f} - {pb.win_right * 0.4 * DEC_COEF:.1f} ns\n"
    f"{'Phase (0 / 1 / 2):':<{w}} {zero_order:.4g} rad / {first_order:.4g} rad/s / {second_order:.4g} rad/s2\n"
    f"{'Sweep Axis (ns):':<{w}} {sweep_axis.tolist()}\n"
    f"{'Flat Index:':<{w}} field_index * POINTS + delay_index; delay fastest\n"
    f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
    f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
)
header_tail = (
    f"{'-' * 50}\nPulse List:\n{pb.pulser_pulse_list()}"
    f"{'-' * 50}\nAWG Pulse List:\n{pb.awg_pulse_list()}"
    f"{'-' * 50}\n"
    'Raw I/Q: (field * delay, ADC sample); map I/Q: (field, delay).\n'
    'Map axes: t = exact delay/length in s, sweep = field in G.\n'
)
header = (
    header_head
    + f"{'Frequency Shift:':<{w}} {-IQ_FREQ} MHz\n"
    + f"{'Horizontal Resolution:':<{w}} {0.4 * DEC_COEF} ns\n"
    + 'Y (Point/): start 0 step 1\n'
)
header_map = header_head + f"{'IQ Frequency:':<{w}} {IQ_FREQ} MHz\n"
integral_map = np.zeros((2, POINTS, FIELD_POINTS))
data = np.zeros((2, points_window, TOTAL_POINTS), dtype = 'float32')
header += header_tail
header_map += header_tail
file_data = file_handler.create_file_dialog(fmt = 'h5')

pb.pulser_open()

# Data acquisition
for k in general.scans(SCANS):
    for idx in range(TOTAL_POINTS):
        j = idx % POINTS
        field_index = idx // POINTS

        # Test only the field endpoints; pulse timing is the same at every field.
        if general.test_flag == 'test' and field_index not in (0, FIELD_POINTS - 1):
            continue
        field = field_axis[field_index]
        if j == 0:
            bh15.magnet_field(field)
            general.wait(FIELD_WAIT)
            if idx > 0:
                pb.pulser_pulse_reset(reset_index = False)
                pb.awg_pulse_reset()

        # Full phase cycle at the first and last point only in test mode, as in HYSCORE.
        n_ph = PHASES if general.test_flag != 'test' or j in (0, POINTS - 1) else 1
        for i in range(n_ph):
            pb.awg_next_phase()
            pb.pulser_update()
            a, b, rng = pb.digitizer_get_curve(
                TOTAL_POINTS, PHASES, current_scan = k, total_scan = SCANS, partial = True)
            readout_ready = True
            if a is not None:
                j0, j1 = rng
                data[0, :, j0:j1] = a
                data[1, :, j0:j1] = b
                dx, dy = pb.digitizer_demodulate(
                    a, b, IQ_FREQ, zero_order, first_order, second_order, integral = True)
                flat = np.arange(j0, j1)
                integral_map[0, flat % POINTS, flat // POINTS] = dx
                integral_map[1, flat % POINTS, flat // POINTS] = dy
                process = general.update_2d(
                    EXP_NAME, integral_map, j0 // POINTS, (j1 - 1) // POINTS + 1,
                    start_step = ((TAU_START / 1e9, STEP / 1e9), (START_FIELD, FIELD_STEP)),
                    xname = 'Tau', xscale = 's',
                    yname = 'Field', yscale = 'G', zname = 'Integral', zscale = 'mV ns',
                    text = f'Scan / Field / Time: {k} / {field:g} G / {sweep_axis[j]:g} ns',
                    pr = process)
        pb.awg_shift()
        if j < POINTS - 1:
            pb.pulser_shift()
    pb.pulser_pulse_reset()
    pb.awg_pulse_reset()

data[0], data[1] = pb.digitizer_at_exit()
pb.pulser_close()
full_map()
readout_ready = False

general.plot_2d(
    EXP_NAME, integral_map,
    start_step = ((TAU_START / 1e9, STEP / 1e9), (START_FIELD, FIELD_STEP)),
    xname = 'Tau', xscale = 's',
    yname = 'Field', yscale = 'G', zname = 'Integral', zscale = 'mV ns', pr = 'None')

# Save the raw I/Q and the integrated map
save_all()
general.message_test(f'{EXP_NAME}: timing and phase cycles passed ({POINTS} points; field endpoints)')
