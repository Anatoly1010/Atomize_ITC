#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import datetime
import struct
import socket
import configparser
from math import exp, sqrt
from threading import Thread
#import time
#import numpy as np
#from PyQt5.QtWidgets import QListView, QAction
from PyQt6 import QtWidgets, uic #, QtCore, QtGui
from PyQt6.QtWidgets import QWidget 
from PyQt6.QtGui import QIcon
import atomize.general_modules.general_functions as general

class MainWindow(QtWidgets.QMainWindow):
    """
    A main window class
    """
    def __init__(self, *args, **kwargs):
        """
        A function for connecting actions and creating a main window
        """
        super(MainWindow, self).__init__(*args, **kwargs)
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # SOCK_DGRAM is UDP

        self.destroyed.connect(lambda: self._on_destroyed())         # connect some actions to exit
        # Load the UI Page
        path_to_main = os.path.dirname(os.path.abspath(__file__))
        gui_path = os.path.join(path_to_main,'gui/mw_main_window.ui')
        icon_path = os.path.join(path_to_main, 'gui/icon_mw.png')
        self.setWindowIcon( QIcon(icon_path) )

        uic.loadUi(gui_path, self)                        # Design file

        # configuration data
        path_config_file = os.path.join(path_to_main,'mw_config.ini')
        config = configparser.ConfigParser()
        config.read(path_config_file)

        self.UDP_IP = str(config['DEFAULT']['UDP_IP'])
        self.UDP_PORT = int(config['DEFAULT']['UDP_PORT'])

        # Connection of different action to different Menus and Buttons
        self.button_initialize.clicked.connect(self.initialize)
        self.button_initialize.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); ; border-style: inset}")
        self.button_off.clicked.connect(self.turn_off)
        self.button_off.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); ; border-style: inset}")
        self.button_telemetry.clicked.connect(self.telemetry)
        self.button_telemetry.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); ; border-style: inset}")

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

        self.telemetry_text.setStyleSheet("QPlainTextEdit { color : rgb(211, 194, 78); }") # rgb(193, 202, 227)
        
        # Spinboxes
        self.Att1_prd.valueChanged.connect(self.att1_prd)
        self.Att1_prd.lineEdit().setReadOnly( True )   # block input from keyboard
        self.Att1_prd.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.Att2_prd.valueChanged.connect(self.att2_prd)
        self.Att2_prd.lineEdit().setReadOnly( True )
        self.Att2_prd.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.Fv_ctrl.valueChanged.connect(self.fv_ctrl)
        self.Fv_ctrl.lineEdit().setReadOnly( True )
        self.Fv_ctrl.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.Fv_prm.valueChanged.connect(self.fv_prm)
        self.Fv_prm.lineEdit().setReadOnly( True )
        self.Fv_prm.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.Att1_prm.valueChanged.connect(self.att1_prm)
        self.Att1_prm.lineEdit().setReadOnly( True )
        self.Att1_prm.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.Att2_prm.valueChanged.connect(self.att2_prm)
        self.Att2_prm.lineEdit().setReadOnly( True )
        self.Att2_prm.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.Synt.valueChanged.connect(self.synt)
        self.Synt.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")

        self.Rot_vane.valueChanged.connect(self.rot_vane)
        #self.Rot_vane.lineEdit().setReadOnly( True )
        self.Rot_vane.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")

        # Radio Buttons
        self.cutoff_1.clicked.connect(self.cutoff_changed_1)
        self.cutoff_1.setStyleSheet("QRadioButton { color : rgb(193, 202, 227); font-weight: bold; }")
        self.cutoff_2.clicked.connect(self.cutoff_changed_2)
        self.cutoff_2.setStyleSheet("QRadioButton { color : rgb(193, 202, 227); font-weight: bold; }")
        self.cutoff_3.clicked.connect(self.cutoff_changed_3)
        self.cutoff_3.setStyleSheet("QRadioButton { color : rgb(193, 202, 227); font-weight: bold; }")

        self.curr_dB = 60
        self.prev_dB = 60
        self.p1 = 'None'

        #self.synt()
        self.initialize()
        self.telemetry()

    def _on_destroyed(self):
        """
        A function to do some actions when the main window is closing.
        """    
        self.initialize_at_exit()
        self.sock.close()
        
        try:
            self.p1.join()
        except ( AttributeError, NameError, TypeError ):
            pass

        #sock.shutdown(socket.SHUT_RDWR)
        #sock.close()

    def quit(self):
        """
        A function to quit the programm
        """
        self.initialize_at_exit()

        try:
            self.p1.join()
        except ( AttributeError, NameError, TypeError ):
            pass

        #sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()
        sys.exit()

    def att1_prd(self):
        """
        A function to send a value to the attenuator 1 in the PRD channel
        """

        param = self.Att1_prd.value()
        temp = 2*param
        MESSAGE = b'\x15' + b'\x01' + struct.pack(">B", int(temp))
        # all variants give the same result. Struct.pack is the fastest
        #print( (int(temp)).to_bytes(1, byteorder='big') )
        #print( struct.pack(">B", int(temp)) )
        
        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        # get attenuation
        MESSAGE = b'\x1f' + b'\x01' + b'\x00'

        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        self.telemetry_text.appendPlainText( 'Att. RECT: ' + str(data_raw[2] / 2) + ' dB')

    def att2_prd(self):
        """
        A function to send a value to the attenuator 2 in the PRD channel
        """

        param = self.Att2_prd.value()
        temp = 2*param
        MESSAGE = b'\x16' + b'\x01' + struct.pack(">B", int(temp))
        
        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        # get attenuation
        MESSAGE = b'\x20' + b'\x01' + b'\x00'

        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        self.telemetry_text.appendPlainText( 'Att. AWG: ' + str(data_raw[2]/2) + ' dB')

    def fv_ctrl(self):
        """
        A function to send a value to the phase shifter in the CTRL channel
        """

        param = self.Fv_ctrl.value()
        
        # cycling
        if param == 360:
            self.Fv_ctrl.setValue(0.0)
            param = self.Fv_ctrl.value()
        else:
            pass

        if param == -5.625:
            self.Fv_ctrl.setValue(360.0 - 5.625)
            param = self.Fv_ctrl.value()
        else:
            pass

        temp = param/5.625
        MESSAGE = b'\x17' + b'\x01' + struct.pack(">B", int(temp))
        
        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        # get phase
        MESSAGE = b'\x21' + b'\x01' + b'\x00'

        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        self.telemetry_text.appendPlainText( 'Test Phase: ' + str(data_raw[2]*5.625) + ' deg')

    def fv_prm(self):
        """
        A function to send a value to the phase shifter in the PRM channel
        """

        param = self.Fv_prm.value()
        
        # cycling
        if param == 360:
            self.Fv_prm.setValue(0.0)
            param = self.Fv_prm.value()
        else:
            pass

        if param == -5.625:
            self.Fv_prm.setValue(360.0 - 5.625)
            param = self.Fv_prm.value()
        else:
            pass

        temp = param/5.625
        MESSAGE = b'\x19' + b'\x01' + struct.pack(">B", int(temp))
        
        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        # get phase
        MESSAGE = b'\x23' + b'\x01' + b'\x00'

        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        self.telemetry_text.appendPlainText( 'Phase: ' + str(data_raw[2]*5.625) + ' deg')

    def att1_prm(self):
        """
        A function to send a value to the attenuator 1 in the PRM channel
        """

        param = self.Att1_prm.value()
        temp = param/2
        MESSAGE = b'\x1c' + b'\x01' + struct.pack(">B", int(temp))
        
        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        # get attenuation
        MESSAGE = b'\x26' + b'\x01' + b'\x00'

        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        self.telemetry_text.appendPlainText( 'Video Att. 1: ' + str(data_raw[2]*2) + ' dB')

    def att2_prm(self):
        """
        A function to send a value to the attenuator 2 in the PRM channel
        """

        param = self.Att2_prm.value()
        temp = 2*param
        MESSAGE = b'\x1a' + b'\x01' + struct.pack(">B", int(temp))
        
        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        # get amplification
        MESSAGE = b'\x24' + b'\x01' + b'\x00'

        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        self.telemetry_text.appendPlainText( 'Video Att. 2: ' + str(data_raw[2]/2) + ' dB')

    def cutoff_changed_2(self):
        """
        A function to change the amplification coefficient in the PRM channel
        """

        MESSAGE = b'\x1b' + b'\x01' + b'\x00'

        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        # get cutt-off
        MESSAGE = b'\x25' + b'\x01' + b'\x00'

        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        if data_raw[2] == 0:
            freq = '30'
        elif data_raw[2] == 1:
            freq = '105'
        elif data_raw[2] == 2:
            freq = '300'

        self.telemetry_text.appendPlainText( 'Cut-off: ' + freq + ' MHz')

    def cutoff_changed_3(self):
        """
        A function to change the amplification coefficient in the PRM channel
        """

        MESSAGE = b'\x1b' + b'\x01' + b'\x01'

        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        # get cutt-off
        MESSAGE = b'\x25' + b'\x01' + b'\x00'

        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        if data_raw[2] == 0:
            freq = '30'
        elif data_raw[2] == 1:
            freq = '105'
        elif data_raw[2] == 2:
            freq = '300'

        self.telemetry_text.appendPlainText( 'Cut-off: ' + freq + ' MHz')

    def cutoff_changed_1(self):
        """
        A function to change the amplification coefficient in the PRM channel
        """

        MESSAGE = b'\x1b' + b'\x01' + b'\x02'

        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        # get cutt-off
        MESSAGE = b'\x25' + b'\x01' + b'\x00'

        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        if data_raw[2] == 0:
            freq = '30'
        elif data_raw[2] == 1:
            freq = '105'
        elif data_raw[2] == 2:
            freq = '300'

        self.telemetry_text.appendPlainText( 'Cut-off: ' + freq + ' MHz')

    def synt(self):
        """
        A function to change the frequency
        """

        param = self.Synt.value()
        temp = str(param)
        if len( temp ) == 4:
            temp = '0' + temp
        elif len( temp ) == 5:
            temp = temp

        MESSAGE = b'\x04' + b'\x08' + b'\x00' + b'\x00' + b'\x00' + temp.encode()
        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(10)


        # get frequency
        MESSAGE = b'\x1e' + b'\x08' + (0).to_bytes(8, byteorder='big')

        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(10)

        if chr(data_raw[4]) == '1':
            state = 'ON'
        elif chr(data_raw[4]) == '0':
            state = 'OFF'

        if chr(data_raw[5]) == '0':
            freq = chr(data_raw[6]) + chr(data_raw[7])\
                + chr(data_raw[8]) + chr(data_raw[9])
        else:
            freq = chr(data_raw[5]) + chr(data_raw[6]) + chr(data_raw[7])\
                + chr(data_raw[8]) + chr(data_raw[9])

        self.telemetry_text.appendPlainText( 'Power: ' + state + '\n' \
            + 'Frequency: ' + freq )

    def pause_and_label(self, time):
        self.label_9.setStyleSheet("QLabel { color : rgb(255, 0, 0); font-weight: bold; }")
        general.wait( time )
        self.label_9.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
    
    def pause_and_label_exit(self, time):
        general.wait( time )

    def rot_vane(self):
        """
        A function to send a value to the rotary vane attenuator
        """
        param = self.Rot_vane.value()
        self.curr_dB = round( float( param ), 1 )
        step = int( self.calibration( self.curr_dB ) ) - int( self.calibration( self.prev_dB ) )

        try:
            self.p1.join()
        except ( AttributeError, NameError, TypeError ):
            pass

        MESSAGE = b'\x0e' + b'\x04' + b'\x01' + b'\x02' + ( step ).to_bytes( 2, byteorder = 'big', signed = True )
        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        # 6 bytes to recieve

        # 36 is a manual calibration
        time_to_wait = abs( 36 * step )

        self.p1 = Thread(target = self.pause_and_label, args = (str(time_to_wait) + ' ms', ) )
        self.p1.start()
        
        data_raw, addr = self.sock.recvfrom(6)
        
        self.telemetry_text.appendPlainText( 'Rotary Vane: ' + str( self.curr_dB ) + ' dB')

        self.prev_dB = self.curr_dB

    def initialize(self):
        """
        A function to initialize a bridge.
        """

        MESSAGE = b'\x27' + b'\x01' + b'\x00'

        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        # 300 MHz BW
        MESSAGE = b'\x1b' + b'\x01' + b'\x02'
        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        # 15 and 20 dB
        temp = 2*self.Att1_prd.value()
        MESSAGE = b'\x15' + b'\x01' + struct.pack(">B", int(temp))
        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        temp = 2*self.Att2_prd.value()
        MESSAGE = b'\x16' + b'\x01' + struct.pack(">B", int(temp))
        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        # Rotary vane to 60 dB
        MESSAGE = b'\x0e' + b'\x04' + b'\x01' + b'\x01' + (3).to_bytes( 2, byteorder = 'big', signed = False )
        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )

        self.p1 = Thread(target = self.pause_and_label, args = ( '5 s', ) )
        self.p1.start()
        
        data_raw, addr = self.sock.recvfrom(6)
        
        self.curr_dB = 60
        self.prev_dB = 60

        self.telemetry_text.appendPlainText( 'Initialization done' )
    
    def initialize_at_exit(self):
        """
        A function to initialize a bridge.
        """
        # Rotary vane to 60 dB
        step = int( self.calibration( 60 ) ) - int( self.calibration( self.prev_dB ) )
        
        MESSAGE = b'\x0e' + b'\x04' + b'\x01' + b'\x02' + ( step ).to_bytes( 2, byteorder = 'big', signed = True )
        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )

        time_to_wait = abs( 36 * step )

        self.p1 = Thread(target = self.pause_and_label_exit, args = ( str(time_to_wait) + ' ms', ) )
        self.p1.start()
        
        data_raw, addr = self.sock.recvfrom(6)
        
        self.curr_dB = 60
        self.prev_dB = 60

    def turn_off(self):
        """
         A function to turn off a bridge.
        """
        self.quit()

    def telemetry(self):
        """
        A function to get the telemetry.
        """

        MESSAGE = b'\x0d' + b'\x08' + (0).to_bytes(8, byteorder='big')
        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )

        data_raw, addr = self.sock.recvfrom(10)

        data = data_raw #.decode()
        if int(data[4]) == 1:
            state = 'INIT'
        elif int(data[4]) == 2:
            state = 'WORK'
        elif int(data[4]) == 3:
            state = 'FAIL'

        self.telemetry_text.appendPlainText( str(datetime.datetime.now().strftime("%d %b %Y %H:%M:%S")) + '\n' +\
             'Temperature: ' + str(data[8]) + '\n' \
             + 'State: ' + state)

    def help(self):
        """
        A function to open a documentation
        """
        pass

    def calibration(self, x):
        # approximation curve
        # step to dB
        return -4409.48 + 676.179 * exp( -0.0508708 * x ) + 2847.41 * exp( 0.00768761 * x ) - 0.345934 * x ** 2 + 2847.41 * exp( 0.00768761 * x ) - 440.034 * sqrt( x )

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
