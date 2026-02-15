import time
import numpy as np
import atomize.general_modules.general_functions as general
import atomize.device_modules.Insys_FPGA_MT  as pb_pro
#import atomize.device_modules.UNION_new as pb_pro

# A possible use in an experimental script
pb = pb_pro.Insys_FPGA_MT()
#pb.pulser_setup()
general.message("pulser_setup")
pb.pulser_pulse(name = 'P1', channel = 'MW' , start = '0 ns'  , length = '16 ns')
pb.pulser_pulse(name = 'P2', channel = 'MW' , start = '320 ns', length = '32 ns', delta_start = '96 ns') #, phase_list =  ['+x', '-x', '-y', '+y'])
#pb.awg_pulse(   name = 'P1', channel = 'CH0', func = 'SINE'   , frequency = ('0 MHz', '191 MHz'), phase = 0, length = '200 ns', sigma = '200 ns', start = '0 ns', delta_start = '2 ns', n = 10)
pb.awg_pulse(   name = 'P1', channel = 'CH0', func = 'SINE', frequency = '250 MHz', phase = 0, length = '3.2 ns', start = '0 ns'  ,                                          )#  phase_list =  ['+x', '-x', '-y', '+y','+y','+y','+y'])
pb.awg_pulse(   name = 'P3', channel = 'CH0', func = 'SINE' , frequency = '250 MHz', phase = 0, length = '3.2 ns', start = '300 ns'  , delta_start = '10 ns') #, phase_list =  ['+x', '-x', '-y', '+y','+y','+y','+y'])
#pb.awg_pulse(   name = 'P2', channel = 'CH0', func = 'SINE'   , frequency = '191 MHz', phase = 1, delta_phase = 0.1, length = '200 ns', sigma = '200 ns', start = '600 ns', delta_start = '10 ns', n = 10)
pb.awg_channel("CH0","CH1")
#pb.awg_channel("CH0")
pb.pulser_repetition_rate('200 Hz')
pb.awg_card_mode('Single Joined')
#pb.pulser_update()
#general.wait('100 ms')
#pb.pulser_visualize()



for j in range(100):     
    general.wait('100 ms')
    #if j%20 ==0:
        #pb.awg_next_phase()
    pb.pulser_shift()
    pb.main_update() 
    pb.awg_shift()


general.wait('5 s')





