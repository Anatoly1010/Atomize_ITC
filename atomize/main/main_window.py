#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import atexit
import os
import sys
import time
import json
import logging
import signal
import socket
import threading
import webbrowser
import subprocess
import configparser
import platform
#from tkinter import filedialog#, ttk
#import tkinter
import numpy as np
from . import widgets
import pyqtgraph as pg
from datetime import datetime
#import OpenGL
from PyQt6.QtCore import QSharedMemory, QSize
from PyQt6.QtGui import QColor, QIcon, QStandardItem, QStandardItemModel, QAction
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QListView, QDockWidget, QVBoxLayout
from PyQt6.QtNetwork import QLocalServer
from PyQt6 import QtWidgets, uic, QtCore, QtGui
#from PyQt6.QtCore import Qt
from pyqtgraph.dockarea import DockArea
import atomize.main.local_config as lconf
import atomize.main.messenger_socket_server as socket_server

class MainWindow(QtWidgets.QMainWindow):
    """
    A main window class.
    """
    def __init__(self, *args, **kwargs):
        """
        A function for connecting actions and creating a main window.
        """
        super(MainWindow, self).__init__(*args, **kwargs)
        # absolute path to icon:
        self.path_to_main = os.path.join(os.path.abspath(os.getcwd()), 'libs')
        os.chdir(self.path_to_main)
        self.icon_path = os.path.join(self.path_to_main ,'..', 'atomize/main','Icon.png')
        self.setWindowIcon(QIcon(self.icon_path))

        #self.destroyed.connect(MainWindow._on_destroyed)          # connect some actions to exit
        self.destroyed.connect(lambda: self._on_destroyed())       # connect some actions to exit
        # Load the UI Page
        uic.loadUi( os.path.join(self.path_to_main ,'..', 'atomize/main/gui/main_window.ui'), self)        # Design file

        # important attribures
        if len(sys.argv) > 1 and sys.argv[1] != '':  # for bash option
            self.script = sys.argv[1]
            self.open_file( self.script )
        elif len(sys.argv) == 1:
            self.script = '' # for not opened script
        self.test_flag = 0 # flag for not running script if test is failed
        self.flag_opened_script_changed = 0 # flag for saving changes in the opened script
        self.path = os.path.join(self.path_to_main,'..','atomize/tests')
        path_to_main = os.path.join(self.path_to_main,'..','atomize/tests')

        self.design_setting()

        # Liveplot server settings
        self.server = QLocalServer()
        self.server.removeServer('LivePlot')
        self.server.listen('LivePlot')
        self.server.newConnection.connect(self.accept)
        self.bytes = bytearray()
        self.target_size = 0
        self.meta = None
        self.insert_dock_right = True
        self.conns = []
        self.shared_mems = []
        signal.signal(signal.SIGINT, self.close)

        # configuration data
        path_config_file = os.path.join(path_to_main, '..', 'config.ini')
        path_config_file_device = os.path.join(path_to_main, '..', 'device_modules/config')
        path_config_file, self.path_config2 = lconf.copy_config(path_config_file, path_config_file_device)

        config = configparser.ConfigParser()
        config.read(path_config_file)
        # directories
        self.open_dir = str(config['DEFAULT']['open_dir'])
        if self.open_dir == '':
            self.open_dir = lconf.load_scripts(os.path.join(path_to_main, '..', 'tests'))

        self.script_dir = str(config['DEFAULT']['script_dir'])
        if self.script_dir == '':
            self.script_dir = lconf.load_scripts(os.path.join(path_to_main, '..', 'tests'))

        # check where we are
        self.system = platform.system()
        
        print( f'SYSTEM: {self.system}' )
        print( f'DATA DIRECTORY: {self.open_dir}' )
        print( f'SCRIPTS DIRECTORY: {self.script_dir}' )
        print( f'MAIN CONFIG PATH: {path_config_file}' )
        print( f'DEVICE CONFIG DIRECTORY: {self.path_config2}' )

        self.path = self.script_dir
        self.test_timeout = int(config['DEFAULT']['test_timeout']) * 1000 # in ms

        # for running different processes using QProcess
        self.process = QtCore.QProcess(self)
        self.process_text_editor = QtCore.QProcess(self)
        self.process_python = QtCore.QProcess(self)
        self.process_tr = QtCore.QProcess(self)
        self.process_osc = QtCore.QProcess(self)
        self.process_osc2 = QtCore.QProcess(self)
        self.process_cw = QtCore.QProcess(self)
        self.process_temp = QtCore.QProcess(self)
        self.process_field = QtCore.QProcess(self)
        self.process_mw = QtCore.QProcess(self)
        self.process_tune_preset = QtCore.QProcess(self)
        self.process_phasing = QtCore.QProcess(self)
        self.process_awg_phasing = QtCore.QProcess(self)
        self.process_t2 = QtCore.QProcess(self)
        self.process_t1 = QtCore.QProcess(self)
        self.process_ed = QtCore.QProcess(self)
        self.process_eseem = QtCore.QProcess(self)
        self.pid = 0


        if self.system == 'Windows':
            self.process_text_editor.setProgram(str(config['DEFAULT']['editorW']))
            print('EDITOR: ' + str(config['DEFAULT']['editorW']))
            self.process.setProgram('python.exe')
            self.process_python.setProgram('python.exe')
            self.process_tr.setProgram('python.exe')
            self.process_osc.setProgram('python.exe')
            self.process_osc2.setProgram('python.exe')
            self.process_cw.setProgram('python.exe')
            self.process_temp.setProgram('python.exe')
            self.process_field.setProgram('python.exe')
            self.process_mw.setProgram('python.exe')
            self.process_tune_preset.setProgram('python.exe')
            self.process_phasing.setProgram('python.exe')
            self.process_awg_phasing.setProgram('python.exe')
            self.process_t2.setProgram('python.exe')
            self.process_t1.setProgram('python.exe')
            self.process_ed.setProgram('python.exe')
            self.process_eseem.setProgram('python.exe')
        elif self.system == 'Linux':
            self.editor = str(config['DEFAULT']['editor'])
            if self.editor == 'nano' or self.editor == 'vi':
                self.process_text_editor.setProgram('xterm')
                print(f'EDITOR: nano / vi')
            else:
                self.process_text_editor.setProgram(str(config['DEFAULT']['editor']))
                print('EDITOR: ' + str(config['DEFAULT']['editor']))
            self.process.setProgram('python3')
            self.process_python.setProgram('python3')
            self.process_tr.setProgram('python3')
            self.process_osc.setProgram('python3')
            self.process_osc2.setProgram('python3')
            self.process_cw.setProgram('python3')
            self.process_temp.setProgram('python3')
            self.process_field.setProgram('python3')
            self.process_mw.setProgram('python3')
            self.process_tune_preset.setProgram('python3')
            self.process_phasing.setProgram('python3')
            self.process_awg_phasing.setProgram('python3')
            self.process_t2.setProgram('python3')
            self.process_t1.setProgram('python3')
            self.process_ed.setProgram('python3')
            self.process_eseem.setProgram('python3')

        self.process.finished.connect(self.on_finished_checking)
        self.process_python.finished.connect(self.on_finished_script)

    ############################################## Liveplot Functions

    def close(self, sig = None, frame = None):
        #print('closing')
        for conn in self.conns:
            conn.close()
        for shm in self.shared_mems:
            shm.detach()
        self._on_destroyed()
        #QApplication.instance().exit()

    def accept(self):
        logging.debug('connection accepted')
        conn = self.server.nextPendingConnection()
        conn.waitForReadyRead()
        key = str(conn.read(36).decode())
        memory = QSharedMemory()
        memory.setKey(key)
        memory.attach()
        logging.debug('attached to memory %s with size %s'%(key, memory.size()))
        #11-04-2021; Should be uncommented in case of problems
        #atexit.register(memory.detach)
        self.conns.append(conn)
        self.shared_mems.append(memory)
        conn.readyRead.connect(lambda: self.read_from(conn, memory))
        conn.disconnected.connect(memory.detach)
        conn.write(b'ok')

    # noinspection PyNoneFunctionAssignment
    def read_from(self, conn, memory):
        logging.debug('reading data')
        self.meta = json.loads(conn.read(320).decode())
        if self.meta['arrsize'] != 0:
            memory.lock()
            raw_data = memory.data()
            if raw_data!=None:
                ba = raw_data[:self.meta['arrsize']]
                arr = np.frombuffer(memoryview(ba), dtype=self.meta['dtype'])
                memory.unlock()
                conn.write(b'ok')
                arr = arr.reshape(self.meta['shape']).copy()
            else: 
                arr = None
        else:
            arr = None
        self.do_operation(arr)
        if conn.bytesAvailable():
            self.read_from(conn, memory)

    def do_operation(self, arr = None):
        def clear(name):
            self.namelist[name].clear()

        def close(name):
            self.namelist[name].close()

        def remove(name):
            del self.namelist[name]

        meta = self.meta
        operation = meta['operation']
        name = meta['name']

        if name in self.namelist:
            pw = self.namelist[name]
            if pw.closed:
                pw.closed = False
                self.dockarea.addDock(pw)

        elif name == "*":
            if operation == 'clear':
                list(map(clear, list(self.namelist.keys())))
            elif operation == 'close':
                list(map(close, list(self.namelist.keys())))
            elif operation == 'remove':
                list(map(remove, list(self.namelist.keys())))
            return
        else:
            if operation in ('clear', 'close', 'remove','none'):
                return
            pw = self.add_new_plot(meta['rank'], name)

        if operation == 'clear':
            pw.clear()
        elif operation == 'close':
            pw.close()
        elif operation == 'none':
            pass
        elif operation == 'remove':
            del self.namelist[name]


        elif operation == 'plot_y':
            start_step = meta['start_step']
            label = meta['label']
            if start_step is not None:
                x0, dx = start_step
                nx = len(arr)
                xs = np.linspace(x0, x0 + (nx - 1)*dx, nx)
                pw.plot(xs, arr, name=label, scatter='False')
            else:
                pw.plot(arr, name=label, scatter='False')


        elif operation == 'plot_xy':
            label = meta['label']
            xnam = meta['Xname']
            xscal = meta['X']
            ynam = meta['Yname']
            yscal = meta['Y']
            scat = meta['Scatter']
            taxis = meta['TimeAxis']
            verline = meta['Vline']
            tex = meta['value']
            pw.plot(arr[0], arr[1], parametric=True, name=label, xname=xnam, xscale =xscal,\
             yname=ynam, yscale =yscal, scatter=scat, timeaxis=taxis, vline=verline, text=tex)


        elif operation == 'plot_z':
            start_step = meta['start_step']
            xnam = meta['Xname']
            xscal = meta['X']
            ynam = meta['Yname']
            yscal = meta['Y']
            znam = meta['Zname']
            zscal = meta['Z']
            tex = meta['value']
            if start_step is not None:
                (x0, dx), (y0, dy) = start_step
                pw.setAxisLabels(xname=xnam, xscale =xscal, yname=ynam, yscale =yscal,\
                zname=znam, zscale =zscal)
                pw.setImage(arr, pos=(x0, y0), scale=(dx, dy)) # , axes={'y':0, 'x':1}
                # Graph title
                if tex != '':
                    pw.setTitle(meta['value'])
            else:
                pw.setAxisLabels(xname=xnam, xscale =xscal, yname=ynam, yscale =yscal,\
                 zname=znam, zscale =zscal)
                pw.setImage(arr) # , axes={'y':0, 'x':1}
                # Graph title
                if tex != '':
                    pw.setTitle(meta['value'])


        elif operation == 'append_y':
            label = meta['label']
            xnam = meta['Xname']
            xscal = meta['X']
            ynam = meta['Yname']
            yscal = meta['Y']
            scat = meta['Scatter']
            taxis = meta['TimeAxis']
            verline = meta['Vline']
            
            xs, ys = pw.get_data(label)
            new_ys = list(ys)
            new_ys.append(meta['value'])
            start_step = meta['start_step']
            if start_step is not None:
                x0, dx = start_step
                nx = len(new_ys)
                xs = np.linspace(x0, x0 + (nx - 1)*dx, nx)
                pw.plot(xs, new_ys, name=label, xname=xnam, xscale =xscal, yname=ynam,\
                 yscale =yscal, scatter=scat, timeaxis=taxis, vline=verline)
            else:
                pw.plot(new_ys, name=label, xname=xnam, xscale =xscal, yname=ynam,\
                 yscale =yscal, scatter=scat, timeaxis=taxis, vline=verline)


        elif operation == 'append_xy':
            label = meta['label']
            xs, ys = pw.get_data(label)
            xn, yn = meta['value']
            new_xs = list(xs)
            new_xs.append(xn)
            new_ys = list(ys)
            new_ys.append(yn)
            pw.plot(new_xs, new_ys, parametric=True, name=label, scatter='False')


        elif operation == 'append_z':
            image = pw.get_data()
            if image is None:
                image = np.array([arr])
            else:
                try:
                    image = np.vstack((np.transpose(image), [arr]))
                except ValueError:
                    image = np.array([arr])
            start_step = meta['start_step']
            xnam = meta['Xname']
            xscal = meta['X']
            ynam = meta['Yname']
            yscal = meta['Y']
            znam = meta['Zname']
            zscal = meta['Z']
            if start_step is not None:
                (x0, dx), (y0, dy) = start_step
                pw.setAxisLabels(xname=xnam, xscale =xscal, yname=ynam, yscale =yscal,\
                 zname=znam, zscale =zscal)
                pw.setImage(image, pos=(x0, y0), scale=(dx, dy), axes={'y':0, 'x':1})
            else:
                pw.setAxisLabels(xname=xnam, xscale =xscal, yname=ynam, yscale =yscal)
                pw.setImage(image, axes={'y':0, 'x':1})


        elif operation == 'label':
            pw.setTitle(meta['value'])

    def add_new_plot(self, rank, name):
        pw = widgets.get_widget(rank, name)
        self.add_plot(pw)
        self.namelist[name] = pw
        return pw

    def add_plot(self, pw):
        self.insert_dock_right = not self.insert_dock_right
        self.dockarea.addDock(pw, position=['bottom', 'bottom'][self.insert_dock_right])
        #print(['bottom', 'right'][self.insert_dock_right])
        #self.dockarea.moveDock(pw, 'above', self.dock_list[-1])   ## move d6 to stack on top of d4

    #####################################################

    def design_setting(self):
        # Connection of different action to different Menus and Buttons
        self.tabwidget.tabBar().setTabTextColor(0, QColor(193, 202, 227))
        self.tabwidget.tabBar().setTabTextColor(1, QColor(193, 202, 227))
        self.tabwidget.tabBar().setTabTextColor(2, QColor(193, 202, 227))
        self.tabwidget.tabBar().setStyleSheet(" font-weight: bold ")
        self.button_open.clicked.connect(self.open_file_dialog)
        self.button_open.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_edit.clicked.connect(self.edit_file)
        self.button_edit.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_test.clicked.connect(self.test)
        self.button_test.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_reload.clicked.connect(self.reload)
        self.button_reload.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_start.clicked.connect(self.start_experiment)
        self.button_start.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_help.clicked.connect(self.help)
        self.button_help.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_quit.clicked.connect(lambda: self.quit())
        self.button_quit.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.textEdit.setStyleSheet("QPlainTextEdit {background-color: rgb(42, 42, 64); color: rgb(211, 194, 78); }\
         QScrollBar:vertical {background-color: rgb(42, 42, 64); }")
        
        # show spaces
        option = QtGui.QTextOption()
        option.setFlags( QtGui.QTextOption.Flag.ShowTabsAndSpaces ) # | QtGui.QTextOption.ShowLineAndParagraphSeparators
        self.textEdit.document().setDefaultTextOption(option)
        self.textEdit.textChanged.connect(self.save_edited_text)

        # set tab distance
        self.textEdit.setTabStopDistance( QtGui.QFontMetricsF(self.textEdit.font()).horizontalAdvance(' ') * 4 )
        #self.textEdit.setTabStopWidth( 20 )

        self.label_filename.setStyleSheet("QLabel { color : rgb(193, 202, 227); }")

        self.text_errors.top_margin  = 2
        self.text_errors.setStyleSheet("QPlainTextEdit {background-color: rgb(42, 42, 64); color: rgb(211, 194, 78); }")
        self.text_errors.setCenterOnScroll(True)
        self.text_errors.ensureCursorVisible()

        self.text_errors.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.ActionsContextMenu)
        self.text_errors.setStyleSheet("QPlainTextEdit {background-color: rgb(42, 42, 64); color: rgb(211, 194, 78); } \
                                    QMenu::item { color: rgb(211, 194, 78); } QMenu::item:selected {background-color: rgb(48, 48, 75);  }\
                                    QMenu::item:selected:active {background-color: rgb(63, 63, 97); } ")
        clear_action = QAction('Clear', self.text_errors)
        clear_action.triggered.connect(self.clear_errors)
        self.text_errors.addAction(clear_action)

        conf_dir_action = QAction('Open Config Directory', self.text_errors)
        conf_dir_action.triggered.connect(self.conf_dir_action)
        self.text_errors.addAction(conf_dir_action)

        list_resources_action = QAction('List Resources', self.text_errors)
        list_resources_action.triggered.connect(self.list_resources_action)
        self.text_errors.addAction(list_resources_action)

        # Control Window tab setting
        self.tab_control.setStyleSheet("background-color: rgb(42, 42, 64); color: rgb(211, 194, 78); ")
        self.button_osc.clicked.connect(self.start_osc_control)
        self.button_osc.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_field.clicked.connect(self.start_field_control)
        self.button_field.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_osc2.clicked.connect(self.start_osc_control_2)
        self.button_osc2.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_cw.clicked.connect(self.start_cw)
        self.button_cw.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_temp.clicked.connect(self.start_temp_control)
        self.button_temp.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_tr.clicked.connect(self.start_tr_control)
        self.button_tr.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_mw.clicked.connect(self.start_mw_control)
        self.button_mw.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_rect.clicked.connect(self.start_rect_phasing)
        self.button_rect.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_awg.clicked.connect(self.start_awg_phasing)
        self.button_awg.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_tune_preset.clicked.connect(self.start_tune_preset)
        self.button_tune_preset.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_t2.clicked.connect(self.start_t2_preset)
        self.button_t2.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_ed.clicked.connect(self.start_ed_preset)
        self.button_ed.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_t1.clicked.connect(self.start_t1_preset)
        self.button_t1.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        self.button_eseem.clicked.connect(self.start_eseem_preset)
        self.button_eseem.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97);\
         border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }\
          QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")

        self.label_creator.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.label.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.script_chooser.setStyleSheet("QComboBox { color : rgb(193, 202, 227); selection-color: rgb(211, 194, 78); font-weight: bold; }")
        self.script_chooser.currentIndexChanged.connect(self.script_open_combo)
        self.script = self.text_to_script_name( self.script_chooser.currentText() )
        # preopen script
        self.open_file( self.script )

        self.checkTests.setStyleSheet("QCheckBox { color : rgb(193, 202, 227); font-weight: bold; }")

        self.dockarea2 = DockArea()
        self.dockarea3 = DockArea()

        self.dock_editor = self.dockarea2.addDock(name="Script Editor")
        self.dock_editor.addWidget(widget = self.textEdit )
        self.gridLayout_tab.addWidget(self.dockarea2, 1, 2, 10, 1)
        
        self.dock_errors = self.dockarea3.addDock(name="Output", position='top')
        self.dock_errors.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.dock_errors.addWidget(widget = self.text_errors )
        self.gridLayout_tab.addWidget(self.dockarea3, 11, 0, 1, 3)

        # Liveplot tab setting
        self.dockarea = DockArea()
        self.namelist = NameList(self)
        self.tab_liveplot.setStyleSheet("background-color: rgb(42, 42, 64); color: rgb(211, 194, 78); ")
        self.gridLayout_tab_liveplot.setColumnMinimumWidth(0, 200)
        self.gridLayout_tab_liveplot.setColumnStretch(1, 2000)
        self.gridLayout_tab_liveplot.addWidget(self.namelist, 0, 0)
        self.gridLayout_tab_liveplot.setAlignment(self.namelist, QtCore.Qt.AlignmentFlag.AlignLeft)
        self.gridLayout_tab_liveplot.addWidget(self.dockarea, 0, 1)
        #self.gridLayout_tab_liveplot.setAlignment(self.dockarea, QtConst.AlignRight)
        self.namelist.setStyleSheet("QNameList {background-color: rgb(42, 42, 64); color: rgb(211, 194, 78); border: 4px solid rgb(40, 30, 45); }")
        self.namelist.setStyleSheet("QListView {background-color: rgb(42, 42, 64); selection-color: rgb(63, 63, 97);\
            color: rgb(211, 194, 78); selection-background-color: rgb(211, 194, 78); } ")

        self.namelist.namelist_view.setStyleSheet("QMenu::item:selected {background-color: rgb(48, 48, 75);  }")

    def _on_destroyed(self):
        """
        A function to do some actions when the main window is closing.
        """
        self.process_python.close()
        self.process_tr.close()
        self.process_osc.close()
        self.process_osc2.close()
        self.process_cw.close()
        self.process_temp.close()
        self.process_field.close()
        self.process_mw.close()
        self.process_tune_preset.close()
        self.process_phasing.close()
        self.process_awg_phasing.close()
        self.process_t2.close()
        self.process_t1.close()
        self.process_ed.close()
        self.process_eseem.close()
    
    def clear_errors(self):
        self.text_errors.clear()

    def conf_dir_action(self):
        self.open_directory(self.path_config2)

    def list_resources_action(self):
        import pyvisa

        rm = pyvisa.ResourceManager()
        print(f"AVAILABLE INSTRUMENTS: {rm.list_resources()}")

    def quit(self):
        """
        A function to quit the programm
        """
        self.process_python.terminate()
        self.process_tr.terminate()
        self.process_osc.terminate()
        self.process_osc2.terminate()
        self.process_cw.terminate()
        self.process_temp.terminate()
        self.process_field.terminate()
        self.process_mw.terminate()
        self.process_tune_preset.terminate()
        self.process_phasing.terminate()
        self.process_awg_phasing.terminate()
        self.process_t2.terminate()
        self.process_t1.terminate()
        self.process_ed.terminate()
        self.process_eseem.terminate()
        sys.exit()
        ####
        #### QProcess: Destroyed while process ("python3") is still running.
        ####

    def start_experiment(self):
        """
        A function to run an experimental script using python.exe.
        """
        if self.script != '':
            stamp = os.stat(self.script).st_mtime
        else:
            self.text_errors.appendPlainText('No experimental script is opened')
            return

        if self.checkTests.checkState().value == 2:
            self.test()
            exec_code = self.process.waitForFinished( msecs = self.test_timeout ) # timeout in msec
        elif self.checkTests.checkState().value == 0:
            self.test_flag = 0
            exec_code = True
            self.text_errors.appendPlainText("Testing of experimental scripts are disabled")

        if self.test_flag == 1:
            self.text_errors.appendPlainText("Experiment cannot be started, since test is not passed. Test execution timeout is " +\
                                str( self.test_timeout / 60000 ) + " minutes")
            return        # stop current function
        elif self.test_flag == 0 and exec_code == True:
            self.process_python.setArguments([self.script])
            self.process_python.start()
            self.pid = self.process_python.processId()
            print(f'SCRIPT PROCESS ID: {self.pid}')

    def start_eseem_preset(self):
        """
        A function to run an phasing for rect channel.
        """
        self.process_eseem.setArguments([os.path.join('..','atomize/control_center/eseem_preset_insys.py')])
        self.process_eseem.start()

    def start_ed_preset(self):
        """
        A function to run an phasing for rect channel.
        """
        self.process_ed.setArguments([os.path.join('..','atomize/control_center/echo_det_preset_insys.py')])
        self.process_ed.start()

    def start_t1_preset(self):
        """
        A function to run an phasing for rect channel.
        """
        self.process_t1.setArguments([os.path.join('..','atomize/control_center/t1_preset_insys.py')])
        self.process_t1.start()

    def start_t2_preset(self):
        """
        A function to run an phasing for rect channel.
        """
        self.process_t2.setArguments([os.path.join('..','atomize/control_center/t2_preset_insys.py')])
        self.process_t2.start()

    def start_rect_phasing(self):
        """
        A function to run an phasing for rect channel.
        """
        self.process_phasing.setArguments([os.path.join('..','atomize/control_center/phasing_insys.py')])
        self.process_phasing.start()

    def start_awg_phasing(self):
        """
        A function to run an phasing for rect channel.
        """
        self.process_awg_phasing.setArguments([os.path.join('..','atomize/control_center/awg_phasing_insys.py')])
        self.process_awg_phasing.start()

    def start_tune_preset(self):
        """
        A function to run tuning.
        """
        self.process_tune_preset.setArguments([os.path.join('..','atomize/control_center/tune_preset.py')])
        self.process_tune_preset.start()

    def start_mw_control(self):
        """
        A function to run an pulse_creator.
        """
        self.process_mw.setArguments([os.path.join('..','atomize/control_center/mw_bridge_control.py')])
        self.process_mw.start()

    def start_tr_control(self):
        """
        A function to run an pulse_creator.
        """
        self.process_tr.setArguments([os.path.join('..','atomize/control_center/tr_control.py')])
        self.process_tr.start()
    
    def start_osc_control(self):
        """
        A function to run an Keysight control.
        """
        self.process_osc.setArguments([os.path.join('..','atomize/control_center/osc_control.py')])
        self.process_osc.start()

    def start_field_control(self):
        """
        A function to run an Field control.
        """
        self.process_field.setArguments([os.path.join('..','atomize/control_center/field_control.py')])
        self.process_field.start()

    def start_osc_control_2(self):
        """
        A function to run an Keysight control.
        """
        self.process_osc2.setArguments([os.path.join('..','atomize/control_center/osc_control_2.py')])
        self.process_osc2.start()

    def start_cw(self):
        """
        A function to run an Keysight control.
        """
        self.process_cw.setArguments([os.path.join('..','atomize/control_center/cw_control.py')])
        self.process_cw.start()

    def start_temp_control(self):
        """
        A function to run an Keysight control.
        """
        self.process_temp.setArguments([os.path.join('..','atomize/control_center/temp_control.py')])
        self.process_temp.start()

    def script_open_combo(self):
        self.script = self.text_to_script_name( self.script_chooser.currentText() )
        self.open_file(  os.path.join(self.script, '..', 'atomize/tests/') )

    def text_to_script_name(self, text_to_parse):

        if text_to_parse == ' Tuning':
            return os.path.join(self.path_to_main, '..', 'atomize/tests/pulse_epr/01_resonator_tuning.py')
        elif text_to_parse == ' T2 Echo Shape':
            return os.path.join(self.path_to_main, '..', 'atomize/tests/pulse_epr/keysight/02_t2_baseline_echo_shape.py')
        elif text_to_parse == ' ED Spectrum':
            return os.path.join(self.path_to_main, '..', 'atomize/tests/pulse_epr/keysight/03_echo_detected_spectrum_baseline.py')
        elif text_to_parse == ' ESEEM Echo Shape':
            return os.path.join(self.path_to_main, '..', 'atomize/tests/pulse_epr/keysight/07_eseem_phase_echo_shape.py')

    def message_box_clicked(self, btn):
        """
        Message Box fow warning
        """
        if btn.text() == "Discrad and Run Experiment":
            self.start_experiment()
        elif btn.text() == "Update Script":
            self.reload()
        else:
            return

    def test(self):
        """
        A function to run script check.
        """

        if self.script != '':
            stamp = os.stat(self.script).st_mtime
        else:
            self.text_errors.appendPlainText('No experimental script is opened')
            return

        if stamp != self.cached_stamp and self.flag_opened_script_changed == 1:
            self.cached_stamp = stamp
            message = QMessageBox(self);  # Message Box for warning of updated file
            message.setWindowTitle("Your script has been changed!")
            message.setStyleSheet("QWidget { background-color : rgb(42, 42, 64); color: rgb(211, 194, 78); }")
            message.addButton(QtWidgets.QPushButton('Discrad and Run Experiment'), QtWidgets.QMessageBox.ButtonRole.YesRole)
            message.addButton(QtWidgets.QPushButton('Update Script'), QtWidgets.QMessageBox.ButtonRole.NoRole)
            message.setText("Your experimental script has been changed   ");
            message.show();
            message.buttonClicked.connect(self.message_box_clicked)   # connect function clicked to button; get the button name
            return        # stop current function

        #self.text_errors.appendPlainText("Testing... Please, wait!")
        #self.process.setArguments(['--errors-only', self.script])
        self.process.setArguments([self.script, 'test'])
        self.process.start()

    def reload(self):
        """
        A function to reload an experimental script.
        """
        try:
            self.cached_stamp = os.stat(self.script).st_mtime
            text = open(self.script).read()
            self.textEdit.setPlainText(text)
        except FileNotFoundError:
            pass

    def on_finished_checking(self):
        """
        A function to add the information about errors found during syntax checking
        to a dedicated text box in the main window of the programm.
        """
        #text = self.process.readAllStandardOutput().data().decode()
        #if text == '':
        #    self.text_errors.appendPlainText("No errors are found!")
        #else:
        #    self.text_errors.appendPlainText(text)
        #    self.text_errors.verticalScrollBar().setValue(self.text_errors.verticalScrollBar().maximum())

        # Version for real tests
        text = self.process.readAllStandardOutput().data().decode()
        text_errors_script = self.process.readAllStandardError().data().decode()
        if text_errors_script == '':
        # if text == '' and text_errors_script == '':
            self.text_errors.appendPlainText("No errors are found")
            self.test_flag = 0
        elif text_errors_script != '':
            self.test_flag = 1
            self.text_errors.appendPlainText(text_errors_script)
            path_status_file = os.path.join(self.path_to_main, 'status')
            file_to_read = open(path_status_file, 'w')
            file_to_read.write('Status:  Off' + '\n')
            file_to_read.close()

            #self.text_errors.verticalScrollBar().setValue(self.text_errors.verticalScrollBar().maximum())

    def on_finished_script(self):
        """
        A function to add the information about errors found during syntax checking to a dedicated text box in the main window of the programm.
        """
        text = self.process_python.readAllStandardOutput().data().decode()
        text_errors_script = self.process_python.readAllStandardError().data().decode()
        if text_errors_script == '':
        #if text == '' and text_errors_script == '':
            self.text_errors.appendPlainText(f"The script PID {self.pid} was executed normally")
        elif text_errors_script != '':
            self.text_errors.appendPlainText(f"The script PID {self.pid} was executed with errors")
            self.text_errors.appendPlainText(text_errors_script)
            #self.text_errors.verticalScrollBar().setValue(self.text_errors.verticalScrollBar().maximum())

    def help(self):
        """
        A function to open a documentation
        """
        webbrowser.open("https://anatoly1010.github.io/atomize_docs/functions/", new = 0, autoraise = True)

    def edit_file(self):
        """
        A function to open an experimental script in a text editor.
        """
        if self.system == 'Linux':
            if self.editor =='nano':
                self.process_text_editor.setArguments(['-e','nano', self.script])
            elif self.editor == 'vi':
                self.process_text_editor.setArguments(['-e','vi', self.script])
            else:
                self.process_text_editor.setArguments([self.script])
        elif self.system == 'Windows':
            self.process_text_editor.setArguments([self.script])
        self.process_text_editor.start()
        
    def open_file(self, filename):
        """
        A function to open an experimental script.
        :param filename: string
        """
        self.cached_stamp = os.stat(filename).st_mtime
        text = open(filename).read()
        self.path = os.path.dirname(filename) # for memorizing the path to the last used folder
        self.script = filename
        self.textEdit.setPlainText(text)

        # scroll to Experimental parameters
        QtCore.QTimer.singleShot(0, lambda: self.textEdit.verticalScrollBar().setValue(9))
        self.label_filename.setText( str( self.script ) )
    
    def save_file(self, filename):
        """
        A function to save a new experimental script.
        :param filename: string
        """
        with open(filename, 'w') as file:
            file.write(self.textEdit.toPlainText())

        self.cached_stamp = os.stat(filename).st_mtime
        self.script = filename

    def open_file_dialog(self):
        """
        A function to open a new window for choosing an experimental script.
        """
        filedialog = QFileDialog(self, 'Open File', directory = self.path, filter = "python (*.py)",\
            options = QtWidgets.QFileDialog.Option.DontUseNativeDialog)
        # use QFileDialog.Option.DontUseNativeDialog to change directory
        filedialog.setStyleSheet("QWidget { background-color : rgb(42, 42, 64); color: rgb(211, 194, 78);}")
        filedialog.setFileMode(QtWidgets.QFileDialog.FileMode.AnyFile)
        filedialog.fileSelected.connect(self.open_file)
        filedialog.show()

    def save_file_dialog(self):
        """
        A function to open a new window for choosing a name for a new experimental script.
        """
        filedialog = QFileDialog(self, 'Save File', directory = self.path, filter = "python (*.py)",\
            options = QtWidgets.QFileDialog.Option.DontUseNativeDialog)
        filedialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        # use QFileDialog.Option.DontUseNativeDialog to change directory
        filedialog.setStyleSheet("QWidget { background-color : rgb(42, 42, 64); color: rgb(211, 194, 78);}")
        filedialog.setFileMode(QtWidgets.QFileDialog.FileMode.AnyFile)
        filedialog.fileSelected.connect(self.save_file)
        filedialog.show()

    def save_edited_text(self):
        if self.script:
            self.flag_opened_script_changed = 1
            with open(self.script, 'w') as file:
                file.write(self.textEdit.toPlainText())
            
            self.cached_stamp = os.stat(self.script).st_mtime

        else:
            self.flag_opened_script_changed = 1
            if self.textEdit.toPlainText() != '': # save file dialog will be opened after at least one character is added
                self.save_file_dialog()
        
    @QtCore.pyqtSlot(str) 
    def add_error_message(self, data):
        """
        A function for adding an error message to a dedicated text box in the main window of the programm;
        This function runs when Helper.changedSignal.emit(str) is emitted.
        :param data: string
        """
        self.text_errors.appendPlainText(str(data))

        if data == 'Script stopped':

            self.process_python.terminate()
            time.sleep(4)
            self.process_python.close()

            #path_to_main = os.path.abspath(os.getcwd())
            #lib_path = os.path.join(self.path_to_main, 'atomize/general_modules', 'libspinapi.so')
            #lib_path2 = os.path.join(self.path_to_main, 'atomize/general_modules', 'spinapi64.dll')

            #if os.path.exists(lib_path) == False and os.path.exists(lib_path2) == False:
            #    self.process_python.close()
            #else:
            #    
            #    ### keysight lines
            #    self.process_python.terminate()
            #    time.sleep(10)
            #
            #    import atomize.device_modules.PB_ESR_500_pro as pb_pro
            #    pb = pb_pro.PB_ESR_500_Pro()
            #    pb.pulser_stop()
            # 
            #    ### comment next lines for keysight:
            #    self.process_python.terminate()
            #
            #    # AWG
            #    hCard1 = spcm_hOpen (create_string_buffer (b'/dev/spcm0'))
            #    spcm_dwSetParam_i32 (hCard1, SPC_M2CMD, M2CMD_CARD_STOP)
            #    # clean up
            #    spcm_vClose (hCard1)

    def open_directory(self, path):
        if os.name == 'nt':
            os.startfile(path)
        elif os.name == 'posix': 
            subprocess.Popen(['open', path]) 
        else:
            print(f"Unsupported operating system: {os.name}")

