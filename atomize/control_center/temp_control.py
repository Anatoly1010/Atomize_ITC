#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
#import random
import configparser
from threading import Timer
#from PyQt6.QtWidgets import QListView, QAction
from PyQt6 import QtWidgets, uic #, QtCore, QtGui
from PyQt6.QtGui import QIcon
import atomize.device_modules.Lakeshore_335 as ls

class MainWindow(QtWidgets.QMainWindow):
    """
    A main window class
    """
    def __init__(self, *args, **kwargs):
        """
        A function for connecting actions and creating a main window
        """
        super(MainWindow, self).__init__(*args, **kwargs)
        
        #self.destroyed.connect(lambda: self._on_destroyed())         # connect some actions to exit
        # Load the UI Page
        path_to_main = os.path.dirname(os.path.abspath(__file__))
        gui_path = os.path.join(path_to_main,'gui/temp_main_window.ui')
        icon_path = os.path.join(path_to_main, 'gui/icon_temp.png')
        self.setWindowIcon( QIcon(icon_path) )

        uic.loadUi(gui_path, self)                        # Design file

        #self.ls335 = ls.Lakeshore_335()

        # Connection of different action to different Menus and Buttons
        self.button_off.clicked.connect(self.turn_off)
        self.button_off.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_start.clicked.connect(self.update_start)
        self.button_start.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_stop.clicked.connect(self.update_stop)
        self.button_stop.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")

        # text labels
        self.label.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_2.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_3.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_4.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_temp2a.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_temp3a.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_heater.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # Spinboxes
        self.Set_point.valueChanged.connect( self.set_point )
        self.Set_point.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.point = float( self.Set_point.value() )

        self.start_flag = 0

        #self.ls335.tc_setpoint( self.point )

    def _on_destroyed(self):
        """
        A function to do some actions when the main window is closing.
        """
        try:
            self.rt.stop()
            self.rt2.stop()
            self.rt3.stop()
        except AttributeError:
            sys.exit()
            
    def quit(self):
        """
        A function to quit the programm
        """
        self._on_destroyed()
        sys.exit()

    def set_point(self):
        """
        A function to change a set point
        """
        self.point = float( self.Set_point.value() )
        
        # preventing coincidences of the commands
        if self.start_flag == 1:
            self.update_stop()
            time.sleep(0.1)
            self.ls335.tc_setpoint( self.point )
            time.sleep(0.1)
            self.update_start()
        else:
            self.ls335.tc_setpoint( self.point )

    def update_stop(self):
        """
        A function to stop oscilloscope
        """
        self._on_destroyed()
        self.start_flag = 0

    def ch2a_temp(self):
        self.label_temp2a.setText( ' ' + str( self.ls335.tc_temperature('A') ) )
        #self.label_temp2a.setText( ' ' + str( round( random.random(), 2 ) ) )

    def ch3a_temp(self):
        self.label_temp3a.setText( ' ' + str( self.ls335.tc_temperature('B') ) )
        #self.label_temp3a.setText( ' ' + str( round( random.random(), 2 ) ) )

    def heater_value(self):
        self.label_heater.setText( ' ' + str( self.ls335.tc_heater_power( )[0] ) )
        #self.label_heater.setText( ' ' + str( round( random.random(), 2 ) ) )

    def update_start(self):
        """
        A function to start getting data from temperature controller
        """
        self.start_flag = 1
        self.rt = RepeatedTimer( 2, self.ch2a_temp )
        # give some time to answer
        time.sleep(0.1)
        self.rt2 = RepeatedTimer( 2, self.ch3a_temp )
        time.sleep(0.1)
        self.rt3 = RepeatedTimer( 2, self.heater_value )
        time.sleep(0.1)

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

class RepeatedTimer(object):
    """
    To run a function repeatedly with the specified interval
    https://stackoverflow.com/questions/3393612/run-certain-code-every-n-seconds
    """

    def __init__(self, interval, function, *args, **kwargs):
        self._timer     = None
        self.interval   = interval
        self.function   = function
        self.args       = args
        self.kwargs     = kwargs
        self.is_running = False
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
        if not self.is_running:
            self._timer = Timer(self.interval, self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        self._timer.cancel()
        self.is_running = False

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
