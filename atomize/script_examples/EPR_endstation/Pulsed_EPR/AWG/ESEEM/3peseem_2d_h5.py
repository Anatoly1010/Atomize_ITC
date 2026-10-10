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
    integral_map[0] = mi.reshape(N2, N1).T
    integral_map[1] = mq.reshape(N2, N1).T


def save_all():
    if general.test_flag == 'test':
        return
    file_handler.save_data(file_data, data, header = header, mode = 'w',
                           axes = (time_axis, None), dtype = 'float32', axes_units = ('s', None))
    if file_data not in ('None', '', None):
        file_handler.save_data(file_data.rsplit('.', 1)[0] + '_map.h5', integral_map,
                               header = header_map, mode = 'w', axes = (t_axis / 1e9, tau_axis / 1e9),
                               dtype = 'float32', axes_units = ('s', 's'))


def cleanup(*args):
    if readout_ready:
        data[0], data[1] = pb.digitizer_at_exit()
    pb.pulser_close()
    if data is not None:
        full_map()
        save_all()
    sys.exit(0)


signal.signal(signal.SIGTERM, cleanup)

# 3pESEEM: pi/2 - tau - pi/2 - T - pi/2 - tau - echo; delays are start-to-start.
N1 = 500                  # T points (inner / fast delay)
N2 = 32                   # tau points (outer / slow delay)
POINTS = N1 * N2
T_START = 64.0
T_STEP = 12.8
TAU_START = 208.0
TAU_STEP = 16.0
FIELD = 3324.0
FIELD_WAIT = '4000 ms'
AVERAGES = 20
SCANS = 1
DEC_COEF = 1               # must match digitizer_insys.param
EXP_NAME = '3pESEEM (T, tau)'

# Pulse parameters
P0_START = 0.0
P1_START = TAU_START
P2_START = TAU_START + T_START
DETECTION_START = 2 * TAU_START + T_START
PULSE_1_LENGTH = '16.0 ns'
PULSE_2_LENGTH = '16.0 ns'
PULSE_3_LENGTH = '16.0 ns'
AMPL_1 = 60
AMPL_2 = 30
AMPL_3 = 60
REP_RATE = '1000 Hz'
PULSE_DETECTION_LENGTH = '512 ns'
SHAPE = 'SINE'
FREQ = '50 MHz'
IQ_FREQ = -float(FREQ.split()[0])

# None uses the phase corrections saved by the phasing GUI.
ZERO_ORDER = None
FIRST_ORDER = None
SECOND_ORDER = None

# Sweep axes
t_axis = T_START + np.arange(N1) * T_STEP
tau_axis = TAU_START + np.arange(N2) * TAU_STEP
process = 'None'

# Setting magnetic field
bh15.magnet_setup(FIELD, 1)
bh15.magnet_field(FIELD)
general.wait(FIELD_WAIT)

# Setting pulses
ph = pb.digitizer_expand_phase_cycling('-1,1,-1', '(x)', '(x)', 'x')
PHASES = len(ph['receiver'])
pb.pulser_pulse(name = 'P0', channel = 'TRIGGER_AWG', start = f'{P0_START:.1f} ns',
                length = PULSE_1_LENGTH)
pb.pulser_pulse(name = 'P1', channel = 'TRIGGER_AWG', start = f'{P1_START:.1f} ns',
                length = PULSE_2_LENGTH)
pb.pulser_pulse(name = 'P2', channel = 'TRIGGER_AWG', start = f'{P2_START:.1f} ns',
                length = PULSE_3_LENGTH, delta_start = f'{T_STEP} ns')
pb.awg_pulse(name = 'A0', channel = 'CH0', func = SHAPE, frequency = FREQ, phase = 0,
             length = PULSE_1_LENGTH, sigma = PULSE_1_LENGTH, start = f'{P0_START:.1f} ns',
             phase_list = ph['pulses'][0], amplitude = AMPL_1)
pb.awg_pulse(name = 'A1', channel = 'CH0', func = SHAPE, frequency = FREQ, phase = 0,
             length = PULSE_2_LENGTH, sigma = PULSE_2_LENGTH, start = f'{P1_START:.1f} ns',
             phase_list = ph['pulses'][1], amplitude = AMPL_2)
pb.awg_pulse(name = 'A2', channel = 'CH0', func = SHAPE, frequency = FREQ, phase = 0,
             length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = f'{P2_START:.1f} ns',
             phase_list = ph['pulses'][2], amplitude = AMPL_3)
