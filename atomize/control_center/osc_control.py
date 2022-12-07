#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import telnetlib
import configparser
#from PyQt6.QtWidgets import QListView, QAction
from PyQt6 import QtWidgets, uic #, QtCore, QtGui
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
        gui_path = os.path.join(path_to_main,'gui/osc_main_window.ui')
        icon_path = os.path.join(path_to_main, 'gui/icon_o1.png')
        self.setWindowIcon( QIcon(icon_path) )

        uic.loadUi(gui_path, self)                        # Design file

        # configuration data
        path_config_file = os.path.join(path_to_main,'osc_config.ini')
        config = configparser.ConfigParser()
        config.read(path_config_file)

        TCP_IP = str(config['DEFAULT']['TCP_IP'])
        TCP_PORT = int(config['DEFAULT']['TCP_PORT'])

        self.telnet = telnetlib.Telnet(TCP_IP, TCP_PORT)

        # Connection of different action to different Menus and Buttons
        self.button_off.clicked.connect(self.turn_off)
        self.button_off.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_stop.clicked.connect(self.osc_stop)
        self.button_stop.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_start.clicked.connect(self.osc_start)
        self.button_start.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
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
        self.label_9.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # Spinboxes
        self.Hor_offset.valueChanged.connect(self.hor_offset)
        self.Hor_offset.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.Wind.valueChanged.connect(self.wind)
        self.Wind.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.Ch1_scale.valueChanged.connect(self.ch1_scale)
        self.Ch1_scale.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.Ch1_offset.valueChanged.connect(self.ch1_offset)
        self.Ch1_offset.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.Ch2_scale.valueChanged.connect(self.ch2_scale)
        self.Ch2_scale.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.Ch2_offset.valueChanged.connect(self.ch2_offset)
        self.Ch2_offset.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.Acq_number.valueChanged.connect(self.acq_number)
        self.Acq_number.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")

        self.combo_trig_ch.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); }")
        
        cur_trig_ch = str( self.combo_trig_ch.currentText() )
        MESSAGE = b':TRIG:EDGE:SOUR ' + cur_trig_ch.encode() + b'\n'
        self.telnet.write( MESSAGE )
        
        self.combo_trig_ch.currentIndexChanged.connect(self.trigger_channel)

    def _on_destroyed(self):
        """
        A function to do some actions when the main window is closing.
        """
        self.telnet.close()

    def quit(self):
        """
        A function to quit the programm
        """
        self._on_destroyed()
        sys.exit()

    def trigger_channel(self):
        """
        A function to change a trigger channel
        """

        trig_ch = str( self.combo_trig_ch.currentText() )
        MESSAGE = b':TRIG:EDGE:SOUR ' + trig_ch.encode() + b'\n'
        self.telnet.write( MESSAGE )


    def hor_offset(self):
        """
        A function to change a horizontal offset
        """

        param = str( self.Hor_offset.value() )
        MESSAGE = b':TIM:POS ' + param.encode() + b'e-6\n'
        self.telnet.write( MESSAGE )

    def wind(self):
        """
        A function to change a window
        """

        param = str( self.Wind.value() )
        MESSAGE = b':TIM:RANG ' + param.encode() + b'e-6\n'
        self.telnet.write( MESSAGE )

    def ch1_scale(self):
        """
        A function to send a CH1 scale
        """

        param = str( self.Ch1_scale.value() )
        MESSAGE = b':CHAN1:SCAL ' + param.encode() + b'e-3\n'
        self.telnet.write( MESSAGE )

    def ch1_offset(self):
        """
        A function to send a CH1 offset
        """

        param = str( self.Ch1_offset.value() )
        MESSAGE = b':CHAN1:OFFS ' + param.encode() + b'e-3\n'
        self.telnet.write( MESSAGE )

    def ch2_scale(self):
        """
        A function to send a CH2 scale
        """

        param = str( self.Ch2_scale.value() )
        MESSAGE = b':CHAN2:SCAL ' + param.encode() + b'e-3\n'
        self.telnet.write( MESSAGE )

    def ch2_offset(self):
        """
        A function to send a CH2 offset
        """

        param = str( self.Ch2_offset.value() )
        MESSAGE = b':CHAN2:OFFS ' + param.encode() + b'e-3\n'
        self.telnet.write( MESSAGE )

    def acq_number(self):
        """
        A function to change number of averages
        """

        param = str( self.Acq_number.value() )
        MESSAGE = b':ACQ:COUN ' + param.encode() + b'\n'
        self.telnet.write( MESSAGE )

    def osc_stop(self):
        """
        A function to stop oscilloscope
        """
        MESSAGE = b':STOP\n'
        self.telnet.write( MESSAGE )

    def osc_start(self):
        """
        A function to stop oscilloscope
        """
        MESSAGE = b':RUN\n'
        self.telnet.write( MESSAGE )

    def turn_off(self):
        """
        A function to turn off a programm.
        """
        self.quit()

    def help(self):
        """
        A function to open a documentation
        """
        pass

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
