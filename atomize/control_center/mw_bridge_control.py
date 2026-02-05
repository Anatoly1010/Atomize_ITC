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
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QDoubleSpinBox, QSpinBox, QComboBox, QPushButton, QTextEdit, QGridLayout, QFrame
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt
import atomize.general_modules.general_functions as general
import atomize.device_modules.ECC_15K as ecc

class MainWindow(QMainWindow):
    """
    A main window class
    """
    def __init__(self, *args, **kwargs):
        """
        A function for connecting actions and creating a main window
        """
        super(MainWindow, self).__init__(*args, **kwargs)
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # SOCK_DGRAM is UDP

        # configuration data
        path_to_main = os.path.dirname(os.path.abspath(__file__))        
        path_config_file = os.path.join(path_to_main,'mw_config.ini')
        config = configparser.ConfigParser()
        config.read(path_config_file)

        #self.ecc15k = ecc.ECC_15K()

        self.UDP_IP = str(config['DEFAULT']['UDP_IP'])
        self.UDP_PORT = int(config['DEFAULT']['UDP_PORT'])

        self.design()

        self.curr_dB = 60
        self.prev_dB = 60
        self.p1 = 'None'

        #self.synt()
        self.initialize()
        #self.telemetry()

        #self.ecc15k.synthetizer_frequency(f"{freq2} MHz")
        #self.ecc15k.synthetizer_power(power2)
        
        #self.telemetry_text.setStyleSheet("QPlainTextEdit { color : rgb(211, 194, 78); }")

    def design(self):

        self.destroyed.connect(lambda: self._on_destroyed())
        self.setObjectName("MainWindow")
        self.setWindowTitle("Pulsed Bridge Control")
        self.setStyleSheet("background-color: rgb(42,42,64);")

        path_to_main = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(path_to_main, 'gui/icon_mw.png')
        self.setWindowIcon( QIcon(icon_path) )

        centralwidget = QWidget(self)
        self.setCentralWidget(centralwidget)

        gridLayout = QGridLayout()
        gridLayout.setContentsMargins(15, 10, 10, 10)
        gridLayout.setVerticalSpacing(4)
        gridLayout.setHorizontalSpacing(20)

        centralwidget.setLayout(gridLayout)


        # ---- Labels & Inputs ----
        labels = [("Rotary Vane", "label_1"), ("Attenuator RECT", "label_2"), ("Attenuator AWG", "label_3"), ("Pulse Phase", "label_4"), ("Signal Phase", "label_5"), ("Video Attenuation 1", "label_6"), ("Video Attenuation 2", "label_7"), ("Frequency Synthesizer 1", "label_8"), ("Frequency Synthesizer 2", "label_9"), ("State Synthesizer 2", "label_10"), ("Power Synthesizer 2", "label_11"), ("Cut-Off Frequency", "label_12")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            setattr(self, attr_name, lbl)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")


        # ---- Boxes ----
        double_boxes = [(QDoubleSpinBox, "Rot_vane", "", self.rot_vane, 0, 60, 60, 0.1, 1, " dB"),
                      (QDoubleSpinBox, "Att1_prd", "", self.att1_prd, 0, 31.5, 16, 0.5, 1, " dB"),
                      (QDoubleSpinBox, "Att2_prd", "", self.att2_prd, 0, 31.5, 16, 0.5, 1, " dB"),
                      (QDoubleSpinBox, "Fv_ctrl", "", self.fv_ctrl, -5.625, 360, 0, 5.625, 3, " deg"),
                      (QDoubleSpinBox, "Fv_prm", "", self.fv_prm, -5.625, 360, 0, 5.625, 3, " deg"),
                      (QSpinBox, "Att1_prm", "", self.att1_prm, 0, 30, 0, 2, 0, " dB"),
                      (QDoubleSpinBox, "Att2_prm", "", self.att2_prm, 0, 31.5, 0, 0.5, 1, " dB"),
                      (QSpinBox, "Synt", "", self.synt, 7000, 12000, 9700, 1, 0, " MHz"),
                      (QSpinBox, "Synt2", "", self.synt2, 800, 12000, 1000, 1, 0, " MHz"),
                      (QSpinBox, "Synt2_power", "", self.synt2_power, 0, 15, 15, 1, 0, "")
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

            if attr_name in ["Att1_prd", "Att2_prd", "Fv_ctrl", "Fv_prm", "Att1_prm", "Att2_prm"]:
                spin_box.lineEdit().setReadOnly( True )

        power2 = int( self.Synt2_power.value() )
        freq2 = int( self.Synt2.value() )

        # ---- Combo boxes----
        combo_boxes = [("Off", "Synt2_state", "", self.synt2_state, 
                        [
                        "Off", "On"
                        ]),
                      ("300 MHz", "Cuttoff_box", "", self.cutoff_changed, 
                        [
                        "30 MHz", "105 MHz", "300 MHz"
                        ])
                      ]


        for cur_text, attr_name, par_name, func, item in combo_boxes:
            combo = QComboBox()
            setattr(self, attr_name, combo)
            combo.currentIndexChanged.connect(func)
            combo.addItems(item)
            combo.setCurrentText(cur_text)
            combo.setFixedSize(130, 26)
            combo.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")


        # ---- Buttons ----
        buttons = [("Reset", "button_initialize", self.initialize),
                   ("Telemetry", "button_telemetry", self.telemetry),
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
        gridLayout.addWidget(self.Rot_vane, 0, 1)

        gridLayout.addWidget(hline(), 1, 0, 1, 2)

        gridLayout.addWidget(self.label_2, 2, 0)
        gridLayout.addWidget(self.Att1_prd, 2, 1)
        gridLayout.addWidget(self.label_3, 3, 0)
        gridLayout.addWidget(self.Att2_prd, 3, 1)

        gridLayout.addWidget(hline(), 4, 0, 1, 2)

        gridLayout.addWidget(self.label_4, 5, 0)
        gridLayout.addWidget(self.Fv_ctrl, 5, 1)
        gridLayout.addWidget(self.label_5, 6, 0)
        gridLayout.addWidget(self.Fv_prm, 6, 1)

        gridLayout.addWidget(hline(), 7, 0, 1, 2)

        gridLayout.addWidget(self.label_6, 8, 0)
        gridLayout.addWidget(self.Att1_prm, 8, 1)
        gridLayout.addWidget(self.label_7, 9, 0)
        gridLayout.addWidget(self.Att2_prm, 9, 1)

        gridLayout.addWidget(hline(), 10, 0, 1, 2)

        gridLayout.addWidget(self.label_8, 11, 0)
        gridLayout.addWidget(self.Synt, 11, 1)

        gridLayout.addWidget(hline(), 12, 0, 1, 2)

        gridLayout.addWidget(self.label_9, 13, 0)
        gridLayout.addWidget(self.Synt2, 13, 1)
        gridLayout.addWidget(self.label_10, 14, 0)
        gridLayout.addWidget(self.Synt2_state, 14, 1)
        gridLayout.addWidget(self.label_11, 15, 0)
        gridLayout.addWidget(self.Synt2_power, 15, 1)

        gridLayout.addWidget(hline(), 16, 0, 1, 2)

        gridLayout.addWidget(self.label_12, 17, 0)
        gridLayout.addWidget(self.Cuttoff_box, 17, 1)

        gridLayout.addWidget(hline(), 18, 0, 1, 2)

        gridLayout.addWidget(self.button_initialize, 19, 0)
        gridLayout.addWidget(self.button_telemetry, 20, 0)
        gridLayout.addWidget(self.button_off, 21, 0)

        gridLayout.setRowStretch(22, 2)
        gridLayout.setColumnStretch(22, 2)

    def synt2(self):
        freq2 = int( self.Synt2.value() )
        #self.ecc15k.synthetizer_frequency(f"{freq2} MHz")
        #self.telemetry_text.appendPlainText( f'Synt2 Freq: {self.ecc15k.synthetizer_frequency().split(" ")[0]}')
    
    def synt2_power(self):
        power2 = int( self.Synt2_power.value() )
        #self.ecc15k.synthetizer_power(power2)
        #self.telemetry_text.appendPlainText( f'Synt2 Power Level: {self.ecc15k.synthetizer_power()}')

    def synt2_state(self):
        txt = str( self.Synt2_state.currentText() )
        #self.ecc15k.synthetizer_state(txt)
        #self.telemetry_text.appendPlainText( f'Synt2 State: {self.ecc15k.synthetizer_state()}')

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

        #self.telemetry_text.appendPlainText( 'Att. RECT: ' + str(data_raw[2] / 2) + ' dB')

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

        #self.telemetry_text.appendPlainText( 'Att. AWG: ' + str(data_raw[2]/2) + ' dB')

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

        #self.telemetry_text.appendPlainText( 'Test Phase: ' + str(data_raw[2]*5.625) + ' deg')

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

        #self.telemetry_text.appendPlainText( 'Phase: ' + str(data_raw[2]*5.625) + ' deg')

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

        #self.telemetry_text.appendPlainText( 'Video Att. 1: ' + str(data_raw[2]*2) + ' dB')

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

        #self.telemetry_text.appendPlainText( 'Video Att. 2: ' + str(data_raw[2]/2) + ' dB')

    def cutoff_changed(self):
        """
        A function to change the bandwidth of the video amplifier
        """
        txt = str( self.Cuttoff_box.currentText() )

        if txt == '300 MHz':
            MESSAGE = b'\x1b' + b'\x01' + b'\x02'

            self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
            data_raw, addr = self.sock.recvfrom(3)

            # get cutt-off
            MESSAGE = b'\x25' + b'\x01' + b'\x00'

            self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
            data_raw, addr = self.sock.recvfrom(3)

            if data_raw[2] == 0:
                freq = 30
            elif data_raw[2] == 1:
                freq = 105
            elif data_raw[2] == 2:
                freq = 300

            #self.telemetry_text.appendPlainText( f'Cut-off: {freq} MHz')
        
        elif txt == '105 MHz':
            MESSAGE = b'\x1b' + b'\x01' + b'\x01'

            self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
            data_raw, addr = self.sock.recvfrom(3)

            # get cutt-off
            MESSAGE = b'\x25' + b'\x01' + b'\x00'

            self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
            data_raw, addr = self.sock.recvfrom(3)

            if data_raw[2] == 0:
                freq = 30
            elif data_raw[2] == 1:
                freq = 105
            elif data_raw[2] == 2:
                freq = 300

            #self.telemetry_text.appendPlainText( f'Cut-off: {freq} MHz')
        
        elif txt == '30 MHz':
            MESSAGE = b'\x1b' + b'\x01' + b'\x00'

            self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
            data_raw, addr = self.sock.recvfrom(3)

            # get cutt-off
            MESSAGE = b'\x25' + b'\x01' + b'\x00'

            self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
            data_raw, addr = self.sock.recvfrom(3)

            if data_raw[2] == 0:
                freq = 30
            elif data_raw[2] == 1:
                freq = 105
            elif data_raw[2] == 2:
                freq = 300

            #self.telemetry_text.appendPlainText(f'Cut-off: {freq} MHz')

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

        #self.telemetry_text.appendPlainText( 'Frequency: ' + freq )

    def pause_and_label(self, time):
        self.label_1.setStyleSheet("QLabel { color : rgb(255, 0, 0); font-weight: bold; }")
        general.wait( time )
        self.label_1.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
    
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
        
        #self.telemetry_text.appendPlainText( 'Rotary Vane: ' + str( self.curr_dB ) + ' dB')

        self.prev_dB = self.curr_dB

    def initialize(self):
        """
        A function to initialize a bridge.
        """

        #MESSAGE = b'\x27' + b'\x01' + b'\x00'

        #self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        #data_raw, addr = self.sock.recvfrom(3)

        self.synt()

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

        #0.0 dB video2
        temp = 2*self.Att2_prm.value()
        MESSAGE = b'\x1a' + b'\x01' + struct.pack(">B", int(temp))
        
        self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
        data_raw, addr = self.sock.recvfrom(3)

        # get amplification
        MESSAGE = b'\x24' + b'\x01' + b'\x00'

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

        #self.telemetry_text.appendPlainText( 'Initialization done' )
    
    def initialize_at_exit(self):
        """
        A function to initialize a bridge.
        """

        #self.ecc15k.synthetizer_state('Off')
        
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

        now = datetime.datetime.now().strftime("%d %b %Y %H:%M:%S")

        header = (
            f"{'Date: '} {now}\n"
            f"{'Temp: '} {data[8]} C\n"
            f"{'State: '} {state}\n"
        )

        general.message(header)

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
    app = QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
