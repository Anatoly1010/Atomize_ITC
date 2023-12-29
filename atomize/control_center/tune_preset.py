#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import random
import datetime
import socket
import numpy as np
from multiprocessing import Process, Pipe
from PyQt6 import QtWidgets, uic
from PyQt6.QtWidgets import QWidget 
from PyQt6.QtGui import QIcon

class MainWindow(QtWidgets.QMainWindow):
    """
    A main window class
    """
    def __init__(self, *args, **kwargs):
        """
        A function for connecting actions and creating a main window
        """
        super(MainWindow, self).__init__(*args, **kwargs)
        
        #self.destroyed.connect(lambda: self._on_destroyed())         # connect some actions to exit
        # Load the UI Page
        path_to_main = os.path.dirname(os.path.abspath(__file__))
        gui_path = os.path.join(path_to_main,'gui/tune_main_window.ui')
        icon_path = os.path.join(path_to_main, 'gui/icon_temp.png')
        self.setWindowIcon( QIcon(icon_path) )

        uic.loadUi(gui_path, self)                        # Design file

        self.design()

        """
        Create a process to interact with an experimental script that will run on a different thread.
        We need a different thread here, since PyQt GUI applications have a main thread of execution 
        that runs the event loop and GUI. If you launch a long-running task in this thread, then your GUI
        will freeze until the task terminates. During that time, the user won’t be able to interact with 
        the application
        """
        self.worker = Worker()

    def design(self):

        # Connection of different action to different Menus and Buttons
        self.button_start.clicked.connect(self.start)
        self.button_start.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_off.clicked.connect(self.turn_off)
        self.button_off.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold;  }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_stop.clicked.connect(self.stop)
        self.button_stop.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")

        # text labels
        self.label.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_4.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_5.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_6.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_7.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_8.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_11.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_12.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # text edits
        self.text_edit_exp_name.setStyleSheet("QTextEdit { color : rgb(211, 194, 78) ; }") # rgb(193, 202, 227)
        self.cur_exp_name = self.text_edit_exp_name.toPlainText()
        self.text_edit_exp_name.textChanged.connect(self.exp_name)

        # Spinboxes        
        self.box_length.valueChanged.connect(self.pulse_length)
        self.box_length.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.cur_length = int( self.box_length.value() )
        self.box_length.lineEdit().setReadOnly( True )

        self.box_rep_rate.valueChanged.connect(self.rep_rate)
        self.box_rep_rate.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.cur_rep_rate = int( self.box_rep_rate.value() )
        
        self.box_st_freq.valueChanged.connect(self.start_freq)
        self.box_st_freq.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.cur_st_freq = int( self.box_st_freq.value() )

        self.box_end_freq.valueChanged.connect(self.end_freq)
        self.box_end_freq.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.cur_end_freq = int( self.box_end_freq.value() )

        self.box_step_freq.valueChanged.connect(self.step_freq)
        self.box_step_freq.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.cur_step_freq = int( self.box_step_freq.value() )
        
        self.box_scan.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.box_scan.valueChanged.connect(self.scan)
        self.box_scan.lineEdit().setReadOnly( True )
        self.cur_scan = int( self.box_scan.value() )
        
        self.box_averag.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.box_averag.valueChanged.connect(self.averages)
        self.cur_averages = int( self.box_averag.value() )

    def _on_destroyed(self):
        """
        A function to do some actions when the main window is closing.
        """
        try:
            self.parent_conn.send('exit')
        except BrokenPipeError:
            self.message('Experimental script is not running')
        except AttributeError:
            self.message('Experimental script is not running')
        self.exp_process.join()

    def quit(self):
        """
        A function to quit the programm
        """
        self._on_destroyed()
        sys.exit()

    def exp_name(self):
        self.cur_exp_name = self.text_edit_exp_name.toPlainText()
        #print( self.cur_exp_name )

    def delta(self):
        self.cur_delta = int( self.box_delta.value() )
        #print(self.cur_end_field)

    def pulse_length(self):
        self.cur_length = int( self.box_length.value() )
        #print(self.cur_start_field)

    def rep_rate(self):
        self.cur_rep_rate = int( self.box_rep_rate.value() )
        #print(self.cur_start_field)

    def averages(self):
        self.cur_averages = int( self.box_averag.value() )
        #print(self.cur_start_field)

    def start_freq(self):
        self.cur_st_freq = int( self.box_st_freq.value() )
        #print(self.cur_lock_ampl)

    def end_freq(self):
        self.cur_end_freq = int( self.box_end_freq.value() )
        #print(self.cur_lock_ampl)

    def step_freq(self):
        self.cur_step_freq = int( self.box_step_freq.value() )
        #print(self.cur_lock_ampl)

    def scan(self):
        """
        A function to send a number of scans
        """
        self.cur_scan = int( self.box_scan.value() )
        #print(self.cur_scan)
        try:
            self.parent_conn.send( 'SC' + str( self.cur_scan ) )
        except AttributeError:
            self.message('Experimental script is not running')
   
    def turn_off(self):
        """
         A function to turn off a program.
        """
        try:
            self.parent_conn.send('exit')
            self.exp_process.join()
        except AttributeError:
            self.message('Experimental script is not running')
            sys.exit()

        sys.exit()

    def stop(self):
        """
        A function to stop script
        """
        try:
            self.parent_conn.send( 'exit' )
            self.exp_process.join()
        except AttributeError:
            self.message('Experimental script is not running')
   
    def start(self):
        """
        Button Start; Run function script(pipe_addres, four parameters of the experimental script)
        from Worker class in a different thread
        Create a Pipe for interaction with this thread
        self.param_i are used as parameters for script function
        """
        # prevent running two processes
        try:
            if self.exp_process.is_alive() == True:
                return
        except AttributeError:
            pass

        if self.cur_st_freq >= self.cur_end_freq:
            self.cur_st_freq, self.cur_end_freq = self.cur_end_freq, self.cur_st_freq

            self.box_end_freq.setValue( self.cur_end_freq )
            self.box_st_freq.setValue( self.cur_st_freq )

        self.parent_conn, self.child_conn = Pipe()
        # a process for running function script 
        # sending parameters for initial initialization
        self.exp_process = Process( target = self.worker.exp_on, args = ( self.child_conn, self.cur_exp_name, \
                                            self.cur_length, self.cur_st_freq, self.cur_rep_rate, self.cur_scan, \
                                            self.cur_end_freq, self.cur_step_freq, self.cur_averages, ) )
               
        self.exp_process.start()
        # send a command in a different thread about the current state
        self.parent_conn.send('start')

    def message(*text):
        sock = socket.socket()
        sock.connect(('localhost', 9091))
        if len(text) == 1:
            sock.send(str(text[0]).encode())
            sock.close()
        else:
            sock.send(str(text).encode())
            sock.close()

