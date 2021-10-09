#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
#from PyQt6.QtWidgets import QListView, QAction
from PyQt6 import QtWidgets, uic #, QtCore, QtGui
from PyQt6.QtGui import QIcon
import atomize.device_modules.BH_15 as bh

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
        gui_path = os.path.join(path_to_main,'gui/field_main_window.ui')
        icon_path = os.path.join(path_to_main, 'gui/icon_f.png')
        self.setWindowIcon( QIcon(icon_path) )

        uic.loadUi(gui_path, self)                        # Design file

        ##bh15 = bh.BH_15()

        # Connection of different action to different Menus and Buttons
        self.button_off.clicked.connect(self.turn_off)
        self.button_off.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_stop.clicked.connect(self.update_stop)
        self.button_stop.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")

        # text labels
        self.label.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label_2.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # Spinboxes
        self.Set_point.valueChanged.connect( self.set_field )
        self.Set_point.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.field = float( self.Set_point.value() )

        self.box_ini.valueChanged.connect( self.set_ini )
        self.box_ini.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")
        self.initialization_step = int( self.box_ini.value() )

        self.cur_field = 0
        ##bh15.magnet_setup(100, 1)

        #print('CF: ' + str(self.cur_field))
        #print('F: ' + str(self.field))

    def _on_destroyed(self):
        """
        A function to do some actions when the main window is closing.
        """
        while self.cur_field > ( self.initialization_step + 1 ):
            ##self.cur_field = bh15.magnet_field( self.cur_field - self.initialization_step )
            self.cur_field = self.cur_field - self.initialization_step
            #print('CF: ' + str(self.cur_field))
            #print('F: ' + str(self.field))

        ##self.cur_field = bh15.magnet_field( 0 )
        self.cur_field = 0
        self.field = 0

        #print('CF: ' + str(self.cur_field))
        #print('F: ' + str(self.field))


    def quit(self):
        """
        A function to quit the programm
        """
        self._on_destroyed()
        sys.exit()

    def set_ini(self):
        """
        A function to change inizialization step
        """
        self.initialization_step = int( self.box_ini.value() )

    def set_field(self):
        """
        A function to change set point
        """
        self.field = float( self.Set_point.value() )
        if self.cur_field < self.field:
            while self.cur_field < self.field:
                ##self.cur_field = bh15.magnet_field( self.cur_field + self.initialization_step )
                self.cur_field = self.cur_field + self.initialization_step
                #print('CF: ' + str(self.cur_field))
                #print('F: ' + str(self.field))

            ##self.cur_field = bh15.magnet_field( self.field )
            self.cur_field = self.field
            #print('CF: ' + str(self.cur_field))
            #print('F: ' + str(self.field))
        else:
            while self.cur_field > self.field:
                ##self.cur_field = bh15.magnet_field( self.cur_field - self.initialization_step )
                self.cur_field = self.cur_field - self.initialization_step
                #print('CF: ' + str(self.cur_field))
                #print('F: ' + str(self.field))

            ##self.cur_field = bh15.magnet_field( self.field )
            self.cur_field =  self.field 
            #print('CF: ' + str(self.cur_field))
            #print('F: ' + str(self.field))

    def update_stop(self):
        """
        A function to stop oscilloscope
        """
        self._on_destroyed()

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
