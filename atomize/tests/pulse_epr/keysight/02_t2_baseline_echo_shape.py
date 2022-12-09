import sys
import signal
import datetime
import numpy as np
import atomize.general_modules.general_functions as general
import atomize.device_modules.PB_ESR_500_pro as pb_pro
#import atomize.device_modules.Spectrum_M4I_4450_X8 as spectrum
import atomize.device_modules.Keysight_2000_Xseries as key
import atomize.device_modules.Mikran_X_band_MW_bridge_v2 as mwBridge
import atomize.device_modules.Lakeshore_335 as ls
import atomize.device_modules.BH_15 as bh
import atomize.general_modules.csv_opener_saver_tk_kinter as openfile

### Experimental parameters
POINTS = 1501
STEP = 12                  # in NS;
FIELD = 3493.0
AVERAGES = 60
SCANS = 1
process = 'None'

# PULSES
REP_RATE = '800 Hz'
PULSE_1_LENGTH = '100 ns'
PULSE_2_LENGTH = '200 ns'
PULSE_1_START = '0 ns'
PULSE_2_START = '600 ns'
PULSE_SIGNAL_START = '1200 ns'

# NAMES
EXP_NAME = 'T2 Echo'

# initialization of the devices
file_handler = openfile.Saver_Opener()

def cleanup(*args):
    #dig4450.digitizer_stop()
    #dig4450.digitizer_close()
    pb.pulser_stop()
    file_handler.save_data(file_data, data, header = header, mode = 'w')
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)

ls335 = ls.Lakeshore_335()
mw = mwBridge.Mikran_X_band_MW_bridge_v2()
pb = pb_pro.PB_ESR_500_Pro()
bh15 = bh.BH_15()
a2012 = key.Keysight_2000_Xseries()
#dig4450 = spectrum.Spectrum_M4I_4450_X8()

# Setting magnetic field
bh15.magnet_setup(FIELD, 1)
bh15.magnet_field(FIELD)

# Setting pulses
pb.pulser_pulse(name = 'P0', channel = 'MW', start = PULSE_1_START, length = PULSE_1_LENGTH, phase_list = ['+x', '-x'])
pb.pulser_pulse(name = 'P1', channel = 'MW', start = PULSE_2_START, length = PULSE_2_LENGTH, delta_start = str(int(STEP/2)) + ' ns', phase_list = ['+x', '+x'])
pb.pulser_pulse(name = 'P2', channel = 'TRIGGER', start = PULSE_SIGNAL_START, length = '100 ns', delta_start = str(STEP) + ' ns')

pb.pulser_repetition_rate( REP_RATE )
pb.pulser_update()

#dig4450.digitizer_read_settings()
#dig4450.digitizer_number_of_averages(AVERAGES)
#time_res = int( 1000 / int(dig4450.digitizer_sample_rate().split(' ')[0]) )
# a full oscillogram will be transfered
#wind = dig4450.digitizer_number_of_points()
#cycle_data_x = np.zeros( (2, int(wind)) )
#cycle_data_y = np.zeros( (2, int(wind)) )
#data = np.zeros( (2, int(wind), POINTS) )

# Setting oscilloscope
a2012.oscilloscope_trigger_channel('Ext')
a2012.oscilloscope_acquisition_type('Average')
a2012.oscilloscope_number_of_averages(AVERAGES)
#a2012.oscilloscope_stop()

a2012.oscilloscope_record_length( 4000 )
real_length = a2012.oscilloscope_record_length( )
wind = a2012.oscilloscope_timebase() * 1000
time_res = wind / real_length
#x_axis = np.linspace(0, (POINTS - 1)*STEP, num = POINTS)
cycle_data_x = np.zeros( (2, real_length) )
cycle_data_y = np.zeros( (2, real_length) )
data = np.zeros( (2, real_length, POINTS) )
###

# Data saving
header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + \
         'T2 Echo Shape\n' + 'Field: ' + str(FIELD) + ' G \n' + \
          str(mw.mw_bridge_att_prm()) + '\n' + str(mw.mw_bridge_att1_prd()) + '\n' + str(mw.mw_bridge_synthesizer()) + '\n' + \
          'Repetition Rate: ' + str(pb.pulser_repetition_rate()) + '\n' + 'Number of Scans: ' + str(SCANS) + '\n' +\
          'Averages: ' + str(AVERAGES) + '\n' + 'Points: ' + str(POINTS) + '\n' + 'Window: ' + str(wind) + ' ns\n' \
          + 'Horizontal Resolution: ' + str(time_res) + ' ns\n' + 'Vertical Resolution: ' + str(STEP) + ' ns\n' \
          + 'Temperature: ' + str(ls335.tc_temperature('B')) + ' K\n' +\
          'Pulse List: ' + '\n' + str(pb.pulser_pulse_list()) + '2D Data'

file_data, file_param = file_handler.create_file_parameters('.param')
file_handler.save_header(file_param, header = header, mode = 'w')

# Data acquisition
for j in general.scans(SCANS):

    for i in range(POINTS):

        # phase cycle
        k = 0
        while k < 2:

            pb.pulser_next_phase()
            a2012.oscilloscope_start_acquisition()
            cycle_data_x[k], cycle_data_y[k] = a2012.oscilloscope_get_curve('CH1'), a2012.oscilloscope_get_curve('CH2')

            #x_axis, cycle_data_x[k], cycle_data_y[k] = dig4450.digitizer_get_curve()

            k += 1

        # acquisition cycle [+, -]
        x, y = pb.pulser_acquisition_cycle(cycle_data_x, cycle_data_y, acq_cycle = ['+', '-'])

        data[0, :, i] = ( data[0, :, i] * (j - 1) + x ) / j
        data[1, :, i] = ( data[1, :, i] * (j - 1) + y ) / j

        process = general.plot_2d(EXP_NAME, data, start_step = ( (0, round( time_res, 2 )), (0, STEP) ), xname = 'Time',\
            xscale = 'ns', yname = 'Delay', yscale = 'ns', zname = 'Intensity', zscale = 'V', pr = process, \
            text = 'Scan / Time: ' + str(j) + ' / '+ str(i*STEP))

        pb.pulser_shift()

    pb.pulser_pulse_reset()

#dig4450.digitizer_stop()
#dig4450.digitizer_close()
pb.pulser_stop()

file_handler.save_data(file_data, data, header = header, mode = 'w')
