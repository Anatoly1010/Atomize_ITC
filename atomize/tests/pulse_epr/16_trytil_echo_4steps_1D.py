import sys
import signal
import datetime
import numpy as np
import atomize.general_modules.general_functions as general
import atomize.device_modules.PB_ESR_500_pro as pb_pro
import atomize.device_modules.Spectrum_M4I_4450_X8 as spectrum
import atomize.device_modules.Mikran_X_band_MW_bridge as mwBridge
import atomize.device_modules.SR_PTC_10 as sr
import atomize.device_modules.BH_15 as bh
import atomize.general_modules.csv_opener_saver_tk_kinter as openfile

### Experimental parameters
POINTS = 1                # 1 point
STEP = 0                  # in NS;
FIELD = 3444.2
AVERAGES = 4096
SCANS = 1024
process = 'None'

# PULSES
REP_RATE = '10000 Hz'
PULSE_1_LENGTH = '22 ns'
PULSE_2_LENGTH = '44 ns'
PULSE_1_START = '0 ns'
PULSE_2_START = '250 ns'        # 1200 ns
PULSE_SIGNAL_START = '500 ns'   # 2400 ns
PHASE_CYCLE = 4

# NAMES
EXP_NAME = 'Echo2'
CURVE_NAME = 'exp1'

# initialization of the devices
file_handler = openfile.Saver_Opener()

def cleanup(*args):
    dig4450.digitizer_stop()
    dig4450.digitizer_close()
    pb.pulser_stop()
    file_handler.save_data(file_data, np.c_[x_axis, data_x, data_y], header = header, mode = 'w')
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)

ptc10 = sr.SR_PTC_10()
mw = mwBridge.Mikran_X_band_MW_bridge()
pb = pb_pro.PB_ESR_500_Pro()
bh15 = bh.BH_15()
dig4450 = spectrum.Spectrum_M4I_4450_X8()

# Setting magnetic field
bh15.magnet_setup(FIELD, 1)
bh15.magnet_field(FIELD)

dig4450.digitizer_read_settings()
dig4450.digitizer_number_of_averages(AVERAGES)
time_res = int( 1000 / int(dig4450.digitizer_sample_rate().split(' ')[0]) )
# a full oscillogram will be transfered
wind = dig4450.digitizer_number_of_points()
cycle_data_x = np.zeros( (PHASE_CYCLE, int(wind)) )
cycle_data_y = np.zeros( (PHASE_CYCLE, int(wind)) )
data_x = np.zeros( int(wind) )
data_y = np.zeros( int(wind) )
x_axis = np.linspace(0, (int(wind) - 1)*time_res, num = int(wind))

# Setting pulses
pb.pulser_pulse(name = 'P0', channel = 'MW', start = PULSE_1_START, length = PULSE_1_LENGTH, \
                phase_list = ['+x','+x','+x','+x'])
pb.pulser_pulse(name = 'P1', channel = 'MW', start = PULSE_2_START, length = PULSE_2_LENGTH, delta_start = str(int(STEP/2)) + ' ns', \
                phase_list = ['+x','-x','+y','-y'])
pb.pulser_pulse(name = 'P2', channel = 'TRIGGER', start = PULSE_SIGNAL_START, length = '100 ns', delta_start = str(STEP) + ' ns')

pb.pulser_repetition_rate( REP_RATE )

# Data saving
header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + \
         'Tritil Echo\n' + 'Field: ' + str(FIELD) + ' G \n' +  \
          str(mw.mw_bridge_att_prm()) + '\n' + str(mw.mw_bridge_att1_prd()) + '\n' + str(mw.mw_bridge_synthesizer()) + '\n' + \
          'Repetition Rate: ' + str(pb.pulser_repetition_rate()) + '\n' + 'Number of Scans: ' + str(SCANS) + '\n' +\
          'Averages: ' + str(AVERAGES) + '\n' + 'Points: ' + str(POINTS) + '\n' + 'Window: ' + str(wind * time_res) + ' ns\n' \
          + 'Horizontal Resolution: ' + str(time_res) + ' ns\n' + 'Vertical Resolution: ' + str(STEP) + ' ns\n' \
          + 'Temperature: ' + str(ptc10.tc_temperature('2A')) + ' K\n' +\
          'Pulse List: ' + '\n' + str(pb.pulser_pulse_list()) + 'Time (ns), X (V*s), Y (V*s) '

file_data, file_param = file_handler.create_file_parameters('.param')
file_handler.save_header(file_param, header = header, mode = 'w')

# Data acquisition
for j in general.scans(SCANS):

    for i in range(POINTS):

        # phase cycle
        k = 0
        while k < PHASE_CYCLE:

            pb.pulser_next_phase()
            x_axis, cycle_data_x[k], cycle_data_y[k] = dig4450.digitizer_get_curve()

            k += 1

        # acquisition cycle [+, -]
        x, y = pb.pulser_acquisition_cycle(cycle_data_x, cycle_data_y, acq_cycle = ['+','+','-','-'])

        data_x = ( data_x * (j - 1) + x ) / j
        data_y = ( data_y * (j - 1) + y ) / j

        process = general.plot_1d(EXP_NAME, x_axis, ( data_x, data_y ), xname = 'Time',\
            xscale = 'ns', yname = 'Intensity', yscale = 'V*s', label = CURVE_NAME, pr = process, \
            text = 'Scan / Time: ' + str(j) + ' / '+ str(i*STEP))

        ##pb.pulser_shift()

    pb.pulser_pulse_reset()

dig4450.digitizer_stop()
dig4450.digitizer_close()
pb.pulser_stop()

file_handler.save_data(file_data, np.c_[x_axis, data_x, data_y], header = header, mode = 'w')
