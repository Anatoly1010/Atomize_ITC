"""ITC protocol launcher with asynchronous output, prompts and stop handling."""
import codecs
import json
import sys
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

from atomize.epr_auto.gui_io import PREFIX
from atomize.general_modules.gui_style import REFINED_STYLES, style_file_dialog


class ProtocolLauncher(QtWidgets.QWidget):
    log = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QtCore.QProcess(self)
        self.process.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.run_button = QtWidgets.QPushButton('Run protocol…')
        self.stop_button = QtWidgets.QPushButton('Stop protocol')
        icon_dir = Path(__file__).resolve().parents[1] / 'control_center' / 'gui'
        self.run_button.setIcon(QtGui.QIcon(str(icon_dir / 'icon_protocol_run.ico')))
        self.stop_button.setIcon(QtGui.QIcon(str(icon_dir / 'icon_protocol_stop.ico')))
        self.stop_button.setEnabled(False)
        self.dry_run = QtWidgets.QCheckBox('Dry run')
        self.dry_run.setChecked(True)
        self.status = QtWidgets.QLabel('No protocol running')
        self.setObjectName('launcherPanel')
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        alignment = 'QPushButton { text-align: left; padding-left: 12px; }'
        self.run_button.setStyleSheet(REFINED_STYLES['BUTTON_STYLE'] + alignment)
        self.stop_button.setStyleSheet(REFINED_STYLES['STOP_BUTTON_STYLE'] + alignment)
        for button in (self.run_button, self.stop_button):
            button.setMinimumSize(208, 42)
            button.setIconSize(QtCore.QSize(22, 22))
        self.dry_run.setStyleSheet(REFINED_STYLES['CHECKBOX_STYLE'])
        self.status.setStyleSheet(REFINED_STYLES['HINT_STYLE'])
        self.controls_layout = QtWidgets.QGridLayout(self)
        self.controls_layout.setContentsMargins(16, 16, 16, 16)
        self.controls_layout.setHorizontalSpacing(48)
        self.controls_layout.setVerticalSpacing(12)
        for column in range(3):
            self.controls_layout.setColumnStretch(column, 1)
            self.controls_layout.setColumnMinimumWidth(column, 208)
        self.controls_layout.addWidget(self.run_button, 0, 0)
        self.controls_layout.addWidget(self.stop_button, 1, 0)
        self.options_widget = QtWidgets.QWidget(self)
        self.options_layout = QtWidgets.QVBoxLayout(self.options_widget)
        self.options_layout.setContentsMargins(0, 0, 0, 0)
        self.options_layout.setSpacing(6)
        self.options_layout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetFixedSize)
        self.options_layout.addWidget(self.dry_run)
        self.controls_layout.addWidget(self.options_widget, 0, 1,
                                       QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft)
        self.controls_layout.addWidget(self.status, 2, 0, 1, 3)
        self.run_button.clicked.connect(self.choose_protocol)
        self.stop_button.clicked.connect(self.request_stop)
        self.directory = str(Path(__file__).resolve().parents[2] / 'protocols')
        self.dialog = None
        self.stopping = False
        self.buffer = ''
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')

    def choose_protocol(self):
        if self.process.state() != QtCore.QProcess.ProcessState.NotRunning:
            return
        dialog = QtWidgets.QFileDialog(self, 'Run EPR protocol', self.directory,
                                       'YAML protocols (*.yaml *.yml)')
        dialog.setOption(QtWidgets.QFileDialog.Option.DontUseNativeDialog)
        dialog.setFileMode(QtWidgets.QFileDialog.FileMode.ExistingFile)
        style_file_dialog(dialog)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            path = dialog.selectedFiles()[0]
            self.directory = str(Path(path).parent)
            self.start_protocol(path)
        dialog.deleteLater()

    def start_protocol(self, path):
        if self.process.state() != QtCore.QProcess.ProcessState.NotRunning:
            self.log.emit('A protocol is already running.')
            return False
        self.buffer = ''
        self.decoder.reset()
        self.stopping = False
        self.run_button.setEnabled(False)
        self.dry_run.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.stop_button.setText('Stop protocol')
        mode = 'dry run' if self.dry_run.isChecked() else 'live'
        self.status.setText(f'{Path(path).name} — {mode}')
        self.log.emit(f'Protocol: {path} ({mode})')
        args = ['-u', '-m', 'atomize.epr_auto', 'run', str(Path(path).resolve()), '--gui']
        if self.dry_run.isChecked():
            args.append('--test')
        self.process.start(sys.executable, args)
        return True

    def _read_output(self):
        self.buffer += self.decoder.decode(bytes(self.process.readAllStandardOutput()))
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            self._line(line.rstrip('\r'))

    def _line(self, line):
        if not line.startswith(PREFIX):
            self.log.emit(line)
            return
        try:
            request = json.loads(line[len(PREFIX):])
            if not isinstance(request, dict):
                raise ValueError('expected a prompt object')
            self._prompt(request)
        except (ValueError, KeyError, TypeError) as error:
            self.log.emit(f'Invalid protocol prompt: {error}')
            self.request_stop()

    def _prompt(self, request):
        if self.stopping:
            return
        choices = {
            'checkpoint': [('Continue', 'continue'), ('Skip', 'skip'), ('Abort', 'stop')],
            'failure': [('Retry', 'retry'), ('Skip', 'skip'), ('Abort', 'stop')],
            'rail': [('Re-run coarse stage', 'yes'), ('No', 'no'), ('Abort', 'stop')],
        }[request['kind']]
        if self.dialog is not None:
            raise ValueError('another prompt is already open')
        dialog = QtWidgets.QMessageBox(self)
        dialog.setWindowTitle('EPR protocol')
        style_file_dialog(dialog)
        dialog.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        dialog.setText(request['prompt'].strip())
        buttons = {}
        for label, reply in choices:
            role = (QtWidgets.QMessageBox.ButtonRole.RejectRole if reply == 'stop'
                    else QtWidgets.QMessageBox.ButtonRole.ActionRole)
            button = dialog.addButton(label, role)
            button.setStyleSheet(REFINED_STYLES['STOP_BUTTON_STYLE'] if reply == 'stop'
                                 else REFINED_STYLES['BUTTON_STYLE'])
            buttons[button] = reply
            if reply == 'stop':
                dialog.setEscapeButton(button)
        self.dialog = dialog
        def answered(_):
            self.dialog = None
            reply = buttons.get(dialog.clickedButton(), 'stop')
            dialog.deleteLater()
            if self.stopping or self.process.state() == QtCore.QProcess.ProcessState.NotRunning:
                return
            if reply == 'stop':
                self.request_stop()
            else:
                self.process.write((reply + '\n').encode())
        dialog.finished.connect(answered)
        dialog.setWindowModality(QtCore.Qt.WindowModality.NonModal)
        dialog.show()

    def request_stop(self):
        if self.process.state() == QtCore.QProcess.ProcessState.NotRunning:
            return
        self.log.emit('Force stop requested (second interrupt).' if self.stopping else 'Protocol stop requested.')
        self.stopping = True
        self.status.setText('Stopping — waiting for cleanup')
        self.stop_button.setText('Force stop')
        self.process.write(b'stop\n')
        if self.dialog is not None:
            self.dialog.reject()

    def _finished(self, code, exit_status):
        self._read_output()
        self.buffer += self.decoder.decode(b'', final=True)
        if self.buffer:
            self._line(self.buffer.rstrip('\r'))
            self.buffer = ''
        self.stopping = True
        if self.dialog is not None:
            self.dialog.reject()
        label = ('crashed' if exit_status == QtCore.QProcess.ExitStatus.CrashExit else
                 {0: 'finished', 1: 'invalid', 2: 'aborted', 3: 'unsupported'}.get(code, f'failed ({code})'))
        self.log.emit(f'Protocol {label}.')
        self.status.setText(f'Protocol {label}')
        self.run_button.setEnabled(True)
        self.dry_run.setEnabled(True)
        self.stop_button.setEnabled(False)

    def _error(self, error):
        self.log.emit(f'Protocol process error: {self.process.errorString()}')
        if error == QtCore.QProcess.ProcessError.FailedToStart:
            self._finished(-1, QtCore.QProcess.ExitStatus.CrashExit)