pb.pulser_pulse(name = 'D', channel = 'DETECTION', start = f'{DETECTION_START:.1f} ns',
                length = PULSE_DETECTION_LENGTH, delta_start = f'{T_STEP} ns', phase_list = ph['receiver'])
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
    f"{'Field:':<{w}} {FIELD} G\n"
    f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
    f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
    f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
    f"{general.fmt(mw.mw_bridge_att2_prd(), w)}\n"
    f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
    f"{'Repetition Rate:':<{w}} {REP_RATE}\n"
    f"{'Number of Scans:':<{w}} {SCANS}\n"
    f"{'Averages:':<{w}} {AVERAGES}\n"
    f"{'Phases:':<{w}} {PHASES}\n"
    f"{'N1:':<{w}} {N1}\n"
    f"{'N2:':<{w}} {N2}\n"
    f"{'T Start:':<{w}} {T_START} ns\n"
    f"{'T Step:':<{w}} {T_STEP} ns\n"
    f"{'Tau Start:':<{w}} {TAU_START} ns\n"
    f"{'Tau Step:':<{w}} {TAU_STEP} ns\n"
    f"{'Window:':<{w}} {PULSE_DETECTION_LENGTH}\n"
    f"{'Integration Window:':<{w}} {pb.win_left * 0.4 * DEC_COEF:.1f} - {pb.win_right * 0.4 * DEC_COEF:.1f} ns\n"
    f"{'Phase (0 / 1 / 2):':<{w}} {zero_order:.4g} rad / {first_order:.4g} rad/s / {second_order:.4g} rad/s2\n"
    f"{'Flat Index:':<{w}} idx = i2*N1 + i1, T fastest\n"
    f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
    f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
)
header_tail = (
    f"{'-' * 50}\nPulse List:\n{pb.pulser_pulse_list()}"
    f"{'-' * 50}\nAWG Pulse List:\n{pb.awg_pulse_list()}"
    f"{'-' * 50}\n"
    'Raw I/Q: (N2*N1, ADC sample); map I/Q: (N2, N1).\n'
    'Map axes: t = T in s, sweep = tau in s.\n'
)
header = (
    header_head
    + f"{'Frequency Shift:':<{w}} {-IQ_FREQ} MHz\n"
    + f"{'Horizontal Resolution:':<{w}} {0.4 * DEC_COEF} ns\n"
    + 'Y (Point/): start 0 step 1\n'
    + header_tail
)
header_map = (
    header_head
    + f"{'IQ Frequency:':<{w}} {IQ_FREQ} MHz\n"
    + f'X (T/ns): start {T_START} step {T_STEP}\n'
    + f'Y (tau/ns): start {TAU_START} step {TAU_STEP}\n'
    + header_tail
)
integral_map = np.zeros((2, N1, N2))
data = np.zeros((2, points_window, POINTS), dtype = 'float32')
file_data = file_handler.create_file_dialog(fmt = 'h5')

pb.pulser_open()

# Data acquisition
for k in general.scans(SCANS):
    for idx in range(POINTS):
        i1 = idx % N1
        i2 = idx // N1

        # Restore T_START at the next tau without resetting the acquisition index.
        if i1 == 0 and idx > 0:
            pb.pulser_pulse_reset(reset_index = False)
            pb.awg_pulse_reset()
            shift = i2 * TAU_STEP
            pb.pulser_redefine_start(name = 'P1', start = f'{P1_START + shift:.1f} ns')
            pb.pulser_redefine_start(name = 'P2', start = f'{P2_START + shift:.1f} ns')
            pb.pulser_redefine_start(name = 'D', start = f'{DETECTION_START + 2 * shift:.1f} ns')

        # Test every delay pair, with full phase cycles only at each row's endpoints.
        n_ph = PHASES if general.test_flag != 'test' or i1 in (0, N1 - 1) else 1
        for i in range(n_ph):
            pb.awg_next_phase()
            pb.pulser_update()
            a, b, rng = pb.digitizer_get_curve(
                POINTS, PHASES, current_scan = k, total_scan = SCANS, partial = True)
            readout_ready = True
            if a is not None:
                j0, j1 = rng
                data[0, :, j0:j1] = a
                data[1, :, j0:j1] = b
                dx, dy = pb.digitizer_demodulate(
                    a, b, IQ_FREQ, zero_order, first_order, second_order, integral = True)
                flat = np.arange(j0, j1)
                integral_map[0, flat % N1, flat // N1] = dx
                integral_map[1, flat % N1, flat // N1] = dy
                process = general.update_2d(
                    EXP_NAME, integral_map, j0 // N1, (j1 - 1) // N1 + 1,
                    start_step = ((T_START / 1e9, T_STEP / 1e9), (TAU_START / 1e9, TAU_STEP / 1e9)),
                    xname = 'T', xscale = 's',
                    yname = 'tau', yscale = 's', zname = 'Integral', zscale = 'mV ns',
                    text = f'Scan / T / tau: {k} / {t_axis[i1]:g} ns / {tau_axis[i2]:g} ns',
                    pr = process)
        pb.awg_shift()
        if i1 < N1 - 1:
            pb.pulser_shift()
    pb.pulser_pulse_reset()
    pb.awg_pulse_reset()

data[0], data[1] = pb.digitizer_at_exit()
pb.pulser_close()
full_map()
readout_ready = False

general.plot_2d(
    EXP_NAME, integral_map,
    start_step = ((T_START / 1e9, T_STEP / 1e9), (TAU_START / 1e9, TAU_STEP / 1e9)),
    xname = 'T', xscale = 's',
    yname = 'tau', yscale = 's', zname = 'Integral', zscale = 'mV ns', pr = 'None')

# Save the raw I/Q and the integrated map
save_all()
general.message_test(f'{EXP_NAME}: timing and phase cycles passed ({N1} T points x {N2} tau points)')
