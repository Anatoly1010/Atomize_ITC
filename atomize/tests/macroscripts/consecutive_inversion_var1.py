import datetime
import numpy as np
import atomize.general_modules.general_functions as general
import atomize.general_modules.csv_opener_saver_tk_kinter as openfile
import inversion as inv

file_handler = openfile.Saver_Opener()

process = 'None'
CURVE_NAME = 'h1cor'
START_FREQ = 9525
START_FIELD = round( 3516 - 175/2.804, 3 )
START_WURST_CENTER = '-175 MHz'
START_SINE_FREQ = '0 MHz'

AVERAGES = 40
POINTS = 70
STEP = 5
EXP_NAME = 'wurst'

data = np.zeros( POINTS )
x_axis = np.linspace(START_FREQ, START_FREQ + STEP * (POINTS), num = POINTS, endpoint = False)

# Data saving
header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + \
         'Inversion\n' + 'Start Field: ' + str(START_FIELD) + ' G \n' + \
         'Start Wurst Center: ' + str(START_WURST_CENTER) +  '\n' + \
         'Start Sine Freq: ' + str(START_SINE_FREQ) + '\n' + \
         'Step: ' + str(STEP) + ' MHz \n' + \
         'Averages: ' + str(AVERAGES) + '\n' + 'Points: ' + str(POINTS) + '\n' + \
         'Frequency (MHz), Mz/M0 '

file_data, file_param = file_handler.create_file_parameters('.param')
file_handler.save_header(file_param, header = header, mode = 'w')

for i in range(POINTS):

    freq = START_FREQ + i * STEP
    mf = round( START_FIELD + i * ( STEP / 2.804), 3)
    wurst = str( int(START_WURST_CENTER.split(" ")[0]) + i * STEP ) + " MHz"

    e0 = inv.experiment_no_wurst( MW_freq = int(freq), Averages = AVERAGES, FREQ = START_SINE_FREQ, MF = mf )
    e1 = inv.experiment_wurst( MW_freq = int(freq), Averages = AVERAGES, FREQ = START_SINE_FREQ, MF = mf, wurst_center = wurst)

    # division by 0 in test run
    if e0 != 0:
        data[i] = e1 / e0
    else:
        data[i] = 1

    process = general.plot_1d(EXP_NAME, x_axis, data, xname = 'Freq',\
        xscale = 'MHz', yname = 'Mz/M0', yscale = '', label = CURVE_NAME, pr = process, \
        text = 'Step: ' + str(i))

file_handler.save_data(file_data, np.c_[x_axis, data], header = header, mode = 'w')

