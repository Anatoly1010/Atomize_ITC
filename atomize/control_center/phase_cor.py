#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import datetime
import numpy as np
from PyQt6.QtWidgets import QWidget, QFileDialog
from PyQt6 import QtWidgets, uic
from PyQt6.QtGui import QIcon        
import atomize.general_modules.general_functions as general
import atomize.general_modules.csv_opener_saver as openfile
import atomize.math_modules.fft as fft_module

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
        self.path_to_main = os.path.dirname(os.path.abspath(__file__))
        gui_path = os.path.join(self.path_to_main,'gui/phase_cor_main_window.ui')
        icon_path = os.path.join(self.path_to_main, 'gui/icon_dig.png')
        self.setWindowIcon( QIcon(icon_path) )

        self.path = os.path.join(self.path_to_main, '..', '..', '..', '..', 'Experimental_Data')
        #self.path = os.path.join(self.path_to_main, '..', '..', '..', '..', '00_Experimental_Data/2022')
        
        uic.loadUi(gui_path, self)                        # Design file

        # text labels
        self.label.setStyleSheet("QLabel { color : rgb(193, 202, 227); }")
        self.label_2.setStyleSheet("QLabel { color : rgb(193, 202, 227); }")
        self.label_3.setStyleSheet("QLabel { color : rgb(193, 202, 227); }")
        self.label_4.setStyleSheet("QLabel { color : rgb(193, 202, 227); }")
        self.label_5.setStyleSheet("QLabel { color : rgb(193, 202, 227); }")

        self.deg_rad = 57.2957795131
        self.sec_order_coef = -2*np.pi/2

        # Spinboxes
        self.First.valueChanged.connect(self.phase_correction)
        self.first_cor = float( self.First.value() )
        self.First.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.Second.valueChanged.connect(self.phase_correction)
        self.second_cor = float( self.Second.value() )
        if self.second_cor != 0.0:
            self.second_cor = self.sec_order_coef / ( float( self.Second.value() ) * 1000 )

        self.Second.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.Zero.valueChanged.connect(self.phase_correction)
        self.zero_cor = float( self.Zero.value() ) / self.deg_rad
        self.Zero.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); }")
        self.Point_drop.valueChanged.connect(self.point_drop)
        self.drop = int( self.Point_drop.value() )
        self.Point_drop.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); }")

        self.menuBar.setStyleSheet("QMenuBar { color: rgb(193, 202, 227); } \
                            QMenu::item { color: rgb(211, 194, 78); } QMenu::item:selected {color: rgb(193, 202, 227); }")
        self.action_read.triggered.connect( self.open_file_dialog )
        self.action_read_1d.triggered.connect( self.open_file_dialog_1d )
        self.action_save.triggered.connect( self.save_file_dialog )
        self.action_save_1d.triggered.connect( self.save_file_dialog_1d )

        # empty data
        self.fft = fft_module.Fast_Fourier()
        self.file_handler = openfile.Saver_Opener()

        self.data_1d = np.zeros((10,3))
        self.data_i = np.zeros((2,4,4))
        self.data_q = np.zeros((2,4,4))
        self.v_res = 2
        self.h_res = 2
        self.wind = 10
        self.points = 41
        self.opened_file = ''
        self.opened_file_1d = ''
        self.op_1d = 0
        self.op_2d = 0
        self.echo_det_spectrum = 0
        self.st_field = 0

    def open_file_dialog(self):
        """
        A function to open file with experimental data
        """
        filedialog = QFileDialog(self, 'Open File', directory = self.path, filter = "Data (*.csv)",\
            options = QtWidgets.QFileDialog.Option.DontUseNativeDialog)
        # use QFileDialog.DontUseNativeDialog to change directory
        filedialog.setStyleSheet("QWidget { background-color : rgb(42, 42, 64); color: rgb(211, 194, 78);}")
        filedialog.setFileMode(QtWidgets.QFileDialog.FileMode.AnyFile)
        filedialog.fileSelected.connect(self.open_file)
        filedialog.show()

    def open_file_dialog_1d(self):
        """
        A function to open file with experimental 1D data
        """
        filedialog = QFileDialog(self, 'Open File', directory = self.path, filter = "Data (*.csv)",\
            options = QtWidgets.QFileDialog.Option.DontUseNativeDialog)
        # use QFileDialog.DontUseNativeDialog to change directory
        filedialog.setStyleSheet("QWidget { background-color : rgb(42, 42, 64); color: rgb(211, 194, 78);}")
        filedialog.setFileMode(QtWidgets.QFileDialog.FileMode.AnyFile)
        filedialog.fileSelected.connect(self.open_file_1d)
        filedialog.show()

    def open_file_1d(self, filename):
        """
        A function to open 1D data
        """
        self.opened_file_1d = filename
        temp = np.genfromtxt(filename, dtype = float, delimiter = ',', skip_header = 1, comments='#') 
        self.data_1d = np.transpose(temp)
        
        # 3 or 4 columns variant
        if len( self.data_1d ) == 4:
            freq, fft_x, fft_y = self.fft.fft( self.data_1d[0][self.drop:], self.data_1d[1][self.drop:], self.data_1d[2][self.drop:], self.h_res, re = 'True' )
            data = self.fft.ph_correction( freq, fft_x, fft_y, self.zero_cor, self.first_cor, self.second_cor )

        elif len( self.data_1d ) == 5:
            freq, fft_x, fft_y = self.fft.fft( self.data_1d[0][self.drop:], self.data_1d[1][self.drop:], self.data_1d[3][self.drop:], self.h_res, re = 'True' )
            data = self.fft.ph_correction( freq, fft_x, fft_y, self.zero_cor, self.first_cor, self.second_cor )

        general.plot_1d('FT Data 1D', freq, ( data[0], data[1] ), xname = 'Frequency Offset', xscale = 'MHz', yname = 'Intensity', yscale = 'Arb. U.', label = 'FFT')

        self.op_1d = 1
        self.op_2d = 0

    def save_file_dialog(self):
        """
        A function to open a new window for choosing parameters
        """
        filedialog = QFileDialog(self, 'Save File', directory = self.path, filter = "Data (*.csv)",\
            options = QtWidgets.QFileDialog.Option.DontUseNativeDialog)
        filedialog.setAcceptMode(QFileDialog.AcceptSave)
        # use QFileDialog.DontUseNativeDialog to change directory
        filedialog.setStyleSheet("QWidget { background-color : rgb(42, 42, 64); color: rgb(211, 194, 78);}")
        filedialog.setFileMode(QtWidgets.QFileDialog.FileMode.AnyFile)
        filedialog.fileSelected.connect(self.save_file)
        filedialog.show()

    def save_file_dialog_1d(self):
        """
        A function to open a new window for choosing parameters
        """
        filedialog = QFileDialog(self, 'Save File', directory = self.path, filter = "Data (*.csv)",\
            options = QtWidgets.QFileDialog.Option.DontUseNativeDialog)
        filedialog.setAcceptMode(QFileDialog.AcceptSave)
        # use QFileDialog.DontUseNativeDialog to change directory
        filedialog.setStyleSheet("QWidget { background-color : rgb(42, 42, 64); color: rgb(211, 194, 78);}")
        filedialog.setFileMode(QtWidgets.QFileDialog.FileMode.AnyFile)
        filedialog.fileSelected.connect(self.save_file_1d)
        filedialog.show()

    def open_file(self, filename):
        """
        A function to open data for both I and Q channel
        """
        self.opened_file = filename
        filename_param = filename.split(".csv")[0] + ".param"
        self.points = int( open(filename_param).read().split("Points: ")[1].split("\n")[0] )
        self.h_res = float( open(filename_param).read().split("Horizontal Resolution: ")[1].split(" ns")[0] )
        try:
            self.v_res = float( open(filename_param).read().split("Vertical Resolution: ")[1].split(" ns")[0] )
            self.echo_det_spectrum = 0
        except ValueError:
            # Echo Detected Spectrum
            self.v_res = round( float(open(filename_param).read().split("Vertical Resolution: ")[1].split(" G")[0]), 3 )
            # Start Field: 3394.7 G
            self.st_field = round( float(open(filename_param).read().split("Start Field: ")[1].split(" G")[0]), 3 )
            self.echo_det_spectrum = 1
        self.wind = float( open(filename_param).read().split("Window: ")[1].split(" ns")[0] )

        filename2 = filename.split(".csv")[0] + "_1.csv"
        self.data_i = np.genfromtxt(filename, dtype = float, delimiter = ',')
        self.data_q = np.genfromtxt(filename2, dtype = float, delimiter = ',')

        #data_i = self.data_i
        #data_i[:,self.drop] = 0.5 * data_i[:,self.drop]
        #data_q = self.data_q
        #data_q[:,self.drop] = 0.5 * data_q[:,self.drop]

        freq, fft_x, fft_y = self.fft.fft( self.data_i[0][self.drop:], self.data_i[:,self.drop:], self.data_q[:,self.drop:], self.h_res, re = 'True' )
        data = self.fft.ph_correction( freq, fft_x, fft_y, self.zero_cor, self.first_cor, self.second_cor )

        if self.echo_det_spectrum == 0:
            general.plot_2d('FT Data', data, start_step = ( (round( freq[0], 0 ), freq[1] - freq[0]), (0, self.v_res) ), xname = 'Frequency Offset',\
                xscale = 'MHz', yname = 'Delay', yscale = 'ns', zname = 'Intensity', zscale = 'V')
        elif self.echo_det_spectrum == 1:
            general.plot_2d('FT Data', data, start_step = ( (round( freq[0], 0 ), freq[1] - freq[0]), (self.st_field, self.v_res) ), xname = 'Frequency Offset',\
                xscale = 'MHz', yname = 'MF', yscale = 'G', zname = 'Intensity', zscale = 'V')

        self.op_1d = 0
        self.op_2d = 1

    def save_file(self, filename):
        """
        A function to save phase corrected 2D data
        """
        if self.op_2d == 1:
            freq, fft_x, fft_y = self.fft.fft( self.data_i[0][self.drop:], self.data_i[:,self.drop:], self.data_q[:,self.drop:], self.h_res, re = 'True' )
            data = self.fft.ph_correction( freq, fft_x, fft_y, self.zero_cor, self.first_cor, self.second_cor )
            header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + \
                     'Corrected File: ' + str( self.opened_file ) + '\n' + \
                     'Zero Order: ' + str( round( self.zero_cor * self.deg_rad, 3 ) ) + '\n' + \
                     'First Order: ' + str( round( self.first_cor, 3 ) ) + '\n' + \
                     'Second Order: ' + str( round( self.second_cor, 3 ) ) + '\n' + \
                     'Points to Drop: ' + str( self.drop ) + '\n' + \
                     '2D Data'

            self.file_handler.save_data(filename, data, header = header, mode = 'w')
        else:
            pass

    def save_file_1d(self, filename):
        """
        A function to save phase corrected 1D data
        """
        if self.op_1d == 1:
            if len( self.data_1d ) == 4:
                freq, fft_x, fft_y = self.fft.fft( self.data_1d[0][self.drop:], self.data_1d[1][self.drop:], self.data_1d[2][self.drop:], self.h_res, re = 'True' )
                data = self.fft.ph_correction( freq, fft_x, fft_y, self.zero_cor, self.first_cor, self.second_cor )

            elif len( self.data_1d ) == 5:
                freq, fft_x, fft_y = self.fft.fft( self.data_1d[0][self.drop:], self.data_1d[1][self.drop:], self.data_1d[3][self.drop:], self.h_res, re = 'True' )
                data = self.fft.ph_correction( freq, fft_x, fft_y, self.zero_cor, self.first_cor, self.second_cor )

            header = 'Date: ' + str(datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")) + '\n' + \
                     'Corrected File: ' + str( self.opened_file_1d ) + '\n' + \
                     'Zero Order: ' + str( round( self.zero_cor * self.deg_rad, 3 ) ) + '\n' + \
                     'First Order: ' + str( round( self.first_cor, 3 ) ) + '\n' + \
                     'Second Order: ' + str( round( self.second_cor, 3 ) ) + '\n' + \
                     'Points to Drop: ' + str( self.drop ) + '\n' + \
                     'Frequency Offset (MHz), X (Arb. U.), Y (Arb. U.) '

            self.file_handler.save_data(filename, np.c_[freq, fft_x, fft_y], header = header, mode = 'w')
        
        else:
            pass

    def _on_destroyed(self):
        """
        A function to do some actions when the main window is closing.
        """
        pass

    def quit(self):
        """
        A function to quit the programm
        """ 
        self._on_destroyed()
        sys.exit()

    def point_drop(self):
        """
        A function for dropping several first points
        """
        self.drop = int( self.Point_drop.value() )

        if self.op_2d == 1:
            if self.drop > len( self.data_i[0] ) - 2:
                self.drop = len( self.data_i[0] ) - 4
                self.Point_drop.setValue( self.drop )
                general.message('Maximum length of the data achieved. A number of drop points was corrected.')

            freq, fft_x, fft_y = self.fft.fft( self.data_i[0][self.drop:], self.data_i[:,self.drop:], self.data_q[:,self.drop:], self.h_res, re = 'True' )
            data = self.fft.ph_correction( freq, fft_x, fft_y, self.zero_cor, self.first_cor, self.second_cor )

            if self.echo_det_spectrum == 0:
                general.plot_2d('FT Data', data, start_step = ( (round( freq[0], 0 ), freq[1] - freq[0]), (0, self.v_res) ), xname = 'Frequency Offset',\
                    xscale = 'MHz', yname = 'Delay', yscale = 'ns', zname = 'Intensity', zscale = 'V')
            elif self.echo_det_spectrum == 1:
                general.plot_2d('FT Data', data, start_step = ( (round( freq[0], 0 ), freq[1] - freq[0]), (self.st_field, self.v_res) ), xname = 'Frequency Offset',\
                    xscale = 'MHz', yname = 'MF', yscale = 'G', zname = 'Intensity', zscale = 'V')

        elif self.op_1d == 1:
            if self.drop > len( self.data_1d[0] ) - 2:
                self.drop = len( self.data_1d[0] ) - 4
                self.Point_drop.setValue( self.drop )
                general.message('Maximum length of the data achieved. A number of drop points was corrected.')

            if len( self.data_1d ) == 4:
                freq, fft_x, fft_y = self.fft.fft( self.data_1d[0][self.drop:], self.data_1d[1][self.drop:], self.data_1d[2][self.drop:], self.h_res, re = 'True' )
                data = self.fft.ph_correction( freq, fft_x, fft_y, self.zero_cor, self.first_cor, self.second_cor )

            elif len( self.data_1d ) == 5:
                freq, fft_x, fft_y = self.fft.fft( self.data_1d[0][self.drop:], self.data_1d[1][self.drop:], self.data_1d[3][self.drop:], self.h_res, re = 'True' )
                data = self.fft.ph_correction( freq, fft_x, fft_y, self.zero_cor, self.first_cor, self.second_cor )

            general.plot_1d('FT Data 1D', freq, ( data[0], data[1] ), xname = 'Frequency Offset', xscale = 'MHz', yname = 'Intensity', yscale = 'Arb. U.', label = 'FFT')
        else:
            pass

    def phase_correction(self):
        """
        A function for phase correction of the data
        """
        self.zero_cor = float( self.Zero.value() ) / self.deg_rad

        # cycling
        if self.zero_cor < 0.0:
            self.Zero.setValue(360.0)
            self.zero_cor = float( self.Zero.value() )/ self.deg_rad
        else:
            pass

        if self.zero_cor > 2*np.pi:
            self.Zero.setValue(0.0)
            self.zero_cor = float( self.Zero.value() ) / self.deg_rad
        else:
            pass

        self.first_cor = float( self.First.value() )
        self.second_cor = float( self.Second.value() )
        if self.second_cor != 0.0:
            self.second_cor = self.sec_order_coef / ( float( self.Second.value() ) * 1000 )

        if self.op_2d == 1:
            freq, fft_x, fft_y = self.fft.fft( self.data_i[0][self.drop:], self.data_i[:,self.drop:], self.data_q[:,self.drop:], self.h_res, re = 'True' )
            data = self.fft.ph_correction( freq, fft_x, fft_y, self.zero_cor, self.first_cor, self.second_cor )

            if self.echo_det_spectrum == 0:
                general.plot_2d('FT Data', data, start_step = ( (round( freq[0], 0 ), freq[1] - freq[0]), (0, self.v_res) ), xname = 'Frequency Offset',\
                    xscale = 'MHz', yname = 'Delay', yscale = 'ns', zname = 'Intensity', zscale = 'V')
            elif self.echo_det_spectrum == 1:
                general.plot_2d('FT Data', data, start_step = ( (round( freq[0], 0 ), freq[1] - freq[0]), (self.st_field, self.v_res) ), xname = 'Frequency Offset',\
                    xscale = 'MHz', yname = 'MF', yscale = 'G', zname = 'Intensity', zscale = 'V')

        elif self.op_1d == 1:
            if len( self.data_1d ) == 4:
                freq, fft_x, fft_y = self.fft.fft( self.data_1d[0][self.drop:], self.data_1d[1][self.drop:], self.data_1d[2][self.drop:], self.h_res, re = 'True' )
                data = self.fft.ph_correction( freq, fft_x, fft_y, self.zero_cor, self.first_cor, self.second_cor )

            elif len( self.data_1d ) == 5:
                freq, fft_x, fft_y = self.fft.fft( self.data_1d[0][self.drop:], self.data_1d[1][self.drop:], self.data_1d[3][self.drop:], self.h_res, re = 'True' )
                data = self.fft.ph_correction( freq, fft_x, fft_y, self.zero_cor, self.first_cor, self.second_cor )

            general.plot_1d('FT Data 1D', freq, ( data[0], data[1] ), xname = 'Frequency Offset', xscale = 'MHz', yname = 'Intensity', yscale = 'Arb. U.', label = 'FFT')
        else:
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
