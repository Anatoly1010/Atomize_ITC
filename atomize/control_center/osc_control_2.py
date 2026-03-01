#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import telnetlib
import configparser
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QDoubleSpinBox, QSpinBox, QPushButton, QTextEdit, QGridLayout, QFrame, QComboBox
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt

class MainWindow(QMainWindow):
    """
    A main window class
    """
    def __init__(self, *args, **kwargs):
        """
        A function for connecting actions and creating a main window
        """
        super(MainWindow, self).__init__(*args, **kwargs)

        path_to_main = os.path.dirname(os.path.abspath(__file__))

        # configuration data
        path_config_file = os.path.join(path_to_main, 'osc_2_config.ini')
        config = configparser.ConfigParser()
        config.read(path_config_file)

        TCP_IP = str(config['DEFAULT']['TCP_IP'])
        TCP_PORT = int(config['DEFAULT']['TCP_PORT'])

        self.telnet = telnetlib.Telnet(TCP_IP, TCP_PORT)
        self.design()

    def design(self):

        self.setObjectName("MainWindow")
        self.setWindowTitle("2012A; IP 192.168.2.22")
        self.setStyleSheet("background-color: rgb(42,42,64);")

        path_to_main = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(path_to_main, 'gui/icon_o2.png')
        self.setWindowIcon( QIcon(icon_path) )

        centralwidget = QWidget(self)
        self.setCentralWidget(centralwidget)

        gridLayout = QGridLayout()
        gridLayout.setContentsMargins(15, 10, 10, 10)
        gridLayout.setVerticalSpacing(4)
        gridLayout.setHorizontalSpacing(20)

        centralwidget.setLayout(gridLayout)


        # ---- Labels & Inputs ----
        labels = [("Horizontal Offset", "label_1"), ("Window", "label_2"), ("CH1 Scale", "label_3"), ("CH1 Offset", "label_4"), ("CH2 Scale", "label_5"), ("CH2 Offset", "label_6"), ("Acquisitions", "label_7"), ("Trigger Channel", "label_8")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            lbl.setFixedSize(190, 26)
            setattr(self, attr_name, lbl)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")


        # ---- Boxes ----
        double_boxes = [(QDoubleSpinBox, "Hor_offset", "", self.hor_offset, -1e6, 1e6, 0, 1, 1, " us"),
                      (QDoubleSpinBox, "Wind", "", self.wind, 0.1, 1e6, 500, 1, 1, " us"),
                      (QSpinBox, "Ch1_scale", "", self.ch1_scale, 2, 2000,200, 5, 0, " mV"),
                      (QSpinBox, "Ch1_offset", "", self.ch1_offset, -1e3, 1e3, 0, 1, 0, " mV"),
                      (QSpinBox, "Ch2_scale", "", self.ch1_scale, 2, 2000,200, 5, 0, " mV"),
                      (QSpinBox, "Ch2_offset", "", self.ch1_offset, -1e3, 1e3, 0, 1, 0, " mV"),
                      (QSpinBox, "Acq_number", "", self.acq_number, 2, 1e3, 10, 1, 0, "")
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
            spin_box.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            
            spin_box.setKeyboardTracking( False )
            setattr(self, attr_name, spin_box)


        # ---- Combo boxes----
        combo_boxes = [("CHAN1", "combo_trig_ch", "", self.trigger_channel, 
                        [
                        "CHAN1", "CHAN2", "EXT", "LINE"
                        ])
                      ]

        for cur_text, attr_name, par_name, func, item in combo_boxes:
            combo = QComboBox()
            setattr(self, attr_name, combo)
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
        
            cur_trig_ch = str( combo.currentText() )
            MESSAGE = b':TRIG:EDGE:SOUR ' + cur_trig_ch.encode() + b'\n'
            self.telnet.write( MESSAGE )

        # ---- Buttons ----
        buttons = [("Run", "button_start", self.osc_start),
                   ("Stop", "button_stop", self.osc_stop),
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
        gridLayout.addWidget(self.Hor_offset, 0, 1)
        gridLayout.addWidget(self.label_2, 1, 0)
        gridLayout.addWidget(self.Wind, 1, 1)

        gridLayout.addWidget(hline(), 2, 0, 1, 2)

        gridLayout.addWidget(self.label_3, 3, 0)
        gridLayout.addWidget(self.Ch1_scale, 3, 1)
        gridLayout.addWidget(self.label_4, 4, 0)
        gridLayout.addWidget(self.Ch1_offset, 4, 1)

        gridLayout.addWidget(hline(), 5, 0, 1, 2)

        gridLayout.addWidget(self.label_5, 6, 0)
        gridLayout.addWidget(self.Ch2_scale, 6, 1)
        gridLayout.addWidget(self.label_6, 7, 0)
        gridLayout.addWidget(self.Ch2_offset, 7, 1)

        gridLayout.addWidget(hline(), 8, 0, 1, 2)

        gridLayout.addWidget(self.label_7, 9, 0)
        gridLayout.addWidget(self.Acq_number, 9, 1)
        gridLayout.addWidget(self.label_8, 10, 0)
        gridLayout.addWidget(self.combo_trig_ch, 10, 1)

        gridLayout.addWidget(hline(), 11, 0, 1, 2)

        gridLayout.addWidget(self.button_start, 12, 0)
        gridLayout.addWidget(self.button_stop, 13, 0)
        gridLayout.addWidget(self.button_off, 14, 0)

        gridLayout.setRowStretch(15, 2)
        gridLayout.setColumnStretch(15, 2)

    def closeEvent(self, event):
        event.ignore()
        self.telnet.close()
        sys.exit()

    def quit(self):
        """
        A function to quit the programm
        """
        self.telnet.close()
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
