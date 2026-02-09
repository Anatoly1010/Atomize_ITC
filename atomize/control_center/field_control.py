#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QObject, QEventLoop, QTimer, QEvent
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QDoubleSpinBox, QSpinBox, QPushButton, QGridLayout, QFrame
#import atomize.device_modules.ITC_FC as itc
import atomize.device_modules.BH_15 as itc
import atomize.general_modules.general_functions as general

class MainWindow(QMainWindow):
    """
    A main window class
    """
    def __init__(self, *args, **kwargs):
        """
        A function for connecting actions and creating a main window
        """
        super(MainWindow, self).__init__(*args, **kwargs)
        
        #self.itc_fc = itc.ITC_FC()
        self.itc_fc = itc.BH_15()

        self.cur_field = 0
        self.cur_field_2 = 0
        #self.itc_fc.magnet_setup(100, 1)

        #self.itc_fc.device
        #self.itc_fc.act_field
        self.design()
        #print('CF: ' + str(self.cur_field))
        #print('F: ' + str(self.field))

        try:
            path_to_main_status = os.path.dirname(os.path.abspath(__file__))
            self.path_status_file = os.path.join(path_to_main_status, '..', 'control_center/field.param')
        except FileNotFoundError:
            pass

        self.read_field()

    def design(self):

        self.destroyed.connect(lambda: self._on_destroyed())
        self.setObjectName("MainWindow")
        self.setWindowTitle("Field Control")
        self.setStyleSheet("background-color: rgb(42,42,64);")

        path_to_main = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(path_to_main, 'gui/icon_f.png')
        self.setWindowIcon( QIcon(icon_path) )

        centralwidget = QWidget(self)
        self.setCentralWidget(centralwidget)

        gridLayout = QGridLayout()
        gridLayout.setContentsMargins(15, 10, 10, 10)
        gridLayout.setVerticalSpacing(4)
        gridLayout.setHorizontalSpacing(20)

        centralwidget.setLayout(gridLayout)

        # ---- Labels & Inputs ----
        labels = [("Set Magnetic Field", "label_1"), ("Field Setting Step", "label_2") ]

        for name, attr_name in labels:
            lbl = QLabel(name)
            setattr(self, attr_name, lbl)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # ---- Boxes ----
        double_boxes = [(QDoubleSpinBox, "Set_point", "field", self.set_field, 0, 15100, 100, 0.5, 2, " G"), 
                        (QSpinBox, "box_ini", "initialization_step", self.set_ini, 1, 100, 10, 1, 0, " G")
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


        # ---- Buttons ----
        buttons = [("Exit", "button_off", self.turn_off),
                   ("Set Zero Field", "button_stop", self.update_stop) ]

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
        gridLayout.addWidget(self.Set_point, 0, 1)
        gridLayout.addWidget(self.label_2, 1, 0)
        gridLayout.addWidget(self.box_ini, 1, 1)

        gridLayout.addWidget(hline(), 2, 0, 1, 2)

        gridLayout.addWidget(self.button_stop, 3, 0)
        gridLayout.addWidget(self.button_off, 4, 0)

        gridLayout.setRowStretch(5, 2)
        gridLayout.setColumnStretch(5, 2)

    def _on_destroyed(self):
        """
        A function to do some actions when the main window is closing.
        """
        self.button_stop.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(211, 194, 78); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } ")

        QApplication.processEvents()

        while self.cur_field > ( self.initialization_step + 1 ):
            self.cur_field = self.itc_fc.magnet_field( self.cur_field - self.initialization_step )

            loop = QEventLoop()
            QTimer.singleShot(15, loop.quit)
            loop.exec()
            
            QApplication.processEvents()

        #self.cur_field = self.itc_fc.magnet_field( 0 )
        self.cur_field = 0
        self.field = 0
        self.itc_fc.magnet_field( self.cur_field )

        self.button_stop.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; } ")
        #print('CF: ' + str(self.cur_field))
        #print('F: ' + str(self.field))

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow():
                self.on_window_focused()
        super().changeEvent(event)

    def on_window_focused(self):
        self.Set_point.blockSignals(True)
        self.read_no_set_field()
        self.Set_point.setValue(self.cur_field_2)
        self.Set_point.blockSignals(False)

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
        #self.read_no_set_field()
        self.field = float( self.Set_point.value() )
        self.write_field(self.field)

        if self.cur_field_2 != self.cur_field:
            self.itc_fc.magnet_setup( self.cur_field_2, 1 )
            self.itc_fc.magnet_field( self.cur_field_2 )

        self.cur_field = self.cur_field_2

        self.button_stop.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(211, 194, 78); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } ")

        QApplication.processEvents()
        
        if self.cur_field < self.field:
            while self.cur_field < self.field:
                self.cur_field = self.itc_fc.magnet_field( self.cur_field + self.initialization_step )

                loop = QEventLoop()
                QTimer.singleShot(15, loop.quit)
                loop.exec()
                
                QApplication.processEvents()                
                #self.cur_field = self.cur_field + self.initialization_step
                #print('CF: ' + str(self.cur_field))
                #print('F: ' + str(self.field))

            self.cur_field = self.itc_fc.magnet_field( self.field )
            self.cur_field = self.field
            #print('CF: ' + str(self.cur_field))
            #print('F: ' + str(self.field))
        else:
            while self.cur_field > self.field:
                self.cur_field = self.itc_fc.magnet_field( self.cur_field - self.initialization_step )

                loop = QEventLoop()
                QTimer.singleShot(15, loop.quit)
                loop.exec()
                
                QApplication.processEvents()
                #self.cur_field = self.cur_field - self.initialization_step
                #print('CF: ' + str(self.cur_field))
                #print('F: ' + str(self.field))

            self.cur_field = self.itc_fc.magnet_field( self.field )
            self.cur_field =  self.field 
            #print('CF: ' + str(self.cur_field))
            #print('F: ' + str(self.field))

        self.button_stop.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; } ")

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

    def read_field(self):
        try:
            text = open( self.path_status_file ).read()
            lines = text.split('\n')
            self.cur_field = float( lines[0].split(':  ')[1] )
            self.Set_point.setValue(self.cur_field)

        except FileNotFoundError:
            pass

    def read_no_set_field(self):
        try:
            text = open( self.path_status_file ).read()
            lines = text.split('\n')
            self.cur_field_2 = float( lines[0].split(':  ')[1] )

        except FileNotFoundError:
            pass

    def write_field(self, field):
        try:
            file_to_write = open(self.path_status_file, 'w')
            file_to_write.write(f'Field:  {field}\n')
            file_to_write.close()
        except FileNotFoundError:
            pass        

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
