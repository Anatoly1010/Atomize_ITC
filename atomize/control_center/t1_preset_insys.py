#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import numpy as np
from multiprocessing import Process, Pipe
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QDoubleSpinBox, QSpinBox, QPushButton, QTextEdit, QGridLayout, QFrame, QProgressBar
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QTimer
import atomize.general_modules.csv_opener_saver as openfile
#import atomize.control_center.status_poller as pol

class MainWindow(QMainWindow):
    """
    A main window class
    """
    def __init__(self, *args, **kwargs):
        """
        A function for connecting actions and creating a main window
        """
        super(MainWindow, self).__init__(*args, **kwargs)
        
        #####
        path_to_main2 = os.path.join(os.path.abspath(os.getcwd()), '..', 'libs')
        os.chdir(path_to_main2)
        #####

        self.design()
        self.exit_clicked = 0

        """
        Create a process to interact with an experimental script that will run on a different thread.
        We need a different thread here, since PyQt GUI applications have a main thread of execution that runs the event loop and GUI. If you launch a long-running task in this thread, then your GUI will freeze until the task terminates. During that time, the user won’t be able to interact with the application
        """
        #self.poller = pol.StatusPoller()
        #self.poller.status_received.connect(self.update_gui_status)
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_messages)
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.check_process_status)
        self.file_handler = openfile.Saver_Opener()

    def design(self):

        self.setObjectName("MainWindow")
        self.setWindowTitle("T1 Measurement")
        self.setStyleSheet("background-color: rgb(42,42,64);")

        path_to_main = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(path_to_main, 'gui/icon_t1.png')
        self.setWindowIcon( QIcon(icon_path) )

        centralwidget = QWidget(self)
        self.setCentralWidget(centralwidget)

        gridLayout = QGridLayout()
        gridLayout.setContentsMargins(15, 10, 10, 10)
        gridLayout.setVerticalSpacing(4)
        gridLayout.setHorizontalSpacing(20)

        centralwidget.setLayout(gridLayout)
        
        # ---- Labels & Inputs ----
        labels = [("Pi/2 Length", "label_1"), ("T", "label_2"), ("Tau", "label_3"), ("Time Step", "label_4"), ("Repetition Rate", "label_5"), ("Magnetic Field", "label_6"), ("Points", "label_7"), ("Acquisitions", "label_8"), ("Number of Scans", "label_9"), ("Experiment Name", "label_10"), ("Curve Name", "label_11"), ("Progress", "label_12")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            lbl.setFixedSize(180, 26)          
            setattr(self, attr_name, lbl)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # ---- Boxes ----
        double_boxes = [(QDoubleSpinBox, "box_length", "cur_length", self.pulse_length, 3.2, 1900, 19.2, 3.2, 1, " ns"),
                      (QDoubleSpinBox, "box_delta", "cur_delta", self.delta, 44.8, 640000, 640, 3.2, 1, " ns"),
                       (QDoubleSpinBox, "box_delta_echo", "cur_delta_echo", self.delta_echo, 44.8, 256000, 288, 3.2, 1, " ns"),
                      (QDoubleSpinBox, "box_time_step", "cur_step", self.time_step, 6.4, 5.12e6, 6.4, 6.4, 1, " ns"),
                      (QSpinBox, "box_rep_rate", "cur_rep_rate", self.rep_rate, 1, 50000, 500, 10, 0, " Hz"),
                      (QDoubleSpinBox, "box_field", "cur_field", self.field, 0, 15000, 3493, 0.5, 2, " G"),
                      (QSpinBox, "box_points", "cur_points", self.points, 1, 20000, 500, 10, 0, ""),
                      (QSpinBox, "box_averag", "cur_averages", self.averages, 1, 5000, 10, 1, 0, ""),
                      (QSpinBox, "box_scan", "cur_scan", self.scan, 1, 100, 1, 1, 0, "")
                        ]

        for widget_class, attr_name, par_name, func, v_min, v_max, cur_val, v_step, dec, suf in double_boxes:
            spin_box = widget_class()
            if isinstance(spin_box, QDoubleSpinBox):
                spin_box.setRange(v_min, v_max)
                spin_box.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97);}")                
            else:
                spin_box.setRange(int(v_min), int(v_max))
                spin_box.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97);}")                
            spin_box.setSingleStep(v_step)
            spin_box.setValue(cur_val)
            if isinstance(spin_box, QDoubleSpinBox):
                spin_box.setDecimals(dec)
            spin_box.setSuffix(suf)
            spin_box.valueChanged.connect(func)
            spin_box.setFixedSize(130, 26)
            spin_box.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)

            spin_box.setKeyboardTracking( False )
            
            setattr(self, attr_name, spin_box)
            if isinstance(spin_box, QDoubleSpinBox):
                setattr(self, par_name, round(float(spin_box.value()), 1))
            else:
                setattr(self, par_name, int(spin_box.value()))

        # ---- Text Edits ----
        text_edit = [("T1", "text_edit_exp_name", "cur_exp_name", self.exp_name),
                     ("exp1", "text_edit_curve", "cur_curve_name", self.curve_name)
                    ]

        for text, attr_name, par_name, func in text_edit:
            txt = QTextEdit(text)
            setattr(self, attr_name, txt)
            setattr(self, par_name, txt.toPlainText())
            txt.textChanged.connect(func)
            txt.setFixedSize(130, 26)
            txt.setAcceptRichText(False)
            txt.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            txt.setStyleSheet("QTextEdit { color : rgb(211, 194, 78) ; selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97);}")


        # ---- Buttons ----
        buttons = [("Start", "button_start", self.start),
                   ("Stop", "button_stop", self.stop),
                   ("Exit", "button_off", self.turn_off) ]

        for name, attr_name, func in buttons:
            btn = QPushButton(name)
            btn.setFixedSize(140, 40)
            btn.clicked.connect(func)
            btn.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; } QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
            setattr(self, attr_name, btn)

        # ---- Separators ----
        def hline():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            line.setLineWidth(2)
            return line


        # ---- Progress Bar ----
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedSize(130, 15)
        self.progress_bar.setTextVisible(True)
        #self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid rgb(83, 83, 117);
                border-radius: 4px;
                background-color: rgb(42, 42, 64);
                color: rgb(211, 194, 78);
                font-weight: bold;
                text-align: right; 
                margin-right: 40px;
                height: 20px;
            }

            QProgressBar::chunk {
                background-color: rgb(193, 202, 227);
                border-radius: 2px;
            }
        """)

        # ---- Layout placement ----
        gridLayout.addWidget(self.label_1, 0, 0)
        gridLayout.addWidget(self.box_length, 0, 1)
        gridLayout.addWidget(self.label_2, 1, 0)
        gridLayout.addWidget(self.box_delta, 1, 1)
        gridLayout.addWidget(self.label_3, 2, 0)
        gridLayout.addWidget(self.box_delta_echo, 2, 1)
        gridLayout.addWidget(self.label_4, 3, 0)
        gridLayout.addWidget(self.box_time_step, 3, 1)
        gridLayout.addWidget(self.label_5, 4, 0)
        gridLayout.addWidget(self.box_rep_rate, 4, 1)

        gridLayout.addWidget(hline(), 5, 0, 1, 2)

        gridLayout.addWidget(self.label_6, 6, 0)
        gridLayout.addWidget(self.box_field, 6, 1)

        gridLayout.addWidget(hline(), 7, 0, 1, 2)

        gridLayout.addWidget(self.label_7, 8, 0)
        gridLayout.addWidget(self.box_points, 8, 1)
        gridLayout.addWidget(self.label_8, 9, 0)
        gridLayout.addWidget(self.box_averag, 9, 1)
        gridLayout.addWidget(self.label_9, 10, 0)
        gridLayout.addWidget(self.box_scan, 10, 1)

        gridLayout.addWidget(hline(), 11, 0, 1, 2)

        gridLayout.addWidget(self.label_10, 12, 0)
        gridLayout.addWidget(self.text_edit_exp_name, 12, 1)
        gridLayout.addWidget(self.label_11, 13, 0)
        gridLayout.addWidget(self.text_edit_curve, 13, 1)

        gridLayout.addWidget(hline(), 14, 0, 1, 2)

        gridLayout.addWidget(self.label_12, 15, 0)
        gridLayout.addWidget(self.progress_bar, 15, 1)

        gridLayout.addWidget(hline(), 16, 0, 1, 2)

        gridLayout.addWidget(self.button_start, 17, 0)
        gridLayout.addWidget(self.button_stop, 18, 0)
        gridLayout.addWidget(self.button_off, 19, 0)

        gridLayout.setRowStretch(20, 2)
        gridLayout.setColumnStretch(20, 2)
    
    def round_to_closest(self, x, y):
        """
        A function to round x to divisible by y
        """
        return round(( y * ( ( x // y ) + (round(x % y, 2) > 0) ) ), 1)

    def round_and_change(self, doubleBox):
        """
        """
        raw = doubleBox.value()
        current = self.round_to_closest( raw, 3.2 )
        if current != raw:
            doubleBox.setValue( current )
        return doubleBox.value()

    def closeEvent(self, event):
        event.ignore()
        self.turn_off()

    def quit(self):
        """
        A function to quit the programm
        """
        self.turn_off()
        sys.exit()

    def curve_name(self):
        self.cur_curve_name = self.text_edit_curve.toPlainText()
        #print( self.cur_curve_name )

    def exp_name(self):
        self.cur_exp_name = self.text_edit_exp_name.toPlainText()
        #print( self.cur_exp_name )

    def delta(self):
        self.cur_delta = self.round_and_change(self.box_delta)
        if self.cur_delta - self.cur_length * 2 < 44.8:
            self.cur_delta = self.cur_length * 2 + 44.8
            self.box_delta.setValue( self.cur_delta )
    
    def delta_echo(self):
        self.cur_delta_echo = self.round_and_change(self.box_delta_echo)
        if self.cur_delta_echo - self.cur_length < 44.8:
            self.cur_delta_echo = self.cur_length + 44.8
            self.box_delta_echo.setValue( self.cur_delta_echo )

    def pulse_length(self):
        self.cur_length = self.round_and_change(self.box_length)
        if self.cur_delta - self.cur_length < 44.8:
            self.cur_delta = self.cur_length + 44.8
            self.box_delta.setValue( self.cur_delta )

    def time_step(self):
        self.cur_step =  self.round_and_change(self.box_time_step)

    def rep_rate(self):
        self.cur_rep_rate = int( self.box_rep_rate.value() )
        #print(self.cur_start_field)

    def points(self):
        self.cur_points = int( self.box_points.value() )
        #print(self.cur_start_field)

    def averages(self):
        self.cur_averages = int( self.box_averag.value() )
        #print(self.cur_start_field)

    def field(self):

        self.cur_field = round( float( self.box_field.value() ), 1 )
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
        self.exit_clicked = 1
        try:
            self.parent_conn.send( 'exit' )
            self.monitor_timer.start(200)
        except AttributeError:
            sys.exit()
            #self.message('Experimental script is not running')

    def check_process_status(self):
        if self.exp_process.is_alive():
            return
        
        self.monitor_timer.stop()
        self.exp_process.join() 
        self.timer.stop()
        self.progress_bar.setValue(0)
        self.button_start.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }  ")
        
        if self.exit_clicked == 1:
            sys.exit()

    def stop(self):
        """
        A function to stop script
        """
        try:
            self.parent_conn.send( 'exit' )
            self.monitor_timer.start(200)

        except AttributeError:
            pass
            #self.message('Experimental script is not running')
    
    def start(self):
        """
        Button Start; Run function script(pipe_addres, four parameters of the experimental script)
        from Worker class in a different thread
        Create a Pipe for interaction with this thread
        self.param_i are used as parameters for script function
        """
        worker = Worker()
        # prevent running two processes
        try:
            if self.exp_process.is_alive() == True:
                return
        except AttributeError:
            pass

        if self.cur_step*self.cur_points + self.cur_delta*2 >= 1000000000 / self.cur_rep_rate:
            self.cur_rep_rate = int( 1 / ( 10**-9 * (self.cur_step*self.cur_points + self.cur_delta*2) ) - 100 )
            if self.cur_rep_rate <= 0:
                self.cur_rep_rate = 2
            
            self.box_rep_rate.setValue( self.cur_rep_rate )


        self.parent_conn, self.child_conn = Pipe()
        # a process for running function script 
        # sending parameters for initial initialization
        self.exp_process = Process( target = worker.exp_test, args = ( self.child_conn, self.cur_curve_name, self.cur_exp_name, self.cur_delta, self.cur_length, self.cur_step, self.cur_rep_rate, self.cur_scan, self.cur_field, self.cur_points, self.cur_averages, self.cur_delta_echo, ) )

        self.button_start.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(211, 194, 78); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } ")
        self.progress_bar.setValue(0)

        self.exp_process.start()
        # send a command in a different thread about the current state
        self.parent_conn.send('start')

        #self.poller.update_command(self.parent_conn)
        #self.poller.start()
        self.is_testing = True
        self.timer.start(100)

    def message(self, *text):
        if len(text) == 1:
            print(f'{text[0]}', flush=True)
        else:
            print(f'{text}', flush=True)

    def update_gui_status(self, status_text):

        self.poller.wait() 

        if self.parent_conn.poll() == True:
            msg_type, data = self.parent_conn.recv()
            self.message(data)    
            self.button_start.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; } ")
        else:
            pass

    def check_messages(self):

        if not hasattr(self, 'last_error'):
            self.last_error = False

        while self.parent_conn.poll():
            try:
                msg_type, data = self.parent_conn.recv()
                
                if msg_type == 'Status':
                    self.progress_bar.setValue(int(data))
                elif msg_type == 'Open':
                    self.open_dialog()
                elif msg_type == 'Error':
                    self.last_error = True
                    self.timer.stop()
                    self.progress_bar.setValue(0)
                    if msg_type != 'test':
                        self.message(data)
                    self.button_start.setStyleSheet("""
                        QPushButton {
                            border-radius: 4px; 
                            background-color: rgb(63, 63, 97); 
                            border-style: outset; 
                            color: rgb(193, 202, 227); 
                            font-weight: bold; 
                        }
                    """)                    
                else:
                    self.timer.stop()
                    self.progress_bar.setValue(0)
                    if msg_type != 'test':
                        self.message(data)
                        self.button_start.setStyleSheet("""
                            QPushButton {
                                border-radius: 4px; 
                                background-color: rgb(63, 63, 97); 
                                border-style: outset; 
                                color: rgb(193, 202, 227); 
                                font-weight: bold; 
                            }
                        """)

            except EOFError:
                self.timer.stop()
                break
            except Exception as e:
                break

        time.sleep(0.1)

        if hasattr(self, 'exp_process') and not self.exp_process.is_alive():
            if self.parent_conn.poll():
                return

            self.timer.stop()

            if getattr(self, 'is_testing', False):
                self.is_testing = False
                if not self.last_error:
                    self.last_error = False 
                    time.sleep(0.1)
                    self.run_main_experiment()
                else:
                    self.last_error = False

    def open_dialog(self):
        file_data = self.file_handler.create_file_dialog(multiprocessing = True)

        if file_data:
            self.parent_conn.send( 'FL' + str( file_data ) )
        else:
            self.parent_conn.send( 'FL' + '' )

    def run_main_experiment(self):

        worker = Worker()
        self.parent_conn, self.child_conn = Pipe()
        
        self.exp_process = Process( target = worker.exp_on, args = ( self.child_conn, self.cur_curve_name, self.cur_exp_name, self.cur_delta, self.cur_length, self.cur_step, self.cur_rep_rate, self.cur_scan, self.cur_field, self.cur_points, self.cur_averages, self.cur_delta_echo, ) )
    
        self.exp_process.start()
        self.parent_conn.send('start')
        self.timer.start(100)

# The worker class that run the digitizer in a different thread
class Worker():
    def __init__(self):
        super(Worker).__init__()
        # initialization of the attribute we use to stop the experimental script

        self.command = 'start'
    
    def exp_on(self, conn, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p12):
        """
        function that contains experimental script
        """
        # [                1,                 2,              3,               4, ]
        #self.cur_curve_name, self.cur_exp_name, self.cur_delta, self.cur_length, 
        # [          5,                 6,             7,              8,               9,                10, ]
        #self.cur_step, self.cur_rep_rate, self.cur_scan, self.cur_field, self.cur_points, self.cur_averages, 
        # [               12 ]
        #self.cur_delta_echo

        # should be inside dig_on() function;
        # freezing after digitizer restart otherwise
        ##import random
        ##import time
        import traceback

        try:
            import datetime
            import numpy as np
            import atomize.general_modules.general_functions as general
            import atomize.device_modules.Insys_FPGA as pb_pro
            import atomize.device_modules.Micran_X_band_MW_bridge_v2 as mwBridge
            import atomize.device_modules.BH_15 as itc
            import atomize.device_modules.Lakeshore_335 as ls
            import atomize.general_modules.csv_opener_saver as openfile

            file_handler = openfile.Saver_Opener()
            ls335 = ls.Lakeshore_335()
            mw = mwBridge.Micran_X_band_MW_bridge_v2()
            pb = pb_pro.Insys_FPGA()
            bh15 = itc.BH_15()

            # parameters for initial initialization

            #POINTS = p9
            STEP = p5
            FIELD = p8
            AVERAGES = p10
            SCANS = p7
            process = 'None'

            # PULSES
            REP_RATE = str(p6) + ' Hz'
            PULSE_1_LENGTH = str( round(float(2*p4), 1) ) + ' ns'
            PULSE_2_LENGTH = str(p4) + ' ns'
            PULSE_3_LENGTH = str( round(float(2*p4), 1) ) + ' ns'
            PULSE_1_START = '0 ns'
            PULSE_2_START = str( p3 ) + ' ns'
            PULSE_3_START = str( round(float(p3 + p12), 1) ) + ' ns'
            PULSE_SIGNAL_START = str( round(p3 + float(2 * p12), 1) ) + ' ns'

            #
            PHASES = 4
            POINTS = p9
            data = np.zeros( ( 2, POINTS ) )
            x_axis = np.linspace(0, (POINTS - 1)*STEP, num = POINTS)
            ###

            bh15.magnet_field(FIELD)#, calibration = 'True')
            general.wait('4000 ms')

            adc_wind = pb.digitizer_read_settings()

            pb.pulser_pulse(name = 'P0', channel = 'MW', start = PULSE_1_START, length = PULSE_1_LENGTH, phase_list = ['+x', '-x', '+x', '-x'])
            pb.pulser_pulse(name = 'P1', channel = 'MW', start = PULSE_2_START, length = PULSE_2_LENGTH, delta_start = str(STEP) + ' ns', phase_list = ['+x', '+x','-x', '-x'])
            pb.pulser_pulse(name = 'P2', channel = 'MW', start = PULSE_3_START, length = PULSE_3_LENGTH, delta_start = str(STEP) + ' ns', phase_list = ['+x', '+x', '+x', '+x'])
            pb.pulser_pulse(name = 'P3', channel = 'DETECTION', start = PULSE_SIGNAL_START, length = f"{adc_wind} ns", delta_start = str(STEP) + ' ns', phase_list = ['+x', '+x', '-x', '-x'])

            pb.pulser_repetition_rate( REP_RATE )
            # read integration window
            pb.digitizer_number_of_averages(AVERAGES)

            pb.pulser_open()

            # the idea of automatic and dynamic changing is
            # sending a new value of repetition rate via self.command
            # in each cycle we will check the current value of self.command
            # self.command = 'exit' will stop the digitizer
            while self.command != 'exit':

                # Start of experiment
                for k in general.scans(SCANS):

                    if self.command == 'exit':
                        break

                    for j in range(POINTS):
                        # phase cycle
                        for i in range(PHASES):

                            pb.pulser_next_phase()
                            general.plot_1d(p2, x_axis / 1e9, ( data[0], data[1] ), xname = 'T', xscale = 's', yname = 'Area', yscale = 'A.U.', label = p1, text = 'Scan / Time: ' + str(k) + ' / ' + str(round(j*STEP, 1)))
                            data[0], data[1] = pb.digitizer_get_curve( POINTS, PHASES, current_scan = k, total_scan = SCANS, integral = True )

                        pb.pulser_shift()
                        conn.send( ('Status', int( 100 * ((k - 1) * POINTS + j + 1) / POINTS / SCANS)) )
                        
                        # check our polling data
                        if self.command[0:2] == 'SC':
                            SCANS = int( self.command[2:] )
                            self.command = 'start'
                        elif self.command == 'exit':
                            if np.isnan(data[0][0]):
                                pass
                            else:
                                break
                        
                        if conn.poll() == True:
                            self.command = conn.recv()

                    general.plot_1d(p2, x_axis  / 1e9, ( data[0], data[1] ), xname = 'T', xscale = 's', yname = 'Area', yscale = 'A.U.', label = p1, text = 'Scan / Time: ' + str(k) + ' / ' + str(round(j*STEP, 1)))

                    pb.pulser_pulse_reset()

                # finish succesfully
                self.command = 'exit'

            if self.command == 'exit':
                
                tb = round( pb.digitizer_window(), 1)
                pb.pulser_close()

                now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                w = 30

                header = (
                    f"{'Date:':<{w}} {now}\n"
                    f"{'Experiment:':<{w}} T1 Inversion Recovery Measurement\n"
                    f"{'Field:':<{w}} {FIELD} G\n"
                    f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att1_prd(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
                    f"{'Repetition Rate:':<{w}} {pb.pulser_repetition_rate()}\n"
                    f"{'Number of Scans:':<{w}} {SCANS}\n"
                    f"{'Averages:':<{w}} {AVERAGES}\n"
                    f"{'Points:':<{w}} {POINTS}\n"
                    f"{'Window:':<{w}} {tb} ns\n"
                    f"{'Horizontal Resolution:':<{w}} {STEP} ns\n"
                    f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
                    f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                    f"{'-'*50}\n"
                    f"Pulse List:\n{pb.pulser_pulse_list()}"
                    f"{'-'*50}\n"
                    f"T (ns), I (A.U.), Q (A.U.)"
                )

                conn.send(('Open', ''))
                
                while True:
                    if conn.poll():
                        msg = conn.recv()
                        if msg.startswith('FL'):
                            file_data = msg[2:]
                            break
                    general.wait('200 ms')

                file_handler.save_data(file_data, np.c_[x_axis, data[0], data[1]], header = header, mode = 'w')

                conn.send( ('', f'Script {p2} finished') )
                general.wait('200 ms')
                conn.close()

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )

    def exp_test(self, conn, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p12):
        """
        function that contains experimental script
        """
        # [                1,                 2,              3,               4, ]
        #self.cur_curve_name, self.cur_exp_name, self.cur_delta, self.cur_length, 
        # [          5,                 6,             7,              8,               9,                10, ]
        #self.cur_step, self.cur_rep_rate, self.cur_scan, self.cur_field, self.cur_points, self.cur_averages, 
        # [               12 ]
        #self.cur_delta_echo

        # should be inside dig_on() function;
        # freezing after digitizer restart otherwise
        ##import random
        ##import time
        import traceback

        sys.argv = ['', 'test']

        try:
            import datetime
            import numpy as np
            import atomize.general_modules.general_functions as general
            general.test_flag = 'test'
            import atomize.device_modules.Insys_FPGA as pb_pro
            import atomize.device_modules.Micran_X_band_MW_bridge_v2 as mwBridge
            import atomize.device_modules.BH_15 as itc
            import atomize.device_modules.Lakeshore_335 as ls
            import atomize.general_modules.csv_opener_saver as openfile

            file_handler = openfile.Saver_Opener()
            ls335 = ls.Lakeshore_335()
            mw = mwBridge.Micran_X_band_MW_bridge_v2()
            pb = pb_pro.Insys_FPGA()
            bh15 = itc.BH_15()

            # parameters for initial initialization

            #POINTS = p9
            STEP = p5
            FIELD = p8
            AVERAGES = p10
            SCANS = p7
            process = 'None'

            # PULSES
            REP_RATE = str(p6) + ' Hz'
            PULSE_1_LENGTH = str( round(float(2*p4), 1) ) + ' ns'
            PULSE_2_LENGTH = str(p4) + ' ns'
            PULSE_3_LENGTH = str( round(float(2*p4), 1) ) + ' ns'
            PULSE_1_START = '0 ns'
            PULSE_2_START = str( p3 ) + ' ns'
            PULSE_3_START = str( round(float(p3 + p12), 1) ) + ' ns'
            PULSE_SIGNAL_START = str( round(p3 + float(2 * p12), 1) ) + ' ns'

            #
            PHASES = 4
            POINTS = p9
            data = np.zeros( ( 2, POINTS ) )
            x_axis = np.linspace(0, (POINTS - 1)*STEP, num = POINTS)
            ###

            bh15.magnet_field(FIELD)#, calibration = 'True')
            general.wait('4000 ms')

            adc_wind = pb.digitizer_read_settings()

            pb.pulser_pulse(name = 'P0', channel = 'MW', start = PULSE_1_START, length = PULSE_1_LENGTH, phase_list = ['+x', '-x', '+x', '-x'])
            pb.pulser_pulse(name = 'P1', channel = 'MW', start = PULSE_2_START, length = PULSE_2_LENGTH, delta_start = str(STEP) + ' ns', phase_list = ['+x', '+x','-x', '-x'])
            pb.pulser_pulse(name = 'P2', channel = 'MW', start = PULSE_3_START, length = PULSE_3_LENGTH, delta_start = str(STEP) + ' ns', phase_list = ['+x', '+x', '+x', '+x'])
            pb.pulser_pulse(name = 'P3', channel = 'DETECTION', start = PULSE_SIGNAL_START, length = f"{adc_wind} ns", delta_start = str(STEP) + ' ns', phase_list = ['+x', '+x', '-x', '-x'])

            pb.pulser_repetition_rate( REP_RATE )
            # read integration window
            pb.digitizer_number_of_averages(AVERAGES)

            pb.pulser_open()

            # the idea of automatic and dynamic changing is
            # sending a new value of repetition rate via self.command
            # in each cycle we will check the current value of self.command
            # self.command = 'exit' will stop the digitizer
            while self.command != 'exit':

                # Start of experiment
                for k in general.scans(SCANS):

                    if self.command == 'exit':
                        break

                    for j in range(POINTS):
                        # phase cycle
                        for i in range(PHASES):

                            pb.pulser_next_phase()
                            general.plot_1d(p2, x_axis / 1e9, ( data[0], data[1] ), xname = 'T', xscale = 's', yname = 'Area', yscale = 'A.U.', label = p1, text = 'Scan / Time: ' + str(k) + ' / ' + str(round(j*STEP, 1)))
                            data[0], data[1] = pb.digitizer_get_curve( POINTS, PHASES, current_scan = k, total_scan = SCANS, integral = True )

                        pb.pulser_shift()
                        #conn.send( ('Status', int( 100 * ((k - 1) * POINTS + j + 1) / POINTS / SCANS)) )
                        
                        # check our polling data
                        if self.command[0:2] == 'SC':
                            SCANS = int( self.command[2:] )
                            self.command = 'start'
                        elif self.command == 'exit':
                            if np.isnan(data[0][0]):
                                pass
                            else:
                                break
                        
                        if conn.poll() == True:
                            self.command = conn.recv()

                    general.plot_1d(p2, x_axis  / 1e9, ( data[0], data[1] ), xname = 'T', xscale = 's', yname = 'Area', yscale = 'A.U.', label = p1, text = 'Scan / Time: ' + str(k) + ' / ' + str(round(j*STEP, 1)))

                    pb.pulser_pulse_reset()

                # finish succesfully
                self.command = 'exit'

            if self.command == 'exit':
                
                tb = round( pb.digitizer_window(), 1)
                pb.pulser_close()

                now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                w = 30

                header = (
                    f"{'Date:':<{w}} {now}\n"
                    f"{'Experiment:':<{w}} T1 Inversion Recovery Measurement\n"
                    f"{'Field:':<{w}} {FIELD} G\n"
                    f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att1_prd(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
                    f"{'Repetition Rate:':<{w}} {pb.pulser_repetition_rate()}\n"
                    f"{'Number of Scans:':<{w}} {SCANS}\n"
                    f"{'Averages:':<{w}} {AVERAGES}\n"
                    f"{'Points:':<{w}} {POINTS}\n"
                    f"{'Window:':<{w}} {tb} ns\n"
                    f"{'Horizontal Resolution:':<{w}} {STEP} ns\n"
                    f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
                    f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                    f"{'-'*50}\n"
                    f"Pulse List:\n{pb.pulser_pulse_list()}"
                    f"{'-'*50}\n"
                    f"T (ns), I (A.U.), Q (A.U.)"
                )

                #conn.send(('Open', ''))
                
                #while True:
                #    if conn.poll():
                #        msg = conn.recv()
                #        if msg.startswith('FL'):
                #            file_data = msg[2:]
                #            break
                #    general.wait('200 ms')

                #file_handler.save_data(file_data, np.c_[x_axis, data[0], data[1]], header = header, mode = 'w')

                conn.send( ('test', f'Script {p2} finished') )
                conn.close()

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )

def main():
    """
    A function to run the main window of the programm.
    """
    app = QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
