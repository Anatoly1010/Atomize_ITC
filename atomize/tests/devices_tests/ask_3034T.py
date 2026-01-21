import time
import numpy as np
import atomize.general_modules.general_functions as general
import atomize.device_modules.Keysight_2000_Xseries as key

xs = []
ys = []

t3034 = key.Keysight_2000_Xseries()

#t3034.oscilloscope_acquisition_type('Average')
#general.message(t3034.oscilloscope_acquisition_type())

#t3034.oscilloscope_timebase('10 us')

t3034.oscilloscope_record_length(4000)
general.message(t3034.oscilloscope_record_length())

#t3034.oscilloscope_horizontal_offset(4000)
#t3034.oscilloscope_trigger_delay('10 us')
#general.message(t3034.oscilloscope_timebase())

#t3034.oscilloscope_start_acquisition()
#x, y, i = t3034.oscilloscope_get_curve('CH2', integral = 'Both')

#general.plot_1d('1D', x, y, label = 'raw', xname = 'Delay', xscale = 's', yname = 'Area', yscale = 'V')
