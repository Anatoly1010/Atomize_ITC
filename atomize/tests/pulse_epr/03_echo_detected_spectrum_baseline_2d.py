import sys
import signal
import datetime
import numpy as np
import atomize.general_modules.general_functions as general
import atomize.device_modules.PB_ESR_500_pro as pb_pro
###import atomize.device_modules.Keysight_3000_Xseries as key
import atomize.device_modules.Spectrum_M4I_4450_X8 as spectrum
import atomize.device_modules.Mikran_X_band_MW_bridge as mwBridge
import atomize.device_modules.BH_15 as bh
import atomize.device_modules.SR_PTC_10 as sr
import atomize.general_modules.csv_opener_saver as openfile

### Experimental parameters
START_FIELD = 3380
END_FIELD = 3530
FIELD_STEP = 1.
TIME_STEP = 32 # in ns
TIME_POINTS = 20
AVERAGES = 5
SCANS = 1
process = 'None'

# PULSES
REP_RATE = '200 Hz'
PULSE_1_LENGTH = '16 ns'
PULSE_2_LENGTH = '32 ns'
PULSE_1_START = '0 ns'
PULSE_2_START = '300 ns'
PULSE_SIGNAL_START = '600 ns'

# NAMES
EXP_NAME = 'ED 2D'
CURVE_NAME = 'exp1'

#
cycle_data_x = np.zeros( 2 )
cycle_data_y = np.zeros( 2 )
points = int( (END_FIELD - START_FIELD) / FIELD_STEP ) + 1
data = np.zeros( (2, points, TIME_POINTS) )
###

file_handler = openfile.Saver_Opener()
ptc10 = sr.SR_PTC_10()
mw = mwBridge.Mikran_X_band_MW_bridge()
pb = pb_pro.PB_ESR_500_Pro()
bh15 = bh.BH_15()
###t3034 = key.Keysight_3000_Xseries()
dig4450 = spectrum.Spectrum_M4I_4450_X8()

def cleanup(*args):
    dig4450.digitizer_stop()
    dig4450.digitizer_close()
    pb.pulser_stop()
    file_handler.save_data(file_data, data, header = header, mode = 'w')
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)
bh15.magnet_setup(START_FIELD, FIELD_STEP)

dig4450.digitizer_read_settings()
dig4450.digitizer_number_of_averages(AVERAGES)
#tb = dig4450.digitizer_number_of_points() * int(  1000 / float( dig4450.digitizer_sample_rate().split(' ')[0] ) )
tb = dig4450.digitizer_window()

pb.pulser_pulse(name ='P0', channel = 'MW', start = PULSE_1_START, length = PULSE_1_LENGTH, phase_list = ['+x', '-x'])
pb.pulser_pulse(name ='P1', channel = 'MW', start = PULSE_2_START, length = PULSE_2_LENGTH, phase_list = ['+x', '+x'], delta_start = str(int(TIME_STEP/2)) + ' ns')
pb.pulser_pulse(name ='P2', channel = 'TRIGGER', start = PULSE_SIGNAL_START, length = '100 ns', delta_start = str(TIME_STEP) + ' ns')

pb.pulser_repetition_rate( REP_RATE )
pb.pulser_update()

# Data saving
header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + 'Echo Detected Spectrum 2D; Phase Cycling\n' + \
            'Start Field: ' + str(START_FIELD) + ' G \n' + 'End Field: ' + str(END_FIELD) + ' G \n' + \
            'Field Step: ' + str(FIELD_STEP) + ' G \n' + str(mw.mw_bridge_att_prm()) + '\n' + str(mw.mw_bridge_att1_prd()) + '\n' + \
            str(mw.mw_bridge_synthesizer()) + '\n' + \
           'Repetition Rate: ' + str(pb.pulser_repetition_rate()) + '\n' + 'Number of Scans: ' + str(SCANS) + '\n' +\
           'Averages: ' + str(AVERAGES) + '\n' + 'Field Points: ' + str(points) + '\n' + 'Time Points: ' + str(TIME_POINTS) + '\n' + \
            'Window: ' + str(tb) + ' ns\n' + \
           'Horizontal Resolution: ' + str(FIELD_STEP) + ' G\n' + 'Vertical Resolution: ' + str(TIME_STEP) + ' ns\n' + \
           'Temperature: ' + str(ptc10.tc_temperature('2A')) + ' K\n' +\
           'Pulse List: ' + '\n' + str(pb.pulser_pulse_list()) + '2D Data'

file_data, file_param = file_handler.create_file_parameters('.param')
file_handler.save_header(file_param, header = header, mode = 'w')

for j in general.scans(SCANS):
    
    l = 0
    for l in range(TIME_POINTS):

        i = 0
        field = START_FIELD
        while field <= END_FIELD:

            bh15.magnet_field(field)
            # phase cycle
            k = 0
            while k < 2:

                pb.pulser_next_phase()
                cycle_data_x[k], cycle_data_y[k] = dig4450.digitizer_get_curve( integral = True )
                k += 1

            # acquisition cycle [+, -]
            x, y = pb.pulser_acquisition_cycle(cycle_data_x, cycle_data_y, acq_cycle = ['+', '-'])
            data[0, i, l] = ( data[0, i, l] * (j - 1) + x ) / j
            data[1, i, l] = ( data[1, i, l] * (j - 1) + y ) / j

            process = general.plot_2d(EXP_NAME, data, start_step = ( (START_FIELD, FIELD_STEP), (0, TIME_STEP) ), xname = 'Field',\
                xscale = 'G', yname = 'Delay', yscale = 'ns', zname = 'I', zscale = 'V', pr = process, \
                text = 'Scan / Time: ' + str(j) + ' / '+ str(l*TIME_STEP) + ' / '+ str(i*FIELD_STEP) )

            field = round( (FIELD_STEP + field), 3 )
            i += 1
            
            pb.pulser_pulse_reset()

            d2 = 0
            while d2 < (l + 1):
                pb.pulser_shift()
                d2 += 1

        bh15.magnet_field(START_FIELD)

    pb.pulser_pulse_reset()

dig4450.digitizer_stop()
dig4450.digitizer_close()
pb.pulser_stop()

file_handler.save_data(file_data, data, header = header, mode = 'w')
