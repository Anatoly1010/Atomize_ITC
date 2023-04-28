import sys
import signal
import datetime
import numpy as np
import atomize.general_modules.general_functions as general
import atomize.device_modules.PB_ESR_500_pro as pb_pro
import atomize.device_modules.Spectrum_M4I_6631_X8 as spectrum
import atomize.device_modules.Spectrum_M4I_4450_X8 as spectrum_dig
import atomize.device_modules.Mikran_X_band_MW_bridge as mwBridge
import atomize.device_modules.SR_PTC_10 as sr
import atomize.device_modules.BH_15 as bh
import atomize.general_modules.csv_opener_saver_tk_kinter as openfile
import atomize.math_modules.fft as fft_module

# initialization of the devices
file_handler = openfile.Saver_Opener()
ptc10 = sr.SR_PTC_10()
mw = mwBridge.Mikran_X_band_MW_bridge()
#pb = pb_pro.PB_ESR_500_Pro()
bh15 = bh.BH_15()
#dig4450 = spectrum_dig.Spectrum_M4I_4450_X8()
#awg = spectrum.Spectrum_M4I_6631_X8()
fft = fft_module.Fast_Fourier()

def cleanup(*args):
    dig4450.digitizer_stop()
    dig4450.digitizer_close()
    awg.awg_stop()
    awg.awg_close()
    pb.pulser_stop()
    #file_handler.save_data(file_data, data, header = header, mode = 'w')
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)

