#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import socket
import numpy as np
from multiprocessing import Process, Pipe
from PyQt6 import QtWidgets, uic #, QtCore, QtGui
from PyQt6.QtWidgets import QFileDialog, QWidget
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt
import atomize.general_modules.general_functions as general
import atomize.device_modules.Insys_FPGA as pb_pro
###import atomize.device_modules.BH_15 as bh

class MainWindow(QtWidgets.QMainWindow):
    """
    A main window class
    """
    def __init__(self, *args, **kwargs):
        """
        A function for connecting actions and creating a main window
        """
        super(MainWindow, self).__init__(*args, **kwargs)
        
        path_to_main = os.path.dirname(os.path.abspath(__file__))
        gui_path = os.path.join(path_to_main,'gui/awg_phasing_main_window_insys.ui')
        icon_path = os.path.join(path_to_main, 'gui/icon_pulse.png')
        self.setWindowIcon( QIcon(icon_path) )

        self.path = os.path.join(path_to_main, '..', '..', '..', '..', 'Experimental_Data')

        #####
        path_to_main2 = os.path.join(os.path.abspath(os.getcwd()), '..', '..', 'libs')
        os.chdir(path_to_main2)
        #####

        self.destroyed.connect(lambda: self._on_destroyed())                # connect some actions to exit
        # Load the UI Page
        uic.loadUi(gui_path, self)                        # Design file

        self.pb = pb_pro.Insys_FPGA()
        
        #########################################################################
        self.awg_output_shift = 0 #494 # in ns; depends on the cable length

        # Phase correction
        self.deg_rad = 57.2957795131
        self.sec_order_coef = -2*np.pi/2
        
        self.design()

    def design(self):
        # Connection of different action to different Menus and Buttons
        self.button_off.clicked.connect(self.turn_off)
        self.button_off.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); ; border-style: inset; font-weight: bold; }")
        self.button_stop.clicked.connect(self.dig_stop)
        self.button_stop.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); ; border-style: inset; font-weight: bold; }")
        self.button_update.clicked.connect(self.update)
        self.button_update.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); ; border-style: inset; font-weight: bold; }")

        # text labels
        self.errors.setStyleSheet("QPlainTextEdit { color : rgb(211, 194, 78); }")  # rgb(193, 202, 227)
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
        self.label_12.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_13.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_14.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_15.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        #self.label_16.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        #self.label_17.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        #self.label_18.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_19.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_20.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_21.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_22.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_23.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_24.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_25.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_26.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_27.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_28.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_29.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_30.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        #self.label_31.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # Spinboxes
        self.P1_st.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        #self.P1_st.lineEdit().setReadOnly( True )   # block input from keyboard
        self.P2_st.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P3_st.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P4_st.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P5_st.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P6_st.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P7_st.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Rep_rate.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Field.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P1_len.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P2_len.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P3_len.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P4_len.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P5_len.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P6_len.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P7_len.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")        
        self.P1_sig.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P2_sig.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P3_sig.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P4_sig.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P5_sig.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P6_sig.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P7_sig.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.P1_type.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.P2_type.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.P3_type.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.P4_type.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.P5_type.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.P6_type.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.P7_type.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.P_to_drop.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Zero_order.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.First_order.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Second_order.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.B_sech.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")

        self.Phase_1.setStyleSheet("QPlainTextEdit { color: rgb(211, 194, 78); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Phase_2.setStyleSheet("QPlainTextEdit { color: rgb(211, 194, 78); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Phase_3.setStyleSheet("QPlainTextEdit { color: rgb(211, 194, 78); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Phase_4.setStyleSheet("QPlainTextEdit { color: rgb(211, 194, 78); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Phase_5.setStyleSheet("QPlainTextEdit { color: rgb(211, 194, 78); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Phase_6.setStyleSheet("QPlainTextEdit { color: rgb(211, 194, 78); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Phase_7.setStyleSheet("QPlainTextEdit { color: rgb(211, 194, 78); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")

        #self.Freq.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.Phase.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Ampl_1.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Ampl_2.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")

        self.freq_1.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.freq_2.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.freq_3.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.freq_4.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.freq_5.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.freq_6.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.freq_7.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")

        self.coef_1.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.coef_2.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.coef_3.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.coef_4.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.coef_5.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.coef_6.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.coef_7.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")

        self.N_wurst.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Wurst_sweep_1.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Wurst_sweep_2.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Wurst_sweep_3.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Wurst_sweep_4.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Wurst_sweep_5.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Wurst_sweep_6.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Wurst_sweep_7.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")

        # Functions
        self.Ampl_1.valueChanged.connect(self.ch0_amp)
        self.ch0_ampl = self.Ampl_1.value()

        self.Ampl_2.valueChanged.connect(self.ch1_amp)
        self.ch1_ampl = self.Ampl_2.value()

        #self.Freq.valueChanged.connect(self.awg_freq)
        #self.cur_freq = str( self.Freq.value() ) + ' MHz'

        self.Phase.valueChanged.connect(self.awg_phase)
        self.cur_phase = self.Phase.value() * np.pi * 2 / 360

        self.P1_st.valueChanged.connect(self.p1_st)
        self.p1_start, self.p1_start_rect = self.round_and_change( self.P1_st )

        self.P2_st.valueChanged.connect(self.p2_st)
        self.p2_start, self.p2_start_rect = self.round_and_change( self.P2_st )

        self.P3_st.valueChanged.connect(self.p3_st)
        self.p3_start, self.p3_start_rect = self.round_and_change( self.P3_st )

        self.P4_st.valueChanged.connect(self.p4_st)
        self.p4_start, self.p4_start_rect = self.round_and_change( self.P4_st )

        self.P5_st.valueChanged.connect(self.p5_st)
        self.p5_start, self.p5_start_rect = self.round_and_change( self.P5_st )

        self.P6_st.valueChanged.connect(self.p6_st)
        self.p6_start, self.p6_start_rect = self.round_and_change( self.P6_st )

        self.P7_st.valueChanged.connect(self.p7_st)
        self.p7_start, self.p7_start_rect = self.round_and_change( self.P7_st )

        self.P1_len.valueChanged.connect(self.p1_len)
        self.p1_length, b = self.round_and_change(self.P1_len)

        self.P2_len.valueChanged.connect(self.p2_len)
        self.p2_length, b = self.round_and_change(self.P2_len)

        self.P3_len.valueChanged.connect(self.p3_len)
        self.p3_length, b = self.round_and_change(self.P3_len)

        self.P4_len.valueChanged.connect(self.p4_len)
        self.p4_length, b = self.round_and_change(self.P4_len)

        self.P5_len.valueChanged.connect(self.p5_len)
        self.p5_length, b = self.round_and_change(self.P5_len)

        self.P6_len.valueChanged.connect(self.p6_len)
        self.p6_length, b = self.round_and_change(self.P6_len)

        self.P7_len.valueChanged.connect(self.p7_len)
        self.p7_length, b = self.round_and_change(self.P7_len)


        self.P1_sig.valueChanged.connect(self.p1_sig)
        self.p1_sigma, b = self.round_and_change(self.P1_sig)

        self.P2_sig.valueChanged.connect(self.p2_sig)
        self.p2_sigma, b = self.round_and_change(self.P2_sig)

        self.P3_sig.valueChanged.connect(self.p3_sig)
        self.p3_sigma, b = self.round_and_change(self.P3_sig)

        self.P4_sig.valueChanged.connect(self.p4_sig)
        self.p4_sigma, b = self.round_and_change(self.P4_sig)

        self.P5_sig.valueChanged.connect(self.p5_sig)
        self.p5_sigma, b = self.round_and_change(self.P5_sig)

        self.P6_sig.valueChanged.connect(self.p6_sig)
        self.p6_sigma, b = self.round_and_change(self.P6_sig)

        self.P7_sig.valueChanged.connect(self.p7_sig)
        self.p7_sigma, b = self.round_and_change(self.P7_sig)

        self.Rep_rate.valueChanged.connect(self.rep_rate)
        self.repetition_rate = str( self.Rep_rate.value() ) + ' Hz'

        self.N_wurst.valueChanged.connect(self.n_wurst)
        self.n_wurst_cur = int( self.N_wurst.value() )

        self.Wurst_sweep_1.valueChanged.connect(self.wurst_sweep_1)
        self.wurst_sweep_cur_1 = self.add_mhz( int( self.Wurst_sweep_1.value() ) )

        self.Wurst_sweep_2.valueChanged.connect(self.wurst_sweep_2)
        self.wurst_sweep_cur_2 = self.add_mhz( int( self.Wurst_sweep_2.value() ) )

        self.Wurst_sweep_3.valueChanged.connect(self.wurst_sweep_3)
        self.wurst_sweep_cur_3 = self.add_mhz( int( self.Wurst_sweep_3.value() ) )

        self.Wurst_sweep_4.valueChanged.connect(self.wurst_sweep_4)
        self.wurst_sweep_cur_4 = self.add_mhz( int( self.Wurst_sweep_4.value() ) )

        self.Wurst_sweep_5.valueChanged.connect(self.wurst_sweep_5)
        self.wurst_sweep_cur_5 = self.add_mhz( int( self.Wurst_sweep_5.value() ) )

        self.Wurst_sweep_6.valueChanged.connect(self.wurst_sweep_6)
        self.wurst_sweep_cur_6 = self.add_mhz( int( self.Wurst_sweep_6.value() ) )
        
        self.Wurst_sweep_7.valueChanged.connect(self.wurst_sweep_7)
        self.wurst_sweep_cur_7 = self.add_mhz( int( self.Wurst_sweep_7.value() ) )

        self.Field.valueChanged.connect(self.field)
        self.mag_field = float( self.Field.value() )
        ###self.bh15.magnet_setup( self.mag_field, 0.5 )
        
        self.P1_type.currentIndexChanged.connect(self.p1_type)
        self.p1_typ = str( self.P1_type.currentText() )
        self.P2_type.currentIndexChanged.connect(self.p2_type)
        self.p2_typ = str( self.P2_type.currentText() )
        self.P3_type.currentIndexChanged.connect(self.p3_type)
        self.p3_typ = str( self.P3_type.currentText() )
        self.P4_type.currentIndexChanged.connect(self.p4_type)
        self.p4_typ = str( self.P4_type.currentText() )
        self.P5_type.currentIndexChanged.connect(self.p5_type)
        self.p5_typ = str( self.P5_type.currentText() )
        self.P6_type.currentIndexChanged.connect(self.p6_type)
        self.p6_typ = str( self.P6_type.currentText() )
        self.P7_type.currentIndexChanged.connect(self.p7_type)
        self.p7_typ = str( self.P7_type.currentText() )
        
        self.Phase_1.textChanged.connect(self.phase_1)
        self.ph_1 = self.Phase_1.toPlainText()[1:(len(self.Phase_1.toPlainText())-1)].split(',')
        self.Phase_2.textChanged.connect(self.phase_2)
        self.ph_2 = self.Phase_2.toPlainText()[1:(len(self.Phase_2.toPlainText())-1)].split(',')
        self.Phase_3.textChanged.connect(self.phase_3)
        self.ph_3 = self.Phase_3.toPlainText()[1:(len(self.Phase_3.toPlainText())-1)].split(',')
        self.Phase_4.textChanged.connect(self.phase_4)
        self.ph_4 = self.Phase_4.toPlainText()[1:(len(self.Phase_4.toPlainText())-1)].split(',')
        self.Phase_5.textChanged.connect(self.phase_5)
        self.ph_5 = self.Phase_5.toPlainText()[1:(len(self.Phase_5.toPlainText())-1)].split(',')
        self.Phase_6.textChanged.connect(self.phase_6)
        self.ph_6 = self.Phase_6.toPlainText()[1:(len(self.Phase_6.toPlainText())-1)].split(',')
        self.Phase_7.textChanged.connect(self.phase_7)
        self.ph_7 = self.Phase_7.toPlainText()[1:(len(self.Phase_7.toPlainText())-1)].split(',')

        # freq
        #self.freq_1.valueChanged.connect(self.p1_freq_f)
        #self.p1_freq = self.add_mhz( self.freq_1.value() )

        self.freq_2.valueChanged.connect(self.p2_freq_f)
        self.p2_freq = self.add_mhz( int( self.freq_2.value() ) )

        self.freq_3.valueChanged.connect(self.p3_freq_f)
        self.p3_freq = self.add_mhz( int( self.freq_3.value() ) )

        self.freq_4.valueChanged.connect(self.p4_freq_f)
        self.p4_freq = self.add_mhz( int( self.freq_4.value() ) )

        self.freq_5.valueChanged.connect(self.p5_freq_f)
        self.p5_freq = self.add_mhz( int( self.freq_5.value() ) )

        self.freq_6.valueChanged.connect(self.p6_freq_f)
        self.p6_freq = self.add_mhz( int( self.freq_6.value() ) )

        self.freq_7.valueChanged.connect(self.p7_freq_f)
        self.p7_freq = self.add_mhz( int( self.freq_7.value() ) )

        # coef in amplitude
        self.coef_2.valueChanged.connect(self.p2_coef_f)
        self.p2_coef = round( 100 / self.coef_2.value() , 2 )

        self.coef_3.valueChanged.connect(self.p3_coef_f)
        self.p3_coef = round( 100 / self.coef_3.value() , 2 )

        self.coef_4.valueChanged.connect(self.p4_coef_f)
        self.p4_coef = round( 100 / self.coef_4.value() , 2 )

        self.coef_5.valueChanged.connect(self.p5_coef_f)
        self.p5_coef = round( 100 / self.coef_5.value() , 2 )

        self.coef_6.valueChanged.connect(self.p6_coef_f)
        self.p6_coef = round( 100 / self.coef_6.value() , 2 )

        self.coef_7.valueChanged.connect(self.p7_coef_f)
        self.p7_coef = round( 100 / self.coef_7.value() , 2 )

        self.menuBar.setStyleSheet("QMenuBar { color: rgb(193, 202, 227); font-weight: bold; } \
                    QMenu::item { color: rgb(211, 194, 78); } QMenu::item:selected {color: rgb(193, 202, 227); }")
        self.action_read.triggered.connect( self.open_file_dialog )
        self.action_save.triggered.connect( self.save_file_dialog )

        # Quadrature Phase Correction
        self.P_to_drop.valueChanged.connect(self.p_to_drop_func)
        self.p_to_drop = int( self.P_to_drop.value() )

        self.Zero_order.valueChanged.connect(self.zero_order_func)
        self.zero_order = float( self.Zero_order.value() ) / self.deg_rad
        
        self.First_order.valueChanged.connect(self.first_order_func)
        self.first_order = float( self.First_order.value() )

        self.Second_order.valueChanged.connect(self.second_order_func)
        self.second_order = float( self.Second_order.value() )
        if self.second_order != 0.0:
            self.second_order = self.sec_order_coef / ( float( self.Second_order.value() ) * 1000 )

        self.B_sech.valueChanged.connect(self.b_sech_func)
        self.b_sech_cur = float( self.B_sech.value() )

        self.Combo_cor.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.Combo_cor.currentIndexChanged.connect(self.combo_cor_fun)
        self.combo_cor_fun()

        self.Combo_synt.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.Combo_synt.currentIndexChanged.connect(self.combo_synt_fun)
        self.combo_synt_fun()

        self.Dec.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Dec.valueChanged.connect( self.decimat )
        self.decimation = self.Dec.value()

        #self.live_mode.setStyleSheet("QCheckBox { color : rgb(193, 202, 227); }")
        #self.live_mode.stateChanged.connect( self.change_live_mode )
        self.l_mode = 0
 
        self.dig_part()

    def dig_part(self):
        """
        Digitizer settings
        """
        # time per point is fixed
        self.time_per_point = 0.4 * self.decimation

        self.Win_left.valueChanged.connect(self.win_left)
        self.cur_win_left = int( float( self.Win_left.value() ) / self.time_per_point )
        self.Win_left.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")
        self.Win_right.valueChanged.connect(self.win_right)
        self.cur_win_right = int( float( self.Win_right.value() ) / self.time_per_point )
        self.Win_right.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")

        self.Acq_number.valueChanged.connect(self.acq_number)
        self.number_averages = int( self.Acq_number.value() )
        self.Acq_number.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97)}")

        self.fft_box.setStyleSheet("QCheckBox { color : rgb(193, 202, 227); }")
        self.Quad_cor.setStyleSheet("QCheckBox { color : rgb(193, 202, 227); }")

        self.fft_box.stateChanged.connect( self.fft_online )
        self.Quad_cor.stateChanged.connect( self.quad_online )

        # flag for not writing the data when digitizer is off
        self.opened = 0
        self.fft = 0
        self.quad = 0
        
        """
        Create a process to interact with an experimental script that will run on a different thread.
        We need a different thread here, since PyQt GUI applications have a main thread of execution 
        that runs the event loop and GUI. If you launch a long-running task in this thread, then your GUI
        will freeze until the task terminates. During that time, the user won’t be able to interact with 
        the application
        """
        self.worker = Worker()

    def combo_synt_fun(self):
        """
        A function to set a default synthetizer for AWG arm
        """
        self.combo_synt = int( self.Combo_synt.currentText() )

    def combo_cor_fun(self):
        """
        A function to set a correction mode for awg pulses
        """
        txt = str( self.Combo_cor.currentText() )
        if txt == 'No':
            self.combo_cor = 0
        elif txt == 'Only Pi/2':
            self.combo_cor = 1
        elif txt == 'All':
            self.combo_cor = 2

    def b_sech_func(self):
        """
        A function to set b_sech parameter for the SECH/TANH pulse
        """
        self.b_sech_cur = float( self.B_sech.value() )

    def quad_online(self):
        """
        Turn on/off Quadrature phase correction
        """
        if self.Quad_cor.checkState().value == 2: # checked
            self.quad = 1
        elif self.Quad_cor.checkState().value == 0: # unchecked
            self.quad = 0
        
        try:
            self.parent_conn_dig.send( 'QC' + str( self.quad ) )
        except AttributeError:
            self.message('Digitizer is not running')

    def zero_order_func(self):
        """
        A function to change the zero order phase correction value
        """
        self.zero_order = float( self.Zero_order.value() ) / self.deg_rad

        # cycling
        if self.zero_order < 0.0:
            self.Zero_order.setValue(360.0)
            self.zero_order = float( self.Zero_order.value() )/ self.deg_rad
        else:
            pass

        if self.zero_order > 2*np.pi:
            self.Zero_order.setValue(0.0)
            self.zero_order = float( self.Zero_order.value() ) / self.deg_rad
        else:
            pass

        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'ZO' + str( self.zero_order ) )
            except AttributeError:
                self.message('Digitizer is not running')

    def first_order_func(self):
        """
        A function to change the first order phase correction value
        """
        self.first_order = float( self.First_order.value() )

        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'FO' + str( self.first_order ) )
            except AttributeError:
                self.message('Digitizer is not running')

    def second_order_func(self):
        """
        A function to change the second order phase correction value
        """
        self.second_order = float( self.Second_order.value() )
        if self.second_order != 0.0:
            self.second_order = self.sec_order_coef / ( float( self.Second_order.value() ) * 1000 )
        
        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'SO' + str( self.second_order ) )
            except AttributeError:
                self.message('Digitizer is not running')

    def p_to_drop_func(self):
        """
        A function to change the number of points to drop
        """
        self.p_to_drop = float( self.P_to_drop.value() )

        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'PD' + str( self.p_to_drop ) )
            except AttributeError:
                self.message('Digitizer is not running')

    def fft_online(self):
        """
        Turn on/off FFT
        """

        if self.fft_box.checkState().value == 2: # checked
            self.fft = 1
        elif self.fft_box.checkState().value == 0: # unchecked
            self.fft = 0
        
        try:
            self.parent_conn_dig.send( 'FF' + str( self.fft ) )
        except AttributeError:
            self.message('Digitizer is not running')

    def change_live_mode(self):
        """
        Turn on/off live mode
        """

        if self.live_mode.checkState().value == 2: # checked
            self.l_mode = 1
        elif self.live_mode.checkState().value == 0: # unchecked
            self.l_mode = 0
        
        try:
            self.parent_conn_dig.send( 'LM' + str( self.l_mode ) )
        except AttributeError:
            self.message('Digitizer is not running')

    def win_left(self):
        """
        A function to change left integration window
        """
        self.cur_win_left = int( float( self.Win_left.value() ) / self.time_per_point )
        if round( self.cur_win_left * self.time_per_point, 1) > round( float( self.remove_ns( self.p1_length ) ), 1):
            self.cur_win_left = int( round( float( self.remove_ns( self.p1_length ) ), 1) / self.time_per_point )
            self.Win_left.setValue( round( self.cur_win_left * self.time_per_point, 1) )

        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'WL' + str( self.cur_win_left ) )
            except AttributeError:
                self.message('Digitizer is not running')

    def win_right(self):
        self.cur_win_right = int( float( self.Win_right.value() ) / self.time_per_point )
        if round( self.cur_win_right * self.time_per_point, 1) > round( float( self.remove_ns( self.p1_length ) ), 1):
            self.cur_win_right = int( round( float( self.remove_ns( self.p1_length ) ), 1) / self.time_per_point )
            self.Win_right.setValue( round( self.cur_win_right * self.time_per_point, 1) )

        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'WR' + str( self.cur_win_right ) )
            except AttributeError:
                self.message('Digitizer is not running')

    def acq_number(self):
        """
        A function to change number of averages
        """
        self.number_averages = int( self.Acq_number.value() )

        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'NA' + str( self.number_averages ) )
            except AttributeError:
                self.message('Digitizer is not running')

    def open_file_dialog(self):
        """
        A function to open a new window for choosing a pulse list
        """
        filedialog = QFileDialog(self, 'Open File', directory = self.path, filter = "AWG pulse phase list (*.phase_awg)",\
            options = QtWidgets.QFileDialog.Option.DontUseNativeDialog)
        # use QFileDialog.DontUseNativeDialog to change directory
        filedialog.setStyleSheet("QWidget { background-color : rgb(42, 42, 64); color: rgb(211, 194, 78);}")
        filedialog.setFileMode(QtWidgets.QFileDialog.FileMode.AnyFile)
        filedialog.fileSelected.connect(self.open_file)
        filedialog.show()

    def save_file_dialog(self):
        """
        A function to open a new window for choosing a pulse list
        """
        filedialog = QFileDialog(self, 'Save File', directory = self.path, filter = "AWG pulse phase list (*.phase_awg)",\
            options = QtWidgets.QFileDialog.Option.DontUseNativeDialog)
        filedialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        # use QFileDialog.DontUseNativeDialog to change directory
        filedialog.setStyleSheet("QWidget { background-color : rgb(42, 42, 64); color: rgb(211, 194, 78);}")
        filedialog.setFileMode(QtWidgets.QFileDialog.FileMode.AnyFile)
        filedialog.fileSelected.connect(self.save_file)
        filedialog.show()

    def open_file(self, filename):
        """
        A function to open a pulse list
        :param filename: string
        """
        self.opened = 1

        text = open(filename).read()
        lines = text.split('\n')

        self.setter(text, 0, self.P1_type, self.P1_st, self.P1_len, self.P1_sig, self.freq_1, self.Wurst_sweep_1, self.coef_1, self.Phase_1)
        self.setter(text, 1, self.P2_type, self.P2_st, self.P2_len, self.P2_sig, self.freq_2, self.Wurst_sweep_2, self.coef_2, self.Phase_2)
        self.setter(text, 2, self.P3_type, self.P3_st, self.P3_len, self.P3_sig, self.freq_3, self.Wurst_sweep_3, self.coef_3, self.Phase_3)
        self.setter(text, 3, self.P4_type, self.P4_st, self.P4_len, self.P4_sig, self.freq_4, self.Wurst_sweep_4, self.coef_4, self.Phase_4)
        self.setter(text, 4, self.P5_type, self.P5_st, self.P5_len, self.P5_sig, self.freq_5, self.Wurst_sweep_5, self.coef_5, self.Phase_5)
        self.setter(text, 5, self.P6_type, self.P6_st, self.P6_len, self.P6_sig, self.freq_6, self.Wurst_sweep_6, self.coef_6, self.Phase_6)
        self.setter(text, 6, self.P7_type, self.P7_st, self.P7_len, self.P7_sig, self.freq_7, self.Wurst_sweep_7, self.coef_7, self.Phase_7)

        self.Rep_rate.setValue( float( lines[7].split(':  ')[1] ) )
        self.Field.setValue( float( lines[8].split(':  ')[1] ) )
        self.Delay.setValue( float( lines[9].split(':  ')[1] ) )
        self.Ampl_1.setValue( int( lines[10].split(':  ')[1] ) )
        self.Ampl_2.setValue( int( lines[11].split(':  ')[1] ) )
        self.Phase.setValue( float( lines[12].split(':  ')[1] ) )
        self.N_wurst.setValue( int( lines[13].split(':  ')[1] ) )
        self.B_sech.setValue( float( lines[14].split(':  ')[1] ) )

        self.live_mode.setCheckState(Qt.CheckState.Unchecked)
        self.fft_box.setCheckState(Qt.CheckState.Unchecked)
        self.Quad_cor.setCheckState(Qt.CheckState.Unchecked)
        self.Win_left.setValue( round(float( lines[17].split(':  ')[1] ), 1) )
        self.Win_right.setValue( round(float( lines[18].split(':  ')[1] ), 1) )
        self.Acq_number.setValue( int( lines[19].split(':  ')[1] ) )
        self.Dec.setValue( int( lines[25].split(':  ')[1] ) )

        try:
            self.P_to_drop.setValue( int( lines[20].split(':  ')[1] ) )
            self.Zero_order.setValue( float( lines[21].split(':  ')[1] ) )
            self.First_order.setValue( float( lines[22].split(':  ')[1] ) )
            self.Second_order.setValue( float( lines[23].split(':  ')[1] ) )
            self.Combo_osc.setCurrentText( str( lines[24].split(':  ')[1] ) )
        except IndexError:
            pass

        self.dig_stop()

        self.fft = 0
        self.quad = 0
        self.opened = 0

    def setter(self, text, index, typ, st, leng, sig, freq, w_sweep, coef, phase):
        """
        Auxiliary function to set all the values from *.awg file
        """
        array = text.split('\n')[index].split(':  ')[1].split(',  ')

        typ.setCurrentText( array[0] )
        if index != 0:
            st.setValue( float( array[1] ) )
            leng.setValue( float( array[2] ) )
            sig.setValue( float( array[3] ) )
        else:
            st.setValue( int( array[1] ) )
            leng.setValue( int( array[2] ) )
            sig.setValue( int( array[3] ) )

        freq.setValue( int( array[4] ) )
        w_sweep.setValue( int( array[5] ) )
        coef.setValue( int( array[6] ) )
        phase.setPlainText( str( array[7] ) )

    def save_file(self, filename):
        """
        A function to save a new pulse list
        :param filename: string
        """
        if filename[-9:] != 'phase_awg':
            filename = filename + '.phase_awg'
        with open(filename, 'w') as file:
            file.write( 'P1:  ' + self.P1_type.currentText() + ',  ' + str(self.P1_st.value()) + ',  ' + str(self.P1_len.value()) + ',  '\
                + str(self.P1_sig.value()) + ',  ' + str(self.freq_1.value()) + ',  ' + str(self.Wurst_sweep_1.value()) + ',  '\
                + str(self.coef_1.value()) + ',  ' + str('[' + ','.join(self.ph_1) + ']') + '\n' )
            file.write( 'P2:  ' + self.P2_type.currentText() + ',  ' + str(self.P2_st.value()) + ',  ' + str(self.P2_len.value()) + ',  '\
                + str(self.P2_sig.value()) + ',  ' + str(self.freq_2.value()) + ',  ' + str(self.Wurst_sweep_2.value()) + ',  '\
                + str(self.coef_2.value()) + ',  ' + str('[' + ','.join(self.ph_2) + ']') + '\n' )
            file.write( 'P3:  ' + self.P3_type.currentText() + ',  ' + str(self.P3_st.value()) + ',  ' + str(self.P3_len.value()) + ',  '\
                + str(self.P3_sig.value()) + ',  ' + str(self.freq_3.value()) + ',  ' + str(self.Wurst_sweep_3.value()) + ',  '\
                + str(self.coef_3.value()) + ',  ' + str('[' + ','.join(self.ph_3) + ']') + '\n' )
            file.write( 'P4:  ' + self.P4_type.currentText() + ',  ' + str(self.P4_st.value()) + ',  ' + str(self.P4_len.value()) + ',  '\
                + str(self.P4_sig.value()) + ',  ' + str(self.freq_4.value()) + ',  ' + str(self.Wurst_sweep_4.value()) + ',  '\
                + str(self.coef_4.value()) + ',  ' + str('[' + ','.join(self.ph_4) + ']') + '\n' )
            file.write( 'P5:  ' + self.P5_type.currentText() + ',  ' + str(self.P5_st.value()) + ',  ' + str(self.P5_len.value()) + ',  '\
                + str(self.P5_sig.value()) + ',  ' + str(self.freq_5.value()) + ',  ' + str(self.Wurst_sweep_5.value()) + ',  '\
                + str(self.coef_5.value()) + ',  ' + str('[' + ','.join(self.ph_5) + ']') + '\n' )
            file.write( 'P6:  ' + self.P6_type.currentText() + ',  ' + str(self.P6_st.value()) + ',  ' + str(self.P6_len.value()) + ',  '\
                + str(self.P6_sig.value()) + ',  ' + str(self.freq_6.value()) + ',  ' + str(self.Wurst_sweep_6.value()) + ',  '\
                + str(self.coef_6.value()) + ',  ' + str('[' + ','.join(self.ph_6) + ']') + '\n' )
            file.write( 'P7:  ' + self.P7_type.currentText() + ',  ' + str(self.P7_st.value()) + ',  ' + str(self.P7_len.value()) + ',  '\
                + str(self.P7_sig.value()) + ',  ' + str(self.freq_7.value()) + ',  ' + str(self.Wurst_sweep_7.value()) + ',  '\
                + str(self.coef_7.value()) + ',  ' + str('[' + ','.join(self.ph_7) + ']') + '\n' )

            file.write( 'Rep rate:  ' + str(self.Rep_rate.value()) + '\n' )
            file.write( 'Field:  ' + str(self.Field.value()) + '\n' )
            file.write( 'Delay:  ' + str(0) + '\n' )
            file.write( 'Ampl 1:  ' + str(self.Ampl_1.value()) + '\n' )
            file.write( 'Ampl 2:  ' + str(self.Ampl_2.value()) + '\n' )
            file.write( 'Phase:  ' + str(self.Phase.value()) + '\n' )
            file.write( 'N WURST; SECH/TANH:  ' + str(self.N_wurst.value()) + '\n' )
            file.write( 'B SECH/TANH:  ' + str(self.B_sech.value()) + '\n' )
            file.write( 'Points:  ' + str( 2016 ) + '\n' )
            file.write( 'Horizontal offset:  ' + str( 1024 ) + '\n' )
            file.write( 'Window left:  ' + str(self.Win_left.value()) + '\n' )
            file.write( 'Window right:  ' + str(self.Win_right.value()) + '\n' )
            file.write( 'Acquisitions:  ' + str(self.Acq_number.value()) + '\n' )
            file.write( 'Points to Drop:  ' + str(self.P_to_drop.value()) + '\n' )
            file.write( 'Zero order:  ' + str(self.Zero_order.value()) + '\n' )
            file.write( 'First order:  ' + str(self.First_order.value()) + '\n' )
            file.write( 'Second order:  ' + str(self.Second_order.value()) + '\n' )
            file.write( 'Oscilloscope:  ' + str('2012a') + '\n' )
            file.write( 'Decimation:  ' + str( self.Dec.value() ) + '\n' )

    def remove_ns(self, string1):
        return string1.split(' ')[0]

    def add_ns(self, string1):
        """
        Function to add ' ns'
        """
        return str( string1 ) + ' ns'

    def add_mhz(self, string1):
        """
        Function to add ' MHz'
        """
        return str( string1 ) + ' MHz'

    def check_length(self, length):
        self.errors.clear()

        if int( length ) != 0 and int( length ) < 12:
            self.errors.appendPlainText( 'Pulse length should be longer than 12 ns' )

        return length

    def round_length(self, length):
        return self.add_ns( length )

    ### stop?
    def _on_destroyed(self):
        """
        A function to do some actions when the main window is closing.
        """
        try:
            self.parent_conn_dig.send('exit')
        except BrokenPipeError:
            self.message('Digitizer is not running')
        except AttributeError:
            self.message('Digitizer is not running')
        #self.digitizer_process.join()
        self.dig_stop()

        # ?
        ##self.awg.awg_clear()
        # AWG should be reinitialized after clear; it helps in test regime; self.max_pulse_length
        ##self.pb.__init__()
        ##self.awg.awg_setup()
        ##self.awg.awg_stop()
        ##self.awg.awg_close()
        ##self.pb.pulser_stop()
        sys.exit()

    def quit(self):
        """
        A function to quit the programm
        """
        self._on_destroyed()
        sys.exit()

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
        return self.add_ns( doubleBox.value() ), self.add_ns( round(doubleBox.value() + self.awg_output_shift, 1) )

    def decimat(self):
        """
        A function to set decimation coefficient
        """
        self.decimation = self.Dec.value()
        self.time_per_point = 0.4 * self.decimation

    def n_wurst(self):
        """
        A function to set n_wurst parameter for the WURST and SECH/TANH pulses
        """
        self.n_wurst_cur = int( self.N_wurst.value() )

    def wurst_sweep_1(self):
        """
        A function to set wurst sweep for pulse 1
        """
        self.wurst_sweep_cur_1 = self.add_mhz( int( self.Wurst_sweep_1.value() ) )

    def wurst_sweep_2(self):
        """
        A function to set wurst sweep for pulse 2
        """
        self.wurst_sweep_cur_2 = self.add_mhz( int( self.Wurst_sweep_2.value() ) )

    def wurst_sweep_3(self):
        """
        A function to set wurst sweep for pulse 3
        """
        self.wurst_sweep_cur_3 = self.add_mhz( int( self.Wurst_sweep_3.value() ) )

    def wurst_sweep_4(self):
        """
        A function to set wurst sweep for pulse 4
        """
        self.wurst_sweep_cur_4 = self.add_mhz( int( self.Wurst_sweep_4.value() ) )

    def wurst_sweep_5(self):
        """
        A function to set wurst sweep for pulse 5
        """
        self.wurst_sweep_cur_5 = self.add_mhz( int( self.Wurst_sweep_5.value() ) )

    def wurst_sweep_6(self):
        """
        A function to set wurst sweep for pulse 6
        """
        self.wurst_sweep_cur_6 = self.add_mhz( int( self.Wurst_sweep_6.value() ) )

    def wurst_sweep_7(self):
        """
        A function to set wurst sweep for pulse 7
        """
        self.wurst_sweep_cur_7 = self.add_mhz( int( self.Wurst_sweep_7.value() ) )

    def ch0_amp(self):
        """
        A function to set AWG CH0 amplitude
        """
        self.ch0_ampl = self.Ampl_1.value()

    def ch1_amp(self):
        """
        A function to set AWG CH1 amplitude
        """
        self.ch1_ampl = self.Ampl_2.value()
    
    def awg_phase(self):
        """
        A function to set AWG CH1 phase shift
        """
        self.cur_phase = self.Phase.value() * np.pi * 2 / 360
        ####
        ###try:
        ###    self.errors.appendPlainText( str( self.cur_phase ) )
        ###    self.parent_conn_dig.send( 'PH' + str( self.cur_phase ) )
        ###except AttributeError:
        ###    self.message('Digitizer is not running')

    def p2_coef_f(self):
        """
        A function to change pulse 2 coefficient
        """
        self.p2_coef = round( 100 / self.coef_2.value() , 2 )

        #if ( self.ch0_ampl / self.p2_coef < 80 ) or ( self.ch1_ampl / self.p2_coef  < 80 ):
        #    if self.ch0_ampl <= self.ch1_ampl:
        #        self.p2_coef = round( ( self.ch0_ampl / 80 ), 2 )
        #    else:
        #        self.p2_coef = round( ( self.ch1_ampl / 80 ), 2 )

        #    self.coef_2.setValue( int( 1 / self.p2_coef * 100 ) )

    def p3_coef_f(self):
        """
        A function to change pulse 3 coefficient
        """
        self.p3_coef = round( 100 / self.coef_3.value() , 2 )
        
    def p4_coef_f(self):
        """
        A function to change pulse 4 coefficient
        """
        self.p4_coef = round( 100 / self.coef_4.value() , 2 )

    def p5_coef_f(self):
        """
        A function to change pulse 5 coefficient
        """
        self.p5_coef = round( 100 / self.coef_5.value() , 2 )

    def p6_coef_f(self):
        """
        A function to change pulse 6 coefficient
        """
        self.p6_coef = round( 100 / self.coef_6.value() , 2 )

    def p7_coef_f(self):
        """
        A function to change pulse 7 coefficient
        """
        self.p7_coef = round( 100 / self.coef_7.value() , 2 )

    def p2_freq_f(self):
        """
        A function to change pulse 2 frequency
        """
        self.p2_freq = self.add_mhz( int( self.freq_2.value() ) )

    def p3_freq_f(self):
        """
        A function to change pulse 3 frequency
        """
        self.p3_freq = self.add_mhz( int( self.freq_3.value() ) )

    def p4_freq_f(self):
        """
        A function to change pulse 4 frequency
        """
        self.p4_freq = self.add_mhz( int( self.freq_4.value() ) )

    def p5_freq_f(self):
        """
        A function to change pulse 5 frequency
        """
        self.p5_freq = self.add_mhz( int( self.freq_5.value() ) )

    def p6_freq_f(self):
        """
        A function to change pulse 6 frequency
        """
        self.p6_freq = self.add_mhz( int( self.freq_6.value() ) )

    def p7_freq_f(self):
        """
        A function to change pulse 7 frequency
        """
        self.p7_freq = self.add_mhz( int( self.freq_7.value() ) )

    def p1_st(self):
        """
        A function to set pulse 1 start
        """
        a, self.p1_start = self.round_and_change(self.P1_st)

    def p2_st(self):
        """
        A function to set pulse 2 start
        """
        self.p2_start, self.p2_start_rect = self.round_and_change(self.P2_st)

    def p3_st(self):
        """
        A function to set pulse 3 start
        """
        self.p3_start, self.p3_start_rect = self.round_and_change(self.P3_st)

    def p4_st(self):
        """
        A function to set pulse 4 start
        """
        self.p4_start, self.p4_start_rect = self.round_and_change(self.P4_st)

    def p5_st(self):
        """
        A function to set pulse 5 start
        """
        self.p5_start, self.p5_start_rect = self.round_and_change(self.P5_st)

    def p6_st(self):
        """
        A function to set pulse 6 start
        """
        self.p6_start, self.p6_start_rect = self.round_and_change(self.P6_st)

    def p7_st(self):
        """
        A function to set pulse 7 start
        """
        self.p7_start, self.p7_start_rect = self.round_and_change(self.P7_st)

    def p1_len(self):
        """
        A function to change a pulse 1 length
        """
        self.p1_length, b = self.round_and_change(self.P1_len)

    def p2_len(self):
        """
        A function to change a pulse 2 length
        """
        self.p2_length, b = self.round_and_change(self.P2_len)

    def p3_len(self):
        """
        A function to change a pulse 3 length
        """
        self.p3_length, b = self.round_and_change(self.P3_len)
    
    def p4_len(self):
        """
        A function to change a pulse 4 length
        """
        self.p4_length, b = self.round_and_change(self.P4_len)

    def p5_len(self):
        """
        A function to change a pulse 5 length
        """
        self.p5_length, b = self.round_and_change(self.P5_len)

    def p6_len(self):
        """
        A function to change a pulse 6 length
        """
        self.p6_length, b = self.round_and_change(self.P6_len)

    def p7_len(self):
        """
        A function to change a pulse 7 length
        """
        self.p7_length, b = self.round_and_change(self.P7_len)

    def p1_sig(self):
        """
        A function to change a pulse 1 sigma
        """
        self.p1_sigma, b = self.round_and_change(self.P1_sig)

    def p2_sig(self):
        """
        A function to change a pulse 2 sigma
        """
        self.p2_sigma, b = self.round_and_change(self.P2_sig)

    def p3_sig(self):
        """
        A function to change a pulse 3 sigma
        """
        self.p3_sigma, b = self.round_and_change(self.P3_sig)

    def p4_sig(self):
        """
        A function to change a pulse 4 sigma
        """
        self.p4_sigma, b = self.round_and_change(self.P4_sig)

    def p5_sig(self):
        """
        A function to change a pulse 5 sigma
        """
        self.p5_sigma, b = self.round_and_change(self.P5_sig)

    def p6_sig(self):
        """
        A function to change a pulse 6 sigma
        """
        self.p6_sigma, b = self.round_and_change(self.P6_sig)

    def p7_sig(self):
        """
        A function to change a pulse 7 sigma
        """
        self.p7_sigma, b = self.round_and_change(self.P7_sig)

    def p1_type(self):
        """
        A function to change a pulse 1 type
        """
        self.p1_typ = str( self.P1_type.currentText() )

    def p2_type(self):
        """
        A function to change a pulse 2 type
        """
        self.p2_typ = str( self.P2_type.currentText() )

    def p3_type(self):
        """
        A function to change a pulse 3 type
        """
        self.p3_typ = str( self.P3_type.currentText() )

    def p4_type(self):
        """
        A function to change a pulse 4 type
        """
        self.p4_typ = str( self.P4_type.currentText() )

    def p5_type(self):
        """
        A function to change a pulse 5 type
        """
        self.p5_typ = str( self.P5_type.currentText() )

    def p6_type(self):
        """
        A function to change a pulse 6 type
        """
        self.p6_typ = str( self.P6_type.currentText() )

    def p7_type(self):
        """
        A function to change a pulse 7 type
        """
        self.p7_typ = str( self.P7_type.currentText() )
    
    def phase_converted(self, ph_str):
        if ph_str == '+x':
            return 0
        elif ph_str == '-x':
            return 3.141593
        elif ph_str == '+y':
            return -1.57080
        elif ph_str == '-y':
            return -4.712390

    def phase_1(self):
        """
        A function to change a pulse 1 phase
        """
        temp = self.Phase_1.toPlainText()
        try:
            if temp[-1] == ']' and temp[0] == '[':
                self.ph_1 = temp[1:(len(temp)-1)].split(',')
                if len(self.ph_1) == 1:
                    self.ph_1.append( self.ph_1[0] )
        except IndexError:
            pass

    def phase_2(self):
        """
        A function to change a pulse 2 phase
        """
        temp = self.Phase_2.toPlainText()
        try:
            if temp[-1] == ']' and temp[0] == '[':
                self.ph_2 = temp[1:(len(temp)-1)].split(',')
                if len(self.ph_2) == 1:
                    self.ph_2.append( self.ph_2[0] )
        except IndexError:
            pass

    def phase_3(self):
        """
        A function to change a pulse 3 phase
        """
        temp = self.Phase_3.toPlainText()
        try:
            if temp[-1] == ']' and temp[0] == '[':
                self.ph_3 = temp[1:(len(temp)-1)].split(',')
                if len(self.ph_3) == 1:
                    self.ph_3.append( self.ph_3[0] )
        except IndexError:
            pass

    def phase_4(self):
        """
        A function to change a pulse 4 phase
        """
        temp = self.Phase_4.toPlainText()
        try:
            if temp[-1] == ']' and temp[0] == '[':
                self.ph_4 = temp[1:(len(temp)-1)].split(',')
                if len(self.ph_4) == 1:
                    self.ph_4.append( self.ph_4[0] )
        except IndexError:
            pass

    def phase_5(self):
        """
        A function to change a pulse 5 phase
        """
        temp = self.Phase_5.toPlainText()
        try:
            if temp[-1] == ']' and temp[0] == '[':
                self.ph_5 = temp[1:(len(temp)-1)].split(',')
                if len(self.ph_5) == 1:
                    self.ph_5.append( self.ph_5[0] )
        except IndexError:
            pass

    def phase_6(self):
        """
        A function to change a pulse 6 phase
        """
        temp = self.Phase_6.toPlainText()
        try:
            if temp[-1] == ']' and temp[0] == '[':
                self.ph_6 = temp[1:(len(temp)-1)].split(',')
                if len(self.ph_6) == 1:
                    self.ph_6.append( self.ph_6[0] )
        except IndexError:
            pass

    def phase_7(self):
        """
        A function to change a pulse 7 phase
        """
        temp = self.Phase_7.toPlainText()
        try:
            if temp[-1] == ']' and temp[0] == '[':
                self.ph_7 = temp[1:(len(temp)-1)].split(',')
                if len(self.ph_7) == 1:
                    self.ph_7.append( self.ph_7[0] )
        except IndexError:
            pass

    def rep_rate(self):
        """
        A function to change a repetition rate
        """
        self.repetition_rate = str( self.Rep_rate.value() ) + ' Hz'
        self.pb.pulser_repetition_rate( self.repetition_rate )

        try:
            self.parent_conn_dig.send( 'RR' + str( self.repetition_rate.split(' ')[0] ) )
        except AttributeError:
            self.message('Digitizer is not running')

    def field(self):
        """
        A function to change a magnetic field
        """
        self.mag_field = float( self.Field.value() )
        ###self.bh15.magnet_field( self.mag_field )
        try:
            self.errors.appendPlainText( str( self.mag_field ) )
            self.parent_conn_dig.send( 'FI' + str( self.mag_field ) )
        except AttributeError:
            self.message('Digitizer is not running')

    def pulse_sequence(self):
        """
        Pulse sequence from defined pulses
        """
        self.pb.pulser_repetition_rate( self.repetition_rate )
        #self.pb.pulser_pulse(name = 'P0', channel = 'TRIGGER_AWG', start = '0 ns', length = '30 ns')

        if int(float( self.p1_length.split(' ')[0] )) != 0:
            self.pb.pulser_pulse(name = 'P1', channel = self.p1_typ, start = self.p1_start, length = self.p1_length ) #, phase_list = self.ph_1

        if int(float( self.p2_length.split(' ')[0] )) != 0:
            # self.p2_length ROUND TO CLOSEST 2
            if self.p2_typ != 'WURST' and self.p2_typ != 'SECH/TANH':
                self.pb.awg_pulse(name = 'P2', channel = 'CH0', func = self.p2_typ, frequency = self.p2_freq, \
                        length = self.p2_length, sigma = self.p2_sigma, start = self.p2_start, d_coef = self.p2_coef, phase_list = self.ph_2 )
            else:
                self.pb.awg_pulse(name = 'P2', channel = 'CH0', func = self.p2_typ, frequency = ( self.p2_freq, self.wurst_sweep_cur_2 ), \
                    length = self.p2_length, sigma = self.p2_sigma, start = self.p2_start, d_coef = self.p2_coef, n = self.n_wurst_cur, phase_list = self.ph_2, b = self.b_sech_cur )

            if self.p2_typ != 'BLANK':
                self.pb.pulser_pulse(name = 'P3', channel = 'TRIGGER_AWG', start = self.p2_start_rect, length = self.p2_length ) 

        if int(float( self.p3_length.split(' ')[0] )) != 0:
            if self.p3_typ != 'WURST' and self.p3_typ != 'SECH/TANH':
                self.pb.awg_pulse(name = 'P4', channel = 'CH0', func = self.p3_typ, frequency = self.p3_freq, \
                        length = self.p3_length, sigma = self.p3_sigma, start = self.p3_start, d_coef = self.p3_coef, phase_list = self.ph_3 )
            else:
                self.pb.awg_pulse(name = 'P4', channel = 'CH0', func = self.p3_typ, frequency = ( self.p3_freq, self.wurst_sweep_cur_3 ), \
                    length = self.p3_length, sigma = self.p3_sigma, start = self.p3_start, d_coef = self.p3_coef, n = self.n_wurst_cur, phase_list = self.ph_3, b = self.b_sech_cur )

            if self.p3_typ != 'BLANK':
                self.pb.pulser_pulse(name = 'P5', channel = 'TRIGGER_AWG', start = self.p3_start_rect, length = self.p3_length )

        if int(float( self.p4_length.split(' ')[0] )) != 0:
            if self.p4_typ != 'WURST' and self.p4_typ != 'SECH/TANH':
                self.pb.awg_pulse(name = 'P6', channel = 'CH0', func = self.p4_typ, frequency = self.p4_freq, \
                        length = self.p4_length, sigma = self.p4_sigma, start = self.p4_start, d_coef = self.p4_coef, phase_list = self.ph_4 )
            else:
                self.pb.awg_pulse(name = 'P6', channel = 'CH0', func = self.p4_typ, frequency = ( self.p4_freq, self.wurst_sweep_cur_4 ), \
                    length = self.p4_length, sigma = self.p4_sigma, start = self.p4_start, d_coef = self.p4_coef, n = self.n_wurst_cur, phase_list = self.ph_4, b = self.b_sech_cur )

            if self.p4_typ != 'BLANK':
                self.pb.pulser_pulse(name = 'P7', channel = 'TRIGGER_AWG', start = self.p4_start_rect, length = self.p4_length )

        if int(float( self.p5_length.split(' ')[0] )) != 0:
            if self.p5_typ != 'WURST' and self.p5_typ != 'SECH/TANH':
                self.pb.awg_pulse(name = 'P8', channel = 'CH0', func = self.p5_typ, frequency = self.p5_freq, \
                        length = self.p5_length, sigma = self.p5_sigma, start = self.p5_start, d_coef = self.p5_coef, phase_list = self.ph_5 )
            else:
                self.pb.awg_pulse(name = 'P8', channel = 'CH0', func = self.p5_typ, frequency = ( self.p5_freq, self.wurst_sweep_cur_5 ), \
                    length = self.p5_length, sigma = self.p5_sigma, start = self.p5_start, d_coef = self.p5_coef, n = self.n_wurst_cur, phase_list = self.ph_5, b = self.b_sech_cur )

            if self.p5_typ != 'BLANK':
                self.pb.pulser_pulse(name = 'P9', channel = 'TRIGGER_AWG', start = self.p5_start_rect, length = self.p5_length )

        if int(float( self.p6_length.split(' ')[0] )) != 0:
            if self.p6_typ != 'WURST' and self.p6_typ != 'SECH/TANH':
                self.pb.awg_pulse(name = 'P10', channel = 'CH0', func = self.p6_typ, frequency = self.p6_freq, \
                        length = self.p6_length, sigma = self.p6_sigma, start = self.p6_start, d_coef = self.p6_coef, phase_list = self.ph_6 )
            else:
                self.pb.awg_pulse(name = 'P10', channel = 'CH0', func = self.p6_typ, frequency = ( self.p6_freq, self.wurst_sweep_cur_6 ), \
                    length = self.p6_length, sigma = self.p6_sigma, start = self.p6_start, d_coef = self.p6_coef, n = self.n_wurst_cur, phase_list = self.ph_6, b = self.b_sech_cur )

            if self.p6_typ != 'BLANK':
                self.pb.pulser_pulse(name = 'P11', channel = 'TRIGGER_AWG', start = self.p6_start_rect, length = self.p6_length )

        if int(float( self.p7_length.split(' ')[0] )) != 0:
            if self.p7_typ != 'WURST' and self.p7_typ != 'SECH/TANH':
                self.pb.awg_pulse(name = 'P12', channel = 'CH0', func = self.p7_typ, frequency = self.p7_freq, \
                        length = self.p7_length, sigma = self.p7_sigma, start = self.p7_start, d_coef = self.p7_coef, phase_list = self.ph_7 )
            else:
                self.pb.awg_pulse(name = 'P12', channel = 'CH0', func = self.p7_typ, frequency = ( self.p7_freq, self.wurst_sweep_cur_7 ), \
                    length = self.p7_length, sigma = self.p7_sigma, start = self.p7_start, d_coef = self.p7_coef, n = self.n_wurst_cur, phase_list = self.ph_7, b = self.b_sech_cur )

            if self.p7_typ != 'BLANK':
                self.pb.pulser_pulse(name = 'P13', channel = 'TRIGGER_AWG', start = self.p7_start_rect, length = self.p7_length )

        #print(self.pb.adc_window)
        self.pb.pulser_default_synt(self.combo_synt)
        ###
        self.pb.phase_shift_ch1_seq_mode_awg = self.cur_phase
        ###self.awg.phase_x = self.cur_phase
        ###

        self.pb.awg_amplitude('CH0', str(self.ch0_ampl), 'CH1', str(self.ch1_ampl) )
        #general.message( str( self.pb.pulser_pulse_list() ) )
        
        ############# DO NOT WORK:
        self.errors.appendPlainText( self.pb.awg_pulse_list() )
        #############

        for i in range( len( self.ph_1 ) ):
            self.pb.awg_next_phase()
            self.pb.pulser_update()

        # the next line gives rise to a bag with FC
        #self.bh15.magnet_field( self.mag_field )
        #self.pb.pb_close()

    def update(self):
        """
        A function to run pulses
        """
        # Stop if necessary
        self.dig_stop()
        # TEST RUN
        self.errors.clear()
        
        self.parent_conn, self.child_conn = Pipe()
        # a process for running test
        self.test_process = Process( target = self.pulser_test, args = ( self.child_conn, 'test', ) )       
        self.test_process.start()

        # in order to finish a test
        time.sleep( 0.5 )

        if self.test_process.exitcode == 0:
            self.test_process.join()

            # RUN
            # can be problem here:
            # maybe it should be moved to pulser_test()
            # and deleted from here
            self.pb.pulser_clear()
            self.pb.awg_clear()
            # init will set the 'None' flag
            self.pb.pulser_test_flag( 'test' )
            self.pb.awg_test_flag( 'test' )
            self.pulse_sequence()
            ##self.errors.appendPlainText( self.awg.awg_pulse_list() )
            self.pb.pulser_test_flag( 'None' )
            self.pb.awg_test_flag( 'None' )

            self.pb.dac_window = 0
            self.pb.adc_window = 0
            self.dig_start()

        else:
            self.test_process.join()
            self.errors.clear()
            self.errors.appendPlainText( 'Incorrect pulse setting. Check that your pulses:\n' + \
                                        '1. Not overlapped\n' + \
                                        '2. Distance between pulses is more than 44.8 ns\n' + \
                                        '3. Pulse length should be longer or equal to sigma\n' + \
                                        '4. Phase sequence does not have equal length for all pulses with nonzero length\n' + \
                                        '\nPulser and AWG card are stopped' )

            # no need in stop and close, since AWG is not opened
            #self.awg.awg_stop()
            #self.awg.awg_close()
            #self.pb.pulser_stop()

    def pulser_test(self, conn, flag):
        """
        Test run
        """

        self.pb.pulser_clear()
        self.pb.awg_clear()
        # AWG should be reinitialized after clear; it helps in test regime; self.max_pulse_length
        #self.pb.__init__()
        self.pb.pulser_test_flag( flag )
        self.pb.awg_test_flag( flag )

        self.pulse_sequence()

    def dig_stop(self):
        """
        A function to stop digitizer
        """
        path_to_main = os.path.abspath( os.getcwd() )
        path_file = os.path.join(path_to_main, '../atomize/control_center/digitizer_insys.param')
        #path_file = os.path.join(path_to_main, '../../atomize/control_center/digitizer_insys.param')

        if self.opened == 0:
            try:
                self.parent_conn_dig.send('exit')
                self.digitizer_process.join()
            except AttributeError:
                self.message('Digitizer is not running')

        #self.opened = 0

        file_to_read = open(path_file, 'w')
        file_to_read.write('Points: ' + str( self.p1_length ) +'\n')
        file_to_read.write('Sample Rate: ' + str( 2500 ) +'\n')
        file_to_read.write('Posstriger: ' + str( 1024) +'\n')
        file_to_read.write('Range: ' + str( 200 ) +'\n')
        file_to_read.write('CH0 Offset: ' + str( 0 ) +'\n')
        file_to_read.write('CH1 Offset: ' + str( 0 ) +'\n')
        
        if self.cur_win_right < self.cur_win_left:
            self.cur_win_left, self.cur_win_right = self.cur_win_right, self.cur_win_left
        if self.cur_win_right == self.cur_win_left:
            self.cur_win_right += 1 #self.time_per_point

        file_to_read.write('Window Left: ' + str( int(self.cur_win_left ) ) +'\n') #/ self.time_per_point
        file_to_read.write('Window Right: ' + str( int(self.cur_win_right ) ) +'\n') #/ self.time_per_point
        file_to_read.write('Decimation: ' + str( self.decimation ) +'\n')

        file_to_read.close()
        self.errors.clear()
        
    def dig_start(self):
        """
        Button Start; Run function script(pipe_addres, four parameters of the experimental script)
        from Worker class in a different thread
        Create a Pipe for interaction with this thread
        self.param_i are used as parameters for script function
        """

        p1_list = [ self.p1_typ, self.p1_start, self.p1_length, self.ph_1 ]
        p2_list = [ self.p2_start_rect, self.round_length( self.P2_len.value() ) ]
        p3_list = [ self.p3_start_rect, self.round_length( self.P3_len.value() ) ]
        p4_list = [ self.p4_start_rect, self.round_length( self.P4_len.value() ) ]
        p5_list = [ self.p5_start_rect, self.round_length( self.P5_len.value() ) ]
        p6_list = [ self.p6_start_rect, self.round_length( self.P6_len.value() ) ]
        p7_list = [ self.p7_start_rect, self.round_length( self.P7_len.value() ) ]

        p2_awg_list = [ self.p2_typ, self.p2_freq, self.wurst_sweep_cur_2, self.p2_length, self.p2_sigma, self.p2_start, \
                        self.p2_coef, self.ph_2 ]
        p3_awg_list = [ self.p3_typ, self.p3_freq, self.wurst_sweep_cur_3, self.p3_length, self.p3_sigma, self.p3_start, \
                        self.p3_coef, self.ph_3 ]
        p4_awg_list = [ self.p4_typ, self.p4_freq, self.wurst_sweep_cur_4, self.p4_length, self.p4_sigma, self.p4_start, \
                        self.p4_coef, self.ph_4 ]
        p5_awg_list = [ self.p5_typ, self.p5_freq, self.wurst_sweep_cur_5, self.p5_length, self.p5_sigma, self.p5_start, \
                        self.p5_coef, self.ph_5 ]
        p6_awg_list = [ self.p6_typ, self.p6_freq, self.wurst_sweep_cur_6, self.p6_length, self.p6_sigma, self.p6_start, \
                        self.p6_coef, self.ph_6 ]
        p7_awg_list = [ self.p7_typ, self.p7_freq, self.wurst_sweep_cur_7, self.p7_length, self.p7_sigma, self.p7_start, \
                        self.p7_coef, self.ph_7 ]

        # prevent running two processes
        try:
            if self.digitizer_process.is_alive() == True:
                return
        except AttributeError:
            pass
        
        self.parent_conn_dig, self.child_conn_dig = Pipe()
        # a process for running function script 
        # sending parameters for initial initialization
        self.digitizer_process = Process( target = self.worker.dig_on, args = ( self.child_conn_dig, self.decimation, self.l_mode, self.number_averages, \
                                            self.cur_win_left, self.cur_win_right, p1_list, p2_list, p3_list, p4_list, p5_list, p6_list, p7_list, \
                                            self.n_wurst_cur, self.repetition_rate.split(' ')[0], self.mag_field, self.fft, self.cur_phase, \
                                            self.ch0_ampl, self.ch1_ampl, 0, p2_awg_list, p3_awg_list, p4_awg_list, p5_awg_list, \
                                            p6_awg_list, p7_awg_list, self.quad, self.zero_order, self.first_order, self.second_order, self.p_to_drop, \
                                            self.b_sech_cur, self.combo_cor, self.combo_synt, 0, ) )
               
        self.digitizer_process.start()
        # send a command in a different thread about the current state
        self.parent_conn_dig.send('start')

    def turn_off(self):
        """
        A function to turn off a programm.
        """
        self.quit()
        sys.exit()

    def message(*text):
        sock = socket.socket()
        sock.connect(('localhost', 9091))
        if len(text) == 1:
            sock.send(str(text[0]).encode())
            sock.close()
        else:
            sock.send(str(text).encode())
            sock.close()

    def help(self):
        """
        A function to open a documentation
        """
        pass

