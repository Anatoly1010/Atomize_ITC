import numpy as np
import atomize.general_modules.general_functions as general
import atomize.device_modules.Keysight_2000_Xseries as key
import atomize.general_modules.csv_opener_saver_tk_kinter as openfile

a2012 = key.Keysight_2000_Xseries()
file_handler = openfile.Saver_Opener()

def cleanup(*args):
    file_handler.save_data(file_data, np.c_[x_axis, data], header = header, mode = 'w')
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)

### Experimental parameters
AVERAGES = 60
# NAMES
EXP_NAME = 'A2012'

# Setting oscilloscope
a2012.oscilloscope_trigger_channel('CH2')
a2012.oscilloscope_acquisition_type('Average')
a2012.oscilloscope_number_of_averages(AVERAGES)
#a2012.oscilloscope_stop()

a2012.oscilloscope_record_length( 4000 )
real_length = a2012.oscilloscope_record_length( )
wind = a2012.oscilloscope_timebase() * 1000
time_res = wind / real_length
x_axis = np.linspace(0, (POINTS - 1)*time_res, num = real_length)
data = np.zeros( real_length )
###

# Data saving
header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + \
         'THz pulse\n' + 'Averages: ' + str(AVERAGES) + '\n' + 'Points: ' + str(real_length) + '\n' + \
         'Window: ' + str(wind) + ' ns\n' + \
         'Horizontal Resolution: ' + str(time_res) + ' ns\n' + \
         'Time (ns), Signal (V) '

file_data, file_param = file_handler.create_file_parameters('.param')
file_handler.save_header(file_param, header = header, mode = 'w')

a2012.oscilloscope_start_acquisition()
data = a2012.oscilloscope_get_curve('CH1')
x_axis = np.linspace(0, (real_length - 1)*time_res, num = real_length)

general.plot_1d(EXP_NAME, x_axis, data, xname = 'Time',\
    xscale = 'ns', yname = 'I', yscale = 'V', label = CURVE_NAME)

file_handler.save_data(file_data, np.c_[x_axis, data], header = header, mode = 'w')
