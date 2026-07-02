import os
import re
import sys
import time
import ctypes
import threading
import numpy as np
import pyqtgraph as pg
from pathlib import Path
from PyQt6 import QtWidgets, uic, QtCore, QtGui
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QWidget, QGridLayout, QLabel, QPushButton, QComboBox, QCheckBox, QVBoxLayout, QApplication
from PyQt6.QtGui import QColor
from atomize.main.main_window import MainWindow, NameList
from atomize.general_modules.gui_style import apply_app_style
import atomize.general_modules.last_dir as ldir
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

###
# All modifications can be found with # mod
###
class MyExtendedNameList(NameList):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        open_action_tr = QAction('Open TR Data', self)
        open_action_tr.triggered.connect(lambda: self.file_dialog_2d(is_2d = True))
        self.namelist_view.addAction(open_action_tr)

        send_action = QAction('Send to Data Treatment', self)
        send_action.triggered.connect(self.send_to_treatment)
        self.namelist_view.addAction(send_action)

    def send_to_treatment(self):
        """
        Hand the selected plot off to the standalone Data Treatment window.
        1D plots (docks with named curves) go to the 1D tool via
        libs/treatment_buffer.csv; 2D image plots go to the 2D tool via
        libs/treatment_buffer_2d.npz. Either way this is the cross-process
        bridge the standalone windows read (they cannot see the main window's
        in-memory plots directly); they pick it up with "Load from plot".
        """
        index = self.namelist_view.currentIndex()
        item = self.namelist_model.itemFromIndex(index)
        if item is None:
            self.window.text_errors.appendPlainText('Select a plot first.')
            return

        name = str(item.text())
        dock = self.plot_dict.get(name)
        if dock is None:
            self.window.text_errors.appendPlainText('Plot "%s" not found.' % name)
            return
        if hasattr(dock, 'curves') and dock.curves:
            self._send_1d_to_treatment(name, dock)
        elif hasattr(dock, 'img_view'):
            self._send_2d_to_treatment(name, dock)
        else:
            self.window.text_errors.appendPlainText(
                'Nothing to send for "%s" (no 1D curves or 2D image).' % name)

    def _send_1d_to_treatment(self, name, dock):
        """Interleaved x0, y0, x1, y1, ... columns padded with NaN; a
        '# labels:' header line names the curves."""
        labels = []
        columns = []
        maxlen = 0
        for label in dock.curves:
            x, y = dock.get_raw_data(label)
            x = np.asarray(x, dtype=float)
            y = np.asarray(y, dtype=float)
            if x.size == 0:
                continue
            labels.append(str(label).replace('|', '/'))
            columns.append((x, y))
            maxlen = max(maxlen, x.size, y.size)

        if not columns:
            self.window.text_errors.appendPlainText('No data in "%s".' % name)
            return

        buf = np.full((maxlen, 2*len(columns)), np.nan)
        for i, (x, y) in enumerate(columns):
            buf[:x.size, 2*i] = x
            buf[:y.size, 2*i + 1] = y

        # carry the X axis name+unit so the 1D tool can label and SI-prefix it
        # (a time axis in 's' then reads in ns rather than raw 2e-9).
        xname = ''
        try:
            ax = dock.plot_widget.getPlotItem().getAxis('bottom')
            nm = (ax.labelText or '').strip()
            un = (ax.labelUnits or '').strip()
            xname = f'{nm} ({un})' if un else nm
        except Exception:
            xname = ''

        buffer_path = os.path.join(self.window.path_to_main, 'treatment_buffer.csv')
        header = 'Atomize data treatment buffer\nlabels: ' + '|'.join(labels)
        if xname:
            header += '\nxname: ' + xname.replace('\n', ' ')
        np.savetxt(buffer_path, buf, delimiter=',', fmt='%.6e', header=header, comments='# ')

        self.window.text_errors.appendPlainText('Sent "%s" to Data Treatment buffer.' % name)
        if self.window.process_treatment.state() == QtCore.QProcess.ProcessState.NotRunning:
            self.window.start_treatment_control()

    def _send_2d_to_treatment(self, name, dock):
        """Dump the selected 2D image (and its axis geometry) to
        libs/treatment_buffer_2d.npz for the 2D Data Treatment window. The
        image stack is (frames, nX, nY); frame 0 = real/I, frame 1 = imag/Q.
        We transpose each frame back to the tool's [trace, point] layout."""
        full = getattr(dock.img_view, 'image', None)
        if full is None:
            self.window.text_errors.appendPlainText('No 2D image data in "%s".' % name)
            return
        full = np.asarray(full, dtype=float)
        if full.ndim == 3:
            i = np.ascontiguousarray(full[0].T)          # (nX, nY) -> [trace, point]
            q = (np.ascontiguousarray(full[1].T) if full.shape[0] > 1
                 else np.zeros_like(i))
        elif full.ndim == 2:
            i = np.ascontiguousarray(full.T)
            q = np.zeros_like(i)
        else:
            self.window.text_errors.appendPlainText(
                'Unexpected 2D image shape %s for "%s".' % (full.shape, name))
            return

        x0 = float(getattr(dock, '_x0', 0.0)); dx = float(getattr(dock, '_xscale', 1.0))
        y0 = float(getattr(dock, '_y0', 0.0)); dy = float(getattr(dock, '_yscale', 1.0))
        try:
            xnm, xsc = dock.h_cross_section_widget.axis    # [xname, xscale]
        except Exception:
            xnm, xsc = 'X', ''
        try:
            ynm, ysc = dock.v_cross_section_widget.axis    # [yname, yscale]
        except Exception:
            ynm, ysc = 'Y', ''

        buffer_path = os.path.join(self.window.path_to_main, 'treatment_buffer_2d.npz')
        np.savez(buffer_path, i=i, q=q,
                 geom=np.array([x0, dx, y0, dy], dtype=float),
                 labels=np.array([str(xnm), str(xsc), str(ynm), str(ysc)]))

        self.window.text_errors.appendPlainText(
            'Sent 2D "%s" to Data Treatment (2D) buffer.' % name)
        if self.window.process_treatment_2d.state() == QtCore.QProcess.ProcessState.NotRunning:
            self.window.start_treatment_2d_control()

    def open_file_tr(self, filename):
        """
        A function to open 2d data
        :param filename: string
        """
        file_path = filename
        self.open_dir = os.path.dirname(filename)
        ldir.save('data', self.open_dir)      # remember the data folder

        header_lines = []

        with open(file_path, 'r') as file_to_read:
            for line in file_to_read:
                if line.startswith('#'):
                    header_lines.append(line)
                else:
                    break

        header_count = len(header_lines)
        header_text = "".join(header_lines)

        start_field_match = re.search(r'Start\s*Field\s*[:=]\s*([+-]?\d*\.\d+|[+-]?\d+)', header_text, re.IGNORECASE)
        field_step_match = re.search(r'Field\s*Step\s*[:=]\s*([+-]?\d*\.\d+|[+-]?\d+)', header_text, re.IGNORECASE)
        time_res_match = re.search(r'Time\s*Resolution\s*[:=]\s*([+-]?\d*\.\d+\s*[a-zA-Zμµ]+|[+-]?\d+\s*[a-zA-Zμµ]+)', header_text, re.IGNORECASE)

        t_step_2 = 1
        if time_res_match:
            t_res_2 = time_res_match.group(1).strip()
            try:
                t_step_2 = float(f"{pg.siEval(t_res_2):.4g}") 
            except Exception as e:
                pass

        start_field = float(start_field_match.group(1)) if start_field_match else 0
        field_step = float(field_step_match.group(1)) if field_step_match else 1

        temp = np.genfromtxt(file_path, dtype = float, delimiter = ',', skip_header = header_count) 

        data_modified = temp.copy()

        data_modified[:, 0] = data_modified[:, 0] - data_modified[:, 0]
        data_modified[:, :] = data_modified[:, :] - data_modified[0, :]

        data_3d = np.stack([temp, data_modified], axis=0)

        #name_plot = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        name_plot = os.path.splitext(os.path.basename(file_path))[0]

        pw = self.window.add_new_plot(2, name_plot)

        if start_field != 0 and t_step_2 != 1 and field_step != 1:
            pw.setAxisLabels(xname = 'Time', xscale = 's',yname = 'Field', yscale = 'G',
                zname = 'Intensity', zscale = 'V')
        else:
            pw.setAxisLabels(xname = 'X', xscale = 'Arb. U.',yname = 'Y', yscale = 'Arb. U.',
                zname = 'Z', zscale = 'Arb. U.')

        pw.setImage(
            data_3d, 
            axes={'t': 0, 'y': 1, 'x': 2}, 
            autoLevels=False,
            pos=(0, start_field),
            scale=(t_step_2, field_step)
        )