# The worker class that run the digitizer in a different thread
class Worker(QWidget):
    def __init__(self, parent = None):
        super(Worker, self).__init__(parent)
        # initialization of the attribute we use to stop the experimental script
        # when button Stop is pressed
        #from atomize.main.client import LivePlotClient

        self.command = 'start'
        
    def dig_on(self, conn, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p13, p14, p15, p16, \
                           p17, p18, p19, p20, p21, p22, p23, p24, p25, p26, p27, p28, p29, p30, p31, p32, p33, p34, p35):
        """
        function that contains updating of the digitizer
        """
        # should be inside dig_on() function;
        # freezing after digitizer restart otherwise
        #import time
        import numpy as np
        import atomize.general_modules.general_functions as general
        import atomize.device_modules.Insys_FPGA as pb_pro
        import atomize.math_modules.fft as fft_module
        ##import atomize.device_modules.ITC_FC as itc

        pb = pb_pro.Insys_FPGA()
        fft = fft_module.Fast_Fourier()
        ##bh15 = itc.ITC_FC()
        #bh15.magnet_setup( p15, 0.5 )
        ##bh15.magnet_field( p15, calibration = 'True' )

        process = 'None'
        num_ave =           p3

        ###
        pb.phase_shift_ch1_seq_mode_awg = p17
        ###

        # correction from file
        if p33 == 0:
            pass
        elif p33 == 1:
            path_to_main = os.path.abspath( os.getcwd() )
            path_file = os.path.join(path_to_main, '../atomize/control_center/correction.param')
            file_to_read = open(path_file, 'r')

            text_from_file = file_to_read.read().split('\n')
            # ['BL: 5.92087', 'A1: 412.868', 'X1: -124.647', 'W1: 62.0069', 'A2: 420.717', 'X2: -35.8879', 
            # 'W2: 34.4214', A3: 9893.97', 'X3: 12.4056', 'W3: 150.304', 'LOW: 16', 'LIMIT: 23', '']

            coef = [float( text_from_file[0].split(' ')[1] ), float( text_from_file[1].split(' ')[1] ), \
                    float( text_from_file[2].split(' ')[1] ), float( text_from_file[3].split(' ')[1] ), \
                    float( text_from_file[4].split(' ')[1] ), float( text_from_file[5].split(' ')[1] ), \
                    float( text_from_file[6].split(' ')[1] ), float( text_from_file[7].split(' ')[1] ),  \
                    float( text_from_file[8].split(' ')[1] ), float( text_from_file[9].split(' ')[1] )]

            pb.awg_correction(only_pi_half = 'True', coef_array = coef, \
                               low_level = float( text_from_file[10].split(' ')[1] ), limit = float( text_from_file[11].split(' ')[1] ))
        elif p33 == 2:
            path_to_main = os.path.abspath( os.getcwd() )
            path_file = os.path.join(path_to_main, '../atomize/control_center/correction.param')
            file_to_read = open(path_file, 'r')

            text_from_file = file_to_read.read().split('\n')
            # ['BL: 5.92087', 'A1: 412.868', 'X1: -124.647', 'W1: 62.0069', 'A2: 420.717', 'X2: -35.8879', 
            # 'W2: 34.4214', A3: 9893.97', 'X3: 12.4056', 'W3: 150.304', 'LOW: 16', 'LIMIT: 23', '']
            
            coef = [float( text_from_file[0].split(' ')[1] ), float( text_from_file[1].split(' ')[1] ), \
                    float( text_from_file[2].split(' ')[1] ), float( text_from_file[3].split(' ')[1] ), \
                    float( text_from_file[4].split(' ')[1] ), float( text_from_file[5].split(' ')[1] ), \
                    float( text_from_file[6].split(' ')[1] ), float( text_from_file[7].split(' ')[1] ),  \
                    float( text_from_file[8].split(' ')[1] ), float( text_from_file[9].split(' ')[1] )]

            pb.awg_correction(only_pi_half = 'False', coef_array = coef, \
                               low_level = float( text_from_file[10].split(' ')[1] ), limit = float( text_from_file[11].split(' ')[1] ))
        
        pb.awg_amplitude('CH0', str(p18), 'CH1', str(p19) )
        pb.pulser_repetition_rate( str(p14) + ' Hz' )

        #pb.pulser_pulse(name = 'P0', channel = 'TRIGGER_AWG', start = '0 ns', length = '30 ns')

        if int(float( p6[2].split(' ')[0] )) != 0:
            pb.pulser_pulse(name = 'P1', channel = p6[0], start = p6[1], length = p6[2]) #, phase_list = p6[3] 
        
        if int(float( p7[1].split(' ')[0] )) != 0:
            if p21[0] != 'WURST' and p21[0] != 'SECH/TANH':
                pb.awg_pulse(name = 'P2', channel = 'CH0', func = p21[0], frequency = p21[1], \
                        length = p21[3], sigma = p21[4], start = p21[5], d_coef = p21[6], phase_list = p21[7] )
            else:
                pb.awg_pulse(name = 'P2', channel = 'CH0', func = p21[0], frequency = ( p21[1], p21[2] ), \
                    length = p21[3], sigma = p21[4], start = p21[5], d_coef = p21[6], n = p13, phase_list = p21[7], b = p32 )

            if p21[0] != 'BLANK':
                pb.pulser_pulse(name = 'P3', channel = 'TRIGGER_AWG', start = p7[0], length = p7[1] ) #p7[1]

        if int(float( p8[1].split(' ')[0] )) != 0:
            if p22[0] != 'WURST' and p22[0] != 'SECH/TANH':
                pb.awg_pulse(name = 'P4', channel = 'CH0', func = p22[0], frequency = p22[1], \
                        length = p22[3], sigma = p22[4], start = p22[5], d_coef = p22[6], phase_list = p22[7] )
            else:
                pb.awg_pulse(name = 'P4', channel = 'CH0', func = p22[0], frequency = ( p22[1], p22[2] ), \
                    length = p22[3], sigma = p22[4], start = p22[5], d_coef = p22[6], n = p13, phase_list = p22[7], b = p32)

            if p22[0] != 'BLANK':
                pb.pulser_pulse(name = 'P5', channel = 'TRIGGER_AWG', start = p8[0], length = p8[1] ) 

        if int(float( p9[1].split(' ')[0] )) != 0:
            if p23[0] != 'WURST' and p23[0] != 'SECH/TANH':
                pb.awg_pulse(name = 'P6', channel = 'CH0', func = p23[0], frequency = p23[1], \
                        length = p23[3], sigma = p23[4], start = p23[5], d_coef = p23[6], phase_list = p23[7] )
            else:
                pb.awg_pulse(name = 'P6', channel = 'CH0', func = p23[0], frequency = ( p23[1], p23[2] ), \
                    length = p23[3], sigma = p23[4], start = p23[5], d_coef = p23[6], n = p13, phase_list = p23[7], b = p32 )

            if p23[0] != 'BLANK':
                pb.pulser_pulse(name = 'P7', channel = 'TRIGGER_AWG', start = p9[0], length = p9[1] ) 

        if int(float( p10[1].split(' ')[0] )) != 0:
            if p24[0] != 'WURST' and p24[0] != 'SECH/TANH':
                pb.awg_pulse(name = 'P8', channel = 'CH0', func = p24[0], frequency = p24[1], \
                        length = p24[3], sigma = p24[4], start = p24[5], d_coef = p24[6], phase_list = p24[7] )
            else:
                pb.awg_pulse(name = 'P8', channel = 'CH0', func = p24[0], frequency = ( p24[1], p24[2] ), \
                    length = p24[3], sigma = p24[4], start = p24[5], d_coef = p24[6], n = p13, phase_list = p24[7], b = p32 )

            if p24[0] != 'BLANK':
                pb.pulser_pulse(name = 'P9', channel = 'TRIGGER_AWG', start = p10[0], length = p10[1] ) 

        if int(float( p11[1].split(' ')[0] )) != 0:
            if p25[0] != 'WURST' and p25[0] != 'SECH/TANH':
                pb.awg_pulse(name = 'P10', channel = 'CH0', func = p25[0], frequency = p25[1], \
                        length = p25[3], sigma = p25[4], start = p25[5], d_coef = p25[6], phase_list = p25[7] )
            else:
                pb.awg_pulse(name = 'P10', channel = 'CH0', func = p25[0], frequency = ( p25[1], p25[2] ), \
                    length = p25[3], sigma = p25[4], start = p25[5], d_coef = p25[6], n = p13, phase_list = p25[7], b = p32 )

            if p25[0] != 'BLANK':
                pb.pulser_pulse(name = 'P11', channel = 'TRIGGER_AWG', start = p11[0], length = p11[1] ) 

        if int(float( p12[1].split(' ')[0] )) != 0:
            if p26[0] != 'WURST' and p26[0] != 'SECH/TANH':
                pb.awg_pulse(name = 'P12', channel = 'CH0', func = p26[0], frequency = p26[1], \
                        length = p26[3], sigma = p26[4], start = p26[5], d_coef = p26[6], phase_list = p26[7] )
            else:
                pb.awg_pulse(name = 'P12', channel = 'CH0', func = p26[0], frequency = ( p26[1], p26[2] ), \
                    length = p26[3], sigma = p26[4], start = p26[5], d_coef = p26[6], n = p13, phase_list = p26[7], b = p32 )

            if p26[0] != 'BLANK':
                pb.pulser_pulse(name = 'P13', channel = 'TRIGGER_AWG', start = p12[0], length = p12[1] )

        pb.pulser_default_synt(p34)
        
        POINTS = 1
        pb.digitizer_decimation(p1)
        DETECTION_WINDOW = round( pb.adc_window * 3.2, 1 )
        TR_ADC = round( 3.2 / 8, 1 )
        WIN_ADC = int( pb.adc_window * 8 / p1 )

        data = np.zeros( ( 2, WIN_ADC, 1 ) )
        ##data = np.random.random( ( 2, WIN_ADC, 1 ) )
        x_axis = np.linspace(0, ( DETECTION_WINDOW - TR_ADC), num = WIN_ADC)

        t_res = 0.4 * p1
        pb.digitizer_number_of_averages(p3)
        PHASES = len( p6[3] )
        
        pb.pulser_visualize()
        pb.pulser_open()

        # the idea of automatic and dynamic changing is
        # sending a new value of repetition rate via self.command
        # in each cycle we will check the current value of self.command
        # self.command = 'exit' will stop the digitizer
        while self.command != 'exit':
            # always test our self.command attribute for stopping the script when neccessary

            if self.command[0:2] == 'PO':
                #points_value = int( self.command[2:] )
                #a2012.oscilloscope_stop()
                #a2012.oscilloscope_timebase( str(points_value) + ' ns' )
                #a2012.oscilloscope_run_stop()
                pass

            elif self.command[0:2] == 'HO':
                #posstrigger_value = int( self.command[2:] )
                #a2012.oscilloscope_stop()
                #a2012.oscilloscope_horizontal_offset( str(posstrigger_value) + ' ns' )
                #a2012.oscilloscope_run_stop()
                pass
                
            elif self.command[0:2] == 'NA':
                num_ave = int( self.command[2:] )
                #print( num_ave )
                pb.digitizer_number_of_averages( num_ave )

            elif self.command[0:2] == 'WL':
                p4 = int( self.command[2:] )
            elif self.command[0:2] == 'WR':
                p5 = int( self.command[2:] )
            elif self.command[0:2] == 'RR':
                p14 = float( self.command[2:] )
                #print( p14 )
                if p14 > 49:
                    pb.pulser_repetition_rate( str(p14) + ' Hz' )
                else:
                    general.message('For REPETITION RATE lower then 50 Hz, please, press UPDATE')
            elif self.command[0:2] == 'FI':
                p15 = float( self.command[2:] )
                bh15.magnet_field( p15, calibration = 'True' )
            elif self.command[0:2] == 'FF':
                p16 = int( self.command[2:] )
            elif self.command[0:2] == 'QC':
                p27 = int( self.command[2:] )
            elif self.command[0:2] == 'ZO':
                p28 = float( self.command[2:] )
            elif self.command[0:2] == 'FO':
                p29 = float( self.command[2:] )
            elif self.command[0:2] == 'SO':
                p30 = float( self.command[2:] )
            elif self.command[0:2] == 'PD':
                p31 = int( self.command[2:] )
            elif self.command[0:2] == 'LM':
                #p2 = int( self.command[2:] )
                pass

            ###
            ###awg.phase_x = p17

            # check integration window
            if p4 > WIN_ADC:
                p4 = WIN_ADC
            if p5 > WIN_ADC:
                p5 = WIN_ADC

            # phase cycle
            PHASES = len( p6[3] )

            for i in range( PHASES ):

                pb.awg_next_phase()
                pb.pulser_update()
                
                if p2 == 0:
                    data[0], data[1] = pb.digitizer_get_curve(POINTS, PHASES, acq_cycle = p6[3], live_mode = 1)
                elif p2 == 1:
                    data[0], data[1] = pb.digitizer_get_curve(POINTS, PHASES, acq_cycle = p6[3], live_mode = 0)
                ##general.wait('100 ms')
                ##data = np.random.random( ( 2, WIN_ADC, 1 ) )

                data_x = data[0].ravel()
                data_y = data[1].ravel()

                if p16 == 0:                
                    general.plot_1d('Dig', x_axis, ( data_x, data_y ), \
                                xscale = 'ns', yscale = 'mV', label = 'ch', vline = (p4 * t_res, p5 * t_res))

                else:
                    # acquisition cycle
                    general.plot_1d('Dig', x_axis, ( data_x, data_y ), label = 'ch', xscale = 'ns', yscale = 'mV', \
                                        vline = (p4 * t_res, p5 * t_res) )

                    if p27 == 0:
                        freq_axis, abs_values = fft.fft(x_axis, data_x, data_y, t_res * 1)
                        m_val = round( np.amax( abs_values ), 2 )
                        process = general.plot_1d('FFT', freq_axis, abs_values, xname = 'Offset', label = 'FFT', \
                                                  xscale = 'MHz', yscale = 'A.U.', text = 'Max ' + str(m_val), pr = process)
                    else:
                        if p31 > len( data_x ) - 0.4 * p1:
                            p31 = len( data_x ) - 0.8 * p1
                            general.message('Maximum length of the data achieved. A number of drop points was corrected.')
                        # fixed resolution of digitizer; 2 ns
                        freq, fft_x, fft_y = fft.fft( x_axis[p31:], data_x[p31:], data_y[p31:], t_res * 1, re = 'True' )
                        data_fft = fft.ph_correction( freq, fft_x, fft_y, p28, p29, p30 )
                        process = general.plot_1d('FFT', freq, ( data_fft[0], data_fft[1] ), xname = 'Offset', xscale = 'MHz', \
                                                   yscale = 'A.U.', label = 'FFT', pr = process)

            self.command = 'start'
            if PHASES != 1:
                pb.awg_pulse_reset()
                pb.pulser_pulse_reset()
            else:
                pass
            
            # poll() checks whether there is data in the Pipe to read
            # we use it to stop the script if the exit command was sent from the main window
            # we read data by conn.recv() only when there is the data to read
            if conn.poll() == True:
                self.command = conn.recv()

        if self.command == 'exit':
            ##print('exit')
            pb.pulser_close()
            
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
