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
    file_handler.save_data(file_data, data, header = header, mode = 'w')
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)

### Experimental parameters
POINTS = 500
STEP = 3.2
FIELD = 3478.0
AVERAGES = 5
SCANS = 5
PHASES = 2
DEC_COEF = 1
process = 'None'

# PULSES
REP_RATE = '1000 Hz'
PULSE_1_LENGTH = '320.0 ns'
PULSE_2_LENGTH = '44.8 ns'
PULSE_PUMP_LENGTH = '16 ns'
PULSE_3_LENGTH = '44.8 ns'
PULSE_DETECTION_LENGTH = '480 ns'

PULSE_1_START = '0 ns'
PULSE_2_START = '320 ns'
PULSE_PUMP_START = '544 ns'
PULSE_3_START = '2208 ns' #'2208 ns'
PULSE_DETECTION = '384 ns' #'3776 ns'

SHAPE = 'SINE'
FREQ_PUMP = '200 MHz'
FREQ_OBSERVE = '130 MHz'

AMPL_1 = 17
AMPL_2 = 34
AMPL_3 = 34
AMPL_PUMP = 100

# NAMES
EXP_NAME = 'deer'

# read adc settings
#adc_wind = pb.digitizer_read_settings() #816.0

# Setting magnetic field
bh15.magnet_setup(FIELD, 1)
bh15.magnet_field(FIELD)
###general.wait('4000 ms')

# Setting pulses
pb.pulser_pulse(name = 'P0', channel = 'TRIGGER_AWG', start = PULSE_1_START, 
            length = PULSE_1_LENGTH)
pb.pulser_pulse(name = 'P1', channel = 'TRIGGER_AWG', start = PULSE_2_START, 
            length = PULSE_2_LENGTH)
pb.pulser_pulse(name = 'P2', channel = 'TRIGGER_AWG', start = PULSE_PUMP_START, 
            length = PULSE_PUMP_LENGTH, delta_start = str(STEP) + ' ns')
pb.pulser_pulse(name = 'P3', channel = 'TRIGGER_AWG', start = PULSE_3_START, 
            length = PULSE_3_LENGTH)

pb.pulser_pulse(name = 'P5', channel = 'TRIGGER_AWG', start = '2640 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P6', channel = 'TRIGGER_AWG', start = '2960 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P7', channel = 'TRIGGER_AWG', start = '3280 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P8', channel = 'TRIGGER_AWG', start = '3600 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P9', channel = 'TRIGGER_AWG', start = '3920 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P10', channel = 'TRIGGER_AWG', start = '4240 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P11', channel = 'TRIGGER_AWG', start = '4560 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P12', channel = 'TRIGGER_AWG', start = '4880 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P13', channel = 'TRIGGER_AWG', start = '5200 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P14', channel = 'TRIGGER_AWG', start = '5520 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P15', channel = 'TRIGGER_AWG', start = '5840 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P16', channel = 'TRIGGER_AWG', start = '6160 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P17', channel = 'TRIGGER_AWG', start = '6480 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P18', channel = 'TRIGGER_AWG', start = '6800 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P19', channel = 'TRIGGER_AWG', start = '7120 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P20', channel = 'TRIGGER_AWG', start = '7440 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P21', channel = 'TRIGGER_AWG', start = '7760 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P22', channel = 'TRIGGER_AWG', start = '8080 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P23', channel = 'TRIGGER_AWG', start = '8400 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P24', channel = 'TRIGGER_AWG', start = '8720 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P25', channel = 'TRIGGER_AWG', start = '9040 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P26', channel = 'TRIGGER_AWG', start = '9360 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P27', channel = 'TRIGGER_AWG', start = '9680 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P28', channel = 'TRIGGER_AWG', start = '10000 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P29', channel = 'TRIGGER_AWG', start = '10320 ns', 
            length = PULSE_3_LENGTH)
pb.pulser_pulse(name = 'P30', channel = 'TRIGGER_AWG', start = '10640 ns', 
            length = PULSE_3_LENGTH)

#['+x', '+x', '+x', '+x', '-x', '-x', '-x', '-x']
#['+x', '+x', '+x', '+x', '+x', '+x', '+x', '+x']
#['+x', '+y', '-x', '-y', '+x', '+y', '-x', '-y']
#['+x', '+x', '+x', '+x', '+x', '+x', '+x', '+x']
#['+x', '+x', '+x', '+x', '-x', '-x', '-x', '-x']

pb.awg_pulse(name = 'A0', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_1_LENGTH, sigma = PULSE_1_LENGTH, start = PULSE_1_START, 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_1)
pb.awg_pulse(name = 'A1', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_2_LENGTH, sigma = PULSE_2_LENGTH, start = PULSE_2_START, 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_2)
pb.awg_pulse(name = 'A2', channel = 'CH0', func = SHAPE, frequency = FREQ_PUMP, phase = 0, 
            length = PULSE_PUMP_LENGTH, sigma = PULSE_PUMP_LENGTH, start = PULSE_PUMP_START,
            phase_list = [
            '+x', '+y'], amplitude = AMPL_PUMP)
