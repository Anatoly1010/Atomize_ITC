"""Shared message and pulse-list panel for the Insys phasing tools."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QTextCursor, QTextOption
from PyQt6.QtWidgets import QLabel, QPlainTextEdit, QTabWidget, QVBoxLayout, QWidget

from atomize.general_modules.gui_style import REFINED_STYLES


class MessageLog(QPlainTextEdit):
    """Keep the existing append/clear API and preserve the reader's position."""

    cleared = pyqtSignal()
    pinned = pyqtSignal(str)

    def appendPlainText(self, text):
        lines = text.splitlines()
        if lines and lines[0].startswith('PHASE CYCLE EXCEEDS ADC BUFFER'):
            # the buffer lines go to the banner only; the rest stays in the log
            self.pinned.emit('\n'.join(lines[:2]))
            text = '\n'.join(lines[2:])
            if not text:
                return
        bar = self.verticalScrollBar()
        position = bar.value()
        following = position == bar.maximum()
        super().appendPlainText(text)
        bar.setValue(bar.maximum() if following else position)

    def clear(self):
        super().clear()
        self.cleared.emit()


class PhasingMessagePanel(QWidget):
    """Pin buffer warnings while messages and pulse details scroll separately."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.buffer_warning = QLabel()
        self.buffer_warning.setTextFormat(Qt.TextFormat.PlainText)
        self.buffer_warning.setWordWrap(True)
        self.buffer_warning.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.buffer_warning.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.buffer_warning.setStyleSheet(REFINED_STYLES['BUFFER_WARNING_STYLE'])
        self.buffer_warning.hide()
        layout.addWidget(self.buffer_warning)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(REFINED_STYLES['TAB_STYLE'])
        self.experiment_status = QLabel('Experiment running')
        self.experiment_status.setStyleSheet(REFINED_STYLES['RUN_STATUS_STYLE'])
        self.tabs.setCornerWidget(self.experiment_status, Qt.Corner.TopRightCorner)
        self.experiment_status.hide()
        self.messages = MessageLog()
        self.pulses = QPlainTextEdit()
        for editor in (self.messages, self.pulses):
            editor.setReadOnly(True)
            editor.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            editor.setStyleSheet(REFINED_STYLES['COMPACT_TEXT_STYLE'] + REFINED_STYLES['SCROLL_STYLE'])
        self.messages.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.messages.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.messages.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.pulses.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.tabs.addTab(self.messages, 'Messages')
        self.tabs.addTab(self.pulses, 'Pulse List')
        layout.addWidget(self.tabs)
        self.messages.pinned.connect(self._pin_buffer_warning)
        self.messages.cleared.connect(self._clear_details)

    def set_experiment_running(self, running):
        self.experiment_status.setVisible(running)

    def _pin_buffer_warning(self, text):
        detail = ' · '.join(line.strip().strip('!') for line in text.splitlines() if line.strip())
        detail = detail.replace('PHASE CYCLE EXCEEDS ADC BUFFER: LIVE PREVIEW UPDATES ONCE PER FULL CYCLE',
                                'Phase cycle exceeds ADC buffer: live preview updates once per full cycle')
        detail = detail.replace('ADC WINDOWS IN BUFFER:', 'ADC windows in buffer:')
        self.buffer_warning.setText('LIVE MODE BUFFER · ' + detail)
        self.buffer_warning.setToolTip(text)
        self.buffer_warning.show()

    def _clear_details(self):
        self.pulses.clear()
        self.buffer_warning.clear()
        self.buffer_warning.setToolTip('')
        self.buffer_warning.hide()
        self.tabs.setCurrentIndex(0)

    def update_pulse_list(self, text):
        """Replace only the pulse details, keeping their scroll position."""
        vertical = self.pulses.verticalScrollBar().value()
        horizontal = self.pulses.horizontalScrollBar().value()
        self.pulses.setPlainText(text)
        self.pulses.verticalScrollBar().setValue(vertical)
        self.pulses.horizontalScrollBar().setValue(horizontal)

    def update_count(self, text):
        """Replace the trailing count block, even when it wraps across lines."""
        marker = 'count_nip: '
        line = marker + text
        cursor = QTextCursor(self.messages.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if cursor.block().text().startswith(marker):
            bar = self.messages.verticalScrollBar()
            position = bar.value()
            following = position == bar.maximum()
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(line)
            bar.setValue(bar.maximum() if following else position)
        else:
            self.messages.appendPlainText(line)
