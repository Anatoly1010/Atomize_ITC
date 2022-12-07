import time
import numpy as np
import atomize.general_modules.general_functions as general
import atomize.device_modules.Keysight_2000_Xseries as key

xs = []
ys = []

t3034 = key.Keysight_2000_Xseries()

#t3034.oscilloscope_horizontal_offset(4000)
#t3034.oscilloscope_trigger_delay('10 us')
general.message(t3034.oscilloscope_horizontal_offset('1 us'))