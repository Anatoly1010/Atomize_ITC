import sys
import signal
import numpy as np
from datetime import datetime
import atomize.general_modules.general_functions as general
import atomize.device_modules.Keysight_3000_Xseries as key
import atomize.device_modules.SR_860 as sr
import atomize.general_modules.csv_opener_saver_tk_kinter as openfile

sr860 = sr.SR_860()
t3034 = key.Keysight_3000_Xseries()
file_handler = openfile.Saver_Opener()

def cleanup(*args):
    file_handler.save_data(file_data, np.c_[POINTS, data_x, data_y], header = header, mode = 'w')
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)

### Experimental parameters
POINTS = 201                                                   # 1 point
# create a nonlinear axis
nonlinear_freq_raw =  10 ** np.linspace( 0, 4, POINTS )
nonlinear_freq = np.unique( general.numpy_round( nonlinear_time_raw, 2 ) ).astype(np.int64)
# the real number of points after rounding to 2 ns and removing repeated values
POINTS = len( nonlinear_time )
data_x = np.zeros( len(POINTS) )
data_y = np.zeros( len(POINTS) )

TC = '100 ms'
LP = '12 dB'
SEN = '500 mV'
SCANS = 1
process = 'None'
# NAMES
EXP_NAME = 'FREQ'
CURVE_NAME = 'exp1'

t3034.wave_gen_frequency('1 Hz')
t3034.wave_gen_run()

sr860.lock_in_time_constant(TC)
sr860.lock_in_ref_slope('External')
sr860.lock_in_lp_filter(LP)
sr860.lock_in_sensitivity(SEN)

# Data saving
header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + \
         'Frequency\n' + 'Number of Scans: ' + str(SCANS) + '\n' +\
         'Time Constant: ' + str(TC) + '\n' + 'Low-pass Filter: ' + str(LP) + '\n' +\
         'Points: ' + str(POINTS) + '\n' + 'Sensitivity: ' + str(SEN) + '\n' + 'Frequency (Hz), X (V), Y (V) '

file_data, file_param = file_handler.create_file_parameters('.param')
file_handler.save_header(file_param, header = header, mode = 'w')

# Data acquisition
for j in general.scans(SCANS):

    for i in range(POINTS):
        
        t3034.wave_gen_frequency( f'{nonlinear_time[i]} Hz' )

        general.wait(TC)
        x, y = sr860.lock_in_get_data('1', '2')

        data_x[i] = ( data_x[i] * (j - 1) + x ) / j
        data_y[i] = ( data_y[i] * (j - 1) + y ) / j

        process = general.plot_1d(EXP_NAME, POINTS, ( data_x, data_y ), xname = 'Frequency',\
            xscale = 'Hz', yname = 'I', yscale = 'V', label = CURVE_NAME, pr = process,\
            text = 'Scan / Point: ' + str(j) + ' / '+ str(i))


file_handler.save_data(file_data, np.c_[POINTS, data_x, data_y], header = header, mode = 'w')