def experiment_no_wurst( MF = 3445, MW_freq = 9544, Averages = 120, FREQ = '50 MHz'):
    
    pb = pb_pro.PB_ESR_500_Pro()
    dig4450 = spectrum_dig.Spectrum_M4I_4450_X8()
    awg = spectrum.Spectrum_M4I_6631_X8()
    
    ### Experimental parameters
    POINTS = 1
    FIELD = MF
    AVERAGES = Averages
    SCANS = 1
    process = 'None'

    # PULSES
    REP_RATE = '1000 Hz'
    PULSE_1_LENGTH = '250 ns'
    PULSE_2_LENGTH = '20 ns'
    PULSE_3_LENGTH = '20 ns'
    # 398 ns is delay from AWG trigger 1.25 GHz
    # 494 ns is delay from AWG trigger 1.00 GHz
    PULSE_AWG_1_START = '0 ns'
    PULSE_AWG_2_START = '320 ns'
    PULSE_AWG_3_START = '620 ns'
    PULSE_DETECTION = '920 ns'
    PULSE_1_START = general.const_shift(PULSE_AWG_1_START, 494)
    PULSE_2_START = general.const_shift(PULSE_AWG_2_START, 494)
    PULSE_3_START = general.const_shift(PULSE_AWG_3_START, 494)
    PULSE_SIGNAL_START = general.const_shift(PULSE_DETECTION, 494)
    PHASES = 64

    SHAPE = 'SINE'
    SINE_FREQ = FREQ
    AMPL_2 =  16           # percent
    AMPL_3 =  32

    # NAMES

    # Setting pulser
    pb.pulser_pulse(name = 'P0', channel = 'TRIGGER_AWG', start = '0 ns', length = '30 ns')

    # For each awg_pulse; length should be longer than in awg_pulse
    #pb.pulser_pulse(name = 'P1', channel = 'AWG', start = PULSE_1_START, length = PULSE_1_LENGTH)
    pb.pulser_pulse(name = 'P2', channel = 'AWG', start = PULSE_2_START, length = PULSE_2_LENGTH)
    pb.pulser_pulse(name = 'P3', channel = 'AWG', start = PULSE_3_START, length = PULSE_3_LENGTH)

    pb.pulser_pulse(name = 'P4', channel = 'TRIGGER', start = PULSE_SIGNAL_START, length = '100 ns')
    #awg.awg_pulse(name = 'P5', channel = 'CH0', func = SHAPE, frequency = FREQ, phase = 0, \
    #            length = PULSE_1_LENGTH, sigma = PULSE_1_LENGTH, start = PULSE_AWG_1_START, phase_list = ['+x','+x','-x','-x'], length_increment = str(STEP) + ' ns')
    awg.awg_pulse(name = 'P6', channel = 'CH0', func = SHAPE, frequency = FREQ, phase = 0, \
                length = PULSE_2_LENGTH, sigma = PULSE_2_LENGTH, start = PULSE_AWG_2_START, phase_list = \
                              ['+x','+x','+x','+x','-x','-x','-x','-x','+y','+y','+y','+y','-y','-y','-y','-y', \
                              '+x','+x','+x','+x','-x','-x','-x','-x','+y','+y','+y','+y','-y','-y','-y','-y', \
                              '+x','+x','+x','+x','-x','-x','-x','-x','+y','+y','+y','+y','-y','-y','-y','-y', \
                              '+x','+x','+x','+x','-x','-x','-x','-x','+y','+y','+y','+y','-y','-y','-y','-y'], \
                              d_coef = 100/AMPL_2 )
    awg.awg_pulse(name = 'P7', channel = 'CH0', func = SHAPE, frequency = FREQ, phase = 0, \
                length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = PULSE_AWG_3_START, phase_list = \
                              ['+x','-x','+y','-y','+x','-x','+y','-y','+x','-x','+y','-y','+x','-x','+y','-y', \
                              '+x','-x','+y','-y','+x','-x','+y','-y','+x','-x','+y','-y','+x','-x','+y','-y', \
                              '+x','-x','+y','-y','+x','-x','+y','-y','+x','-x','+y','-y','+x','-x','+y','-y', \
                              '+x','-x','+y','-y','+x','-x','+y','-y','+x','-x','+y','-y','+x','-x','+y','-y'], \
                              d_coef = 100/AMPL_3 )

    pb.pulser_repetition_rate( REP_RATE )
    pb.pulser_update()

    awg.awg_sample_rate(1000)
    awg.awg_clock_mode('External')
    awg.awg_reference_clock(100)
    awg.awg_channel('CH0', 'CH1')
    awg.awg_card_mode('Single Joined')
    awg.awg_setup()

    # Setting magnetic field
    bh15.magnet_setup(FIELD, 1)
    bh15.magnet_field(FIELD)

    # Setting MW frequency
    mw.mw_bridge_synthesizer(MW_freq)

    dig4450.digitizer_read_settings()
    dig4450.digitizer_number_of_averages(AVERAGES)
    time_res = int( 1000 / int(dig4450.digitizer_sample_rate().split(' ')[0]) )
    # a full oscillogram will be transfered
    wind = dig4450.digitizer_number_of_points()
    cycle_data_x = np.zeros( (PHASES, int(wind)) )
    cycle_data_y = np.zeros( (PHASES, int(wind)) )
    data = np.zeros( (2, int(wind), POINTS) )
    echo_intensity = 0

    # Data acquisition
    for j in general.scans(SCANS):

        for i in range(POINTS):

            # phase cycle
            k = 0
            pb.pulser_update()
            while k < PHASES:

                awg.awg_next_phase()
                x_axis, cycle_data_x[k], cycle_data_y[k] = dig4450.digitizer_get_curve()

                awg.awg_stop()
                k += 1
            
            # acquisition cycle
            x, y = pb.pulser_acquisition_cycle(cycle_data_x, cycle_data_y, acq_cycle = \
                         ['+','+','-','-','-','-','+','+','-i','-i','+i','+i','+i','+i','-i','-i', \
                         '+','+','-','-','-','-','+','+','-i','-i','+i','+i','+i','+i','-i','-i', \
                         '+','+','-','-','-','-','+','+','-i','-i','+i','+i','+i','+i','-i','-i', \
                         '+','+','-','-','-','-','+','+','-i','-i','+i','+i','+i','+i','-i','-i'])
            
            data[0, :, i] = ( data[0, :, i] * (j - 1) + x ) / j
            data[1, :, i] = ( data[1, :, i] * (j - 1) + y ) / j

            freq_axis, abs_values = fft.fft(x_axis, data[0, :, i], data[1, :, i], 2)
            m_ind = np.argmax( abs_values )

            echo_intensity = ( echo_intensity + np.sum( abs_values[m_ind-24:m_ind+25] ) / 50 - np.sum( abs_values[0:39] ) / 40 ) / 2

        #awg.awg_pulse_reset()
        #pb.pulser_pulse_reset()

    dig4450.digitizer_stop()
    dig4450.digitizer_close()
    awg.awg_stop()
    awg.awg_close()
    pb.pulser_stop()

    return echo_intensity