pb.awg_pulse(name = 'A3', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = PULSE_3_START, 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)

pb.pulser_pulse(name = 'P4', channel = 'DETECTION', start = PULSE_DETECTION, 
            length = PULSE_DETECTION_LENGTH,
            phase_list = [
            '+x', '+x'])

pb.awg_pulse(name = 'A5', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '2640 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A6', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '2960 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A7', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '3280 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A8', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '3600 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A9', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '3920 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A10', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '4240 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A11', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '4560 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A12', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '4880 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A13', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '5200 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A14', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '5520 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A15', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '5840 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A16', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '6160 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A17', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '6480 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A18', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '6800 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A19', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '7120 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A20', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '7440 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A21', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '7760 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A22', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '8080 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A23', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '8400 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A24', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '8720 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A25', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '9040 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A26', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '9360 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A27', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '9680 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A28', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '10000 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A29', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '10320 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)
pb.awg_pulse(name = 'A30', channel = 'CH0', func = SHAPE, frequency = FREQ_OBSERVE, phase = 0, 
            length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = '10640 ns', 
            phase_list = [
            '+x', '+x'], amplitude = AMPL_3)


pb.digitizer_decimation(DEC_COEF)
length_val = float(PULSE_DETECTION_LENGTH.split(' ')[0])
points_window = int(round(length_val / 0.4 / DEC_COEF))
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
    f"{'Experiment:':<{w}} DEER\n"
    f"{'Field:':<{w}} {FIELD} G\n"
    f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
    f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
    f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
    f"{general.fmt(mw.mw_bridge_att1_prd(), w)}\n"
    f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
    f"{'Repetition Rate:':<{w}} {pb.pulser_repetition_rate()}\n"
    f"{'Number of Scans:':<{w}} {SCANS}\n"
    f"{'Averages:':<{w}} {AVERAGES}\n"
    f"{'Points:':<{w}} {POINTS}\n"
    f"{'Window:':<{w}} {PULSE_DETECTION_LENGTH}\n"
    f"{'Horizontal Resolution:':<{w}} {0.4 * DEC_COEF:.1g} ns\n"
    f"{'Vertical Resolution:':<{w}} {STEP} ns\n"
    f"{'Temperature:':<{w}} {ls335.tc_temperature('B')} K\n"
    f"{'-'*50}\n"
    f"Pulse List:\n{pb.pulser_pulse_list()}"
    f"{'-'*50}\n"
    f"2D Data"
)

#file_data = file_handler.create_file_dialog()

scan_time = 0
st_time = time.time()
# Data acquisition
for k in general.scans(SCANS):

    st_time2 = time.time()

    for j in range(POINTS):

        # phase cycle
        for i in range(PHASES):
            
            ##text = 'Scan / Time: ' + str(k) + ' / ' + str(round( j*STEP, 1 )),

            if (j == 2) and (k == 5):
                st_time3 = time.time()

            pb.awg_next_phase()
            pb.pulser_update()
            
            if (j == 2) and (k == 5):
                general.message( f'PC: {round(1000*(time.time() - st_time3), 2)} ms' )

            a, b = pb.digitizer_get_curve( POINTS, PHASES, current_scan = k, total_scan = SCANS ) #, integral = True )

            if a is not None:
                data[0], data[1] = a, b
                process = general.plot_2d(EXP_NAME, data, start_step = ( (0, 0.4), (0, STEP) ), xname = 'Time', xscale = 's', yname = 'Delay', yscale = 's', zname = 'Intensity', zscale = 'mV', pr = process)


        pb.pulser_shift()
        pb.awg_pulse_reset()

    pb.pulser_pulse_reset()

    if k != SCANS:
        scan_time = scan_time + round(1000*(time.time() - st_time2), 1)
    
    general.message( f'FULL SCAN TIME: {round(1000*(time.time() - st_time2), 1)} ms' )

pb.pulser_close()

general.message( f'AVERAGE TIME: {round(scan_time / (SCANS - 1 ), 1)} ms' )
general.message( f'FULL TIME: {round(1000*(time.time() - st_time), 1)} ms' )

general.plot_2d(EXP_NAME, data, start_step = ( (0, 0.4), (0, STEP) ), xname = 'Time', xscale = 's', yname = 'Delay', yscale = 's', zname = 'Intensity', zscale = 'mV', text = 'Scan / Time: ' + str(k) + ' / ' + str(round( j*STEP, 1 )), pr = 'None')

#file_handler.save_data(file_data, data, header = header, mode = 'w')


cip = pb.count_ip(PHASES)
x = np.arange(len(cip))

#general.plot_1d('CIP', x, cip, xname = 'NIP', xscale = '', yname = 'Count', yscale = '', pr = 'None')
general.message( f"Calculated Time: {round(AVERAGES * PHASES * POINTS, 1)} ms" )
general.message( f"Counts: {cip}" )
general.message( f"TC: {np.sum(cip)}" )
