#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
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
        
        self.save_scan = 0
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
        self.setWindowTitle("TR EPR")
        self.setStyleSheet("background-color: rgb(42,42,64);")

        path_to_main = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(path_to_main, 'gui/icon_tr.png')
        self.setWindowIcon( QIcon(icon_path) )

        centralwidget = QWidget(self)
        self.setCentralWidget(centralwidget)

        gridLayout = QGridLayout()
        gridLayout.setContentsMargins(15, 10, 10, 10)
        gridLayout.setVerticalSpacing(4)
        gridLayout.setHorizontalSpacing(20)

        centralwidget.setLayout(gridLayout)

        # ---- Labels & Inputs ----
        labels = [("Start Field", "label_1"), ("End Field", "label_2"), ("Field Step", "label_3"), ("Off-Resonance Field", "label_4"), ("Off-Resonance Acquisitions", "label_5"), ("Acquisitions", "label_6"), ("Number of Scans", "label_7"), ("Save Each Scan", "label_8"), ("Two-Side Measurement", "label_9"), ("Number of Oscilloscopes", "label_10"), ("Trigger Channel", "label_11"), ("Experiment Name", "label_12")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            setattr(self, attr_name, lbl)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")


        # ---- Boxes ----
        double_boxes = [(QDoubleSpinBox, "box_st_field", "cur_start_field", self.st_field, 0, 15000, 3000, 1, 1, " G"),
                      (QDoubleSpinBox, "box_end_field", "cur_end_field", self.end_field, 0, 15000, 4000, 1, 1, " G"),
                      (QDoubleSpinBox, "box_step_field", "cur_step", self.step_field, 0.01, 50, 0.5, 0.1, 2, " G"),
                      (QDoubleSpinBox, "box_off_res_field", "cur_offres_field", self.offres_field, 0, 15000, 500, 1, 1, " G"),
                      (QSpinBox, "box_ave", "cur_ave", self.ave, 2, 2000, 10, 1, 0, ""),
                      (QSpinBox, "box_ave_offres", "cur_ave_offres", self.ave_offres, 2, 2000, 10, 1, 0, ""),
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
                setattr(self, par_name, float(spin_box.value()))
            else:
                setattr(self, par_name, int(spin_box.value()))


        # ---- Combo boxes----
        combo_boxes = [("1", "combo_num_osc", "cur_num_osc", self.num_osc, 
                        [
                        "1", "2", "2 + THz Pulse"
                        ]),
                      ("CH2", "combo_trig_ch", "cur_trig_ch", self.trig_ch, 
                        [
                        "CH2", "Ext"
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

            if par_name == 'cur_num_osc' and len( str( self.cur_num_osc ) ) > 1:
                self.cur_num_osc = 3
            elif par_name == 'cur_num_osc':
                self.cur_num_osc = int( self.cur_num_osc )

        # ---- Text Edits ----
        text_edit = [("TR", "text_edit_exp_name", "cur_exp_name", self.exp_name),
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
        check_boxes = [("checkbox_back_scan", self.two_side_measure),
                       ("check_scan", self.save_each_scan)
                       ]

        for attr_name, func in check_boxes:
            check = QCheckBox("")
            setattr(self, attr_name, check)
            check.stateChanged.connect(func)
            check.setFixedSize(130, 26)
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
        gridLayout.addWidget(self.label_4, 3, 0)
        gridLayout.addWidget(self.box_off_res_field, 3, 1)

        gridLayout.addWidget(hline(), 4, 0, 1, 2)

        gridLayout.addWidget(self.label_5, 5, 0)
        gridLayout.addWidget(self.box_ave_offres, 5, 1)
        gridLayout.addWidget(self.label_6, 6, 0)
        gridLayout.addWidget(self.box_ave, 6, 1)
        gridLayout.addWidget(self.label_7, 7, 0)
        gridLayout.addWidget(self.box_scan, 7, 1)
        gridLayout.addWidget(self.label_8, 8, 0)
        gridLayout.addWidget(self.check_scan, 8, 1)
        gridLayout.addWidget(self.label_9, 9, 0)
        gridLayout.addWidget(self.checkbox_back_scan, 9, 1)

        gridLayout.addWidget(hline(), 10, 0, 1, 2)

        gridLayout.addWidget(self.label_10, 11, 0)
        gridLayout.addWidget(self.combo_num_osc, 11, 1)
        gridLayout.addWidget(self.label_11, 12, 0)
        gridLayout.addWidget(self.combo_trig_ch, 12, 1)

        gridLayout.addWidget(hline(), 13, 0, 1, 2)

        gridLayout.addWidget(self.label_12, 14, 0)
        gridLayout.addWidget(self.text_edit_exp_name, 14, 1)

        gridLayout.addWidget(hline(), 15, 0, 1, 2)

        gridLayout.addWidget(self.button_start, 16, 0)
        gridLayout.addWidget(self.button_stop, 17, 0)
        gridLayout.addWidget(self.button_off, 18, 0)

        gridLayout.setRowStretch(19, 2)
        gridLayout.setColumnStretch(19, 2)

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
            pass
            #self.message('Experimental script is not running')

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
            pass
            #self.message('Experimental script is not running')

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
                                            self.cur_ave, self.cur_num_osc, self.cur_trig_ch, self.save_scan, self.two_side, ) )
            

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

    def update_gui_status(self, status_text):

        self.poller.wait() 

        if self.parent_conn.poll() == True:
            msg_type, data = self.parent_conn.recv()
            self.message(data)    
            self.button_start.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; } ")
        else:
            pass


# The worker class that run the digitizer in a different thread
class Worker(QWidget):
    def __init__(self, parent = None):
        super(Worker, self).__init__(parent)
        # initialization of the attribute we use to stop the experimental script

        self.command = 'start'
                   
    def exp_on(self, conn, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12):
        """
        function that contains experimental script
        """
        # [                  1,                 2,                  3,                    4, ]
        #self.cur_offres_field, self.cur_exp_name, self.cur_end_field, self.cur_start_field, 
        # [          5,                   6,              7,           8,                9,               10,             11,       12 ]
        #self.cur_step, self.cur_ave_offres, self.cur_scan, self.cur_ave, self.cur_num_osc, self.cur_trig_ch, self.save_scan, self.two_side,

        # should be inside dig_on() function;
        # freezing after digitizer restart otherwise
        import traceback

        try:
            import sys
            import atomize.general_modules.general_functions as general
            import atomize.device_modules.Keysight_2000_Xseries as key
            import atomize.device_modules.Keysight_2000_Xseries_2 as key2
            import atomize.device_modules.BH_15 as itc
            import pyqtgraph as pg
            #import atomize.device_modules.ITC_FC as itc
            import atomize.device_modules.Lakeshore_335 as ls
            import atomize.device_modules.Agilent_53131a as ag
            import atomize.general_modules.csv_opener_saver_tk_kinter as openfile

            w = 30
            file_handler = openfile.Saver_Opener()
            process = 'None'
            ag53131a = ag.Agilent_53131a()
            ls335 = ls.Lakeshore_335()
            a2012 = key.Keysight_2000_Xseries()
            #bh15 = itc.ITC_FC()
            bh15 = itc.BH_15()
            
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

            a2012.oscilloscope_record_length( 4000 )
            try:
                real_length = a2012.oscilloscope_record_length( )
            except ZeroDivisionError:
                general.message('Incorrect Trigger Channel')

            ##t_res = round( a2012.oscilloscope_timebase() / real_length, 7 )    # in us
            ##t_res_rough = round( t_res, 3 )
            t_res = a2012.oscilloscope_time_resolution()
            t_step = float(f"{pg.siEval(t_res):.4g}")

            ##real_length = 4000
            if p9 > 1:
                a2012_2.oscilloscope_record_length( 4000 )
                try:
                    real_length_2 = a2012_2.oscilloscope_record_length( )
                except ZeroDivisionError:
                    general.message('Incorrect Trigger Channel')                
                #print(a2012_2.oscilloscope_record_length( ))
                #t_res_2 = round( a2012_2.oscilloscope_timebase() / real_length, 7 ) # in us
                #t_res_2_rough = round( t_res_2, 3 )
                t_res_2 = a2012_2.oscilloscope_time_resolution()
                t_step_2 = float(f"{pg.siEval(t_res_2):.4g}")

            # parameters for initial initialization
            field = 100
            START_FIELD = p4
            END_FIELD = p3
            FIELD_STEP = p5
            OFFRES_FIELD = p1
            initialization_step = 10
            SCANS = p7
            points = int( (END_FIELD - START_FIELD) / FIELD_STEP ) + 1

            #bh15.magnet_setup( 100, FIELD_STEP)

            if p9 == 1:
                data = np.zeros( (2, real_length, points + 1) )
            elif p9 == 2:
                data = np.zeros( (2, real_length, points + 1) )
                data_2 = np.zeros( (2, real_length_2, points + 1) )
            else:
                data = np.zeros( (3, real_length, points + 1) )
                data_2 = np.zeros( (2, real_length_2, points + 1) )
            
            temp_start = str( ls335.tc_temperature('A') )

            # Oscilloscopes bugs
            #a2012.oscilloscope_number_of_averages(2)
            #if p9 > 1:
            #    a2012_2.oscilloscope_number_of_averages(2)

            #a2012.oscilloscope_start_acquisition()
            #if p9 > 1:
            #    a2012_2.oscilloscope_start_acquisition()
            
            #if p9 == 1:
            #    y = a2012.oscilloscope_get_curve('CH1')

            #elif p9 == 2:
            #    y = a2012.oscilloscope_get_curve('CH1')
            #    y2 = a2012_2.oscilloscope_get_curve('CH1')

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

                    now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                    temp_end = str( ls335.tc_temperature('A') )

                    header = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off Res Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )
                    
                    file_handler.save_header(file_save_1, header = header, mode = 'w')
                elif p9 == 2:
                    file_save_1, file_save_2 = file_handler.create_file_parameters('_osc2.csv')

                    now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                    temp_end = str( ls335.tc_temperature('A') )

                    header = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off Res Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    header_2 = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum (Header 2)\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off Res Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res_2}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*w}\n"
                        f"2D Data"
                    )

                    file_handler.save_header(file_save_1, header = header, mode = 'w')
                    file_handler.save_header(file_save_2, header = header_2, mode = 'w')

                elif p9 == 3:
                    file_save_1, file_save_2 = file_handler.create_file_parameters('_osc2.csv')
                    file_save_3 = file_save_1.split('.csv')[0] + '_pulse.csv'

                    now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                    temp_end = str( ls335.tc_temperature('A') )

                    header = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off Res Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temp Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temp End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    header_2 = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum (Header 2)\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off Res Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res_2}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*w}\n"
                        f"2D Data"
                    )

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
                        data_2[0, :, 0] = ( data_2[0, :, 0] * (j - 1) + y2 ) / j
                        data_2[1, :, 0] = ( data_2[0, :, 0] - data_2[0, :, 0] )
                        data_2[1, :, :] = ( data_2[1, :, :] - data_2[1, 0, :] )

                    elif p9 == 3:
                        y = a2012.oscilloscope_get_curve('CH1')
                        ##y = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                        data[0, :, 0] = ( data[0, :, 0] * (j - 1) + y ) / j
                        data[1, :, 0] = ( data[0, :, 0] - data[0, :, 0] )
                        data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )

                        y3 = a2012.oscilloscope_get_curve('CH2')
                        ##y3 = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                        data[2, :, 0] = ( data[2, :, 0] * (j - 1) + y3 ) / j

                        y2 = a2012_2.oscilloscope_get_curve('CH1')
                        ##y2 = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                        data_2[0, :, 0] = ( data_2[0, :, 0] * (j - 1) + y2 ) / j
                        data_2[1, :, 0] = ( data_2[1, :, 0] - data_2[0, :, 0] )
                        data_2[1, :, :] = ( data_2[1, :, :] - data_2[1, 0, :] )

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

                    if p12 == 0:
                        j = j
                    elif p12 == 1:
                        j = 2*j - 1

                    while field <= END_FIELD:
                        
                        if self.command == 'exit':
                            break

                        general.wait('80 ms')

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
                            data_2[0, :, i+1] = ( data_2[0, :, i+1] * (j - 1) + y2) / j
                            data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                            data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )
                            data_2[1, :, i+1] = ( data_2[0, :, i+1] - data_2[0, :, 0] )
                            data_2[1, :, :] = ( data_2[1, :, :] - data_2[1, 0, :] )

                        elif p9 == 3:
                            y = a2012.oscilloscope_get_curve('CH1')
                            ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                            y2 = a2012_2.oscilloscope_get_curve('CH1')
                            ##y2 = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                            y3 = a2012.oscilloscope_get_curve('CH2')
                            ##y3 = 1 + 100*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))

                            data[0, :, i+1] = ( data[0, :, i+1] * (j - 1) + y ) / j
                            data_2[0, :, i+1] = ( data_2[0, :, i+1] * (j - 1) + y2) / j
                            data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                            data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )
                            data_2[1, :, i+1] = ( data_2[0, :, i+1] - data_2[0, :, 0] )
                            data_2[1, :, :] = ( data_2[1, :, :] - data_2[1, 0, :] )
                            data[3, :, i+1] = ( data[3, :, i+1] * (j - 1) + y3 ) / j

                        #start_time = time.time()

                        process = general.plot_2d( p2, data[:,:,1:points+1],  xname='Time', start_step=( (0, t_step), (START_FIELD, FIELD_STEP) ), xscale='s', yname='Field', yscale='G', zname='Intensity', zscale='V', pr = process, text = 'S / F: ' + str(j) + ' / ' + str(field))

                        if p9 > 1:

                            process = general.plot_2d( f"{p2}_2", data_2[:,:,1:points+1], xname='Time', start_step=( (0, t_step_2), (START_FIELD, FIELD_STEP) ), xscale='s', yname='Field', yscale='G', zname='Intensity', zscale='V', pr = process, text = 'S / F: ' + str(j) + ' / ' + str(field))

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

                    if p12 == 1:

                        while field > START_FIELD:
                            
                            if self.command == 'exit':
                                break

                            i -= 1
                            general.wait('80 ms')

                            field = round( (-FIELD_STEP + field), 3 )
                            bh15.magnet_field(field)

                            a2012.oscilloscope_start_acquisition()
                            if p9 > 1:
                                a2012_2.oscilloscope_start_acquisition()
                            
                            ##ch_time = np.random.randint(250, 500, 1)
                            if p9 == 1:
                                y = a2012.oscilloscope_get_curve('CH1')
                                ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))

                                data[0, :, i+1] = ( data[0, :, i+1] * j + y ) / ( j + 1 )
                                data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                                data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )

                            elif p9 == 2:
                                y = a2012.oscilloscope_get_curve('CH1')
                                ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                                y2 = a2012_2.oscilloscope_get_curve('CH1')
                                ##y2 = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))

                                data[0, :, i+1] = ( data[0, :, i+1] * j + y ) / ( j + 1 )
                                data_2[0, :, i+1] = ( data_2[0, :, i+1] * j + y2) / ( j + 1 )
                                data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                                data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )
                                data_2[1, :, i+1] = ( data_2[0, :, i+1] - data_2[0, :, 0] )
                                data_2[1, :, :] = ( data_2[1, :, :] - data_2[1, 0, :] )

                            elif p9 == 3:
                                y = a2012.oscilloscope_get_curve('CH1')
                                ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                                y2 = a2012_2.oscilloscope_get_curve('CH1')
                                ##y2 = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                                y3 = a2012.oscilloscope_get_curve('CH2')
                                ##y3 = 1 + 100*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))

                                data[0, :, i+1] = ( data[0, :, i+1] * j + y ) / ( j + 1 )
                                data_2[0, :, i+1] = ( data_2[0, :, i+1] * j + y2) / ( j + 1 )
                                data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                                data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )
                                data_2[1, :, i+1] = ( data_2[0, :, i+1] - data_2[0, :, 0] )
                                data_2[1, :, :] = ( data_2[1, :, :] - data_2[1, 0, :] )
                                data[3, :, i+1] = ( data[3, :, i+1] * j + y3 ) / ( j + 1 )

                            #start_time = time.time()

                            process = general.plot_2d( p2, data[:,:,1:points+1],  xname='Time', start_step=( (0, t_step), (START_FIELD, FIELD_STEP) ), xscale='s', yname='Field', yscale='G', zname='Intensity', zscale='V', pr = process, text = 'S / F: ' + str(j) + ' / ' + str(field))

                            if p9 > 1:

                                process = general.plot_2d( f"{p2}_2", data_2[:,:,1:points+1],  xname='Time', start_step=( (0, t_step_2), (START_FIELD, FIELD_STEP) ), xscale='s', yname='Field', yscale='G', zname='Intensity', zscale='V', pr = process, text = 'S / F: ' + str(j) + ' / ' + str(field))

                            #general.message( str( time.time() - start_time ) )

                            # check our polling data
                            if self.command[0:2] == 'SC':
                                SCANS = int( self.command[2:] )
                                self.command = 'start'
                            elif self.command == 'exit':
                                break
                            
                            if conn.poll() == True:
                                self.command = conn.recv()


                    while field > OFFRES_FIELD:
                        field = bh15.magnet_field( field - initialization_step)
                        field = field - initialization_step
                        general.wait('30 ms')
                    
                    field = bh15.magnet_field( OFFRES_FIELD )
                    field = OFFRES_FIELD
                    
                    if p9 == 1 and p11 == 1 and p12 == 0:
                        if j == 1:
                            file_handler.save_data(file_save_1, np.transpose( data[0, :, :] ), header = header)
                        else:
                            file_save_j = file_save_1.split('.csv')[0] + f'_{j}_scans.csv'
                            file_handler.save_data(file_save_j, np.transpose( data[0, :, :] ), header = header)

                    j += 1

                # finish succesfully
                self.command = 'exit'

            if self.command == 'exit':
                #general.message(f'Script {p2} finished')
                
                temp_end = str( ls335.tc_temperature('B') )
                if p9 == 1 and p11 == 0:
                    ##t_res = 1
                    now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                    temp_end = str( ls335.tc_temperature('A') )

                    header = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off Res Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    file_handler.save_data(file_save_1, np.transpose( data[0, :, :] ), header = header)
                elif p9 == 2:

                    now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                    temp_end = str( ls335.tc_temperature('A') )

                    header = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off Res Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    header_2 = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum (Header 2)\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off Res Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res_2}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*w}\n"
                        f"2D Data"
                    )

                    file_handler.save_data(file_save_1, np.transpose( data[0, :, :] ), header = header)
                    file_handler.save_data(file_save_2, np.transpose( data_2[0, :, :] ), header = header_2)
                elif p9 == 3:

                    now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                    temp_end = str( ls335.tc_temperature('A') )

                    header = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off Res Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    header_2 = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum (Header 2)\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off Res Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res_2}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*w}\n"
                        f"2D Data"
                    )

                    file_handler.save_data(file_save_1, np.transpose( data[0, :, :] ), header = header)
                    file_handler.save_data(file_save_2, np.transpose( data_2[0, :, :] ), header = header_2)
                    file_handler.save_data(file_save_3, np.transpose( data[3, :, :] ), header = header)

                while field > OFFRES_FIELD:
                    field = bh15.magnet_field( field - initialization_step)
                    field = field - initialization_step
                field = bh15.magnet_field( OFFRES_FIELD )
                field = OFFRES_FIELD

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
