import sys
import signal
import datetime
import numpy as np
import atomize.general_modules.general_functions as general
import atomize.device_modules.PB_ESR_500_pro as pb_pro
#import atomize.device_modules.Spectrum_M4I_4450_X8 as spectrum
import atomize.device_modules.Keysight_2000_Xseries as key
import atomize.device_modules.Mikran_X_band_MW_bridge_v2 as mwBridge
import atomize.device_modules.BH_15 as bh
import atomize.device_modules.Lakeshore_335 as ls
import atomize.general_modules.csv_opener_saver_tk_kinter as openfile

### Experimental parameters
POINTS = 401
STEP = 10                  # in NS;
FIELD = 3389
AVERAGES = 50
SCANS = 1
process = 'None'

# PULSES
REP_RATE = '1000 Hz'
PULSE_1_LENGTH = '16 ns'
PULSE_2_LENGTH = '16 ns'
PULSE_3_LENGTH = '16 ns'
PULSE_1_START = '0 ns'
PULSE_2_START = '300 ns'
PULSE_3_START = '356 ns'
PULSE_SIGNAL_START = '656 ns'
PHASES = 4

# NAMES
EXP_NAME = 'ESEEM Echo'
CURVE_NAME = 'exp1'

# initialization of the devices
file_handler = openfile.Saver_Opener()
ls335 = ls.Lakeshore_335()
mw = mwBridge.Mikran_X_band_MW_bridge_v2()
pb = pb_pro.PB_ESR_500_Pro()
a2012 = key.Keysight_2000_Xseries()
bh15 = bh.BH_15()
#dig4450 = spectrum.Spectrum_M4I_4450_X8()

def cleanup(*args):
    #dig4450.digitizer_stop()
    #dig4450.digitizer_close()
    pb.pulser_stop()
    file_handler.save_data(file_data, data, header = header, mode = 'w')
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)

bh15.magnet_setup(FIELD, 1)
bh15.magnet_field(FIELD)

pb.pulser_pulse(name = 'P0', channel = 'MW', start = PULSE_1_START, length = PULSE_1_LENGTH, phase_list = ['+x', '-x', '+x', '-x'])
# 208 ns between P0 and P1 is set according to modulation deep in ESEEM. Can be adjust using different delays;
pb.pulser_pulse(name = 'P1', channel = 'MW', start = PULSE_2_START, length = PULSE_2_LENGTH, phase_list = ['+x', '+x', '-x', '-x'])
pb.pulser_pulse(name = 'P2', channel = 'MW', start = PULSE_3_START, length = PULSE_3_LENGTH, delta_start = str(STEP) + ' ns', phase_list = ['+x', '+x', '+x', '+x'])
pb.pulser_pulse(name = 'P3', channel = 'TRIGGER', start = PULSE_SIGNAL_START, length = '100 ns', delta_start = str(STEP) + ' ns')

pb.pulser_repetition_rate( REP_RATE )
pb.pulser_update()

#dig4450.digitizer_read_settings()
#dig4450.digitizer_number_of_averages(AVERAGES)
#time_res = int( 1000 / int(dig4450.digitizer_sample_rate().split(' ')[0]) )
# a full oscillogram will be transfered
#wind = dig4450.digitizer_number_of_points()
#cycle_data_x = np.zeros( (4, int(wind)) )
#cycle_data_y = np.zeros( (4, int(wind)) )
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
cycle_data_x = np.zeros( (PHASES, real_length) )
cycle_data_y = np.zeros( (PHASES, real_length) )
data = np.zeros( (PHASES, real_length, POINTS) )
###

# Data saving
header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + 'ESEEM Echo Shape\n' + \
            'Field: ' + str(FIELD) + ' G \n' + str(mw.mw_bridge_att_prm()) + '\n' + str(mw.mw_bridge_att2_prm()) + '\n' + str(mw.mw_bridge_att1_prd()) + '\n' + \
            str(mw.mw_bridge_synthesizer()) + '\n' + \
           'Repetition Rate: ' + str(pb.pulser_repetition_rate()) + '\n' + 'Number of Scans: ' + str(SCANS) + '\n' +\
           'Averages: ' + str(AVERAGES) + '\n' + 'Points: ' + str(POINTS) + '\n' + 'Window: ' + str(wind) + ' ns\n' \
           + 'Horizontal Resolution: ' + str(time_res) + ' ns\n' + 'Vertical Resolution: ' + str(STEP) + ' ns\n' \
           'Temperature: ' + str(ls335.tc_temperature('B')) + ' K\n' +\
           'Pulse List: ' + '\n' + str(pb.pulser_pulse_list()) + '2D Data'

file_data, file_param = file_handler.create_file_parameters('.param')
file_handler.save_header(file_param, header = header, mode = 'w')

# Data acquisition
for j in general.scans(SCANS):

    for i in range(POINTS):

        # phase cycle
        k = 0
        while k < PHASES:

            pb.pulser_next_phase()
            #x_axis, cycle_data_x[k], cycle_data_y[k] = dig4450.digitizer_get_curve()
            
            a2012.oscilloscope_start_acquisition()
            cycle_data_x[k], cycle_data_y[k] = a2012.oscilloscope_get_curve('CH1'), a2012.oscilloscope_get_curve('CH2')
            
            k += 1
        
        # acquisition cycle [+, -, -, +]
        x, y = pb.pulser_acquisition_cycle(cycle_data_x, cycle_data_y, acq_cycle = ['+', '-', '-', '+'])

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
