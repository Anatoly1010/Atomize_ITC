import os
import runpy
import atomize.general_modules.general_functions as general
import nutations as nut

path_to_main = os.path.abspath( os.getcwd() )
path_to_folder = os.path.join( path_to_main, '..', '..', 'Experimental_Data/Kuznetsov/md3' )

POINTS = 100
STEP = 4
START_FREQ = 9520
START_FIELD = 3438.67

#filename = str( 9594 ) + ' MHz.csv'
#path = os.path.join( path_to_folder, filename )

#round(  , 3 )
#int( )
#nut.experiment( MW_freq = int(9544), MF = 3445, Averages = 70, path_to_file = os.path.join( path_to_folder, str( 9544 ) + ' MHz.csv' ) )
##nut.experiment( MW_freq = int(9594), MF = 3463, Averages = 120, path_to_file = os.path.join( path_to_folder, str( 9594 ) + ' MHz.csv' ) )

for i in range( POINTS ):
	FREQ = START_FREQ + STEP * i
	FIELD = START_FIELD + round( (STEP * i) / 2.804 , 3 )
    #filename = str( int( FREQ ) ) + ' MHz.csv'
	#path = os.path.join( path_to_folder, filename )

	nut.experiment( MW_freq = int(FREQ), MF = FIELD, Averages = 150, path_to_file = os.path.join( path_to_folder, str( int(FREQ) ) + ' MHz.csv' ) )
	#nut.experiment( MW_freq = int(FREQ), MF = FIELD, Averages = 120, path_to_file = path )
    # vivod chaga dobavit


	
 

