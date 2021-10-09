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
        self.label_9.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
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
        self.box_scan.lineEdit().setReadOnly( True )
        self.cur_scan = int( self.box_scan.value() )
        
        self.box_graph.valueChanged.connect(self.graph_show)
        self.box_graph.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.cur_graph = float( self.box_graph.value() )
        self.box_graph.lineEdit().setReadOnly( True )

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
    
    def graph_show(self):
        """
        A function to send a number of points for drawing
        """
        self.cur_graph = int( self.box_graph.value() )
        #print(self.cur_graph)
        try:
            self.parent_conn.send( 'GR' + str( self.cur_graph ) )
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

        if self.cur_start_field >= self.cur_end_field:
            self.cur_start_field, self.cur_end_field = self.cur_end_field, self.cur_start_field

            self.box_end_field.setValue( self.cur_end_field )
            self.box_st_field.setValue( self.cur_start_field )

        self.parent_conn, self.child_conn = Pipe()
        # a process for running function script 
        # sending parameters for initial initialization
        self.exp_process = Process( target = self.worker.exp_on, args = ( self.child_conn, self.cur_curve_name, self.cur_exp_name, \
                                            self.cur_end_field, self.cur_start_field, self.cur_step, self.cur_lock_ampl, self.cur_scan, \
                                            self.cur_tc, self.cur_sens, self.cur_graph, ) )
               
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
        # [                1,                 2,                  3,                    4, ]
        #self.cur_curve_name, self.cur_exp_name, self.cur_end_field, self.cur_start_field, 
        # [          5,                 6,              7,           8,             9,             10 ]
        #self.cur_step, self.cur_lock_ampl, self.cur_scan, self.cur_tc, self.cur_sens, self.cur_graph

        # should be inside dig_on() function;
        # freezing after digitizer restart otherwise
        import atomize.general_modules.general_functions as general
        import atomize.device_modules.SR_830 as sr
        import atomize.device_modules.BH_15 as bh
        import atomize.device_modules.Lakeshore_335 as ls
        import atomize.device_modules.Agilent_53131a as ag
        import atomize.general_modules.csv_opener_saver_tk_kinter as openfile

        file_handler = openfile.Saver_Opener()
        ##ag53131a = ag.Agilent_53131a()
        ##ls335 = ls.Lakeshore_335()
        ##sr830 = sr.SR_830()
        ##bh15 = bh.BH_15()

        # parameters for initial initialization
        field = 1000
        START_FIELD = p4
        END_FIELD = p3
        FIELD_STEP = p5
        initialization_step = 10
        SCANS = p7

        points = int( (END_FIELD - START_FIELD) / FIELD_STEP ) + 1
        data = np.zeros(points)
        x_axis = np.linspace(START_FIELD, END_FIELD, num = points) 

        ##bh15.magnet_setup(field, p5)
        ##sr830.lock_in_time_constant( p8 )
        ##sr830.lock_in_sensitivity( '1 V' )
        ##sr830.lock_in_ref_amplitude( p6 )
        ##sr830.lock_in_phase( 159.6 )
        ##sr830.lock_in_ref_frequency( 100000 )

        # the idea of automatic and dynamic changing is
        # sending a new value of repetition rate via self.command
        # in each cycle we will check the current value of self.command
        # self.command = 'exit' will stop the digitizer
        while self.command != 'exit':
            # Start of experiment
            while field < START_FIELD:
                
                ##field = bh15.magnet_field( field + initialization_step )
                field = field + initialization_step

            ##field = bh15.magnet_field( START_FIELD )
            ##sr830.lock_in_sensitivity( p9 )

            j = 1
            while j <= SCANS:

                i = 0
                field = START_FIELD
                while field <= END_FIELD:
                    
                    ##general.wait( sr830.lock_in_time_constant() )
                    general.wait('10 ms')

                    ##data[i] = ( data[i] * (j - 1) + sr830.lock_in_get_data() ) / j
                    data[i] = ( data[i] * (j - 1) + random.random() ) / j

                    if i % p10 == 0:
                        general.plot_1d( p2, x_axis, data, xname = 'Magnetic Field',\
                            xscale = 'G', yname = 'Signal Intensity', yscale = 'V', label = p1 )
                        general.text_label( p2, "Scan / Field: ", str(j) + ' / '+ str(field) )
                    else:
                        pass

                    field = round( (FIELD_STEP + field), 3 )
                    ##bh15.magnet_field(field)

                    # check our polling data
                    if self.command[0:2] == 'SC':
                        SCANS = int( self.command[2:] )
                        self.command = 'start'
                    elif self.command[0:2] == 'GR':
                        p10 = int( self.command[2:] )
                        self.command = 'start'
                    elif self.command == 'exit':
                        break
                    
                    if conn.poll() == True:
                        self.command = conn.recv()

                    i += 1

                while field > START_FIELD:
                    ##field = bh15.magnet_field( field - initialization_step )
                    field = field - initialization_step

                j += 1

            # finish succesfully
            self.command = 'exit'

        if self.command == 'exit':
            general.message('Script finished')
            ##sr830.lock_in_sensitivity( '1 V' )
            while field >= START_FIELD:
                ##field = bh15.magnet_field( field - initialization_step )
                field = field - initialization_step 

            # Data saving
            ## str( ls335.tc_temperature('B') )
            ## str( ag53131a.freq_counter_frequency('CH3') / 1000000 )
            header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + 'Continious Wave EPR Spectrum\n' + \
                        'Start Field: ' + str(START_FIELD) + ' G \n' + 'End Field: ' + str(END_FIELD) + ' G \n' + \
                        'Field Step: ' + str(FIELD_STEP) + ' G \n' + 'Number of Scans: ' + str(SCANS) + '\n' + \
                        'Temperature: ' + str( 10 ) + ' K\n' +\
                        'Time Constant: ' + str(p8) + '\n' + 'Modulation amplitude: ' + str(p6) + ' V\n' + \
                        'Frequency: ' + str( 9.750 ) + ' GHz\n' + 'Field (G), X (V)'

            file_handler.save_1D_dialog( ( x_axis, data ), header = header )

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
