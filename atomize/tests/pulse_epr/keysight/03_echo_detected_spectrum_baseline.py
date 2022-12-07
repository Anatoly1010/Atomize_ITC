import sys
import signal
import datetime
import numpy as np
import atomize.general_modules.general_functions as general
import atomize.device_modules.PB_ESR_500_pro as pb_pro
import atomize.device_modules.Keysight_2000_Xseries as key
#import atomize.device_modules.Spectrum_M4I_4450_X8 as spectrum
import atomize.device_modules.Mikran_X_band_MW_bridge_v2 as mwBridge
import atomize.device_modules.BH_15 as bh
import atomize.device_modules.Lakeshore_335 as ls
import atomize.general_modules.csv_opener_saver as openfile

### Experimental parameters
START_FIELD = 3336
END_FIELD = 3536
FIELD_STEP = 2
AVERAGES = 10
SCANS = 1
process = 'None'

# PULSES
REP_RATE = '500 Hz'
PULSE_1_LENGTH = '16 ns'
PULSE_2_LENGTH = '32 ns'
PULSE_1_START = '0 ns'
PULSE_2_START = '300 ns'
PULSE_SIGNAL_START = '600 ns'

# NAMES
EXP_NAME = 'ED'
CURVE_NAME = 'exp1'

#
#cycle_data_x = np.zeros( 2 )
#cycle_data_y = np.zeros( 2 )
#points = int( (END_FIELD - START_FIELD) / FIELD_STEP ) + 1
#data_x = np.zeros(points)
#data_y = np.zeros(points)
x_axis = np.linspace(START_FIELD, END_FIELD, num = points) 
###

file_handler = openfile.Saver_Opener()
ls335 = ls.Lakeshore_335()
mw = mwBridge.Mikran_X_band_MW_bridge_v2()
pb = pb_pro.PB_ESR_500_Pro()
bh15 = bh.BH_15()
a2012 = key.Keysight_2000_Xseries()
##dig4450 = spectrum.Spectrum_M4I_4450_X8()

def cleanup(*args):
    #dig4450.digitizer_stop()
    #dig4450.digitizer_close()
    pb.pulser_stop()
    file_handler.save_data(file_data, np.c_[x_axis, data_x, data_y], header = header, mode = 'w')
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)

bh15.magnet_setup(START_FIELD, FIELD_STEP)

a2012.oscilloscope_trigger_channel('Ext')
tb = a2012.oscilloscope_time_resolution()
a2012.oscilloscope_record_length(250)
a2012.oscilloscope_acquisition_type('Average')
a2012.oscilloscope_number_of_averages(AVERAGES)
###a2012.oscilloscope_stop()


#dig4450.digitizer_read_settings()
#dig4450.digitizer_number_of_averages(AVERAGES)
#tb = dig4450.digitizer_number_of_points() * int(  1000 / float( dig4450.digitizer_sample_rate().split(' ')[0] ) )
#tb = dig4450.digitizer_window()

pb.pulser_pulse(name ='P0', channel = 'MW', start = PULSE_1_START, length = PULSE_1_LENGTH, phase_list = ['+x', '-x'])
pb.pulser_pulse(name ='P1', channel = 'MW', start = PULSE_2_START, length = PULSE_2_LENGTH, phase_list = ['+x', '+x'])
pb.pulser_pulse(name ='P2', channel = 'TRIGGER', start = PULSE_SIGNAL_START, length = '100 ns')

pb.pulser_repetition_rate( REP_RATE )
pb.pulser_update()

# Data saving
#tb
header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + 'Echo Detected Spectrum\n' + \
            'Start Field: ' + str(START_FIELD) + ' G \n' + 'End Field: ' + str(END_FIELD) + ' G \n' + \
            'Field Step: ' + str(FIELD_STEP) + ' G \n' + str(mw.mw_bridge_att_prm()) + '\n' + str(mw.mw_bridge_att1_prd()) + '\n' + \
            str(mw.mw_bridge_synthesizer()) + '\n' + \
           'Repetition Rate: ' + str(pb.pulser_repetition_rate()) + '\n' + 'Number of Scans: ' + str(SCANS) + '\n' +\
           'Averages: ' + str(AVERAGES) + '\n' + 'Points: ' + str(points) + '\n' + 'Window: ' + str(str(t3034.oscilloscope_timebase()*1000)) + ' ns\n' + \
           'Temperature: ' + str(ls335.tc_temperature('B')) + ' K\n' +\
           'Pulse List: ' + '\n' + str(pb.pulser_pulse_list()) + 'Field (G), X (V*s), Y (V*s) '

file_data, file_param = file_handler.create_file_parameters('.param')
file_handler.save_header(file_param, header = header, mode = 'w')

for j in general.scans(SCANS):

    i = 0
    field = START_FIELD

    while field <= END_FIELD:

        bh15.magnet_field(field)

        # phase cycle
        k = 0
        while k < 2:

            pb.pulser_next_phase()

            #cycle_data_x[k], cycle_data_y[k] = dig4450.digitizer_get_curve( integral = True )
            t3034.oscilloscope_start_acquisition()
            cycle_data_x[k] = t3034.oscilloscope_area('CH1')
            cycle_data_y[k] = t3034.oscilloscope_area('CH2')

            k += 1

        # acquisition cycle [+, -]
        x, y = pb.pulser_acquisition_cycle(cycle_data_x, cycle_data_y, acq_cycle = ['+', '-'])
        data_x[i] = ( data_x[i] * (j - 1) + x ) / j
        data_y[i] = ( data_y[i] * (j - 1) + y ) / j

        process = general.plot_1d(EXP_NAME, x_axis, ( data_x, data_y ), xname = 'Field',\
            xscale = 'G', yname = 'Area', yscale = 'V*s', label = CURVE_NAME, pr = process, \
            text = 'Scan / Field: ' + str(j) + ' / '+ str(field))

        field = round( (FIELD_STEP + field), 3 )
        i += 1
        
        pb.pulser_pulse_reset()
    
    bh15.magnet_field(START_FIELD)


#dig4450.digitizer_stop()
#dig4450.digitizer_close()
pb.pulser_stop()

file_handler.save_data(file_data, np.c_[x_axis, data_x, data_y], header = header, mode = 'w')
