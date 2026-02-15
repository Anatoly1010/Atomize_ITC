import time
import numpy as np
import atomize.general_modules.general_functions as general
import atomize.device_modules.Planar_C2220 as c2220



C2220 = c2220.Planar_C2220()

POINTS = 20000
CENTER = '9634.0 MHz'
SPAN = '10000 kHz'

C2220.vector_analyzer_source_power(0, source = 1)
#general.message( C2220.vector_analyzer_source_power(source = 2) )

C2220.vector_analyzer_frequency_center(CENTER, channel = 1)
#general.message( C2220.vector_analyzer_frequency_center(channel = 1) )

C2220.vector_analyzer_frequency_span(SPAN, channel = 1)
#general.message( C2220.vector_analyzer_frequency_span(channel = 1) )

C2220.vector_analyzer_points(POINTS, channel = 1)
#general.message( C2220.vector_analyzer_points(channel = 1) )

POINTS = C2220.vector_analyzer_points(channel = 1)

C2220.vector_analyzer_if_bandwith('5000 Hz', channel = 1)
#general.message( C2220.vector_analyzer_if_bandwith(channel = 1) )

xs = np.zeros( POINTS )
y1 = np.zeros( POINTS )
y2 = np.zeros( POINTS )
ts = []
ss = []
sr = []
srr = []

C2220.vector_analyzer_trigger_source('BUS')
#general.message( C2220.vector_analyzer_trigger_source() )

C2220.vector_analyzer_trigger_mode('SINGLE', channel = 1)
C2220.vector_analyzer_send_trigger()
#general.message( C2220.vector_analyzer_trigger_mode(channel = 1) )

#general.message( C2220.vector_analyzer_get_freq_data(channel = 1) )
#general.message( C2220.vector_analyzer_get_data(s = 'S11', type = 'AP', channel = 1) )

#general.message( C2220.vector_analyzer_query("SENSe1:SWEep:CW:TIME?") )

# wait to measure
#general.wait('500 ms')
xs = C2220.vector_analyzer_get_freq_data(channel = 1)
y1, y2 = C2220.vector_analyzer_get_data(s = 'S11', type = 'AP', channel = 1) #'S11'

general.plot_1d('Ampl', xs, y1, xname = 'Freq', xscale = 'MHz', yname = 'Ampl', yscale = 'dB')
#general.plot_1d('Phase', xs, y2, xname = 'Freq', xscale = 'MHz', yname = 'Ph', yscale = 'deg')
cent = f'{xs[np.argmin(y1)]} MHz'
#general.wait('2000 ms')

POINTS = 9 #10 #3
SPAN = '3 kHz' #'4 kHz' #'0 kHz'
C2220.vector_analyzer_if_bandwith('50000 Hz', channel = 1)

C2220.vector_analyzer_points(POINTS, channel = 1)
C2220.vector_analyzer_frequency_span(SPAN, channel = 1)

C2220.vector_analyzer_frequency_center(cent, channel = 1)

st = time.time()

#for i in general.to_infinity():
for i in range(100):
    
    ###
    ###C2220.vector_analyzer_frequency_center(cent, channel = 1)
    C2220.vector_analyzer_points(20000, channel = 1)
    C2220.vector_analyzer_frequency_span('0 kHz', channel = 1)
    meas_time = np.array(C2220.vector_analyzer_query("SENSe1:SWEep:CW:TIME?")).astype(np.float64)
    general.message(meas_time)
    ###
    C2220.vector_analyzer_trigger_mode('SINGLE', channel = 1)
    C2220.vector_analyzer_send_trigger()

    ###
    ###xs = C2220.vector_analyzer_get_freq_data(channel = 1)
    ###
    y1, y2 = C2220.vector_analyzer_get_data(s = 'S11', type = 'AP', channel = 1) #'S11'

    #general.plot_1d('Ampl', xs, y1, xname = 'Freq', xscale = 'MHz', yname = 'Ampl', yscale = 'V')
    general.plot_1d('Ampl', meas_time / 20000 * np.arange(20000), y1, xname = 'Freq', xscale = 'Hz', yname = 'Ampl', yscale = 'V')
    #general.plot_1d('Phase', xs, y2, xname = 'Freq', xscale = 'MHz', yname = 'Ph', yscale = 'deg')

    cent = f'{xs[np.argmin(y1)]} MHz'
    ts.append( time.time() - st )
    ss.append( float( cent.split(" ")[0] ) )
    #sr.append( (y1[np.argmin(y1)] + y1[np.argmin(y1)+1] + y1[np.argmin(y1)-1]) / 3 )
    sr.append( np.mean( y1 ) )
    #srr.append( (y1[np.argmin(y1)] + y1[np.argmin(y1)+1] + y1[np.argmin(y1)-1]) / 3 / float( cent.split(" ")[0]  ) )
    #srr.append( (y2[np.argmin(y1)] + y2[np.argmin(y1)+1] + y2[np.argmin(y1)-1]) / 3 )

    #general.plot_1d('S_freq', ts, ss, xname = 'Time', xscale = 's', yname = 'Freq', yscale = 'MHz')
    #general.plot_1d('S_ref', ts, sr, xname = 'Time', xscale = 's', yname = 'Level', yscale = 'dB')
    #general.plot_1d('S_ph', ts, srr, xname = 'Time', xscale = 's', yname = 'Phase', yscale = 'deg')


    #if i % 30 == 0:
    #    ts.append( time.time() - st )
    #    ss.append(float( cent.split(" ")[0] ) )
    #    sr.append( np.min(y1) )

    #    general.plot_1d('S_freq', ts, ss, xname = 'Time', xscale = 's', yname = 'Freq', yscale = 'MHz')
    #    general.plot_1d('S_ref', ts, sr, xname = 'Time', xscale = 's', yname = 'Level', yscale = 'dB')

