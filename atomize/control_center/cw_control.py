#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import random
import datetime
import socket
import numpy as np
from multiprocessing import Process, Pipe
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QDoubleSpinBox, QSpinBox, QComboBox, QPushButton, QTextEdit, QGridLayout, QFrame, QCheckBox
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt
import atomize.control_center.status_poller as pol

class MainWindow(QMainWindow):
    """
    A main window class
    """
    def __init__(self, *args, **kwargs):
        """
        A function for connecting actions and creating a main window
        """
        super(MainWindow, self).__init__(*args, **kwargs)

        self.two_side = 0
        self.design()

        """
        Create a process to interact with an experimental script that will run on a different thread.
        We need a different thread here, since PyQt GUI applications have a main thread of execution that runs the event loop and GUI. If you launch a long-running task in this thread, then your GUI will freeze until the task terminates. During that time, the user won’t be able to interact with the application
        """
        self.worker = Worker()
        self.poller = pol.StatusPoller()
        self.poller.status_received.connect(self.update_gui_status)        

    def design(self):

        self.destroyed.connect(lambda: self._on_destroyed())
        self.setObjectName("MainWindow")
        self.setWindowTitle("CW EPR")
        self.setStyleSheet("background-color: rgb(42,42,64);")

        path_to_main = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(path_to_main, 'gui/icon_cw.png')
        self.setWindowIcon( QIcon(icon_path) )

        centralwidget = QWidget(self)
        self.setCentralWidget(centralwidget)

        gridLayout = QGridLayout()
        gridLayout.setContentsMargins(15, 10, 10, 10)
        gridLayout.setVerticalSpacing(4)
        gridLayout.setHorizontalSpacing(20)

        centralwidget.setLayout(gridLayout)


        # ---- Labels & Inputs ----
        labels = [("Start Field", "label_1"), ("End Field", "label_2"), ("Field Step", "label_3"), ("Lock In Amplitude", "label_4"), ("Lock In Time Constant", "label_5"), ("Lock In Sensitivity", "label_6"), ("Number of Scans", "label_7"), ("Two-Side Measurement", "label_8"), ("Experiment Name", "label_9"), ("Curve Name", "label_10")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            setattr(self, attr_name, lbl)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")


        # ---- Boxes ----
        double_boxes = [(QDoubleSpinBox, "box_st_field", "cur_start_field", self.st_field, 0, 15000, 3000, 1, 1, " G"),
                      (QDoubleSpinBox, "box_end_field", "cur_end_field", self.end_field, 0, 15000, 4000, 1, 1, " G"),
                      (QDoubleSpinBox, "box_step_field", "cur_step", self.step_field, 0.01, 50, 0.5, 0.1, 2, " G"),
                      (QDoubleSpinBox, "box_lock_ampl", "cur_lock_ampl", self.lock_ampl, 0.001, 2.0, 2.0, 0.1, 3, " V"),
                      (QSpinBox, "box_scan", "cur_scan", self.scan, 1, 100, 1, 1, 0, "")
                        ]

        for widget_class, attr_name, par_name, func, v_min, v_max, cur_val, v_step, dec, suf in double_boxes:
            spin_box = widget_class()
            if isinstance(spin_box, QDoubleSpinBox):
                spin_box.setRange(v_min, v_max)
                spin_box.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97); }")
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
                setattr(self, par_name, float(spin_box.value()))
            else:
                setattr(self, par_name, int(spin_box.value()))


        # ---- Combo boxes----
        combo_boxes = [("30 ms", "combo_tc", "cur_tc", self.lock_tc, 
                        [
                        "1 s", "300 ms", "100 ms", "30 ms", "10 ms",
                        "3 ms", "1 ms", "300 us", "100 us", "30 us",
                        "10 us", "3 us", "1 us"
                        ]),
                      ("200 mV", "combo_sens", "cur_sens", self.lock_sens, 
                        [
                        "1 V", "500 mV", "200 mV", "100 mV", "50 mV",
                        "20 mV", "10 mV", "5 mV", "2 mV", "1 mV",
                        "500 uV", "200 uV", "100 uV"
                        ])
                      ]

        for cur_text, attr_name, par_name, func, item in combo_boxes:
            combo = QComboBox()
            setattr(self, attr_name, combo)
            setattr(self, par_name, combo.currentText())
            combo.currentIndexChanged.connect(func)
            combo.addItems(item)
            combo.setCurrentText(cur_text)
            combo.setFixedSize(130, 26)
            combo.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")

        # ---- Text Edits ----
        text_edit = [("CW", "text_edit_exp_name", "cur_exp_name", self.curve_name),
                     ("exp1", "text_edit_curve", "cur_curve_name", self.exp_name)
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


        # ---- Check Boxes ----
        check_boxes = [("checkbox_back_scan", self.two_side_measure)]

        for attr_name, func in check_boxes:
            check = QCheckBox("")
            setattr(self, attr_name, check)
            check.stateChanged.connect(func)
            check.setStyleSheet("""
                QCheckBox { 
                    color: rgb(193, 202, 227); 
                    background-color: transparent; 
                    font-weight: bold;
                    spacing: 8px; 
                }

                QCheckBox::indicator {
                    width: 14px;
                    height: 14px;
                    background-color: rgb(63, 63, 97);
                    border: 1px solid rgb(83, 83, 117);
                    border-radius: 3px;
                }

                QCheckBox::indicator:hover {
                    border: 1px solid rgb(211, 194, 78);
                }

                QCheckBox::indicator:pressed {
                    background-color: rgb(83, 83, 117);
                }

                QCheckBox::indicator:checked {
                    background-color: rgb(211, 194, 78);
                    border: 3px solid rgb(63, 63, 97); 
                }
            """)

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


        # ---- Layout placement ----
        gridLayout.addWidget(self.label_1, 0, 0)
        gridLayout.addWidget(self.box_st_field, 0, 1)
        gridLayout.addWidget(self.label_2, 1, 0)
        gridLayout.addWidget(self.box_end_field, 1, 1)
        gridLayout.addWidget(self.label_3, 2, 0)
        gridLayout.addWidget(self.box_step_field, 2, 1)

        gridLayout.addWidget(hline(), 3, 0, 1, 2)

        gridLayout.addWidget(self.label_4, 4, 0)
        gridLayout.addWidget(self.box_lock_ampl, 4, 1)

        gridLayout.addWidget(self.label_5, 5, 0)
        gridLayout.addWidget(self.combo_tc, 5, 1)

        gridLayout.addWidget(self.label_6, 6, 0)
        gridLayout.addWidget(self.combo_sens, 6, 1)

        gridLayout.addWidget(hline(), 7, 0, 1, 2)

        gridLayout.addWidget(self.label_7, 8, 0)
        gridLayout.addWidget(self.box_scan, 8, 1)
        gridLayout.addWidget(self.label_8, 9, 0)
        gridLayout.addWidget(self.checkbox_back_scan, 9, 1)

        gridLayout.addWidget(hline(), 10, 0, 1, 2)

        gridLayout.addWidget(self.label_9, 11, 0)
        gridLayout.addWidget(self.text_edit_exp_name, 11, 1)
        gridLayout.addWidget(self.label_10, 12, 0)
        gridLayout.addWidget(self.text_edit_curve, 12, 1)

        gridLayout.addWidget(hline(), 13, 0, 1, 2)

        gridLayout.addWidget(self.button_start, 14, 0)
        gridLayout.addWidget(self.button_stop, 15, 0)
        gridLayout.addWidget(self.button_off, 16, 0)

        gridLayout.setRowStretch(17, 2)
        gridLayout.setColumnStretch(17, 2)

    def two_side_measure(self):
        """
        Turn on/off backward measurement
        """
        if self.checkbox_back_scan.checkState().value == 2: # checked
            self.two_side = 1
        elif self.checkbox_back_scan.checkState().value == 0: # unchecked
            self.two_side = 0

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

    def st_field(self, value):
        """
        A function to send a start field value
        """
        self.cur_start_field = round( float( value ), 3 )
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
            pass
            #self.message('Experimental script is not running')

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

    def update_gui_status(self, status_text):

        self.poller.wait() 

        if self.parent_conn.poll() == True:
            msg_type, data = self.parent_conn.recv()
            self.message(data)            
            self.button_start.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; } ")   
        else:
            pass

    def stop(self):
        """
        A function to stop script
        """
        try:
            self.button_start.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }  ")
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
        self.exp_process = Process( target = self.worker.exp_on, args = ( self.child_conn, self.cur_curve_name, self.cur_exp_name, self.cur_end_field, self.cur_start_field, self.cur_step, self.cur_lock_ampl, self.cur_scan, self.cur_tc, self.cur_sens, self.two_side, ) )
        
        self.button_start.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(211, 194, 78); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } ")

        self.exp_process.start()
        # send a command in a different thread about the current state
        self.parent_conn.send('start')

        self.poller.update_command(self.parent_conn)
        self.poller.start()

    def message(self, *text):
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
        # [          5,                 6,              7,           8,             9,     ]
        #self.cur_step, self.cur_lock_ampl, self.cur_scan, self.cur_tc, self.cur_sens, 
        #           10,     ]
        #self.two_side,

        # should be inside dig_on() function;
        # freezing after digitizer restart otherwise
        import traceback

        try:
            import atomize.general_modules.general_functions as general
            import atomize.device_modules.SR_860 as sr
            #import atomize.device_modules.ITC_FC as itc
            import atomize.device_modules.BH_15 as itc
            import atomize.device_modules.Lakeshore_335 as ls
            import atomize.device_modules.Agilent_53131a as ag
            import atomize.general_modules.csv_opener_saver_tk_kinter as openfile

            file_handler = openfile.Saver_Opener()
            ag53131a = ag.Agilent_53131a()
            ls335 = ls.Lakeshore_335()
            sr860 = sr.SR_860()
            #itc_fc = itc.ITC_FC()
            itc_fc = itc.BH_15()

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
            sr860.lock_in_ref_amplitude( f'{p6} V' )
            sr860.lock_in_phase( 159.6 - 0 ) #159.6
            sr860.lock_in_ref_frequency( '100 kHz' )

            t_start = str( ls335.tc_temperature('A') )
            
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

                field = itc_fc.magnet_field( START_FIELD )#, calibration = 'True' )
                general.wait('4000 ms')

                sr860.lock_in_sensitivity( p9 )

                j = 1
                while j <= SCANS:

                    i = 0
                    field = START_FIELD
                    if p10 == 0:
                        general.wait('2000 ms')
                    elif p10 == 1:
                        pass

                    if self.command == 'exit':
                        break

                    while field <= END_FIELD:
                        
                        #if tc_wait == 1:
                        general.wait( p8 )
                            #general.wait('10 ms')

                        if p10 == 0:
                            data[i] = ( data[i] * (j - 1) + sr860.lock_in_get_data() ) / j
                        elif p10 == 1:
                            data[i] = ( data[i] * (2*j - 2) + sr860.lock_in_get_data() ) / (2*j - 1)

                        process = general.plot_1d( p2, x_axis, data, xname = 'Field',
                            xscale = 'G', yname = 'Intensity', yscale = 'V', label = p1, 
                            text = 'Scan / Field: ' + str(j) + ' / ' + str(field), pr = process )

                        field = round( (FIELD_STEP + field), 3 )
                        itc_fc.magnet_field(field) #, calibration = 'True')

                        # check our polling data
                        if self.command[0:2] == 'SC':
                            SCANS = int( self.command[2:] )
                            self.command = 'start'
                        elif self.command == 'exit':
                            break
                        
                        if conn.poll() == True:
                            self.command = conn.recv()

                        i += 1

                    if p10 == 0:

                        while field > START_FIELD:
                            field = itc_fc.magnet_field( field - initialization_step)
                            field = field - initialization_step

                    elif p10 == 1:
                        while field > START_FIELD:

                            i -= 1
                            #if tc_wait == 1:
                            general.wait( p8 )
                                #general.wait('10 ms')
                            
                            field = round( (-FIELD_STEP + field), 3 )
                            itc_fc.magnet_field(field) #, calibration = 'True')
                            
                            data[i] = ( data[i] * (2*j - 1) + sr860.lock_in_get_data() ) / (2*j)

                            process = general.plot_1d( p2, x_axis, data, xname = 'Field',
                                xscale = 'G', yname = 'Intensity', yscale = 'V', label = p1,
                                text = 'Scan / Field: ' + str(j) + ' / ' + str(field), 
                                pr = process )

                            # check our polling data
                            if self.command[0:2] == 'SC':
                                SCANS = int( self.command[2:] )
                                self.command = 'start'
                            elif self.command == 'exit':
                                break
                            
                            if conn.poll() == True:
                                self.command = conn.recv()
                    
                    j += 1

                # finish succesfully
                self.command = 'exit'

            if self.command == 'exit':
                #general.message(f'Script {p2} finished')
                sr860.lock_in_sensitivity( '1 V' )
                while field > START_FIELD:
                    field = itc_fc.magnet_field( field - initialization_step )
                    field = field - initialization_step 

                now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                w = 25

                # Data saving
                header = (
                    f"{'Date:':<{w}} {now}\n"
                    f"{'Experiment:':<{w}} Continuous Wave EPR Spectrum\n"
                    f"{'Start Field:':<{w}} {START_FIELD} G\n"
                    f"{'End Field:':<{w}} {END_FIELD} G\n"
                    f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                    f"{'Number of Scans:':<{w}} {SCANS}\n"
                    f"{'Temperature Start Exp:':<{w}} {t_start} K\n"
                    f"{'Temperature End Exp:':<{w}} {ls335.tc_temperature('A')} K\n"
                    f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                    f"{'Time Constant:':<{w}} {p8}\n"
                    f"{'Modulation Ampl:':<{w}} {p6} V\n"
                    f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                    f"{'-'*50}\n"
                    f"Field (G), X (V)"
                )

                file_data, file_param = file_handler.create_file_parameters('.param')
                file_handler.save_data(file_data, np.c_[x_axis, data], header = header, mode = 'w')

                conn.send( ('', f'Script {p2} finished') )

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