def experiment_wurst( MF = 3445, MW_freq = 9544, Averages = 120, FREQ = '50 MHz', wurst_center = '40 MHz'):
    
    pb = pb_pro.PB_ESR_500_Pro()
    dig4450 = spectrum_dig.Spectrum_M4I_4450_X8()
    awg = spectrum.Spectrum_M4I_6631_X8()
    
    ### Experimental parameters
    POINTS = 1
    FIELD = MF
    AVERAGES = Averages
    SCANS = 1
    process = 'None'

    # PULSES
    REP_RATE = '1000 Hz'
    PULSE_1_LENGTH = '250 ns'
    PULSE_2_LENGTH = '20 ns'
    PULSE_3_LENGTH = '20 ns'
    # 398 ns is delay from AWG trigger 1.25 GHz
    # 494 ns is delay from AWG trigger 1.00 GHz
    PULSE_AWG_1_START = '0 ns'
    PULSE_AWG_2_START = '320 ns'
    PULSE_AWG_3_START = '620 ns'
    PULSE_DETECTION = '920 ns'
    PULSE_1_START = general.const_shift(PULSE_AWG_1_START, 494)
    PULSE_2_START = general.const_shift(PULSE_AWG_2_START, 494)
    PULSE_3_START = general.const_shift(PULSE_AWG_3_START, 494)
    PULSE_SIGNAL_START = general.const_shift(PULSE_DETECTION, 494)
    PHASES = 64

    SHAPE = 'SINE'
    SINE_FREQ = FREQ
    AMPL_2 =  16            # percent
    AMPL_3 =  32
    WURST_CENTER = wurst_center
    WURST_SWEEP = '300 MHz'
    # NAMES

    # Setting pulser
    pb.pulser_pulse(name = 'P0', channel = 'TRIGGER_AWG', start = '0 ns', length = '30 ns')

    # For each awg_pulse; length should be longer than in awg_pulse
    pb.pulser_pulse(name = 'P1', channel = 'AWG', start = PULSE_1_START, length = PULSE_1_LENGTH)
    pb.pulser_pulse(name = 'P2', channel = 'AWG', start = PULSE_2_START, length = PULSE_2_LENGTH)
    pb.pulser_pulse(name = 'P3', channel = 'AWG', start = PULSE_3_START, length = PULSE_3_LENGTH)

    pb.pulser_pulse(name = 'P4', channel = 'TRIGGER', start = PULSE_SIGNAL_START, length = '100 ns')
    awg.awg_pulse(name = 'P4', channel = 'CH0', func = 'WURST', frequency = (WURST_CENTER, WURST_SWEEP), phase = 0, \
                length = PULSE_1_LENGTH, sigma = PULSE_1_LENGTH, start = PULSE_AWG_1_START, \
                phase_list = ['+x','+x','+x','+x','+x','+x','+x','+x','+x','+x','+x','+x','+x','+x','+x','+x', \
                              '-x','-x','-x','-x','-x','-x','-x','-x','-x','-x','-x','-x','-x','-x','-x','-x', \
                              '+y','+y','+y','+y','+y','+y','+y','+y','+y','+y','+y','+y','+y','+y','+y','+y', \
                              '-y','-y','-y','-y','-y','-y','-y','-y','-y','-y','-y','-y','-y','-y','-y','-y'], \
                              n = 30, b = 0.02) #, d_coef = 100/25
    awg.awg_pulse(name = 'P6', channel = 'CH0', func = SHAPE, frequency = FREQ, phase = 0, \
                length = PULSE_2_LENGTH, sigma = PULSE_2_LENGTH, start = PULSE_AWG_2_START, phase_list = \
                              ['+x','+x','+x','+x','-x','-x','-x','-x','+y','+y','+y','+y','-y','-y','-y','-y', \
                              '+x','+x','+x','+x','-x','-x','-x','-x','+y','+y','+y','+y','-y','-y','-y','-y', \
                              '+x','+x','+x','+x','-x','-x','-x','-x','+y','+y','+y','+y','-y','-y','-y','-y', \
                              '+x','+x','+x','+x','-x','-x','-x','-x','+y','+y','+y','+y','-y','-y','-y','-y'], \
                              d_coef = 100/AMPL_2 )
    awg.awg_pulse(name = 'P7', channel = 'CH0', func = SHAPE, frequency = FREQ, phase = 0, \
                length = PULSE_3_LENGTH, sigma = PULSE_3_LENGTH, start = PULSE_AWG_3_START, phase_list = \
                              ['+x','-x','+y','-y','+x','-x','+y','-y','+x','-x','+y','-y','+x','-x','+y','-y', \
                              '+x','-x','+y','-y','+x','-x','+y','-y','+x','-x','+y','-y','+x','-x','+y','-y', \
                              '+x','-x','+y','-y','+x','-x','+y','-y','+x','-x','+y','-y','+x','-x','+y','-y', \
                              '+x','-x','+y','-y','+x','-x','+y','-y','+x','-x','+y','-y','+x','-x','+y','-y'], \
                              d_coef = 100/AMPL_3 )

    pb.pulser_repetition_rate( REP_RATE )
    pb.pulser_update()

    awg.awg_sample_rate(1000)
    awg.awg_clock_mode('External')
    awg.awg_reference_clock(100)
    awg.awg_channel('CH0', 'CH1')
    awg.awg_card_mode('Single Joined')
    awg.awg_setup()

    # Setting magnetic field
    bh15.magnet_setup(FIELD, 1)
    bh15.magnet_field(FIELD)

    # Setting MW frequency
    mw.mw_bridge_synthesizer(MW_freq)

    dig4450.digitizer_read_settings()
    dig4450.digitizer_number_of_averages(AVERAGES)
    time_res = int( 1000 / int(dig4450.digitizer_sample_rate().split(' ')[0]) )
    # a full oscillogram will be transfered
    wind = dig4450.digitizer_number_of_points()
    cycle_data_x = np.zeros( (PHASES, int(wind)) )
    cycle_data_y = np.zeros( (PHASES, int(wind)) )
    data = np.zeros( (2, int(wind), POINTS) )
    echo_intensity = 0

    # Data acquisition
    for j in general.scans(SCANS):

        for i in range(POINTS):

            # phase cycle
            k = 0
            pb.pulser_update()
            while k < PHASES:

                awg.awg_next_phase()
                x_axis, cycle_data_x[k], cycle_data_y[k] = dig4450.digitizer_get_curve()

                awg.awg_stop()
                k += 1
            
            # acquisition cycle
            x, y = pb.pulser_acquisition_cycle(cycle_data_x, cycle_data_y, acq_cycle = \
                         ['+','+','-','-','-','-','+','+','-i','-i','+i','+i','+i','+i','-i','-i', \
                         '+','+','-','-','-','-','+','+','-i','-i','+i','+i','+i','+i','-i','-i', \
                         '+','+','-','-','-','-','+','+','-i','-i','+i','+i','+i','+i','-i','-i', \
                         '+','+','-','-','-','-','+','+','-i','-i','+i','+i','+i','+i','-i','-i'])
            
            data[0, :, i] = ( data[0, :, i] * (j - 1) + x ) / j
            data[1, :, i] = ( data[1, :, i] * (j - 1) + y ) / j

            freq_axis, abs_values = fft.fft(x_axis, data[0, :, i], data[1, :, i], 2)
            m_ind = np.argmax( abs_values )

            echo_intensity_wurst = ( echo_intensity + np.sum( abs_values[m_ind-24:m_ind+25] ) / 50 - np.sum( abs_values[0:39] ) / 40 ) / 2

        #awg.awg_pulse_reset()
        #pb.pulser_pulse_reset()

    dig4450.digitizer_stop()
    dig4450.digitizer_close()
    awg.awg_stop()
    awg.awg_close()
    pb.pulser_stop()

    return echo_intensity_wurst

