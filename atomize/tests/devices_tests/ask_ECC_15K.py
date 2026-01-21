import numpy as np
import atomize.general_modules.general_functions as general
import atomize.device_modules.ECC_15K as ecc


ecc15k = ecc.ECC_15K()

#bh15.magnet_setup(2000, 10)
general.message(ecc15k.synthetizer_name())

#ecc15k.synthetizer_state('On')
#general.message(ecc15k.synthetizer_state())

#ecc15k.synthetizer_frequency('9701 MHz')
#general.message(ecc15k.synthetizer_frequency())

#ecc15k.synthetizer_power(15)
#general.message(ecc15k.synthetizer_power())

#ecc15k.synthetizer_state('Off')
