#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
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
        gui_path = os.path.join(path_to_main,'gui/tr_main_window.ui')
        icon_path = os.path.join(path_to_main, 'gui/icon_tr.png')
        self.setWindowIcon( QIcon(icon_path) )

        uic.loadUi(gui_path, self)                        # Design file

        # Connection of different action to different Menus and Buttons
        self.button_start.clicked.connect(self.start)
        self.button_start.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_off.clicked.connect(self.turn_off)
        self.button_off.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
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
        self.label_11.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # text edits
        self.text_edit_exp_name.setStyleSheet("QTextEdit { color : rgb(211, 194, 78) ; }") # rgb(193, 202, 227)
        self.cur_exp_name = self.text_edit_exp_name.toPlainText()
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
        
        self.box_off_res_field.valueChanged.connect(self.offres_field)
        self.box_off_res_field.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.cur_offres_field = float( self.box_off_res_field.value() )
        
        self.box_scan.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.box_scan.valueChanged.connect(self.scan)
        #self.box_scan.lineEdit().setReadOnly( True )
        self.cur_scan = int( self.box_scan.value() )
        
        self.box_ave.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.box_ave.valueChanged.connect(self.ave)
        #self.box_ave.lineEdit().setReadOnly( True )
        self.cur_ave = int( self.box_ave.value() )
        
        self.box_ave_offres.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.box_ave_offres.valueChanged.connect(self.ave_offres)
        #self.box_ave_offres.lineEdit().setReadOnly( True )
        self.cur_ave_offres = int( self.box_ave_offres.value() )

        self.combo_num_osc.currentIndexChanged.connect(self.num_osc)
        if len( self.combo_num_osc.currentText() ) > 1:
            self.cur_num_osc = 3
        else:
            self.cur_num_osc = int( self.combo_num_osc.currentText() )
        self.combo_num_osc.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")

        self.combo_trig_ch.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.cur_trig_ch = str( self.combo_trig_ch.currentText() )
        self.combo_trig_ch.currentIndexChanged.connect(self.trig_ch)
        
        self.check_scan.setStyleSheet("QCheckBox { color : rgb(193, 202, 227); }")
        self.check_scan.stateChanged.connect( self.save_each_scan )

        self.save_scan = 0
        
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

    def save_each_scan(self):
        """
        Turn on/off save each scan when using one oscilloscope
        """
        if self.check_scan.checkState().value == 2: # checked
            self.save_scan = 1
        elif self.check_scan.checkState().value == 0: # unchecked
            self.save_scan = 0

    def exp_name(self):
        self.cur_exp_name = self.text_edit_exp_name.toPlainText()
        #print( self.cur_exp_name )

    def trig_ch(self):
        """
        A function to send a trigger channel
        """
        self.cur_trig_ch = str( self.combo_trig_ch.currentText() )
        #print(self.cur_end_field)

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

    def offres_field(self):
        """
        A function to send an off-resonance field
        """
        self.cur_offres_field = round( float( self.box_off_res_field.value() ), 3 )
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

    def ave(self):
        """
        A function to send a number of averages
        """
        self.cur_ave = int( self.box_ave.value() )
        #print(self.cur_ave)

    def num_osc(self):
        """
        A function to send number of oscilloscopes
        """
        if len( self.combo_num_osc.currentText() ) > 1:
            self.cur_num_osc = 3
        else:
            self.cur_num_osc = int( self.combo_num_osc.currentText() )

    def ave_offres(self):
        """
        A function to send a number of averages for off-resonance
        """
        self.cur_ave_offres = int( self.box_ave_offres.value() )
        #print(self.cur_ave_offres)

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
        self.exp_process = Process( target = self.worker.exp_on, args = ( self.child_conn, self.cur_offres_field, self.cur_exp_name, \
                                            self.cur_end_field, self.cur_start_field, self.cur_step, self.cur_ave_offres, self.cur_scan, \
                                            self.cur_ave, self.cur_num_osc, self.cur_trig_ch, self.save_scan, ) )
            

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
                   
    def exp_on(self, conn, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11):
        """
        function that contains experimental script
        """
        # [                  1,                 2,                  3,                    4, ]
        #self.cur_offres_field, self.cur_exp_name, self.cur_end_field, self.cur_start_field, 
        # [          5,                   6,              7,           8,                9,               10,             11 ]
        #self.cur_step, self.cur_ave_offres, self.cur_scan, self.cur_ave, self.cur_num_osc, self.cur_trig_ch, self.save_scan

        # should be inside dig_on() function;
        # freezing after digitizer restart otherwise
        import sys
        import atomize.general_modules.general_functions as general
        import atomize.device_modules.Keysight_2000_Xseries as key
        import atomize.device_modules.Keysight_2000_Xseries_2 as key2
        #import atomize.device_modules.BH_15 as bh
        import atomize.device_modules.ITC_FC as itc
        import atomize.device_modules.Lakeshore_335 as ls
        import atomize.device_modules.Agilent_53131a as ag
        import atomize.general_modules.csv_opener_saver_tk_kinter as openfile

        file_handler = openfile.Saver_Opener()
        process = 'None'
        ag53131a = ag.Agilent_53131a()
        ls335 = ls.Lakeshore_335()
        a2012 = key.Keysight_2000_Xseries()
        bh15 = itc.ITC_FC()
        
        ag53131a.freq_counter_digits(8)
        ag53131a.freq_counter_stop_mode('Digits')

        if p9 == 1:
            a2012.oscilloscope_trigger_channel(p10)
            a2012.oscilloscope_acquisition_type('Average')
            a2012.oscilloscope_run_stop()

        else:
            a2012_2 = key2.Keysight_2000_Xseries()
            
            a2012.oscilloscope_trigger_channel(p10)
            a2012.oscilloscope_acquisition_type('Average')
            a2012.oscilloscope_run_stop()

            a2012_2.oscilloscope_trigger_channel('Ext')
            a2012_2.oscilloscope_acquisition_type('Average')
            a2012_2.oscilloscope_run_stop()

        a2012.oscilloscope_record_length( 5000 )
        try:
            real_length = a2012.oscilloscope_record_length( )
        except ZeroDivisionError:
            general.message('Incorrect Trigger Channel')

        t_res = round( a2012.oscilloscope_timebase() / real_length, 7 )    # in us
        t_res_rough = round( t_res, 3 )
        ##real_length = 4000
        if p9 > 1:
            a2012_2.oscilloscope_record_length( 5000 )
            #print(a2012_2.oscilloscope_record_length( ))
            t_res_2 = round( a2012_2.oscilloscope_timebase() / real_length, 7 ) # in us
            t_res_2_rough = round( t_res_2, 3 )

        # parameters for initial initialization
        field = 100
        START_FIELD = p4
        END_FIELD = p3
        FIELD_STEP = p5
        OFFRES_FIELD = p1
        initialization_step = 10
        SCANS = p7
        points = int( (END_FIELD - START_FIELD) / FIELD_STEP ) + 1

        if p9 == 1:
            data = np.zeros( (2, real_length, points + 1) )
        elif p9 == 2:
            data = np.zeros( (4, real_length, points + 1) )
        else:
            data = np.zeros( (5, real_length, points + 1) )
        
        ##axis_x = np.arange(4000)
        
        temp_start = str( ls335.tc_temperature('B') )

        # Oscilloscopes bugs
        a2012.oscilloscope_number_of_averages(2)
        if p9 > 1:
            a2012_2.oscilloscope_number_of_averages(2)

        a2012.oscilloscope_start_acquisition()
        if p9 > 1:
            a2012_2.oscilloscope_start_acquisition()
        
        if p9 == 1:
            y = a2012.oscilloscope_get_curve('CH1')

        elif p9 == 2:
            y = a2012.oscilloscope_get_curve('CH1')
            y2 = a2012_2.oscilloscope_get_curve('CH1')

        # the idea of automatic and dynamic changing is
        # sending a new value of repetition rate via self.command
        # in each cycle we will check the current value of self.command
        # self.command = 'exit' will stop the script
        while self.command != 'exit':
            # Start of experiment
            while field < OFFRES_FIELD:
                field = bh15.magnet_field( field + initialization_step)
                field = field + initialization_step
                general.wait('30 ms')

            # Data saving
            j = 1
            if p9 == 1:
                file_save_1, file_save_param = file_handler.create_file_parameters('.param')
                ##t_res = 1
                header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + 'Time Resolved EPR Spectrum\n' + \
                            'Start Field: ' + str(START_FIELD) + ' G \n' + 'End Field: ' + str(END_FIELD) + ' G \n' + \
                            'Field Step: ' + str(FIELD_STEP) + ' G \n' + \
                            'Off Resonance Field: ' + str(OFFRES_FIELD) + ' G \n' + \
                            'Number of Off Resonance Averages: ' + str(p6) + '\n' + \
                            'Number of Averages: ' + str(p8) + '\n' + \
                            'Number of Scans: ' + str(SCANS) + '\n' + \
                            'Temperature Start Exp: ' + str( temp_start ) + ' K\n' +\
                            'Temperature End Exp: ' + str( temp_start ) + ' K\n' +\
                            'Record Length: ' + str(real_length) + ' Points\n' + 'Time Resolution: ' + str(t_res) + ' us\n' + \
                            'Frequency: ' + str( round( ag53131a.freq_counter_frequency('CH3') / 1000000, 6) ) + ' GHz\n' + '2D Data'
                
                file_handler.save_header(file_save_1, header = header, mode = 'w')
            elif p9 == 2:
                file_save_1, file_save_2 = file_handler.create_file_parameters('_osc2.csv')

                header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + 'Time Resolved EPR Spectrum\n' + \
                            'Start Field: ' + str(START_FIELD) + ' G \n' + 'End Field: ' + str(END_FIELD) + ' G \n' + \
                            'Field Step: ' + str(FIELD_STEP) + ' G \n' + \
                            'Off Resonance Field: ' + str(OFFRES_FIELD) + ' G \n' + \
                            'Number of Off Resonance Averages: ' + str(p6) + '\n' + \
                            'Number of Averages: ' + str(p8) + '\n' + \
                            'Number of Scans: ' + str(SCANS) + '\n' + \
                            'Temperature Start Exp: ' + str( temp_start ) + ' K\n' +\
                            'Temperature End Exp: ' + str( temp_start ) + ' K\n' +\
                            'Record Length: ' + str(real_length) + ' Points\n' + 'Time Resolution: ' + str(t_res) + ' us\n' + \
                            'Frequency: ' + str( round( ag53131a.freq_counter_frequency('CH3') / 1000000, 6) ) + ' GHz\n' + '2D Data'

                header_2 = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + 'Time Resolved EPR Spectrum\n' + \
                            'Start Field: ' + str(START_FIELD) + ' G \n' + 'End Field: ' + str(END_FIELD) + ' G \n' + \
                            'Field Step: ' + str(FIELD_STEP) + ' G \n' + \
                            'Off Resonance Field: ' + str(OFFRES_FIELD) + ' G \n' + \
                            'Number of Off Resonance Averages: ' + str(p6) + '\n' + \
                            'Number of Averages: ' + str(p8) + '\n' + \
                            'Number of Scans: ' + str(SCANS) + '\n' + \
                            'Temperature Start Exp: ' + str( temp_start ) + ' K\n' +\
                            'Temperature End Exp: ' + str( temp_start ) + ' K\n' +\
                            'Record Length: ' + str(real_length) + ' Points\n' + 'Time Resolution: ' + str(t_res_2) + ' us\n' + \
                            'Frequency: ' + str( round( ag53131a.freq_counter_frequency('CH3') / 1000000, 6) ) + ' GHz\n' + '2D Data'

                file_handler.save_header(file_save_1, header = header, mode = 'w')
                file_handler.save_header(file_save_2, header = header_2, mode = 'w')

            elif p9 == 3:
                file_save_1, file_save_2 = file_handler.create_file_parameters('_osc2.csv')
                file_save_3 = file_save_1.split('.csv')[0] + '_pulse.csv'

                header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + 'Time Resolved EPR Spectrum\n' + \
                            'Start Field: ' + str(START_FIELD) + ' G \n' + 'End Field: ' + str(END_FIELD) + ' G \n' + \
                            'Field Step: ' + str(FIELD_STEP) + ' G \n' + \
                            'Off Resonance Field: ' + str(OFFRES_FIELD) + ' G \n' + \
                            'Number of Off Resonance Averages: ' + str(p6) + '\n' + \
                            'Number of Averages: ' + str(p8) + '\n' + \
                            'Number of Scans: ' + str(SCANS) + '\n' + \
                            'Temperature Start Exp: ' + str( temp_start ) + ' K\n' +\
                            'Temperature End Exp: ' + str( temp_start ) + ' K\n' +\
                            'Record Length: ' + str(real_length) + ' Points\n' + 'Time Resolution: ' + str(t_res) + ' us\n' + \
                            'Frequency: ' + str( round( ag53131a.freq_counter_frequency('CH3') / 1000000, 6) ) + ' GHz\n' + '2D Data'

                header_2 = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + 'Time Resolved EPR Spectrum\n' + \
                            'Start Field: ' + str(START_FIELD) + ' G \n' + 'End Field: ' + str(END_FIELD) + ' G \n' + \
                            'Field Step: ' + str(FIELD_STEP) + ' G \n' + \
                            'Off Resonance Field: ' + str(OFFRES_FIELD) + ' G \n' + \
                            'Number of Off Resonance Averages: ' + str(p6) + '\n' + \
                            'Number of Averages: ' + str(p8) + '\n' + \
                            'Number of Scans: ' + str(SCANS) + '\n' + \
                            'Temperature Start Exp: ' + str( temp_start ) + ' K\n' +\
                            'Temperature End Exp: ' + str( temp_start ) + ' K\n' +\
                            'Record Length: ' + str(real_length) + ' Points\n' + 'Time Resolution: ' + str(t_res_2) + ' us\n' + \
                            'Frequency: ' + str( round( ag53131a.freq_counter_frequency('CH3') / 1000000, 6) ) + ' GHz\n' + '2D Data'

                file_handler.save_header(file_save_1, header = header, mode = 'w')
                file_handler.save_header(file_save_2, header = header_2, mode = 'w')
                file_handler.save_header(file_save_3, header = header, mode = 'w')

            while j <= SCANS:
                if self.command == 'exit':
                    break

                field = bh15.magnet_field( OFFRES_FIELD )
                field = OFFRES_FIELD

                general.wait('4000 ms')

                a2012.oscilloscope_number_of_averages(p6)
                if p9 > 1:
                    a2012_2.oscilloscope_number_of_averages(p6)
                
                a2012.oscilloscope_start_acquisition()
                if p9 > 1:
                    a2012_2.oscilloscope_start_acquisition()

                ##ch_time = np.random.randint(250, 500, 1)
                if p9 == 1:
                    y = a2012.oscilloscope_get_curve('CH1')
                    ##y = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                    data[0, :, 0] = ( data[0, :, 0] * (j - 1) + y ) / j
                    data[1, :, 0] = ( data[0, :, 0] - data[0, :, 0] )
                    data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )
                    
                elif p9 == 2:
                    y = a2012.oscilloscope_get_curve('CH1')
                    ##y = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                    data[0, :, 0] = ( data[0, :, 0] * (j - 1) + y ) / j
                    data[1, :, 0] = ( data[0, :, 0] - data[0, :, 0] )
                    data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )

                    y2 = a2012_2.oscilloscope_get_curve('CH1')
                    ##y2 = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                    data[2, :, 0] = ( data[2, :, 0] * (j - 1) + y2 ) / j
                    data[3, :, 0] = ( data[2, :, 0] - data[2, :, 0] )
                    data[3, :, :] = ( data[3, :, :] - data[3, 0, :] )

                elif p9 == 3:
                    y = a2012.oscilloscope_get_curve('CH1')
                    ##y = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                    data[0, :, 0] = ( data[0, :, 0] * (j - 1) + y ) / j
                    data[1, :, 0] = ( data[0, :, 0] - data[0, :, 0] )
                    data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )

                    y3 = a2012.oscilloscope_get_curve('CH2')
                    ##y3 = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                    data[4, :, 0] = ( data[4, :, 0] * (j - 1) + y3 ) / j

                    y2 = a2012_2.oscilloscope_get_curve('CH1')
                    ##y2 = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                    data[2, :, 0] = ( data[2, :, 0] * (j - 1) + y2 ) / j
                    data[3, :, 0] = ( data[2, :, 0] - data[2, :, 0] )
                    data[3, :, :] = ( data[3, :, :] - data[3, 0, :] )

                while field < START_FIELD:
                    field = bh15.magnet_field( field + initialization_step)
                    general.wait('30 ms')
                    field = field + initialization_step

                field = bh15.magnet_field( START_FIELD )
                field = START_FIELD

                general.wait('4000 ms')

                a2012.oscilloscope_number_of_averages(p8)
                if p9 > 1:
                    a2012_2.oscilloscope_number_of_averages(p8)

                i = 0
                while field <= END_FIELD:
                    
                    if self.command == 'exit':
                        break

                    general.wait('50 ms')

                    a2012.oscilloscope_start_acquisition()
                    if p9 > 1:
                        a2012_2.oscilloscope_start_acquisition()
                    
                    ##ch_time = np.random.randint(250, 500, 1)
                    if p9 == 1:
                        y = a2012.oscilloscope_get_curve('CH1')
                        ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                        
                        data[0, :, i+1] = ( data[0, :, i+1] * (j - 1) + y ) / j
                        data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                        data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )

                    elif p9 == 2:
                        y = a2012.oscilloscope_get_curve('CH1')
                        ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                        y2 = a2012_2.oscilloscope_get_curve('CH1')
                        ##y2 = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))

                        data[0, :, i+1] = ( data[0, :, i+1] * (j - 1) + y ) / j
                        data[2, :, i+1] = ( data[2, :, i+1] * (j - 1) + y2) / j
                        data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                        data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )
                        data[3, :, i+1] = ( data[2, :, i+1] - data[2, :, 0] )
                        data[3, :, :] = ( data[3, :, :] - data[3, 0, :] )

                    elif p9 == 3:
                        y = a2012.oscilloscope_get_curve('CH1')
                        ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                        y2 = a2012_2.oscilloscope_get_curve('CH1')
                        ##y2 = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                        y3 = a2012.oscilloscope_get_curve('CH2')
                        ##y3 = 1 + 100*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))

                        data[0, :, i+1] = ( data[0, :, i+1] * (j - 1) + y ) / j
                        data[2, :, i+1] = ( data[2, :, i+1] * (j - 1) + y2) / j
                        data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                        data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )
                        data[3, :, i+1] = ( data[2, :, i+1] - data[2, :, 0] )
                        data[3, :, :] = ( data[3, :, :] - data[3, 0, :] )
                        data[4, :, i+1] = ( data[4, :, i+1] * (j - 1) + y3 ) / j

                    #start_time = time.time()

                    # (0, t_res) xscale='us'
                    process = general.plot_2d( p2, data[:,:,1:points+1],  xname='Time', start_step=( (0, t_res_rough), (START_FIELD, FIELD_STEP) ),\
                        xscale='us', yname='Field', yscale='G', zname='Intensity', zscale='V', pr = process, \
                        text = 'Scan / Field: ' + str(j) + ' / ' + str(field))

                    #general.message( str( time.time() - start_time ) )

                    field = round( (FIELD_STEP + field), 3 )
                    bh15.magnet_field(field)

                    # check our polling data
                    if self.command[0:2] == 'SC':
                        SCANS = int( self.command[2:] )
                        self.command = 'start'
                    elif self.command == 'exit':
                        break
                    
                    if conn.poll() == True:
                        self.command = conn.recv()

                    i += 1

                while field > OFFRES_FIELD:
                    field = bh15.magnet_field( field - initialization_step)
                    field = field - initialization_step
                    general.wait('30 ms')
                
                field = bh15.magnet_field( OFFRES_FIELD )
                field = OFFRES_FIELD
                
                if p9 == 1 and p11 == 1:
                    if j == 1:
                        file_handler.save_data(file_save_1, np.transpose( data[0, :, :] ), header = header)
                    else:
                        file_save_j = file_save_1.split('.csv')[0] + f'_{j}_scans.csv'
                        file_handler.save_data(file_save_j, np.transpose( data[0, :, :] ), header = header)

                j += 1

            # finish succesfully
            self.command = 'exit'

        if self.command == 'exit':
            general.message('Script finished')
            
            temp_end = str( ls335.tc_temperature('B') )
            if p9 == 1 and p11 == 0:
                ##t_res = 1
                header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + 'Time Resolved EPR Spectrum\n' + \
                            'Start Field: ' + str(START_FIELD) + ' G \n' + 'End Field: ' + str(END_FIELD) + ' G \n' + \
                            'Field Step: ' + str(FIELD_STEP) + ' G \n' + \
                            'Off Resonance Field: ' + str(OFFRES_FIELD) + ' G \n' + \
                            'Number of Off Resonance Averages: ' + str(p6) + '\n' + \
                            'Number of Averages: ' + str(p8) + '\n' + \
                            'Number of Scans: ' + str(SCANS) + '\n' + \
                            'Temperature Start Exp: ' + str( temp_start ) + ' K\n' +\
                            'Temperature End Exp: ' + str( temp_end ) + ' K\n' +\
                            'Record Length: ' + str(real_length) + ' Points\n' + 'Time Resolution: ' + str(t_res) + ' us\n' + \
                            'Frequency: ' + str( round( ag53131a.freq_counter_frequency('CH3') / 1000000, 6) ) + ' GHz\n' + '2D Data'

                file_handler.save_data(file_save_1, np.transpose( data[0, :, :] ), header = header)
            elif p9 == 2:

                header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + 'Time Resolved EPR Spectrum\n' + \
                            'Start Field: ' + str(START_FIELD) + ' G \n' + 'End Field: ' + str(END_FIELD) + ' G \n' + \
                            'Field Step: ' + str(FIELD_STEP) + ' G \n' + \
                            'Off Resonance Field: ' + str(OFFRES_FIELD) + ' G \n' + \
                            'Number of Off Resonance Averages: ' + str(p6) + '\n' + \
                            'Number of Averages: ' + str(p8) + '\n' + \
                            'Number of Scans: ' + str(SCANS) + '\n' + \
                            'Temperature Start Exp: ' + str( temp_start ) + ' K\n' +\
                            'Temperature End Exp: ' + str( temp_end ) + ' K\n' +\
                            'Record Length: ' + str(real_length) + ' Points\n' + 'Time Resolution: ' + str(t_res) + ' us\n' + \
                            'Frequency: ' + str( round( ag53131a.freq_counter_frequency('CH3') / 1000000, 6) ) + ' GHz\n' + '2D Data'

                header_2 = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + 'Time Resolved EPR Spectrum\n' + \
                            'Start Field: ' + str(START_FIELD) + ' G \n' + 'End Field: ' + str(END_FIELD) + ' G \n' + \
                            'Field Step: ' + str(FIELD_STEP) + ' G \n' + \
                            'Off Resonance Field: ' + str(OFFRES_FIELD) + ' G \n' + \
                            'Number of Off Resonance Averages: ' + str(p6) + '\n' + \
                            'Number of Averages: ' + str(p8) + '\n' + \
                            'Number of Scans: ' + str(SCANS) + '\n' + \
                            'Temperature Start Exp: ' + str( temp_start ) + ' K\n' +\
                            'Temperature End Exp: ' + str( temp_end ) + ' K\n' +\
                            'Record Length: ' + str(real_length) + ' Points\n' + 'Time Resolution: ' + str(t_res_2) + ' us\n' + \
                            'Frequency: ' + str( round( ag53131a.freq_counter_frequency('CH3') / 1000000, 6) ) + ' GHz\n' + '2D Data'

                file_handler.save_data(file_save_1, np.transpose( data[0, :, :] ), header = header)
                file_handler.save_data(file_save_2, np.transpose( data[2, :, :] ), header = header_2)
            elif p9 == 3:

                header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + 'Time Resolved EPR Spectrum\n' + \
                            'Start Field: ' + str(START_FIELD) + ' G \n' + 'End Field: ' + str(END_FIELD) + ' G \n' + \
                            'Field Step: ' + str(FIELD_STEP) + ' G \n' + \
                            'Off Resonance Field: ' + str(OFFRES_FIELD) + ' G \n' + \
                            'Number of Off Resonance Averages: ' + str(p6) + '\n' + \
                            'Number of Averages: ' + str(p8) + '\n' + \
                            'Number of Scans: ' + str(SCANS) + '\n' + \
                            'Temperature Start Exp: ' + str( temp_start ) + ' K\n' +\
                            'Temperature End Exp: ' + str( temp_end ) + ' K\n' +\
                            'Record Length: ' + str(real_length) + ' Points\n' + 'Time Resolution: ' + str(t_res) + ' us\n' + \
                            'Frequency: ' + str( round( ag53131a.freq_counter_frequency('CH3') / 1000000, 6) ) + ' GHz\n' + '2D Data'

                header_2 = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + 'Time Resolved EPR Spectrum\n' + \
                            'Start Field: ' + str(START_FIELD) + ' G \n' + 'End Field: ' + str(END_FIELD) + ' G \n' + \
                            'Field Step: ' + str(FIELD_STEP) + ' G \n' + \
                            'Off Resonance Field: ' + str(OFFRES_FIELD) + ' G \n' + \
                            'Number of Off Resonance Averages: ' + str(p6) + '\n' + \
                            'Number of Averages: ' + str(p8) + '\n' + \
                            'Number of Scans: ' + str(SCANS) + '\n' + \
                            'Temperature Start Exp: ' + str( temp_start ) + ' K\n' +\
                            'Temperature End Exp: ' + str( temp_end ) + ' K\n' +\
                            'Record Length: ' + str(real_length) + ' Points\n' + 'Time Resolution: ' + str(t_res_2) + ' us\n' + \
                            'Frequency: ' + str( round( ag53131a.freq_counter_frequency('CH3') / 1000000, 6) ) + ' GHz\n' + '2D Data'

                file_handler.save_data(file_save_1, np.transpose( data[0, :, :] ), header = header)
                file_handler.save_data(file_save_2, np.transpose( data[2, :, :] ), header = header_2)
                file_handler.save_data(file_save_3, np.transpose( data[4, :, :] ), header = header)

            while field > OFFRES_FIELD:
                field = bh15.magnet_field( field - initialization_step)
                field = field - initialization_step
            field = bh15.magnet_field( OFFRES_FIELD )
            field = OFFRES_FIELD

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
