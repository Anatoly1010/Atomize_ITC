#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import random
import datetime
import socket
import numpy as np
from multiprocessing import Process, Pipe
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QDoubleSpinBox, QSpinBox, QPushButton, QTextEdit, QGridLayout, QFrame
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
        
        #####
        path_to_main2 = os.path.join(os.path.abspath(os.getcwd()), '..', 'libs') #'..',
        os.chdir(path_to_main2)
        #####

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
        self.setWindowTitle("Resonator Scanning")
        self.setStyleSheet("background-color: rgb(42,42,64);")

        path_to_main = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(path_to_main, 'gui/icon_temp.png')
        self.setWindowIcon( QIcon(icon_path) )

        centralwidget = QWidget(self)
        self.setCentralWidget(centralwidget)

        gridLayout = QGridLayout()
        gridLayout.setContentsMargins(15, 10, 10, 10)
        gridLayout.setVerticalSpacing(4)
        gridLayout.setHorizontalSpacing(20)

        centralwidget.setLayout(gridLayout)
        
        # ---- Labels & Inputs ----
        labels = [("Pulse Length", "label_1"), ("Repetition Rate", "label_2"), ("Start Frequency", "label_3"), ("End Frequency", "label_4"), ("Frequency Step", "label_5"), ("Acquisitions", "label_6"), ("Number of Scans", "label_7"), ("Experiment Name", "label_8"), ("Trigger Channel", "label_9"), ("Curve Channel", "label_10"), ("Oscilloscope IP", "label_11")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            setattr(self, attr_name, lbl)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # ---- Boxes ----
        double_boxes = [(QDoubleSpinBox, "box_length", "cur_length", self.pulse_length, 3.2, 1900, 102.4, 3.2, 1, " ns"),
                      (QSpinBox, "box_rep_rate", "cur_rep_rate", self.rep_rate, 1, 50000, 500, 10, 0, " Hz"),
                      (QSpinBox, "box_st_freq", "cur_st_freq", self.start_freq, 7000, 12000, 9500, 1, 0, " MHz"),
                      (QSpinBox, "box_end_freq", "cur_end_freq", self.end_freq, 7000, 12000, 9900, 1, 0, " MHz"),
                      (QSpinBox, "box_step_freq", "cur_step_freq", self.step_freq, 1, 50, 1, 1, 0, " MHz"),
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
        text_edit = [("Tune", "text_edit_exp_name", "cur_exp_name", self.exp_name),
                     ("LASER -> CH2", "text_comment", "cur_comment", self.comment),
                     ("CH1", "text_comment_2", "cur_comment_2", self.comment),
                     ("192.168.2.21", "text_comment_3", "cur_comment_3", self.comment)
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

        # ---- Layout placement ----
        gridLayout.addWidget(self.label_1, 0, 0)
        gridLayout.addWidget(self.box_length, 0, 1)
        gridLayout.addWidget(self.label_2, 1, 0)
        gridLayout.addWidget(self.box_rep_rate, 1, 1)

        gridLayout.addWidget(hline(), 2, 0, 1, 2)

        gridLayout.addWidget(self.label_3, 3, 0)
        gridLayout.addWidget(self.box_st_freq, 3, 1)
        gridLayout.addWidget(self.label_4, 4, 0)
        gridLayout.addWidget(self.box_end_freq, 4, 1)
        gridLayout.addWidget(self.label_5, 5, 0)
        gridLayout.addWidget(self.box_step_freq, 5, 1)
        
        gridLayout.addWidget(hline(), 6, 0, 1, 2)

        gridLayout.addWidget(self.label_6, 7, 0)
        gridLayout.addWidget(self.box_averag, 7, 1)
        gridLayout.addWidget(self.label_7, 8, 0)
        gridLayout.addWidget(self.box_scan, 8, 1)

        gridLayout.addWidget(hline(), 9, 0, 1, 2)

        gridLayout.addWidget(self.label_8, 10, 0)
        gridLayout.addWidget(self.text_edit_exp_name, 10, 1)
        
        gridLayout.addWidget(hline(), 11, 0, 1, 2)

        gridLayout.addWidget(self.label_9, 12, 0)
        gridLayout.addWidget(self.text_comment, 12, 1)
        gridLayout.addWidget(self.label_10, 13, 0)
        gridLayout.addWidget(self.text_comment_2, 13, 1)
        gridLayout.addWidget(self.label_11, 14, 0)
        gridLayout.addWidget(self.text_comment_3, 14, 1)

        gridLayout.addWidget(hline(), 15, 0, 1, 2)

        gridLayout.addWidget(self.button_start, 16, 0)
        gridLayout.addWidget(self.button_stop, 17, 0)
        gridLayout.addWidget(self.button_off, 18, 0)

        gridLayout.setRowStretch(19, 2)
        gridLayout.setColumnStretch(19, 2)

    def comment(self):
        pass

    def round_to_closest(self, x, y):
        """
        A function to round x to divisible by y
        """
        return round(( y * ( ( x // y ) + (round(x % y, 2) > 0) ) ), 1)

    def round_and_change(self, doubleBox, y):
        """
        """
        raw = doubleBox.value()
        current = self.round_to_closest( raw, y )
        if current != raw:
            doubleBox.setValue( current )
        return doubleBox.value()

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
        #self.cur_length = int( self.box_length.value() )
        self.cur_length = self.round_and_change(self.box_length, 3.2)

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

        if self.cur_st_freq >= self.cur_end_freq:
            self.cur_st_freq, self.cur_end_freq = self.cur_end_freq, self.cur_st_freq

            self.box_end_freq.setValue( self.cur_end_freq )
            self.box_st_freq.setValue( self.cur_st_freq )

        self.parent_conn, self.child_conn = Pipe()
        # a process for running function script 
        # sending parameters for initial initialization
        self.exp_process = Process( target = self.worker.exp_on, args = ( self.child_conn, self.cur_exp_name, self.cur_length, self.cur_st_freq, self.cur_rep_rate, self.cur_scan, self.cur_end_freq, self.cur_step_freq, self.cur_averages, ) )

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
        #import random
        import traceback

        try:
            import sys
            import numpy as np
            import pyqtgraph as pg
            import atomize.general_modules.general_functions as general
            import atomize.device_modules.Keysight_2000_Xseries as a2012
            import atomize.device_modules.Micran_X_band_MW_bridge_v2 as mwBridge
            import atomize.device_modules.Insys_FPGA as pb_pro
            import atomize.device_modules.Lakeshore_335 as ls
            import atomize.general_modules.csv_opener_saver_tk_kinter as openfile

            file_handler = openfile.Saver_Opener()
            a2012 = a2012.Keysight_2000_Xseries()
            pb = pb_pro.Insys_FPGA()
            ls335 = ls.Lakeshore_335()
            mw = mwBridge.Micran_X_band_MW_bridge_v2()

            ### Experimental parameters
            START_FREQ = p5
            END_FREQ = p8
            STEP = p9
            SCANS = p7
            AVERAGES = p10
            PHASES = 2
            process = 'None'

            # PULSES
            REP_RATE = str(p6) + ' Hz'
            PULSE_1_LENGTH = str(p4) + ' ns'
            PULSE_1_START = '0 ns'

            # setting pulses:
            pb.pulser_pulse(name ='P0', channel = 'DETECTION', start = PULSE_1_START, length = '640 ns', phase_list = ['+x', '+x'])
            pb.pulser_pulse(name ='P1', channel = 'MW', start = PULSE_1_START, length = PULSE_1_LENGTH, phase_list = ['+x', '+x'])
            pb.pulser_pulse(name ='P2', channel = 'LASER', start = PULSE_1_START, length = PULSE_1_LENGTH)


            pb.pulser_repetition_rate( REP_RATE )
            pb.digitizer_number_of_averages(2)

            pb.pulser_open()

            for i in range( PHASES ):
                pb.pulser_next_phase()
                general.wait('200 ms')

            a2012.oscilloscope_acquisition_type('Average')
            a2012.oscilloscope_trigger_channel('CH2')
            a2012.oscilloscope_number_of_averages(AVERAGES)
            a2012.oscilloscope_run_stop()

            a2012.oscilloscope_record_length( 2000 )
            real_length = a2012.oscilloscope_record_length( )

            t_res = a2012.oscilloscope_time_resolution()
            t_step = float(f"{pg.siEval(t_res):.4g}")

            points = int( (END_FREQ - START_FREQ) / STEP ) + 1
            data = np.zeros( (points, real_length) )
            ###

            freq_before = int(str( mw.mw_bridge_synthesizer() ).split(' ')[1])
            # initialize the power and skip the incorrect first point
            mw.mw_bridge_synthesizer( START_FREQ )
            general.wait('200 ms')
            a2012.oscilloscope_start_acquisition()
            a2012.oscilloscope_get_curve('CH1')

            # the idea of automatic and dynamic changing is
            # sending a new value of repetition rate via self.command
            # in each cycle we will check the current value of self.command
            # self.command = 'exit' will stop the digitizer
            while self.command != 'exit':

                # Start of experiment
                for k in general.scans(SCANS):

                    i = 0
                    freq = START_FREQ
                    mw.mw_bridge_synthesizer( freq )
                    general.wait('300 ms')
                    
                    a2012.oscilloscope_start_acquisition()
                    a2012.oscilloscope_get_curve('CH1')

                    while freq <= END_FREQ:
                        
                        mw.mw_bridge_synthesizer( freq )

                        a2012.oscilloscope_start_acquisition()
                        y = -a2012.oscilloscope_get_curve('CH1')
                        general.wait('300 ms')
                        
                        data[i] = ( data[i] * k + y ) / (k + 1)

                        general.plot_2d(p2, np.transpose( data ), start_step = ( (0, t_step), (START_FREQ * 1e6, STEP * 1e6) ), xname = 'Time', xscale = 's', yname = 'Frequency', yscale = 'Hz', zname = 'Intensity', zscale = 'V', text = 'Scan / Frequency: ' + str(k) + ' / ' + str(freq))
                        
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

                # finish succesfully
                self.command = 'exit'

            if self.command == 'exit':

                mw.mw_bridge_synthesizer( freq_before )
                general.wait('300 ms')

                pb.pulser_close()

                # Data saving
                now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                w = 30

                header = (
                    f"{'Date:':<{w}} {now}\n"
                    f"{'Experiment:':<{w}} Tune\n"
                    f"{'Start Frequency:':<{w}} {START_FREQ} MHz\n"
                    f"{'End Frequency:':<{w}} {END_FREQ} MHz\n"
                    f"{'Frequency Step:':<{w}} {STEP} MHz\n"
                    f"{'Time Resolution:':<{w}} {t_res}\n"
                    f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
                    f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                    f"{'-'*w}\n"
                    f"2D Data"
                )

                file_data, file_param = file_handler.create_file_parameters('.param')
                #file_handler.save_header(file_param, header = header, mode = 'w')

                file_handler.save_data(file_data, np.transpose( data ), header = header, mode = 'w')

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
