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
        
        self.destroyed.connect(lambda: self._on_destroyed())         # connect some actions to exit
        # Load the UI Page
        path_to_main = os.path.dirname(os.path.abspath(__file__))
        gui_path = os.path.join(path_to_main,'gui/echo_det_main_window.ui')
        icon_path = os.path.join(path_to_main, 'gui/icon_ed.png')
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
        self.label_2.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_4.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_5.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_6.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_7.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_8.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_10.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_11.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_12.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # text edits
        self.text_edit_curve.setStyleSheet("QTextEdit { color : rgb(211, 194, 78) ; }") # rgb(193, 202, 227)
        self.text_edit_exp_name.setStyleSheet("QTextEdit { color : rgb(211, 194, 78) ; }") # rgb(193, 202, 227)
        self.cur_curve_name = self.text_edit_curve.toPlainText()
        self.cur_exp_name = self.text_edit_exp_name.toPlainText()
        self.text_edit_curve.textChanged.connect(self.curve_name)
        self.text_edit_exp_name.textChanged.connect(self.exp_name)

        # Spinboxes
        self.box_delta.valueChanged.connect(self.delta)
        self.box_delta.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.cur_delta = int( self.box_delta.value() )
        self.box_delta.lineEdit().setReadOnly( True )
        
        self.box_length.valueChanged.connect(self.pulse_length)
        self.box_length.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.cur_length = int( self.box_length.value() )
        self.box_length.lineEdit().setReadOnly( True )

        self.box_rep_rate.valueChanged.connect(self.rep_rate)
        self.box_rep_rate.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.cur_rep_rate = int( self.box_rep_rate.value() )
        
        self.box_st_field.valueChanged.connect(self.start_field)
        self.box_st_field.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.cur_st_field = round( float( self.box_st_field.value() ), 3 )

        self.box_end_field.valueChanged.connect(self.end_field)
        self.box_end_field.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.cur_end_field = round( float( self.box_end_field.value() ), 3 )

        self.box_step_field.valueChanged.connect(self.step_field)
        self.box_step_field.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.cur_step_field = round( float( self.box_step_field.value() ), 3 )
        
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

    def curve_name(self):
        self.cur_curve_name = self.text_edit_curve.toPlainText()
        #print( self.cur_curve_name )

    def exp_name(self):
        self.cur_exp_name = self.text_edit_exp_name.toPlainText()
        #print( self.cur_exp_name )

    def delta(self):
        self.cur_delta = int( self.box_delta.value() )
        if self.cur_delta - self.cur_length < 40:
            self.cur_delta = self.cur_length + 40
            self.box_delta.setValue( self.cur_delta )
        # trigger
        if self.cur_delta - self.cur_length * 2 < 12:
            self.cur_delta = self.cur_length * 2 + 12
            self.box_delta.setValue( self.cur_delta )
        #print(self.cur_end_field)

    def pulse_length(self):
        self.cur_length = int( self.box_length.value() )
        if self.cur_delta - self.cur_length < 40:
            self.cur_delta = self.cur_length + 40
            self.box_delta.setValue( self.cur_delta )
        # trigger
        if self.cur_delta - self.cur_length * 2 < 12:
            self.cur_delta = self.cur_length * 2 + 12
            self.box_delta.setValue( self.cur_delta )
        #print(self.cur_start_field)

    def rep_rate(self):
        self.cur_rep_rate = int( self.box_rep_rate.value() )
        #print(self.cur_start_field)

    def averages(self):
        self.cur_averages = int( self.box_averag.value() )
        #print(self.cur_start_field)

    def start_field(self):
        self.cur_st_field = round( float( self.box_st_field.value() ), 3 )
        #print(self.cur_lock_ampl)

    def end_field(self):
        self.cur_end_field = round( float( self.box_end_field.value() ), 3 )
        #print(self.cur_lock_ampl)

    def step_field(self):
        self.cur_step_field = round( float( self.box_step_field.value() ), 3 )
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

        if self.cur_st_field >= self.cur_end_field:
            self.cur_st_field, self.cur_end_field = self.cur_end_field, self.cur_st_field

            self.box_end_field.setValue( self.cur_end_field )
            self.box_st_field.setValue( self.cur_st_field )

        self.parent_conn, self.child_conn = Pipe()
        # a process for running function script 
        # sending parameters for initial initialization
        self.exp_process = Process( target = self.worker.exp_on, args = ( self.child_conn, self.cur_curve_name, self.cur_exp_name, \
                                            self.cur_delta, self.cur_length, self.cur_st_field, self.cur_rep_rate, self.cur_scan, \
                                            self.cur_end_field, self.cur_step_field, self.cur_averages, ) )
               
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
                   
    def exp_on(self, conn, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10):
        """
        function that contains experimental script
        """
        # [                1,                 2,              3,               4, ]
        #self.cur_curve_name, self.cur_exp_name, self.cur_delta, self.cur_length, 
        # [              5,                 6,             7,                  8,                   9,                10 ]
        #self.cur_st_field, self.cur_rep_rate, self.cur_scan, self.cur_end_field, self.cur_step_field, self.cur_averages

        # should be inside dig_on() function;
        # freezing after digitizer restart otherwise
        ##import random
        ##import time
        import datetime
        import numpy as np
        import atomize.general_modules.general_functions as general
        import atomize.device_modules.PB_ESR_500_pro as pb_pro
        ###import atomize.device_modules.Keysight_2000_Xseries as key
        import atomize.device_modules.Mikran_X_band_MW_bridge_v2 as mwBridge
        import atomize.device_modules.Spectrum_M4I_2211_X8 as spectrum
        import atomize.device_modules.ITC_FC as itc
        import atomize.device_modules.Lakeshore_335 as ls
        import atomize.general_modules.csv_opener_saver_tk_kinter as openfile

        file_handler = openfile.Saver_Opener()
        ls335 = ls.Lakeshore_335()
        mw = mwBridge.Mikran_X_band_MW_bridge_v2()
        pb = pb_pro.PB_ESR_500_Pro()
        bh15 = itc.ITC_FC()
        ###a2012 = key.Keysight_2000_Xseries()
        dig4450 = spectrum.Spectrum_M4I_2211_X8()

        ### Experimental parameters
        START_FIELD = p5
        END_FIELD = p8
        FIELD_STEP = p9
        AVERAGES = p10
        SCANS = p7
        process = 'None'

        # PULSES
        REP_RATE = str(p6) + ' Hz'
        PULSE_1_LENGTH = str(p4) + ' ns'
        PULSE_2_LENGTH = str( int(2*p4) ) + ' ns'
        PULSE_1_START = '0 ns'
        PULSE_2_START = str( p3 ) + ' ns'
        PULSE_SIGNAL_START = str( int(2*p3) ) + ' ns'

        #
        cycle_data_x = np.zeros( 2 )
        cycle_data_y = np.zeros( 2 )
        points = int( (END_FIELD - START_FIELD) / FIELD_STEP ) + 1
        data_x = np.zeros(points)
        data_y = np.zeros(points)
        x_axis = np.linspace(START_FIELD, END_FIELD, num = points)
        ###

        bh15.magnet_field(START_FIELD, calibration = 'True')
        general.wait('4000 ms')

        ###a2012.oscilloscope_trigger_channel('Ext')
        ###a2012.oscilloscope_record_length(4000)
        ###a2012.oscilloscope_acquisition_type('Average')
        ###a2012.oscilloscope_number_of_averages(AVERAGES)
        ###a2012.oscilloscope_stop()

        # read integration window
        ###a2012.oscilloscope_read_settings()
        dig4450.digitizer_read_settings()
        dig4450.digitizer_number_of_averages(AVERAGES)

        pb.pulser_pulse(name ='P0', channel = 'MW', start = PULSE_1_START, length = PULSE_1_LENGTH, phase_list = ['+x', '-x'])
        pb.pulser_pulse(name ='P1', channel = 'MW', start = PULSE_2_START, length = PULSE_2_LENGTH, phase_list = ['+x', '+x'])
        pb.pulser_pulse(name ='P2', channel = 'TRIGGER', start = PULSE_SIGNAL_START, length = '100 ns')

        pb.pulser_repetition_rate( REP_RATE )
        pb.pulser_update()
        
        # the idea of automatic and dynamic changing is
        # sending a new value of repetition rate via self.command
        # in each cycle we will check the current value of self.command
        # self.command = 'exit' will stop the digitizer
        while self.command != 'exit':

            # Start of experiment
            j = 1
            while j <= SCANS:

                i = 0
                field = START_FIELD
                
                if self.command == 'exit':
                    break

                while field <= END_FIELD:
                    # phase cycle
                    k = 0
                    while k < 2:

                        pb.pulser_next_phase()

                        cycle_data_x[k], cycle_data_y[k] = dig4450.digitizer_get_curve( integral = True )
                        ###a2012.oscilloscope_start_acquisition()
                        ###cycle_data_x[k], cycle_data_y[k] = a2012.oscilloscope_get_curve('CH1', integral = True), a2012.oscilloscope_get_curve('CH2', integral = True)
                        #cycle_data_y[k] = a2012.oscilloscope_area('CH2')

                        k += 1

                    # acquisition cycle [+, -]
                    x, y = pb.pulser_acquisition_cycle(cycle_data_x, cycle_data_y, acq_cycle = ['+', '-'])
                    data_x[i] = ( data_x[i] * (j - 1) + x ) / j
                    data_y[i] = ( data_y[i] * (j - 1) + y ) / j

                    # no phase cycling
                    bh15.magnet_field(field, calibration = 'True')

                    process = general.plot_1d(p2, x_axis, ( data_x, data_y ), xname = 'Field',\
                        xscale = 'G', yname = 'Area', yscale = 'V*s', label = p1, pr = process, \
                        text = 'Scan / Field: ' + str(j) + ' / ' + str(field))

                    field = round( (FIELD_STEP + field), 3 )
                    
                    # check our polling data
                    if self.command[0:2] == 'SC':
                        SCANS = int( self.command[2:] )
                        self.command = 'start'
                    elif self.command == 'exit':
                        break
                    
                    if conn.poll() == True:
                        self.command = conn.recv()

                    i += 1

                    pb.pulser_pulse_reset()

                bh15.magnet_field(START_FIELD, calibration = 'True')
                general.wait('4000 ms')

                j += 1

            # finish succesfully
            self.command = 'exit'

        if self.command == 'exit':
            general.message('Script finished')
            ###tb = a2012.oscilloscope_window()

            #tb = dig4450.digitizer_number_of_points() * int(  1000 / float( dig4450.digitizer_sample_rate().split(' ')[0] ) )
            tb = dig4450.digitizer_window()
            dig4450.digitizer_stop()
            dig4450.digitizer_close()
            pb.pulser_stop()

            # Data saving
            header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + 'Echo Detected Spectrum\n' + \
                        'Start Field: ' + str(START_FIELD) + ' G \n' + 'End Field: ' + str(END_FIELD) + ' G \n' + \
                        'Field Step: ' + str(FIELD_STEP) + ' G \n' + str(mw.mw_bridge_att_prm()) + '\n' + str(mw.mw_bridge_att2_prm()) + '\n' +\
                        str(mw.mw_bridge_att1_prd()) + '\n' + str(mw.mw_bridge_synthesizer()) + '\n' + \
                       'Repetition Rate: ' + str(pb.pulser_repetition_rate()) + '\n' + 'Number of Scans: ' + str(SCANS) + '\n' +\
                       'Averages: ' + str(AVERAGES) + '\n' + 'Points: ' + str(points) + '\n' + 'Window: ' + str(tb) + ' ns\n' + \
                       'Temperature: ' + str(ls335.tc_temperature('B')) + ' K\n' +\
                       'Pulse List: ' + '\n' + str(pb.pulser_pulse_list()) + 'Field (G), X (V*s), Y (V*s) '

            file_data, file_param = file_handler.create_file_parameters('.param')
            file_handler.save_header(file_param, header = header, mode = 'w')
            file_handler.save_data(file_data, np.c_[x_axis, data_x, data_y], header = header, mode = 'w')

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
