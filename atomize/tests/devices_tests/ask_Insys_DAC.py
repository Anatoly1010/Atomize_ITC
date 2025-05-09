import sys
import time
import signal
import numpy as np
import atomize.general_modules.general_functions as general
import atomize.device_modules.Insys_FPGA as pb_pro

def cleanup(*args):
    pb.pulser_close()
    #file_handler.save_data(file_data, np.c_[x_axis, data_x, data_y], header = header, mode = 'w')
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)

pb = pb_pro.Insys_FPGA()

POINTS = 40
PHASES_AWG = 4
SCANS = 1
DETECTION_WINDOW = 819.2
NUM_AVE = 50
DEC_COEF = 1

pb.digitizer_decimation(DEC_COEF)
#pb.awg_amplitude('CH0', '100', 'CH1', '100')

pb.pulser_pulse(name = 'P0', channel = 'TRIGGER_AWG' , start = '0 ns', length = '80 ns', delta_start='3.2 ns')
pb.pulser_pulse(name = 'P1', channel = 'TRIGGER_AWG' , start = '320 ns', length = '80 ns', delta_start='3.2 ns')
pb.pulser_pulse(name = 'P2', channel = 'TRIGGER' , start = '320 ns', length = str(DETECTION_WINDOW ) + ' ns', delta_start='6.4 ns')

pb.awg_pulse(name = 'P0', channel = 'CH0', func = 'SINE', frequency = '50 MHz', length = '80 ns', sigma = '16 ns', phase_list =  ['+x', '-x', '+x', '-x'])
pb.awg_pulse(name = 'P1', channel = 'CH0', func = 'SINE', frequency = '25 MHz', length = '80 ns', sigma = '16 ns', phase_list =  ['+x', '-x', '+x', '-x'])

data = np.zeros( ( 2, int( (DETECTION_WINDOW / 3.2) * 8 / DEC_COEF), int( POINTS ) ) )

a = time.time()
pb.pulser_repetition_rate('100 Hz')
pb.pulser_open()
pb.digitizer_number_of_averages(NUM_AVE)

for k in general.scans(SCANS):

    for j in range( int(POINTS) ):

        for i in range(PHASES_AWG):

            pb.awg_next_phase()
            #pb.pulser_visualize()
            pb.pulser_update()

            data[0], data[1] = pb.digitizer_get_curve( POINTS, PHASES_AWG, acq_cycle = ['+x', '-x', '+x', '-x'] )

            general.plot_2d('2D', data, start_step = ( (0, 0.4 * DEC_COEF), (0, 102.4) ), xname = 'Time',\
                            xscale = 'ns', yname = 'Delay', yscale = 'ns', zname = 'Intensity', zscale = 'mV')

        pb.pulser_shift()
        pb.awg_pulse_reset()

    pb.pulser_pulse_reset()

general.message( round(time.time() - a, 1) )
general.message( f'CALCULATED: {POINTS * PHASES_AWG * SCANS * NUM_AVE / 1000}' )

pb.pulser_close()