def experiment_double_wurst( MF = 3445, Averages = 120):
    
    pb = pb_pro.PB_ESR_500_Pro()
    dig4450 = spectrum_dig.Spectrum_M4I_4450_X8()
    awg = spectrum.Spectrum_M4I_6631_X8()
    
    ### Experimental parameters
    POINTS = 1
    FIELD = MF
    AVERAGES = Averages
    SCANS = 1
    process = 'None'

    # PULSES
    REP_RATE = '1000 Hz'
    PULSE_1_LENGTH = '200 ns'
    PULSE_2_LENGTH = '200 ns'
    # 398 ns is delay from AWG trigger 1.25 GHz
    # 494 ns is delay from AWG trigger 1.00 GHz
    PULSE_AWG_1_START = '0 ns'
    PULSE_AWG_2_START = '400 ns'
    PULSE_DETECTION = '800 ns'
    PULSE_1_START = general.const_shift(PULSE_AWG_1_START, 494)
    PULSE_2_START = general.const_shift(PULSE_AWG_2_START, 494)
    PULSE_SIGNAL_START = general.const_shift(PULSE_DETECTION, 494)
    PHASES = 16

    SHAPE = 'WURST'
    CENTER = '100 MHz'
    SWEEP = '300 MHz'
    AMPL_1 =  15            # percent
    AMPL_2 = 100

    # NAMES

    # Setting pulser
    pb.pulser_pulse(name = 'P0', channel = 'TRIGGER_AWG', start = '0 ns', length = '30 ns')

    # For each awg_pulse; length should be longer than in awg_pulse
    pb.pulser_pulse(name = 'P1', channel = 'AWG', start = PULSE_1_START, length = PULSE_1_LENGTH)
    pb.pulser_pulse(name = 'P2', channel = 'AWG', start = PULSE_2_START, length = PULSE_2_LENGTH)

    pb.pulser_pulse(name = 'P4', channel = 'TRIGGER', start = PULSE_SIGNAL_START, length = '100 ns')
    awg.awg_pulse(name = 'P5', channel = 'CH0', func = SHAPE, frequency = (CENTER, SWEEP), phase = 0, \
                length = PULSE_1_LENGTH, sigma = PULSE_1_LENGTH, start = PULSE_AWG_1_START, \
                phase_list = ['+x','+x','+x','+x','-x','-x','-x','-x','+y','+y','+y','+y','-y','-y','-y','-y'],
                d_coef = 100/AMPL_1)
    awg.awg_pulse(name = 'P6', channel = 'CH0', func = SHAPE, frequency = (CENTER, SWEEP), phase = 0, \
                length = PULSE_2_LENGTH, sigma = PULSE_2_LENGTH, start = PULSE_AWG_2_START, \
                phase_list = ['+x','-x','+y','-y','+x','-x','+y','-y','+x','-x','+y','-y','+x','-x','+y','-y'],
                d_coef = 100/AMPL_2 )

    pb.pulser_repetition_rate( REP_RATE )
    pb.pulser_update()

    awg.awg_sample_rate(1000)
    awg.awg_clock_mode('External')
    awg.awg_reference_clock(100)
    awg.awg_channel('CH0', 'CH1')
    awg.awg_card_mode('Single Joined')
    awg.awg_setup()

    # Setting magnetic field
    bh15.magnet_setup(FIELD, 1)
    bh15.magnet_field(FIELD)

    # Setting MW frequency
    #mw.mw_bridge_synthesizer(MW_freq)

    dig4450.digitizer_read_settings()
    dig4450.digitizer_number_of_averages(AVERAGES)
    time_res = int( 1000 / int(dig4450.digitizer_sample_rate().split(' ')[0]) )
    # a full oscillogram will be transfered
    wind = dig4450.digitizer_number_of_points()
    cycle_data_x = np.zeros( (PHASES, int(wind)) )
    cycle_data_y = np.zeros( (PHASES, int(wind)) )
    data = np.zeros( (2, int(wind), POINTS) )
    max_intensity = 0

    # Data acquisition
    for j in general.scans(SCANS):

        for i in range(POINTS):

            # phase cycle
            k = 0
            pb.pulser_update()
            while k < PHASES:

                awg.awg_next_phase()
                x_axis, cycle_data_x[k], cycle_data_y[k] = dig4450.digitizer_get_curve()

                awg.awg_stop()
                k += 1
            
            # acquisition cycle
            x, y = pb.pulser_acquisition_cycle(cycle_data_x, cycle_data_y, acq_cycle = \
                        ['+', '+', '-', '-', '-', '-', '+', '+', '-i', '-i', '+i', '+i', '+i', '+i', '-i', '-i'] )
            
            data[0, :, i] = ( data[0, :, i] * (j - 1) + x ) / j
            data[1, :, i] = ( data[1, :, i] * (j - 1) + y ) / j

            freq_axis, abs_values = fft.fft(x_axis, data[0, :, i], data[1, :, i], 2)
            m_ind = np.argmax( abs_values )

            max_intensity = ( max_intensity + np.sum( abs_values[m_ind-5:m_ind+6] ) / 10 ) / 2

        #awg.awg_pulse_reset()
        #pb.pulser_pulse_reset()

    dig4450.digitizer_stop()
    dig4450.digitizer_close()
    awg.awg_stop()
    awg.awg_close()
    pb.pulser_stop()

    return max_intensity