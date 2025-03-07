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
        gui_path = os.path.join(path_to_main,'gui/cw_main_window.ui')
        icon_path = os.path.join(path_to_main, 'gui/icon_cw.png')
        self.setWindowIcon( QIcon(icon_path) )

        uic.loadUi(gui_path, self)                        # Design file

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
        self.label_3.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_4.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_5.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_6.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_7.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_8.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_10.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # text edits
        self.text_edit_curve.setStyleSheet("QTextEdit { color : rgb(211, 194, 78) ; }") # rgb(193, 202, 227)
        self.text_edit_exp_name.setStyleSheet("QTextEdit { color : rgb(211, 194, 78) ; }") # rgb(193, 202, 227)
        self.cur_curve_name = self.text_edit_curve.toPlainText()
        self.cur_exp_name = self.text_edit_exp_name.toPlainText()
        self.text_edit_curve.textChanged.connect(self.curve_name)
        self.text_edit_exp_name.textChanged.connect(self.exp_name)

        # Spinboxes
        self.box_end_field.valueChanged.connect(self.end_field)
        self.box_end_field.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.cur_end_field = float( self.box_end_field.value() )
        self.box_st_field.valueChanged.connect(self.st_field)
        self.box_st_field.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.cur_start_field = float( self.box_st_field.value() )
        self.box_step_field.valueChanged.connect(self.step_field)
        self.box_step_field.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.cur_step = float( self.box_step_field.value() )
        self.box_lock_ampl.valueChanged.connect(self.lock_ampl)
        self.box_lock_ampl.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.cur_lock_ampl = float( self.box_lock_ampl.value() )
        self.box_scan.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.box_scan.valueChanged.connect(self.scan)
        #self.box_scan.lineEdit().setReadOnly( True )
        self.cur_scan = int( self.box_scan.value() )
        
        self.combo_tc.currentIndexChanged.connect(self.lock_tc)
        self.cur_tc = self.combo_tc.currentText() 
        self.combo_tc.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.combo_sens.currentIndexChanged.connect(self.lock_sens)
        self.cur_sens = self.combo_sens.currentText()
        self.combo_sens.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        
        """
        Create a process to interact with an experimental script that will run on a different thread.
        We need a different thread here, since PyQt GUI applications have a main thread of execution 
        that runs the event loop and GUI. If you launch a long-running task in this thread, then your GUI
        will freeze until the task terminates. During that time, the user won’t be able to interact with 
        the application
        """
        self.worker = Worker()

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

    def end_field(self):
        """
        A function to send an end field value
        """
        self.cur_end_field = round( float( self.box_end_field.value() ), 3 )
        #print(self.cur_end_field)

    def st_field(self):
        """
        A function to send a start field value
        """
        self.cur_start_field = round( float( self.box_st_field.value() ), 3 )
        #print(self.cur_start_field)

    def step_field(self):
        """
        A function to send a step field value
        """
        self.cur_step = round( float( self.box_step_field.value() ), 3 )
        #print(self.cur_step)

    def lock_ampl(self):
        """
        A function to send a lock in amplitude value
        """
        self.cur_lock_ampl = round( float( self.box_lock_ampl.value() ), 3 )
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

    def lock_tc(self):
        """
        A function to send time constant
        """
        self.cur_tc = self.combo_tc.currentText()
        #print( self.cur_tc )

    def lock_sens(self):
        """
        A function to send sensitivity
        """
        self.cur_sens = self.combo_sens.currentText()
        #print( self.cur_sens )
    
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

        if self.cur_start_field >= self.cur_end_field:
            self.cur_start_field, self.cur_end_field = self.cur_end_field, self.cur_start_field

            self.box_end_field.setValue( self.cur_end_field )
            self.box_st_field.setValue( self.cur_start_field )

        self.parent_conn, self.child_conn = Pipe()
        # a process for running function script 
        # sending parameters for initial initialization
        self.exp_process = Process( target = self.worker.exp_on, args = ( self.child_conn, self.cur_curve_name, self.cur_exp_name, \
                                            self.cur_end_field, self.cur_start_field, self.cur_step, self.cur_lock_ampl, self.cur_scan, \
                                            self.cur_tc, self.cur_sens, ) )
               
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
                   
    def exp_on(self, conn, p1, p2, p3, p4, p5, p6, p7, p8, p9):
        """
        function that contains experimental script
        """
        # [                1,                 2,                  3,                    4, ]
        #self.cur_curve_name, self.cur_exp_name, self.cur_end_field, self.cur_start_field, 
        # [          5,                 6,              7,           8,             9,     ]
        #self.cur_step, self.cur_lock_ampl, self.cur_scan, self.cur_tc, self.cur_sens, 

        # should be inside dig_on() function;
        # freezing after digitizer restart otherwise
        import atomize.general_modules.general_functions as general
        import atomize.device_modules.SR_860 as sr
        import atomize.device_modules.ITC_FC as itc
        #import atomize.device_modules.BH_15 as itc
        import atomize.device_modules.Lakeshore_335 as ls
        import atomize.device_modules.Agilent_53131a as ag
        import atomize.general_modules.csv_opener_saver_tk_kinter as openfile

        file_handler = openfile.Saver_Opener()
        ag53131a = ag.Agilent_53131a()
        ls335 = ls.Lakeshore_335()
        sr860 = sr.SR_860()
        itc_fc = itc.ITC_FC()
        #itc_fc = itc.BH_15()

        # parameters for initial initialization
        field = p4
        START_FIELD = p4
        END_FIELD = p3
        FIELD_STEP = p5
        initialization_step = 10
        SCANS = p7
        process = 'None'

        #itc_fc.magnet_setup( 100, FIELD_STEP)

        tc_wait = 0
        raw = p8.split(" ")
        if int( raw[0] ) > 100 or raw[1] == 's':
            tc_wait = 1

        points = int( (END_FIELD - START_FIELD) / FIELD_STEP ) + 1
        data = np.zeros(points)
        x_axis = np.linspace(START_FIELD, END_FIELD, num = points) 

        sr860.lock_in_time_constant( p8 )
        sr860.lock_in_sensitivity( '1 V' )
        sr860.lock_in_ref_amplitude( p6 )
        sr860.lock_in_phase( 159.6 - 180 ) #159.6
        sr860.lock_in_ref_frequency( 100000 )

        t_start = str( ls335.tc_temperature('B') )
        
        ag53131a.freq_counter_digits(8)
        ag53131a.freq_counter_stop_mode('Digits')
        
        #START_FIELD = 3460.2
        # the idea of automatic and dynamic changing is
        # sending a new value of repetition rate via self.command
        # in each cycle we will check the current value of self.command
        # self.command = 'exit' will stop the digitizer
        while self.command != 'exit':
            # Start of experiment
            while field < START_FIELD:
                
                field = itc_fc.magnet_field( field + initialization_step)
                ##field = START_FIELD
                general.wait('1000 ms')

            field = itc_fc.magnet_field( START_FIELD, calibration = 'True' )
            general.wait('4000 ms')

            sr860.lock_in_sensitivity( p9 )

            j = 1
            while j <= SCANS:

                i = 0
                field = START_FIELD
                general.wait('2000 ms')

                if self.command == 'exit':
                    break

                while field <= END_FIELD:
                    
                    #if tc_wait == 1:
                    general.wait( p8 )
                        #general.wait('10 ms')

                    data[i] = ( data[i] * (j - 1) + sr860.lock_in_get_data() ) / j

                    process = general.plot_1d( p2, x_axis, data, xname = 'Field',\
                        xscale = 'G', yname = 'Intensity', yscale = 'V', label = p1, pr = process, \
                        text = 'Scan / Field: ' + str(j) + ' / ' + str(field) )

                    field = round( (FIELD_STEP + field), 3 )
                    itc_fc.magnet_field(field, calibration = 'True')

                    # check our polling data
                    if self.command[0:2] == 'SC':
                        SCANS = int( self.command[2:] )
                        self.command = 'start'
                    elif self.command == 'exit':
                        break
                    
                    if conn.poll() == True:
                        self.command = conn.recv()

                    i += 1

                while field > START_FIELD:
                    field = itc_fc.magnet_field( field - initialization_step)
                    field = field - initialization_step

                j += 1

            # finish succesfully
            self.command = 'exit'

        if self.command == 'exit':
            general.message('Script finished')
            sr860.lock_in_sensitivity( '1 V' )
            while field >= START_FIELD:
                field = itc_fc.magnet_field( field - initialization_step )
                field = field - initialization_step 

            # Data saving
            header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + 'Continious Wave EPR Spectrum\n' + \
                        'Start Field: ' + str(START_FIELD) + ' G \n' + 'End Field: ' + str(END_FIELD) + ' G \n' + \
                        'Field Step: ' + str(FIELD_STEP) + ' G \n' + 'Number of Scans: ' + str(SCANS) + '\n' + \
                        'Temperature Start Exp: ' + str( t_start ) + ' K\n' +\
                        'Temperature End Exp: ' + str( ls335.tc_temperature('B') ) + ' K\n' +\
                        'Time Constant: ' + str(p8) + '\n' + 'Modulation Amplitude: ' + str(p6) + ' V\n' + \
                        'Frequency: ' + str( round( ag53131a.freq_counter_frequency('CH3') / 1000000, 6) ) + ' GHz\n' + 'Field (G), X (V)'

            file_data, file_param = file_handler.create_file_parameters('.param')
            file_handler.save_data(file_data, np.c_[x_axis, data], header = header, mode = 'w')

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
