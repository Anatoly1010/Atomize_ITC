#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import configparser
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QObject
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QDoubleSpinBox, QComboBox, QPushButton, QGridLayout, QFrame
import atomize.device_modules.Lakeshore_335 as ls

class MainWindow(QMainWindow):
    """
    A main window class
    """
    def __init__(self, *args, **kwargs):
        """
        A function for connecting actions and creating a main window
        """
        super(MainWindow, self).__init__(*args, **kwargs)
        
        # Create a signal to emit
        #self.communicate = Communicate()
        #self.communicate.sig_lm335[list].connect(self.update_labels)

        self.ls335 = ls.Lakeshore_335()
        self.start_flag = 0

        #self.ls335.tc_setpoint( self.point )
        self.design()

    def design(self):

        self.setObjectName("MainWindow")
        self.setWindowTitle("Temperature Control")
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
        labels = [("Heater Range", "label_1"), ("Set Temperature", "label_2")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            lbl.setFixedSize(190, 26)
            setattr(self, attr_name, lbl)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")


        # ---- Boxes ----
        double_boxes = [(QDoubleSpinBox, "Set_point", "point", self.set_point, 3, 320, 80, 0.1, 2, " K")
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
        combo_boxes = [("Off", "combo_range", "cur_range", self.heater_range, 
                        [
                        "Off", "High", "Medium", "Low"
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
            combo.setStyleSheet("""
                QComboBox 
                { color : rgb(193, 202, 227); 
                selection-color: rgb(211, 194, 78); 
                selection-background-color: rgb(63, 63, 97);
                outline: none;
                }
                """)


        # ---- Buttons ----
        buttons = [("Exit", "button_off", self.turn_off) ]

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
        gridLayout.addWidget(self.label_2, 0, 0)
        gridLayout.addWidget(self.Set_point, 0, 1)
        gridLayout.addWidget(self.label_1, 1, 0)
        gridLayout.addWidget(self.combo_range, 1, 1)

        gridLayout.addWidget(hline(), 2, 0, 1, 2)

        gridLayout.addWidget(self.button_off, 3, 0)

        gridLayout.setRowStretch(4, 2)
        gridLayout.setColumnStretch(4, 2)

    def closeEvent(self, event):
        event.accept()
            
    def quit(self):
        """
        A function to quit the programm
        """
        sys.exit()

    def heater_range(self):
        """
        A function to set heater range
        """
        self.cur_range = self.combo_range.currentText()

        rang = self.chose_range( self.cur_range )
        self.ls335.tc_heater_range( rang )

    def chose_range(self, text):
        if text == 'High':
            return '50 W'
        elif text == 'Medium':
            return '5 W'
        elif text == 'Low':
            return '0.5 W'
        else:
            return 'Off'

    def set_point(self):
        """
        A function to change a set point
        """
        self.point = round( float( self.Set_point.value() ), 3 )
        
        self.ls335.tc_setpoint( self.point )

    def turn_off(self):
        """
        A function to turn off a programm.
        """
        self.quit()

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