class MainExtended(MainWindow):

    def __init__(self, *args, **kwargs):
        """
        A function for connecting actions and creating a main window.
        """
        super().__init__(*args, **kwargs)
        path_to_main = Path(__file__).parent
        self.path_to_main = os.path.join(path_to_main, '..', '..', 'libs')

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
        self.process_sequence_calc = QtCore.QProcess(self)
        self.process_excitation = QtCore.QProcess(self)
        self.process_spin_sim = QtCore.QProcess(self)
        self.process_treatment = QtCore.QProcess(self)
        self.process_treatment_2d = QtCore.QProcess(self)
        self.process_deer = QtCore.QProcess(self)
        #self.process_t2 = QtCore.QProcess(self)
        #self.process_t1 = QtCore.QProcess(self)
        #self.process_ed = QtCore.QProcess(self)
        #self.process_eseem = QtCore.QProcess(self)

        self.all_processes = [self.process_tr, self.process_osc,
            self.process_osc2, self.process_cw, self.process_temp,
            self.process_field, self.process_mw, self.process_tune_preset,
            self.process_phasing, self.process_awg_phasing, self.process_sequence_calc,
            self.process_excitation, self.process_spin_sim, self.process_treatment, self.process_treatment_2d,
            self.process_deer
        ]
        #, self.process_t2, self.process_t1, self.process_ed, self.process_eseem]

        for process in self.all_processes:
            process.readyReadStandardOutput.connect(self.handle_output_control_center)

        # Use the current interpreter (sys.executable) so subprocesses inherit
        # the pipx/venv/conda site-packages — bare 'python3' would resolve to
        # system Python via PATH and miss PyQt6 et al. installed in the venv.
        for process in self.all_processes:
            process.setProgram(sys.executable)

        self.set_control_center()

        self.skip_lines = 0

    def create_namelist(self):
        return MyExtendedNameList(self)

    def handle_output_control_center(self):
        sending_process = self.sender()
        if not sending_process:
            return

        raw_data = sending_process.readAllStandardOutput().data().decode(self.system_encoding, errors='replace')
        if raw_data.startswith("print "):
            msg = raw_data[6:].strip()
            self.text_errors.appendPlainText(msg)
        # Sequence Calculator one-click open: launch the target phasing tool
        # pre-loaded with the preset it just wrote.
        elif raw_data.startswith("open_awg "):
            self.start_awg_phasing(raw_data[9:].strip())
        elif raw_data.startswith("open_rect "):
            self.start_rect_phasing(raw_data[10:].strip())
        # Insys stdOut
        elif raw_data.startswith("before "):
            self.skip_lines = 1
        elif 'ret = 0' in raw_data:
            self.skip_lines = 0
        elif raw_data.startswith("closing "):
            pass
        elif self.skip_lines != 1:
            self.text_errors.appendPlainText(raw_data[:-1])

    # control tab design
    def set_control_center(self):
        
        tab3 = QWidget()
        main_layout = QVBoxLayout(tab3)
        gridlayout = QGridLayout()
        gridlayout.setContentsMargins(5, 7, 5, 5)
        main_layout.addLayout(gridlayout)

        self.tabwidget.addTab(tab3, "EPR Endstation Control")
        self.tabwidget.tabBar().setTabTextColor(2, QColor(193, 202, 227))
        self.tabwidget.tabBar().setStyleSheet(" font-weight: bold ") 

        button_list = []

        button_name_1 = ["CW EPR", "TR EPR", "2012A; IP x.2.21", "2012A_2; IP x.2.22", "Set Temperature", "Set MF"]
        button_name_2 = ["Pulsed MW Bridge", "", "RECT Channel", "AWG Channel"]
        button_name_3 = ["Resonator Tuning", "", "Data Treatment", "Data Treatment 2D", "DEER / PDS", "Pulse Sequence", "Excitation Profile", "Spin Dynamics"]
        #, "T2 Measurement", "T1 Measurement", "ED Spectrum", "3pESEEM"]

        actions_1 = [self.start_cw, self.start_tr_control, self.start_osc_control, self.start_osc_control_2, self.start_temp_control, self.start_field_control]
        actions_2 = [self.start_mw_control, None, self.start_rect_phasing, self.start_awg_phasing]
        actions_3 = [self.start_tune_preset, None, self.start_treatment_control, self.start_treatment_2d_control, self.start_deer_analysis, self.start_sequence_calculator, self.start_excitation_profile, self.start_spin_sim]
        #, self.start_t2_preset, self.start_t1_preset, self.start_ed_preset, self.start_eseem_preset]

        columns_data = [(button_name_1, actions_1, 1), (button_name_2, actions_2, 2), (button_name_3, actions_3, 3)]

        for names, actions, col_idx in columns_data:
            for row_idx, name in enumerate(names):
                if not name:
                    continue
                
                btn = QPushButton(name)
                btn.setFixedSize(140, 40)
                btn.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; } QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")

                if actions and row_idx < len(actions) and actions[row_idx]:
                    btn.clicked.connect(actions[row_idx])
                    
                gridlayout.addWidget(btn, row_idx , col_idx)
                button_list.append(btn)

        # Test option
        label_2 = QLabel("Test Scripts:")
        label_2.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        label_2.setFixedWidth(100)
        gridlayout.addWidget(label_2, 0, 4)

        self.checkTests = QCheckBox("")
        gridlayout.addWidget(self.checkTests, 0, 5)
        self.checkTests.setStyleSheet("""
                QCheckBox { 
                    color: rgb(193, 202, 227); 
                    background-color: transparent; 
                    font-weight: bold;
                    spacing: 8px; 
                }

                QCheckBox::indicator {
                    width: 14px;
                    height: 14px;
                    background-color: rgb(63, 63, 97);
                    border: 1px solid rgb(83, 83, 117);
                    border-radius: 3px;
                }

                QCheckBox::indicator:hover {
                    border: 1px solid rgb(211, 194, 78);
                }

                QCheckBox::indicator:pressed {
                    background-color: rgb(83, 83, 117);
                }

                QCheckBox::indicator:checked {
                    background-color: rgb(211, 194, 78);
                    border: 3px solid rgb(63, 63, 97); 
                }
            """)

        self.checkTests.setFixedSize(140, 40)
        self.checkTests.setChecked(True)
        self.checkTests.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)


        #gridlayout.setColumnMinimumWidth(0, 20)
        #gridlayout.setRowMinimumHeight(0, 12)
        gridlayout.setHorizontalSpacing(15)
        gridlayout.setColumnStretch(6, 3)
        # Stretch row sits below the tallest button column (column 3 now has a
        # button on row 7), so the version label stays pinned to the bottom.
        gridlayout.setRowStretch(8, 3)

        bottom_label = QLabel("https://anatoly1010.github.io/atomize_docs/; Version 0.3.2; 01/03/2026")
        bottom_label.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        main_layout.addWidget(bottom_label)

    # redefined method
    def closeEvent(self, event):
        """
        A function to do some actions when the main window is closing.
        """
        processes = [
            self.process_python, self.process_tr, self.process_osc, 
            self.process_osc2, self.process_cw, self.process_temp, 
            self.process_field, self.process_mw, self.process_tune_preset,
            self.process_phasing, self.process_awg_phasing, self.process_sequence_calc,
            self.process_excitation, self.process_spin_sim, self.process_treatment, self.process_treatment_2d,
            self.process_deer
        ]
            #, self.process_t2, self.process_t1, self.process_ed, self.process_eseem]

        active_processes = []
        for p in processes:
            try:
                if p and p.state() != QtCore.QProcess.ProcessState.NotRunning:
                    active_processes.append(p)
            except AttributeError:
                pass

        if active_processes:
            event.ignore()
            self.text_errors.appendPlainText(f"{len(active_processes)} process is still running. Please terminate it")
        else:
            sys.exit()

    # redefined method
    def quit(self):
        """
        A function to quit the programm
        """
        processes = [
            self.process_python, self.process_tr, self.process_osc, 
            self.process_osc2, self.process_cw, self.process_temp, 
            self.process_field, self.process_mw, self.process_tune_preset,
            self.process_phasing, self.process_awg_phasing, self.process_sequence_calc,
            self.process_excitation, self.process_spin_sim, self.process_treatment, self.process_treatment_2d,
            self.process_deer
        ]
            #, self.process_t2, self.process_t1, self.process_ed, self.process_eseem]

        active_processes = []
        for p in processes:
            try:
                if p and p.state() != QtCore.QProcess.ProcessState.NotRunning:
                    active_processes.append(p)
            except AttributeError:
                pass

        if active_processes:
            self.text_errors.appendPlainText(f"{len(active_processes)} process is still running. Please terminate it")
        else:
            sys.exit()

    # redefined method
    def start_experiment(self):
        """
        A function to run an experimental script using python.exe.
        """
        if len(self.script_queue.keys()) != 0:
            self.queue = 1
            first_index = self.script_queue.namelist_model.index(0, 0 )
            self.script_queue.namelist_view.setCurrentIndex(first_index)            
        else:
            self.queue = 0

        if self.queue == 0:
            name = self.script
        else:
            name = self.script_queue.values()[0]

        if self.script != '':
            stamp = os.stat(name).st_mtime
        else:
            self.text_errors.appendPlainText('No experimental script is opened')
            return

        # mod
        if self.checkTests.checkState().value == 2:
            self.test(name)
            exec_code = self.success
            #self.process.waitForFinished( msecs = self.test_timeout ) # timeout in msec
        elif self.checkTests.checkState().value == 0:
            self.test_flag = 0
            exec_code = True
            self.text_errors.appendPlainText("Testing of experimental scripts are disabled")
        # mod

        if self.test_flag == 1:
            self.text_errors.appendPlainText("Experiment cannot be started, since test is not passed. Test execution timeout is " +\
                                str( self.test_timeout / 60000 ) + " minutes")
            return
        elif self.test_flag == 0 and exec_code == True:
            self.process_python.setArguments([name])
            self.button_start.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(211, 194, 78); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } ")
            self.process_python.start()
            self.pid = self.process_python.processId()
            print(f'SCRIPT PROCESS ID: {self.pid}')

    # redefined method
    def on_finished_checking(self, exit_code, exit_status, loop, process):
        """
        A function to add the information about errors found during syntax checking
        to a dedicated text box in the main window of the programm.
        """
        text = process.readAllStandardOutput().data().decode(self.system_encoding, errors='replace')
        text_errors_script = process.readAllStandardError().data().decode(self.system_encoding, errors='replace')
        if text_errors_script == '':
            self.text_errors.appendPlainText("No errors are found")
            self.test_flag = 0
            self.checked = 1
        elif text_errors_script != '':
            self.test_flag = 1
            self.checked = 0
            self.text_errors.appendPlainText(text_errors_script)
            # mod
            path_status_file = os.path.join(self.path_to_main, 'status')
            file_to_read = open(path_status_file, 'w')
            file_to_read.write('Status:  Off' + '\n')
            file_to_read.close()
            # mod

        self.button_test.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; } ")

        self.success = (exit_status == QtCore.QProcess.ExitStatus.NormalExit and exit_code == 0)
        loop.quit()

    # redefined method
    @QtCore.pyqtSlot(str)
    def add_error_message(self, data):
        """
        A function for adding an error message to a dedicated text box in the main window of the programm;
        This function runs when Helper.changedSignal.emit(str) is emitted.
        :param data: string
        """
        self.text_errors.appendPlainText(str(data))

        if data == 'Script stopped':
            self.script_queue.clear()
            self.queue = 0
            #mod
            #self.process_python.close()
            self.process_python.terminate()
            time.sleep(2)
            self.process_python.close()
            # mod

    ##### new methods:
    ###unused
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
    ###unused

    def start_rect_phasing(self, preset=None):
        """
        A function to run an phasing for rect channel.
        :param preset: optional *.phase path to auto-open (from Seq Calculator).
        """
        args = [os.path.join('..','atomize/control_center/phasing_insys.py')]
        if preset and isinstance(preset, str):
            args.append(preset)
        self.process_phasing.setArguments(args)
        self.process_phasing.start()

    def start_awg_phasing(self, preset=None):
        """
        A function to run an phasing for awg channel.
        :param preset: optional *.phase_awg path to auto-open (from Seq Calculator).
        """
        args = [os.path.join('..','atomize/control_center/awg_phasing_insys.py')]
        if preset and isinstance(preset, str):
            args.append(preset)
        self.process_awg_phasing.setArguments(args)
        self.process_awg_phasing.start()

    def start_sequence_calculator(self):
        """
        A function to run the EPR sequence timing & phase-cycling calculator.
        """
        self.process_sequence_calc.setArguments([os.path.join('..','atomize/control_center/sequence_calculator.py')])
        self.process_sequence_calc.start()

    def start_excitation_profile(self):
        """
        A function to run the pulse excitation/inversion profile simulator.
        """
        self.process_excitation.setArguments([os.path.join('..','atomize/control_center/excitation_profile.py')])
        self.process_excitation.start()

    def start_spin_sim(self):
        """
        A function to run the density-matrix pulse-sequence simulator.
        """
        self.process_spin_sim.setArguments([os.path.join('..','atomize/control_center/spin_dynamics_sim.py')])
        self.process_spin_sim.start()

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

    def start_treatment_control(self):
        """
        A function to run the data-treatment window (fitting / FFT / smoothing).
        """
        self.process_treatment.setArguments([os.path.join('..','atomize/control_center/data_treatment.py')])
        self.process_treatment.start()

    def start_treatment_2d_control(self):
        """
        A function to run the 2D data-treatment window (FFT along an axis /
        2D FFT / slice / projection).
        """
        self.process_treatment_2d.setArguments([os.path.join('..','atomize/control_center/data_treatment_2d.py')])
        self.process_treatment_2d.start()

    def start_deer_analysis(self):
        """
        A function to run the standalone DEER / PDS analysis window
        (background fit + Tikhonov inversion to a distance distribution P(r)).
        """
        self.process_deer.setArguments([os.path.join('..','atomize/control_center/deer_analysis.py')])
        self.process_deer.start()

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

def main():
    """
    A function to run the main window of the programm.
    """
    # Windows taskbar
    try:
        myappid = 'atomize'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass
    
    app = QtWidgets.QApplication(sys.argv)
    # Pin the Fusion style + shared dark palette (same as the control-center
    # tools) so native widgets and pyqtgraph's right-click context menus pick up
    # the Atomize dark theme. app_id is omitted to keep the AUMID set above.
    apply_app_style(app)
    main = MainExtended(ptm = '../../libs')
    main.show()
    sys.exit( app.exec() )

if __name__ == '__main__':
    main()