# The worker class that run the digitizer in a different thread
class Worker(QWidget):
    def __init__(self, parent = None):
        super(Worker, self).__init__(parent)
        # initialization of the attribute we use to stop the experimental script

        self.command = 'start'
                   
    def exp_on(self, conn, p2, p4, p5, p6, p7, p8, p9, p10):
        """
        function that contains experimental script
        """
        # [               2,               4, ]
        # self.cur_exp_name, self.cur_length, 
        # [             5,                 6,             7,                 8,                  9,                10 ]
        #self.cur_st_freq, self.cur_rep_rate, self.cur_scan, self.cur_end_freq, self.cur_step_freq, self.cur_averages

        # should be inside dig_on() function;
        # freezing after digitizer restart otherwise
        import random
        import sys
        import numpy as np
        import atomize.general_modules.general_functions as general
        import atomize.device_modules.Keysight_2000_Xseries as a2012
        import atomize.device_modules.Micran_X_band_MW_bridge_v2 as mwBridge
        ###import atomize.device_modules.Spectrum_M4I_4450_X8 as spectrum
        import atomize.device_modules.PB_ESR_500_pro as pb_pro

        a2012 = a2012.Keysight_2000_Xseries()
        pb = pb_pro.PB_ESR_500_Pro()
        mw = mwBridge.Micran_X_band_MW_bridge_v2()
        ###dig4450 = spectrum.Spectrum_M4I_4450_X8()

        ### Experimental parameters
        START_FREQ = p5
        END_FREQ = p8
        STEP = p9
        SCANS = p7
        AVERAGES = p10
        process = 'None'

        # PULSES
        REP_RATE = str(p6) + ' Hz'
        PULSE_1_LENGTH = str(p4) + ' ns'
        PULSE_1_START = '0 ns'

        # setting pulses:
        pb.pulser_pulse(name ='P0', channel = 'TRIGGER', start = PULSE_1_START, length = PULSE_1_LENGTH)
        pb.pulser_pulse(name ='P1', channel = 'MW', start = PULSE_1_START, length = PULSE_1_LENGTH)

        pb.pulser_repetition_rate( REP_RATE )
        pb.pulser_update()

        a2012.oscilloscope_acquisition_type('Average')
        a2012.oscilloscope_trigger_channel('Ext')
        a2012.oscilloscope_number_of_averages(AVERAGES)
        a2012.oscilloscope_stop()

        # Oscilloscopes bug
        a2012.oscilloscope_number_of_averages(2)
        a2012.oscilloscope_start_acquisition()

        y = a2012.oscilloscope_get_curve('CH1')
        a2012.oscilloscope_stop()

        #
        ###dig4450.digitizer_read_settings()
        ###dig4450.digitizer_number_of_averages(AVERAGES)
        ###real_length = int (dig4450.digitizer_number_of_points( ) )

        a2012.oscilloscope_record_length( 1000 )
        real_length = a2012.oscilloscope_record_length( )

        points = int( (END_FREQ - START_FREQ) / STEP ) + 1
        data = np.zeros( (points, real_length) )
        ###

        freq_before = int(str( mw.mw_bridge_synthesizer() ).split(' ')[1])
        # initialize the power and skip the incorrect first point
        mw.mw_bridge_synthesizer( START_FREQ )
        general.wait('200 ms')
        a2012.oscilloscope_start_acquisition()
        a2012.oscilloscope_get_curve('CH2')

        # the idea of automatic and dynamic changing is
        # sending a new value of repetition rate via self.command
        # in each cycle we will check the current value of self.command
        # self.command = 'exit' will stop the digitizer
        while self.command != 'exit':

            # Start of experiment
            j = 1
            while j <= SCANS:

                i = 0
                freq = START_FREQ
                mw.mw_bridge_synthesizer( freq )
                general.wait('300 ms')
                
                a2012.oscilloscope_start_acquisition()
                a2012.oscilloscope_get_curve('CH2')

                while freq <= END_FREQ:
                    
                    mw.mw_bridge_synthesizer( freq )

                    a2012.oscilloscope_start_acquisition()
                    y = a2012.oscilloscope_get_curve('CH2')
                    general.wait('300 ms')
                    ###x, y, z = dig4450.digitizer_get_curve( )
                    ##y = np.random.normal(3, 2.5, size = (real_length)) 
                    
                    data[i] = ( data[i] * (j - 1) + y ) / j

                    process = general.plot_2d(p2, np.transpose( data ), start_step = ( (0, 1), (START_FREQ*1000000, STEP*1000000) ),\
                                     xname = 'Time', xscale = 's', yname = 'Frequency', yscale = 'Hz', zname = 'Intensity', zscale = 'V', \
                                     pr = process, text = 'Scan / Frequency: ' + str(j) + ' / ' + str(freq))
                    
                    freq = round( (STEP + freq), 3 )
                    
                    # check our polling data
                    if self.command[0:2] == 'SC':
                        SCANS = int( self.command[2:] )
                        self.command = 'start'
                    elif self.command[0:2] == 'GR':
                        p11 = int( self.command[2:] )
                        self.command = 'start'
                    elif self.command == 'exit':
                        break
                    
                    if conn.poll() == True:
                        self.command = conn.recv()

                    i += 1

                mw.mw_bridge_synthesizer( START_FREQ )
                j += 1

            # finish succesfully
            self.command = 'exit'

        if self.command == 'exit':
            general.message('Script finished')
            mw.mw_bridge_synthesizer( freq_before )
            ###dig4450.digitizer_stop()
            ###dig4450.digitizer_close()
            pb.pulser_stop()

def main():
    """
    A function to run the main window of the programm.
    """
    app = QtWidgets.QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