class NameList(QDockWidget):
    def __init__(self, window):
        super(NameList, self).__init__('Current Plots:')
        self.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        
        #directories
        self.path_to_main = os.path.join(os.path.abspath(os.getcwd()))
        path_to_main = os.path.join(self.path_to_main,'..','atomize/tests')

        path_config_file = os.path.join(path_to_main, '..', 'config.ini')
        path_config_file_device = os.path.join(path_to_main, '..', 'device_modules/config')
        path_config_file, path_config2 = lconf.copy_config(path_config_file, path_config_file_device)

        config = configparser.ConfigParser()
        config.read(path_config_file)
        # directories
        self.open_dir = str(config['DEFAULT']['open_dir'])
        if self.open_dir == '':
            self.open_dir = lconf.load_scripts(os.path.join(path_to_main, '..', 'tests'))
        
        self.namelist_model = QStandardItemModel()
        self.namelist_view = QListView()
        self.namelist_view.setModel(self.namelist_model)
        self.setWidget(self.namelist_view)
        self.window = window
        self.plot_dict = {}

        self.namelist_view.doubleClicked.connect(self.activate_item)
        self.namelist_view.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.ActionsContextMenu)
        delete_action = QAction("Delete Selected", self.namelist_view)
        ###
        pause_action = QAction("Stop Script", self.namelist_view)
        delete_action.triggered.connect(self.delete_item)
        pause_action.triggered.connect(self.pause)
        self.namelist_view.addAction(delete_action)
        self.namelist_view.addAction(pause_action)

        open_action = QAction('Open 1D Data', self)
        open_action.triggered.connect(self.file_dialog) #self.open_file_dialog_1
        self.namelist_view.addAction(open_action)

        open_action_2 = QAction('Open 2D Data', self)
        open_action_2.triggered.connect(self.file_dialog_2d) #self.open_file_dialog_2
        self.namelist_view.addAction(open_action_2)

    def open_file(self, filename):
        """
        A function to open 1d data.
        :param filename: string
        """
        file_path = filename

        header_array = []
        header = 0

        file_to_read = open(filename, 'r')
        for i, line in enumerate(file_to_read):
            if i is header: break
            temp = line.split("#")
            header_array.append(temp)
        file_to_read.close()

        temp = np.genfromtxt(file_path, dtype = float, delimiter = ',', skip_header = 1, comments = '#') 
        data = np.transpose(temp)

        name_plot = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        pw = self.window.add_new_plot(1, name_plot)
        if len(data) == 2:
            pw.plot(data[0], data[1], parametric = True, name = file_path, xname = 'X', xscale = 'Arb. U.',\
                yname = 'Y', yscale = 'Arb. U.', label = 'Data_1', scatter = 'False')
        elif len(data) == 3 and np.isnan(data[2][0]) != True:
            pw.plot(data[0], data[1], parametric = True, name = file_path + '_1', xname = 'X', xscale = 'Arb. U.',\
                yname = 'Y', yscale = 'Arb. U.', label = 'Data_1', scatter = 'False')
            pw.plot(data[0], data[2], parametric = True, name = file_path + '_2', xname = 'X', xscale = 'Arb. U.',\
                yname = 'Y', yscale = 'Arb. U.', label = 'Data_2', scatter = 'False')
        elif len(data) == 3 and np.isnan(data[2][0]) == True:
            pw.plot(data[0], data[1], parametric = True, name = file_path, xname = 'X', xscale = 'Arb. U.',\
                yname = 'Y', yscale = 'Arb. U.', label = 'Data_1', scatter = 'False')
        elif len(data) == 4 and np.isnan(data[3][0]) == True:
            pw.plot(data[0], data[1], parametric = True, name = file_path + '_1', xname = 'X', xscale = 'Arb. U.',\
                yname = 'Y', yscale = 'Arb. U.', label = 'Data_1', scatter = 'False')
            pw.plot(data[0], data[2], parametric = True, name = file_path + '_2', xname = 'X', xscale = 'Arb. U.',\
                yname = 'Y', yscale = 'Arb. U.', label = 'Data_2', scatter = 'False')
        elif len(data) == 5 and np.isnan(data[4][0]) == True:
            pw.plot(data[0], data[1], parametric = True, name = file_path + '_1', xname = 'X', xscale = 'Arb. U.',\
                yname = 'Y', yscale = 'Arb. U.', label = 'Data_1', scatter = 'False')
            pw.plot(data[0], data[3], parametric = True, name = file_path + '_2', xname = 'X', xscale = 'Arb. U.',\
                yname = 'Y', yscale = 'Arb. U.', label = 'Data_2', scatter = 'False')

    def open_file_2d(self, filename):
        """
        A function to open 2d data
        :param filename: string
        """
        file_path = filename

        header_array = []
        header = 0

        header_array = []
        file_to_read = open(file_path, 'r')
        for i, line in enumerate(file_to_read):
            if i is header: break
            temp = line.split("#")
            header_array.append(temp)
        file_to_read.close()

        temp = np.genfromtxt(file_path, dtype = float, delimiter = ',', skip_header = 0) 
        data = temp

        name_plot = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        pw = self.window.add_new_plot(2, name_plot)
        pw.setAxisLabels(xname = 'X', xscale = 'Arb. U.',yname = 'X', yscale = 'Arb. U.',\
            zname = 'X', zscale = 'Arb. U.')
        pw.setImage(data, axes = {'y': 0, 'x': 1})

    # unused
    def open_file_dialog(self, directory = '', header = 0):
        pass
        # For Tkinter Open 1D; Unused
        # file_path = self.file_dialog(directory = directory)

        #header_array = [];
        #file_to_read = open(file_path, 'r')
        #for i, line in enumerate(file_to_read):
        #    if i is header: break
        #    temp = line.split("#")
        #    header_array.append(temp)
        #file_to_read.close()

        #temp = np.genfromtxt(file_path, dtype = float, delimiter = ',', skip_header = 0) 
        #data = np.transpose(temp)

        #name_plot = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        #pw = self.window.add_new_plot(1, name_plot)
        #if len(data) == 2:
        #    pw.plot(data[0], data[1], parametric = True, name = file_path, xname = 'X', xscale = 'Arb. U.',\
        #            yname = 'Y', yscale = 'Arb. U.', label = 'Data_1', scatter = 'False')
        #elif len(data) == 3:
        #    pw.plot(data[0], data[1], parametric = True, name = file_path + '_1', xname = 'X', xscale = 'Arb. U.',\
        #            yname = 'Y', yscale = 'Arb. U.', label = 'Data_1', scatter = 'False')
        #    pw.plot(data[0], data[2], parametric = True, name = file_path + '_2', xname = 'X', xscale = 'Arb. U.',\
        #            yname = 'Y', yscale = 'Arb. U.', label = 'Data_2', scatter = 'False')

    # unused
    def open_file_dialog_2(self, directory = '', header = 0):
        pass
        # For Tkinter Open 1D; Unused
        #file_path = self.file_dialog(directory = directory)

        #header_array = []
        #file_to_read = open(file_path, 'r')
        #for i, line in enumerate(file_to_read):
        #    if i is header: break
        #    temp = line.split("#")
        #    header_array.append(temp)
        #file_to_read.close()

        #temp = np.genfromtxt(file_path, dtype = float, delimiter = ',', skip_header = 0) 
        #data = temp

        #name_plot = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        #pw = self.window.add_new_plot(2, name_plot)
        #pw.setAxisLabels(xname = 'X', xscale = 'Arb. U.',yname = 'X', yscale = 'Arb. U.',\
        #    zname = 'X', zscale = 'Arb. U.')
        #pw.setImage(data, axes = {'y': 0, 'x': 1})

    def file_dialog(self, directory = ''):
        """
        A function to open a new window for choosing 1d data
        """
        filedialog = QFileDialog(self, 'Open File', directory = self.open_dir, filter = "CSV (*.csv)", \
                                    options = QtWidgets.QFileDialog.Option.DontUseNativeDialog )
        # options = QtWidgets.QFileDialog.Option.DontUseNativeDialog
        # use QFileDialog.Option.DontUseNativeDialog to change directory
        filedialog.setStyleSheet("QWidget { background-color : rgb(42, 42, 64); color: rgb(211, 194, 78);}")
        filedialog.setFileMode(QtWidgets.QFileDialog.FileMode.AnyFile)
        filedialog.fileSelected.connect(self.open_file)
        filedialog.show()

        # Tkinter Open 1D data
        #root = tkinter.Tk()
        #s = ttk.Style().theme_use('alt')
        #root.withdraw()

        #file_path = filedialog.askopenfilename(**dict(
        #    initialdir = self.open_dir,
        #    filetypes = [("CSV", "*.csv"), ("TXT", "*.txt"),\
        #    ("DAT", "*.dat"), ("all", "*.*")],
        #    title = 'Select file to open')
        #    )
        #return file_path

    def file_dialog_2d(self, directory = ''):
        """
        A function to open a new window for choosing 2D data
        """
        filedialog = QFileDialog(self, 'Open File', directory = self.open_dir, filter = "CSV (*.csv)", \
                                    options = QtWidgets.QFileDialog.Option.DontUseNativeDialog )
        #options = QtWidgets.QFileDialog.Option.DontUseNativeDialog
        # use QFileDialog.Option.DontUseNativeDialog to change directory
        filedialog.setStyleSheet("QWidget { background-color : rgb(42, 42, 64); color: rgb(211, 194, 78);}")
        filedialog.setFileMode(QtWidgets.QFileDialog.FileMode.AnyFile)
        filedialog.fileSelected.connect(self.open_file_2d)
        filedialog.show()

    def activate_item(self, index):
        item = self.namelist_model.itemFromIndex(index)
        plot = self.plot_dict[str(item.text())]
        if plot.closed:
            plot.closed = False
            self.window.add_plot(plot)

    def delete_item(self):
        index = self.namelist_view.currentIndex()
        item = self.namelist_model.itemFromIndex(index)
        del self[str(item.text())]

    def pause(self):
        sock = socket.socket()
        sock.connect(('localhost', 9091))
        sock.send(b'Script stopped')
        sock.close()

    def __getitem__(self, item):
        return self.plot_dict[item]

    def __setitem__(self, name, plot):
        model = QStandardItem(name)
        model.setEditable(False)
        self.namelist_model.appendRow(model)
        self.plot_dict[name] = plot

    def __contains__(self, value):
        return value in self.plot_dict

    def __delitem__(self, name):
        self.namelist_model.removeRow(self.namelist_model.findItems(name)[0].index().row())
        self.plot_dict[name].close()
        del self.plot_dict[name]

    def keys(self):
        return list( self.plot_dict.keys() )


def main():
    """
    A function to run the main window of the programm.
    """
    app = QtWidgets.QApplication(sys.argv)
    main = MainWindow()
    helper = socket_server.Helper()
    server = socket_server.Socket_server()
    # to connect a function add_error_message when the signal from the helper will be emitted.
    #QtCore.Qt.ContextMenuPolicy.ActionsContextMenu
    helper.changedSignal.connect( main.add_error_message, QtCore.Qt.ConnectionType.QueuedConnection )
    threading.Thread( target = server.start_messenger_server, args = (helper,), daemon = True ).start()
    main.show()
    sys.exit( app.exec() )

if __name__ == '__main__':
    main()
