#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import socket
import numpy as np
from multiprocessing import Process, Pipe
from PyQt6 import QtWidgets, uic #, QtCore, QtGui
from PyQt6.QtWidgets import QWidget, QFileDialog
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt
import atomize.general_modules.general_functions as general
import atomize.device_modules.PB_ESR_500_pro as pb_pro
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
        gui_path = os.path.join(path_to_main,'gui/phasing_main_window.ui')
        icon_path = os.path.join(path_to_main, 'gui/icon_pulse.png')
        self.setWindowIcon( QIcon(icon_path) )

        self.path = os.path.join(path_to_main, '..', '..', '..', '..', 'experimental_data')

        self.destroyed.connect(lambda: self._on_destroyed())                # connect some actions to exit
        # Load the UI Page
        uic.loadUi(gui_path, self)                                          # Design file

        self.pb = pb_pro.PB_ESR_500_Pro()
        ###self.bh15 = bh.BH_15()
        
        # Phase correction
        self.deg_rad = 57.2957795131
        self.sec_order_coef = -2*np.pi/2

        # First initialization problem
        # corrected directly in the module BH-15
        #try:
            #self.bh15.magnet_setup( 3500, 0.5 )
        #except BrokenPipeError:
        #    pass

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
        self.label_16.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_17.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_18.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_19.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # Spinboxes
        self.P1_st.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        #self.P1_st.lineEdit().setReadOnly( True )   # block input from keyboard
        self.P2_st.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.P3_st.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.P4_st.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.P5_st.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.P6_st.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.P7_st.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.Rep_rate.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.Field.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.P1_len.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.P2_len.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.P3_len.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.P4_len.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.P5_len.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.P6_len.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.P7_len.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.P1_type.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.P2_type.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.P3_type.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.P4_type.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.P5_type.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.P6_type.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.P7_type.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.P_to_drop.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.Zero_order.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.First_order.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.Second_order.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")

        self.Phase_1.setStyleSheet("QPlainTextEdit { color: rgb(211, 194, 78); }")
        self.Phase_2.setStyleSheet("QPlainTextEdit { color: rgb(211, 194, 78); }")
        self.Phase_3.setStyleSheet("QPlainTextEdit { color: rgb(211, 194, 78); }")
        self.Phase_4.setStyleSheet("QPlainTextEdit { color: rgb(211, 194, 78); }")
        self.Phase_5.setStyleSheet("QPlainTextEdit { color: rgb(211, 194, 78); }")
        self.Phase_6.setStyleSheet("QPlainTextEdit { color: rgb(211, 194, 78); }")
        self.Phase_7.setStyleSheet("QPlainTextEdit { color: rgb(211, 194, 78); }")

        # Functions
        self.P1_st.valueChanged.connect(self.p1_st)
        self.p1_start = self.add_ns( self.P1_st.value() )

        self.P2_st.valueChanged.connect(self.p2_st)
        self.p2_start = self.add_ns( self.P2_st.value() )

        self.P3_st.valueChanged.connect(self.p3_st)
        self.p3_start = self.add_ns( self.P3_st.value() )

        self.P4_st.valueChanged.connect(self.p4_st)
        self.p4_start = self.add_ns( self.P4_st.value() )

        self.P5_st.valueChanged.connect(self.p5_st)
        self.p5_start = self.add_ns( self.P5_st.value() )

        self.P6_st.valueChanged.connect(self.p6_st)
        self.p6_start = self.add_ns( self.P6_st.value() )

        self.P7_st.valueChanged.connect(self.p7_st)
        self.p7_start = self.add_ns( self.P7_st.value() )


        self.P1_len.valueChanged.connect(self.p1_len)
        self.p1_length = self.add_ns( self.P1_len.value() )

        self.P2_len.valueChanged.connect(self.p2_len)
        self.p2_length = self.add_ns( self.P2_len.value() )

        self.P3_len.valueChanged.connect(self.p3_len)
        self.p3_length = self.add_ns( self.P3_len.value() )

        self.P4_len.valueChanged.connect(self.p4_len)
        self.p4_length = self.add_ns( self.P4_len.value() )

        self.P5_len.valueChanged.connect(self.p5_len)
        self.p5_length = self.add_ns( self.P5_len.value() )

        self.P6_len.valueChanged.connect(self.p6_len)
        self.p6_length = self.add_ns( self.P6_len.value() )

        self.P7_len.valueChanged.connect(self.p7_len)
        self.p7_length = self.add_ns( self.P7_len.value() )

        self.Rep_rate.valueChanged.connect(self.rep_rate)
        self.repetition_rate = str( self.Rep_rate.value() ) + ' Hz'

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

        self.laser_flag = 0
        self.laser_q_switch_delay = 141000 # in ns

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

        self.menu_bar_file()

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

        self.Combo_laser.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        self.Combo_laser.currentIndexChanged.connect(self.combo_laser_fun)
        self.combo_laser_fun()

        self.dig_part()

    def dig_part(self):
        """
        Digitizer settings
        """
        # time per point is fixed
        self.time_per_point = 2

        self.Timescale.valueChanged.connect(self.timescale)
        self.points = int( self.Timescale.value() )
        self.Timescale.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.Hor_offset.valueChanged.connect(self.hor_offset)
        self.posttrigger = int( self.Hor_offset.value() )
        self.Hor_offset.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")

        self.Win_left.valueChanged.connect(self.win_left)
        self.cur_win_left = int( self.Win_left.value() ) #* self.time_per_point
        self.Win_left.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.Win_right.valueChanged.connect(self.win_right)
        self.cur_win_right = int( self.Win_right.value() ) #* self.time_per_point
        self.Win_right.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")

        self.Acq_number.valueChanged.connect(self.acq_number)
        self.number_averages = int( self.Acq_number.value() )
        self.Acq_number.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")

        self.shift_box.setStyleSheet("QCheckBox { color : rgb(193, 202, 227); }")
        self.fft_box.setStyleSheet("QCheckBox { color : rgb(193, 202, 227); }")
        self.Quad_cor.setStyleSheet("QCheckBox { color : rgb(193, 202, 227); }")

        #self.shift_box.stateChanged.connect( self.simul_shift )
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

    def combo_laser_fun(self):
        """
        A function to set a default laser
        """
        txt = str( self.Combo_laser.currentText() )
        if txt == 'Nd:YaG':
            self.combo_laser_num = 1
        elif txt == 'NovoFEL':
            self.combo_laser_num = 2

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

    def simul_shift(self):
        """
        Special function for simultaneous change of number of points and horizontal offset
        """
        if self.shift_box.checkState().value == 2: # checked
            self.Timescale.valueChanged.disconnect()
            #self.Hor_offset.valueChanged.disconnect() 
            self.Timescale.valueChanged.connect(self.timescale_hor_offset)
            #self.Hor_offset.valueChanged.connect(self.timescale_hor_offset)
        elif self.shift_box.checkState().value == 0: # unchecked
            self.Timescale.valueChanged.disconnect()
            self.Timescale.valueChanged.connect(self.timescale)
            self.points = int( self.Timescale.value() )
            #self.Hor_offset.valueChanged.disconnect() 
            #self.Hor_offset.valueChanged.connect(self.hor_offset)
            self.posttrigger = int( self.Hor_offset.value() )

    def timescale_hor_offset(self):
        """
        A function to simultaneously change a number of points and horizontal offset of the digitizer
        """
        dif = self.points - self.posttrigger 
        points_temp = self.points

        # number of points can be lower than posttrigger since we firstly adjust them
        if dif > 0 and dif <= 176:  
            self.opened = 1
            self.timescale()
            self.opened = 0
            # check whether we increase or decrease number of points
            if self.points < points_temp:
                self.posttrigger = self.points - abs( dif )
                self.Hor_offset.setValue( self.posttrigger )
                self.timescale()
            else:
                self.posttrigger = self.points - abs( dif )
                self.timescale()
                self.Hor_offset.setValue( self.posttrigger )
        else:
            self.timescale()
            self.posttrigger = self.points - abs( dif )
            self.Hor_offset.setValue( self.posttrigger )

    def timescale(self):
        """
        A function to change a number of points of the digitizer
        """
        self.points = int( self.Timescale.value() )
        
        """
        if self.points % 16 != 0:
            self.points = self.round_to_closest( self.points, 16 )
            self.Timescale.setValue( self.points )

        if self.shift_box.checkState() == 0:
            if self.points - self.posttrigger < 16:
                self.points = self.points + 16
                self.Timescale.setValue( self.points )

        if self.points - self.posttrigger > 8000:
            self.points = self.posttrigger + 8000
            self.Timescale.setValue( self.points )
        """

        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'PO' + str( self.points ) )
            except AttributeError:
                self.message('Digitizer is not running')

        #self.opened = 0

    def hor_offset(self):
        """
        A function to change horizontal offset (posttrigger)
        """
        self.posttrigger = int( self.Hor_offset.value() )

        """
        if self.posttrigger % 16 != 0:
            self.posttrigger = self.round_to_closest( self.posttrigger, 16 )
            self.Hor_offset.setValue( self.posttrigger )

        if self.points - self.posttrigger <= 16:
            self.posttrigger = self.points - 16
            self.Hor_offset.setValue( self.posttrigger )

        if self.points - self.posttrigger > 8000:
            self.posttrigger = self.points - 8000
            self.Hor_offset.setValue( self.posttrigger )
        """

        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'HO' + str( self.posttrigger ) )
            except AttributeError:
                self.message('Digitizer is not running')

    def win_left(self):
        """
        A function to change left integration window
        """
        self.cur_win_left = int( self.Win_left.value() ) #* self.time_per_point
        #if self.cur_win_left / self.time_per_point > self.points:
        #    self.cur_win_left = self.points * self.time_per_point
        #    self.Win_left.setValue( self.cur_win_left / self.time_per_point )
        
        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'WL' + str( self.cur_win_left ) )
            except AttributeError:
                self.message('Digitizer is not running')

    def win_right(self):
        self.cur_win_right = int( self.Win_right.value() ) #* self.time_per_point
        #if self.cur_win_right / self.time_per_point > self.points:
        #    self.cur_win_right = self.points * self.time_per_point
        #    self.Win_right.setValue( self.cur_win_right / self.time_per_point )

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

    def menu_bar_file(self):
        """
        Design settings for QMenuBar
        """
        self.menuBar.setStyleSheet("QMenuBar { color: rgb(193, 202, 227); font-weight: bold; } \
                            QMenu::item { color: rgb(211, 194, 78); } QMenu::item:selected {color: rgb(193, 202, 227); }")
        self.action_read.triggered.connect( self.open_file_dialog )
        self.action_save.triggered.connect( self.save_file_dialog )

    def open_file_dialog(self):
        """
        A function to open a new window for choosing a pulse list
        """
        filedialog = QFileDialog(self, 'Open File', directory = self.path, filter = "Pulse Phase List (*.phase)",\
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
        filedialog = QFileDialog(self, 'Save File', directory = self.path, filter = "Pulse Phase List (*.phase)",\
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

        self.setter(text, 0, self.P1_type, self.P1_st, self.P1_len, self.Phase_1)
        self.setter(text, 1, self.P2_type, self.P2_st, self.P2_len, self.Phase_2)
        self.setter(text, 2, self.P3_type, self.P3_st, self.P3_len, self.Phase_3)
        self.setter(text, 3, self.P4_type, self.P4_st, self.P4_len, self.Phase_4)
        self.setter(text, 4, self.P5_type, self.P5_st, self.P5_len, self.Phase_5)
        self.setter(text, 5, self.P6_type, self.P6_st, self.P6_len, self.Phase_6)
        self.setter(text, 6, self.P7_type, self.P7_st, self.P7_len, self.Phase_7)
        self.Rep_rate.setValue( int( lines[7].split(':  ')[1] ) )
        self.Field.setValue( float( lines[8].split(':  ')[1] ) )

        self.shift_box.setCheckState(Qt.CheckState.Unchecked)
        self.fft_box.setCheckState(Qt.CheckState.Unchecked)
        self.Quad_cor.setCheckState(Qt.CheckState.Unchecked)
        self.Timescale.setValue( int( lines[9].split(':  ')[1] ) )
        self.Hor_offset.setValue( int( lines[10].split(':  ')[1] ) )
        self.Win_left.setValue( int( lines[11].split(':  ')[1] ) )
        self.Win_right.setValue( int( lines[12].split(':  ')[1] ) )
        self.Acq_number.setValue( int( lines[13].split(':  ')[1] ) )

        try:
            self.P_to_drop.setValue( int( lines[14].split(':  ')[1] ) )
            self.Zero_order.setValue( float( lines[15].split(':  ')[1] ) )
            self.First_order.setValue( float( lines[16].split(':  ')[1] ) )
            self.Second_order.setValue( float( lines[17].split(':  ')[1] ) )
        except IndexError:
            pass

        self.dig_stop()

        self.fft = 0
        self.quad = 0
        self.opened = 0

    def setter(self, text, index, typ, st, leng, phase):
        """
        Auxiliary function to set all the values from *.pulse file
        """
        array = text.split('\n')[index].split(':  ')[1].split(',  ')

        typ.setCurrentText( array[0] )
        st.setValue( int( array[1] ) )
        leng.setValue( int( array[2] ) )
        phase.setPlainText( str( array[3] ) )

    def save_file(self, filename):
        """
        A function to save a new pulse list
        :param filename: string
        """
        if filename[-5:] != 'phase':
            filename = filename + '.phase'
        with open(filename, 'w') as file:
            file.write( 'P1:  ' + self.P1_type.currentText() + ',  ' + str(self.P1_st.value()) + ',  ' + str(self.P1_len.value()) + ',  ' + str('[' + ','.join(self.ph_1) + ']') + '\n' )
            file.write( 'P2:  ' + self.P2_type.currentText() + ',  ' + str(self.P2_st.value()) + ',  ' + str(self.P2_len.value()) + ',  ' + str('[' + ','.join(self.ph_2) + ']') + '\n' )
            file.write( 'P3:  ' + self.P3_type.currentText() + ',  ' + str(self.P3_st.value()) + ',  ' + str(self.P3_len.value()) + ',  ' + str('[' + ','.join(self.ph_3) + ']') + '\n' )
            file.write( 'P4:  ' + self.P4_type.currentText() + ',  ' + str(self.P4_st.value()) + ',  ' + str(self.P4_len.value()) + ',  ' + str('[' + ','.join(self.ph_4) + ']') + '\n' )
            file.write( 'P5:  ' + self.P5_type.currentText() + ',  ' + str(self.P5_st.value()) + ',  ' + str(self.P5_len.value()) + ',  ' + str('[' + ','.join(self.ph_5) + ']') + '\n' )
            file.write( 'P6:  ' + self.P6_type.currentText() + ',  ' + str(self.P6_st.value()) + ',  ' + str(self.P6_len.value()) + ',  ' + str('[' + ','.join(self.ph_6) + ']') + '\n' )
            file.write( 'P7:  ' + self.P7_type.currentText() + ',  ' + str(self.P7_st.value()) + ',  ' + str(self.P7_len.value()) + ',  ' + str('[' + ','.join(self.ph_7) + ']') + '\n' )
            file.write( 'Rep rate:  ' + str(self.Rep_rate.value()) + '\n' )
            file.write( 'Field:  ' + str(self.Field.value()) + '\n' )
            file.write( 'Points:  ' + str(self.Timescale.value()) + '\n' )
            file.write( 'Horizontal offset:  ' + str(self.Hor_offset.value()) + '\n' )
            file.write( 'Window left:  ' + str(self.Win_left.value()) + '\n' )
            file.write( 'Window right:  ' + str(self.Win_right.value()) + '\n' )
            file.write( 'Acquisitions:  ' + str(self.Acq_number.value()) + '\n' )
            file.write( 'Points to Drop:  ' + str(self.P_to_drop.value()) + '\n' )
            file.write( 'Zero order:  ' + str(self.Zero_order.value()) + '\n' )
            file.write( 'First order:  ' + str(self.First_order.value()) + '\n' )
            file.write( 'Second order:  ' + str(self.Second_order.value()) + '\n' )

    def phase_converted(self, ph_str):
        if ph_str == '+x':
            return '+x'
        elif ph_str == '-x':
            return '-x'
        elif ph_str == '+y':
            return '+y'
        elif ph_str == '-y':
            return '-y'

    def phase_1(self):
        """
        A function to change a pulse 1 phase
        """
        temp = self.Phase_1.toPlainText()
        try:
            if temp[-1] == ']' and temp[0] == '[':
                self.ph_1 = temp[1:(len(temp)-1)].split(',')
                #print(self.ph_1)
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
        except IndexError:
            pass

    def remove_ns(self, string1):
        return string1.split(' ')[0]

    def add_ns(self, string1):
        """
        Function to add ' ns'
        """
        return str( string1 ) + ' ns'

    def check_length(self, length):
        self.errors.clear()

        if int( length ) != 0 and int( length ) < 12:
            self.errors.appendPlainText( 'Pulse should be longer than 12 ns' )

        return length

    # stop?
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
        self.digitizer_process.join()
        self.dig_stop()
        
        ##self.pb.pulser_stop()
        #sys.exit()

    def quit(self):
        """
        A function to quit the programm
        """
        self._on_destroyed()
        sys.exit()

    def p1_st(self):
        """
        A function to set pulse 1 start
        """
        self.p1_start = self.P1_st.value()
        if self.p1_start % 2 != 0:
            self.p1_start = self.p1_start + 1
            self.P1_st.setValue( self.p1_start )

        self.p1_start = self.add_ns( self.P1_st.value() )

    def p2_st(self):
        """
        A function to set pulse 2 start
        """
        self.p2_start = self.P2_st.value()
        if self.p2_start % 2 != 0:
            self.p2_start = self.p2_start + 1
            self.P2_st.setValue( self.p2_start )

        self.p2_start = self.add_ns( self.P2_st.value() )

    def p3_st(self):
        """
        A function to set pulse 3 start
        """
        self.p3_start = self.P3_st.value()
        if self.p3_start % 2 != 0:
            self.p3_start = self.p3_start + 1
            self.P3_st.setValue( self.p3_start )

        self.p3_start = self.add_ns( self.P3_st.value() )

    def p4_st(self):
        """
        A function to set pulse 4 start
        """
        self.p4_start = self.P4_st.value()
        if self.p4_start % 2 != 0:
            self.p4_start = self.p4_start + 1
            self.P4_st.setValue( self.p4_start )

        self.p4_start = self.add_ns( self.P4_st.value() )

    def p5_st(self):
        """
        A function to set pulse 5 start
        """
        self.p5_start = self.P5_st.value()
        if self.p5_start % 2 != 0:
            self.p5_start = self.p5_start + 1
            self.P5_st.setValue( self.p5_start )

        self.p5_start = self.add_ns( self.P5_st.value() )

    def p6_st(self):
        """
        A function to set pulse 6 start
        """
        self.p6_start = self.P6_st.value()
        if self.p6_start % 2 != 0:
            self.p6_start = self.p6_start + 1
            self.P6_st.setValue( self.p6_start )

        self.p6_start = self.add_ns( self.P6_st.value() )

    def p7_st(self):
        """
        A function to set pulse 7 start
        """
        self.p7_start = self.P7_st.value()
        if self.p7_start % 2 != 0:
            self.p7_start = self.p7_start + 1
            self.P7_st.setValue( self.p7_start )

        self.p7_start = self.add_ns( self.P7_st.value() )

    def p1_len(self):
        """
        A function to change a pulse 1 length
        """
        self.p1_length = self.P1_len.value()
        if self.p1_length % 2 != 0:
            self.p1_length = self.p1_length + 1
            self.P1_len.setValue( self.p1_length )

        pl = self.check_length( self.P1_len.value() )
        self.p1_length = self.add_ns( pl )

    def p2_len(self):
        """
        A function to change a pulse 2 length
        """
        self.p2_length = self.P2_len.value()
        if self.p2_length % 2 != 0:
            self.p2_length = self.p2_length + 1
            self.P2_len.setValue( self.p2_length )

        pl = self.check_length( self.P2_len.value() )
        self.p2_length = self.add_ns( pl )

    def p3_len(self):
        """
        A function to change a pulse 3 length
        """
        self.p3_length = self.P3_len.value()
        if self.p3_length % 2 != 0:
            self.p3_length = self.p3_length + 1
            self.P3_len.setValue( self.p3_length )

        pl = self.check_length( self.P3_len.value() )
        self.p3_length = self.add_ns( pl )

    def p4_len(self):
        """
        A function to change a pulse 4 length
        """
        self.p4_length = self.P4_len.value()
        if self.p4_length % 2 != 0:
            self.p4_length = self.p4_length + 1
            self.P4_len.setValue( self.p4_length )

        pl = self.check_length( self.P4_len.value() )
        self.p4_length = self.add_ns( pl )

    def p5_len(self):
        """
        A function to change a pulse 5 length
        """
        self.p5_length = self.P5_len.value()
        if self.p5_length % 2 != 0:
            self.p5_length = self.p5_length + 1
            self.P5_len.setValue( self.p5_length )

        pl = self.check_length( self.P5_len.value() )
        self.p5_length = self.add_ns( pl )

    def p6_len(self):
        """
        A function to change a pulse 6 length
        """
        self.p6_length = self.P6_len.value()
        if self.p6_length % 2 != 0:
            self.p6_length = self.p6_length + 1
            self.P6_len.setValue( self.p6_length )

        pl = self.check_length( self.P6_len.value() )
        self.p6_length = self.add_ns( pl )

    def p7_len(self):
        """
        A function to change a pulse 7 length
        """
        self.p7_length = self.P7_len.value()
        if self.p7_length % 2 != 0:
            self.p7_length = self.p7_length + 1
            self.P7_len.setValue( self.p7_length )

        pl = self.check_length( self.P7_len.value() )
        self.p7_length = self.add_ns( pl )

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
        if self.p2_typ == 'LASER':
            self.laser_flag = 1
        else:
            self.laser_flag = 0

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

    def rep_rate(self):
        """
        A function to change a repetition rate
        """
        self.repetition_rate = str( self.Rep_rate.value() ) + ' Hz'

        #self.pb.pulser_repetition_rate( self.repetition_rate )

        if self.laser_flag != 1:
            self.pb.pulser_repetition_rate( self.repetition_rate )
        #    ###self.update()
        elif self.laser_flag == 1 and self.combo_laser_num == 1:
            self.repetition_rate = '9.9 Hz'
            self.pb.pulser_repetition_rate( self.repetition_rate )
            self.Rep_rate.setValue(9.9)
        #    ###self.update()
            self.errors.appendPlainText( '9.9 Hz is a maximum repetiton rate with LASER pulse' )
        elif self.laser_flag == 1 and self.combo_laser_num == 2:
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
        if self.laser_flag != 1:
            self.pb.pulser_repetition_rate( self.repetition_rate )
            
            if int( self.p1_length.split(' ')[0] ) != 0:
                self.pb.pulser_pulse( name = 'P0', channel = self.p1_typ, start = self.p1_start, length = self.p1_length)
                # 2022-10-05
                #, \phase_list = self.ph_1
            if int( self.p2_length.split(' ')[0] ) != 0:
                self.pb.pulser_pulse( name = 'P1', channel = self.p2_typ, start = self.p2_start, length = self.p2_length, \
                                        phase_list = self.ph_2 )
            if int( self.p3_length.split(' ')[0] ) != 0:
                self.pb.pulser_pulse( name = 'P2', channel = self.p3_typ, start = self.p3_start, length = self.p3_length, \
                                        phase_list = self.ph_3 )
            if int( self.p4_length.split(' ')[0] ) != 0:
                self.pb.pulser_pulse( name = 'P3', channel = self.p4_typ, start = self.p4_start, length = self.p4_length, \
                                        phase_list = self.ph_4  )
            if int( self.p5_length.split(' ')[0] ) != 0:
                self.pb.pulser_pulse( name = 'P4', channel = self.p5_typ, start = self.p5_start, length = self.p5_length, \
                                        phase_list = self.ph_5 )
            if int( self.p6_length.split(' ')[0] ) != 0:
                self.pb.pulser_pulse( name = 'P5', channel = self.p6_typ, start = self.p6_start, length = self.p6_length, \
                                        phase_list = self.ph_6  )
            if int( self.p7_length.split(' ')[0] ) != 0:
                self.pb.pulser_pulse( name = 'P6', channel = self.p7_typ, start = self.p7_start, length = self.p7_length, \
                                        phase_list = self.ph_7  )

        else:
            if self.combo_laser_num == 1:
                self.pb.pulser_repetition_rate( '9.9 Hz' )
                self.Rep_rate.setValue(9.9)
            else:
                pass

            # add q_switch_delay
            self.p1_start_sh = self.add_ns( int( self.remove_ns( self.p1_start ) ) + self.laser_q_switch_delay )
            self.p3_start_sh = self.add_ns( int( self.remove_ns( self.p3_start ) ) + self.laser_q_switch_delay )
            self.p4_start_sh = self.add_ns( int( self.remove_ns( self.p4_start ) ) + self.laser_q_switch_delay )
            self.p5_start_sh = self.add_ns( int( self.remove_ns( self.p5_start ) ) + self.laser_q_switch_delay )
            self.p6_start_sh = self.add_ns( int( self.remove_ns( self.p6_start ) ) + self.laser_q_switch_delay )
            self.p7_start_sh = self.add_ns( int( self.remove_ns( self.p7_start ) ) + self.laser_q_switch_delay )

            if int( self.p1_length.split(' ')[0] ) != 0:
                self.pb.pulser_pulse( name = 'P0', channel = self.p1_typ, start = self.p1_start_sh, length = self.p1_length)
                # 2022-10-05
                #, \phase_list = self.ph_1
            if int( self.p2_length.split(' ')[0] ) != 0:
                self.pb.pulser_pulse( name = 'P1', channel = self.p2_typ, start = self.p2_start, length = self.p2_length, \
                                        phase_list = self.ph_2 )
            if int( self.p3_length.split(' ')[0] ) != 0:
                self.pb.pulser_pulse( name = 'P2', channel = self.p3_typ, start = self.p3_start_sh, length = self.p3_length, \
                                        phase_list = self.ph_3 )
            if int( self.p4_length.split(' ')[0] ) != 0:
                self.pb.pulser_pulse( name = 'P3', channel = self.p4_typ, start = self.p4_start_sh, length = self.p4_length, \
                                        phase_list = self.ph_4 )
            if int( self.p5_length.split(' ')[0] ) != 0:
                self.pb.pulser_pulse( name = 'P4', channel = self.p5_typ, start = self.p5_start_sh, length = self.p5_length, \
                                        phase_list = self.ph_5 )
            if int( self.p6_length.split(' ')[0] ) != 0:
                self.pb.pulser_pulse( name = 'P5', channel = self.p6_typ, start = self.p6_start_sh, length = self.p6_length, \
                                        phase_list = self.ph_6 )
            if int( self.p7_length.split(' ')[0] ) != 0:
                self.pb.pulser_pulse( name = 'P6', channel = self.p7_typ, start = self.p7_start_sh, length = self.p7_length, \
                                        phase_list = self.ph_7 )

            self.errors.appendPlainText( '140 us is added to all the pulses except the LASER pulse' )

        self.errors.appendPlainText( self.pb.pulser_pulse_list() )

        # before adding pulse phases
        #self.pb.pulser_update()
        # ?
        for i in range( len( self.ph_1 ) ):
            self.pb.pulser_next_phase()

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
        #print( self.test_process.exitcode )

        if self.test_process.exitcode == 0:
            self.test_process.join()

            # RUN
            # ?
            # can be problem here:
            # maybe it should be moved to pulser_test()
            # and deleted from here
            self.pb.pulser_clear()
            self.pb.pulser_test_flag('test')
            self.pulse_sequence()
            #self.errors.appendPlainText( self.pb.pulser_pulse_list() )
            
            self.pb.pulser_test_flag('None')
            self.dig_start()

        else:
            self.test_process.join()
            #14-03-2021
            #self.pb.pulser_stop()
            self.errors.clear()
            self.errors.appendPlainText( 'Incorrect pulse setting. Check that your pulses:\n' + \
                                        '1. Not overlapped\n' + \
                                        '2. Distance between MW pulses is more than 42 ns\n' + \
                                        '3. Pulses are longer or equal to 12 ns\n' + \
                                        '4. Field Controller is stucked\n' + \
                                        '5. LASER pulse should not be in 208-232; 152-182; 102-126; <76 ns from first MW\n' + \
                                        '6. Phase sequence does not have equal length for all pulses with nonzero length\n' + \
                                        '\nPulser is stopped')

    def pulser_test(self, conn, flag):
        """
        Test run
        """
        self.pb.pulser_clear()
        self.pb.pulser_test_flag( flag )
        self.pulse_sequence()

    def dig_stop(self):
        """
        A function to stop digitizer
        """
        path_to_main = os.path.abspath( os.getcwd() )
        path_file = os.path.join(path_to_main, 'atomize/control_center/digitizer.param')
        #path_file = os.path.join(path_to_main, '../../atomize/control_center/digitizer.param')

        if self.opened == 0:
            try:
                self.parent_conn_dig.send('exit')
                self.digitizer_process.join()
            except AttributeError:
                self.message('Digitizer is not running')

        #self.opened = 0

        file_to_read = open(path_file, 'w')
        file_to_read.write('Points: ' + str( self.points ) +'\n')
        file_to_read.write('Sample Rate: ' + str( 500 ) +'\n')
        file_to_read.write('Posstriger: ' + str( self.posttrigger ) +'\n')
        file_to_read.write('Range: ' + str( 500 ) +'\n')
        file_to_read.write('CH0 Offset: ' + str( 0 ) +'\n')
        file_to_read.write('CH1 Offset: ' + str( 0 ) +'\n')
        
        if self.cur_win_right < self.cur_win_left:
            self.cur_win_left, self.cur_win_right = self.cur_win_right, self.cur_win_left
        if self.cur_win_right == self.cur_win_left:
            self.cur_win_right += 1 #self.time_per_point

        file_to_read.write('Window Left: ' + str( int(self.cur_win_left) ) +'\n') #/ self.time_per_point
        file_to_read.write('Window Right: ' + str( int(self.cur_win_right ) ) +'\n') #/ self.time_per_point

        file_to_read.close()
        self.errors.clear()
        
    def dig_start(self):
        """
        Button Start; Run function script(pipe_addres, four parameters of the experimental script)
        from Worker class in a different thread
        Create a Pipe for interaction with this thread
        self.param_i are used as parameters for script function
        """

        if self.laser_flag != 1:
            p1_list = [ self.p1_typ, self.p1_start, self.p1_length, self.ph_1 ]
            p2_list = [ self.p2_typ, self.p2_start, self.p2_length, self.ph_2 ]
            p3_list = [ self.p3_typ, self.p3_start, self.p3_length, self.ph_3 ]
            p4_list = [ self.p4_typ, self.p4_start, self.p4_length, self.ph_4 ]
            p5_list = [ self.p5_typ, self.p5_start, self.p5_length, self.ph_5 ]
            p6_list = [ self.p6_typ, self.p6_start, self.p6_length, self.ph_6 ]
            p7_list = [ self.p7_typ, self.p7_start, self.p7_length, self.ph_7 ]
        else: 
            p1_list = [ self.p1_typ, self.p1_start_sh, self.p1_length, self.ph_1 ]
            p2_list = [ self.p2_typ, self.p2_start, self.p2_length, self.ph_2 ]
            p3_list = [ self.p3_typ, self.p3_start_sh, self.p3_length, self.ph_3 ]
            p4_list = [ self.p4_typ, self.p4_start_sh, self.p4_length, self.ph_4 ]
            p5_list = [ self.p5_typ, self.p5_start_sh, self.p5_length, self.ph_5 ]
            p6_list = [ self.p6_typ, self.p6_start_sh, self.p6_length, self.ph_6 ]
            p7_list = [ self.p7_typ, self.p7_start_sh, self.p7_length, self.ph_7 ]

        # prevent running two processes
        try:
            if self.digitizer_process.is_alive() == True:
                return
        except AttributeError:
            pass
        
        self.parent_conn_dig, self.child_conn_dig = Pipe()
        # a process for running function script 
        # sending parameters for initial initialization
        self.digitizer_process = Process( target = self.worker.dig_on, args = ( self.child_conn_dig, self.points, self.posttrigger, self.number_averages, \
                                            self.cur_win_left, self.cur_win_right, p1_list, p2_list, p3_list, p4_list, p5_list, p6_list, p7_list, \
                                            self.laser_flag, self.repetition_rate.split(' ')[0], self.mag_field, self.fft, self.quad, self.zero_order, self.first_order, \
                                            self.second_order, self.p_to_drop, self.combo_laser_num, ) )
               
        self.digitizer_process.start()
        # send a command in a different thread about the current state
        self.parent_conn_dig.send('start')

    def turn_off(self):
        """
        A function to turn off a programm.
        """
        try:
            self.parent_conn_dig.send('exit')
            self.digitizer_process.join()
        except AttributeError:
            self.message('Digitizer is not running')
            sys.exit()

        sys.exit()

    def help(self):
        """
        A function to open a documentation
        """
        pass

    def message(*text):
        sock = socket.socket()
        sock.connect(('localhost', 9091))
        if len(text) == 1:
            sock.send(str(text[0]).encode())
            sock.close()
        else:
            sock.send(str(text).encode())
            sock.close()

    def round_to_closest(self, x, y):
        """
        A function to round x to divisible by y
        """
        return int( y * ( ( x // y) + (x % y > 0) ) )

# The worker class that run the digitizer in a different thread
class Worker(QWidget):
    def __init__(self, parent = None):
        super(Worker, self).__init__(parent)
        # initialization of the attribute we use to stop the experimental script
        # when button Stop is pressed
        #from atomize.main.client import LivePlotClient

        self.command = 'start'
    
    def dig_on(self, conn, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p13, p14, p15, p16, p17, p18, p19, p20, p21, p22):
        """
        function that contains updating of the digitizer
        """
        # should be inside dig_on() function;
        # freezing after digitizer restart otherwise
        #import time
        import numpy as np
        import atomize.general_modules.general_functions as general
        ##import atomize.device_modules.Spectrum_M4I_4450_X8 as spectrum
        import atomize.device_modules.Keysight_2000_Xseries as key
        import atomize.device_modules.PB_ESR_500_pro as pb_pro
        import atomize.math_modules.fft as fft_module
        import atomize.device_modules.ITC_FC as itc

        pb = pb_pro.PB_ESR_500_Pro()
        fft = fft_module.Fast_Fourier()
        bh15 = itc.ITC_FC()
        bh15.magnet_setup( p15, 1 )

        process = 'None'
        ##dig = spectrum.Spectrum_M4I_4450_X8()
        a2012 = key.Keysight_2000_Xseries()
        # parameters for initial initialization
        #points_value =      p1
        ##dig.digitizer_number_of_points( p1 )
        #posstrigger_value = p2
        ##dig.digitizer_posttrigger(      p2 )
        num_ave =           p3
        ##dig.digitizer_number_of_averages( p3 )

        #p4 window left
        #p5 window right
        ##dig.digitizer_setup()

        if p13 != 1:
            pb.pulser_repetition_rate( str(p14) + ' Hz' )
            
            if int( p6[2].split(' ')[0] ) != 0:
                pb.pulser_pulse( name = 'P0', channel = p6[0], start = p6[1], length = p6[2] )
            if int( p7[2].split(' ')[0] ) != 0:
                pb.pulser_pulse( name = 'P1', channel = p7[0], start = p7[1], length = p7[2], phase_list = p7[3] )
            if int( p8[2].split(' ')[0] ) != 0:
                pb.pulser_pulse( name = 'P2', channel = p8[0], start = p8[1], length = p8[2], phase_list = p8[3] )
            if int( p9[2].split(' ')[0] ) != 0:
                pb.pulser_pulse( name = 'P3', channel = p9[0], start = p9[1], length = p9[2], phase_list = p9[3] )
            if int( p10[2].split(' ')[0] ) != 0:
                pb.pulser_pulse( name = 'P4', channel = p10[0], start = p10[1], length = p10[2], phase_list = p10[3] )
            if int( p11[2].split(' ')[0] ) != 0:
                pb.pulser_pulse( name = 'P5', channel = p11[0], start = p11[1], length = p11[2], phase_list = p11[3] )
            if int( p12[2].split(' ')[0] ) != 0:
                pb.pulser_pulse( name = 'P6', channel = p12[0], start = p12[1], length = p12[2], phase_list = p12[3] )

        else:
            if p22 == 1:
                pb.pulser_repetition_rate( '9.9 Hz' )
            else:
                pass

            # add q_switch_delay 141000 ns
            p6[1] = str( int( p6[1].split(' ')[0] ) + 141000 ) + ' ns'
            # p7 is a laser pulser
            p8[1] = str( int( p8[1].split(' ')[0] ) + 141000 ) + ' ns'
            p9[1] = str( int( p9[1].split(' ')[0] ) + 141000 ) + ' ns'
            p10[1] = str( int( p10[1].split(' ')[0] ) + 141000 ) + ' ns'
            p11[1] = str( int( p11[1].split(' ')[0] ) + 141000 ) + ' ns'
            p12[1] = str( int( p12[1].split(' ')[0] ) + 141000 ) + ' ns'

            if int( p6[2].split(' ')[0] ) != 0:
                pb.pulser_pulse( name = 'P0', channel = p6[0], start = p6[1], length = p6[2] )
            if int( p7[2].split(' ')[0] ) != 0:
                # p7 is a laser pulser
                pb.pulser_pulse( name = 'P1', channel = p7[0], start = p7[1], length = p7[2] ) #, phase_list = p7[3]
            if int( p8[2].split(' ')[0] ) != 0:
                pb.pulser_pulse( name = 'P2', channel = p8[0], start = p8[1], length = p8[2], phase_list = p8[3] )
            if int( p9[2].split(' ')[0] ) != 0:
                pb.pulser_pulse( name = 'P3', channel = p9[0], start = p9[1], length = p9[2], phase_list = p9[3] )
            if int( p10[2].split(' ')[0] ) != 0:
                pb.pulser_pulse( name = 'P4', channel = p10[0], start = p10[1], length = p10[2], phase_list = p10[3] )
            if int( p11[2].split(' ')[0] ) != 0:
                pb.pulser_pulse( name = 'P5', channel = p11[0], start = p11[1], length = p11[2], phase_list = p11[3] )
            if int( p12[2].split(' ')[0] ) != 0:
                pb.pulser_pulse( name = 'P6', channel = p12[0], start = p12[1], length = p12[2], phase_list = p12[3] )

        pb.pulser_update()

        a2012.oscilloscope_trigger_channel('Ext')
        a2012.oscilloscope_record_length(4000)
        a2012.oscilloscope_acquisition_type('Average')
        a2012.oscilloscope_stop()

        # Oscilloscopes bug
        a2012.oscilloscope_number_of_averages(2)
        a2012.oscilloscope_start_acquisition()

        y = a2012.oscilloscope_get_curve('CH1')

        real_length = a2012.oscilloscope_record_length( )
        t_res = round( a2012.oscilloscope_timebase() / real_length, 5 )    # in us

        a2012.oscilloscope_number_of_averages(p3)

        cycle_data_x = np.zeros( (len(p6[3]), int(real_length)) )
        cycle_data_y = np.zeros( (len(p6[3]), int(real_length)) )
        data_x = np.zeros( real_length ) #p1
        data_y = np.zeros( real_length ) #p1

        # the idea of automatic and dynamic changing is
        # sending a new value of repetition rate via self.command
        # in each cycle we will check the current value of self.command
        # self.command = 'exit' will stop the digitizer
        while self.command != 'exit':
            # always test our self.command attribute for stopping the script when neccessary

            if self.command[0:2] == 'PO':            
                points_value = int( self.command[2:] )
                a2012.oscilloscope_stop()
                a2012.oscilloscope_timebase( str(points_value) + ' ns' )
                a2012.oscilloscope_run()

                # Oscilloscopes bug
                a2012.oscilloscope_number_of_averages(2)
                a2012.oscilloscope_start_acquisition()

                y = a2012.oscilloscope_get_curve('CH1')
                a2012.oscilloscope_number_of_averages(num_ave)
                a2012.oscilloscope_stop()

            elif self.command[0:2] == 'HO':
                posstrigger_value = int( self.command[2:] )
                a2012.oscilloscope_stop()
                a2012.oscilloscope_horizontal_offset( str(posstrigger_value) + ' ns' )
                a2012.oscilloscope_run()

                # Oscilloscopes bug
                a2012.oscilloscope_number_of_averages(2)
                a2012.oscilloscope_start_acquisition()

                y = a2012.oscilloscope_get_curve('CH1')
                a2012.oscilloscope_number_of_averages(num_ave)
                a2012.oscilloscope_stop()

            elif self.command[0:2] == 'NA':
                num_ave = int( self.command[2:] )
                a2012.oscilloscope_stop()
                a2012.oscilloscope_number_of_averages(num_ave)
                a2012.oscilloscope_run()
                #dig.digitizer_stop()
                #dig.digitizer_number_of_averages( num_ave )
                #dig.digitizer_setup()
            elif self.command[0:2] == 'WL':
                p4 = int( self.command[2:] )
            elif self.command[0:2] == 'WR':
                p5 = int( self.command[2:] )
            elif self.command[0:2] == 'RR':
                p14 = float( self.command[2:] )
                pb.pulser_repetition_rate( str(p14) + ' Hz' )
            elif self.command[0:2] == 'FI':
                p15 = float( self.command[2:] )
                bh15.magnet_field( p15 )
            elif self.command[0:2] == 'FF':
                p16 = int( self.command[2:] )
            elif self.command[0:2] == 'QC':
                p17 = int( self.command[2:] )
            elif self.command[0:2] == 'ZO':
                p18 = float( self.command[2:] )
            elif self.command[0:2] == 'FO':
                p19 = float( self.command[2:] )
            elif self.command[0:2] == 'SO':
                p20 = float( self.command[2:] )
            elif self.command[0:2] == 'PD':
                p21 = int( self.command[2:] )

            real_length = a2012.oscilloscope_record_length( )
            t_res = round( a2012.oscilloscope_timebase() / real_length, 6 )    # in us

            cycle_data_x = np.zeros( (len(p6[3]), int(real_length)) )
            cycle_data_y = np.zeros( (len(p6[3]), int(real_length)) )
            data_x = np.zeros( real_length ) #p1
            data_y = np.zeros( real_length ) #p1
            x_axis = np.linspace(0, real_length * t_res, num = real_length, endpoint = False)

            # check integration window
            if p4 > real_length:
                p4 = real_length
            if p5 > real_length:
                p5 = real_length

            # phase cycle
            k = 0
            while k < len( p6[3] ):

                pb.pulser_next_phase()
                a2012.oscilloscope_start_acquisition()
                cycle_data_x[k], cycle_data_y[k] = a2012.oscilloscope_get_curve('CH1'), a2012.oscilloscope_get_curve('CH2')
                k += 1

            if p16 == 0:
                # acquisition cycle
                data_x, data_y = pb.pulser_acquisition_cycle(cycle_data_x, cycle_data_y , acq_cycle = p6[3])
                process = general.plot_1d('Digitizer', x_axis, ( data_x, data_y ), label = 'ch', xscale = 'us', yscale = 'V', \
                                            vline = (p4 * t_res, p5 * t_res), pr = process )

            else:
                # acquisition cycle
                data_x, data_y = pb.pulser_acquisition_cycle(cycle_data_x, cycle_data_y , acq_cycle = p6[3])
                process = general.plot_1d('Digitizer', x_axis, ( data_x, data_y ), label = 'ch', xscale = 'us', yscale = 'V', \
                                    vline = (p4 * t_res, p5 * t_res), pr = process )
                if p17 == 0:
                    freq_axis, abs_values = fft.fft(x_axis, data_x, data_y, t_res * 1000)
                    m_val = round( np.amax( abs_values ), 2 )
                    process = general.plot_1d('FFT', freq_axis, abs_values, xname = 'Freq Offset', label = 'FFT', xscale = 'MHz', \
                                              yscale = 'Arb. U.', text = 'Max ' + str(m_val), pr = process)
                else:
                    if p21 > len( data_x ) - 2:
                        p21 = len( data_x ) - 4
                        general.message('Maximum length of the data achieved. A number of drop points was corrected.')
                    # fixed resolution of digitizer; 2 ns
                    freq, fft_x, fft_y = fft.fft( x_axis[p21:], data_x[p21:], data_y[p21:], t_res * 1000, re = 'True' )
                    data = fft.ph_correction( freq, fft_x, fft_y, p18, p19, p20 )
                    process = general.plot_1d('FFT', freq, ( data[0], data[1] ), xname = 'Freq Offset', xscale = 'MHz', \
                                              yscale = 'Arb. U.', label = 'FFT', pr = process)

            self.command = 'start'
            pb.pulser_pulse_reset()
            ###time.sleep( 0.2 )

            # poll() checks whether there is data in the Pipe to read
            # we use it to stop the script if the exit command was sent from the main window
            # we read data by conn.recv() only when there is the data to read
            if conn.poll() == True:
                self.command = conn.recv()

        if self.command == 'exit':

            #dig.digitizer_stop()
            #dig.digitizer_close()
            # ?
            #pb.pulser_clear()
            a2012.oscilloscope_stop()
            pb.pulser_stop()
            pb.pulser_pulse_reset()


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
