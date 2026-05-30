#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
2D Data Treatment control-center window.

Standalone QProcess launched from the "EPR Endstation Control" tab, the 2D
sibling of data_treatment.py, for I/Q 2D datasets (echo decay / FID vs a
parameter). It mirrors the phase_cor.py workflow:

  * I/Q loading by name convention — open `name.csv` (I); `name_1.csv` (Q) is
    loaded automatically. Each file is a matrix [trace, point] (rows = the
    slow/indirect parameter, columns = the fast within-trace axis).
  * Axis metadata is set by hand (start / step / name / unit per axis) — there
    is no .param sidecar.
  * Two independent, chainable operations:
      - Phase correction: multiply I+iQ by exp(i·(φ₀ + φ₁·x + φ₂·x²)) along the
        X axis (φ₀ in degrees, φ₁/φ₂ in rad per X-unit / X-unit²).
      - FFT (selectable axis): complex FFT of I+iQ along the within-trace (X) or
        the indirect (Y) axis, with optional apodization + zero fill; the
        transformed axis becomes frequency.

There is NO embedded plot: results are pushed to the main GUI via
general.plot_2d, which provides the heatmap + X/Y cross-section docks. Real and
imaginary parts ride along as the two toggleable frames of a (2, nX, nY) array.
"Result → input" chains one operation into the next (e.g. phase → FFT).
"""

import os
import sys
import numpy as np

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QComboBox, QGridLayout, QVBoxLayout, QHBoxLayout, QTabWidget, QDoubleSpinBox,
    QSpinBox, QLineEdit, QCheckBox, QFrame)

import atomize.general_modules.general_functions as general
import atomize.general_modules.csv_opener_saver as openfile
import atomize.math_modules.signal_processing as sigproc

BG = 'rgb(42, 42, 64)'
FG = 'rgb(193, 202, 227)'
ACCENT = 'rgb(211, 194, 78)'

BUTTON_STYLE = ("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); "
    "border-style: outset; color: rgb(193, 202, 227); font-weight: bold; padding: 4px; } "
    "QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")

LABEL_STYLE = "QLabel { color : rgb(193, 202, 227); font-weight: bold; }"

DSPIN_STYLE = ("QDoubleSpinBox { color : rgb(193, 202, 227); "
    "selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97); }")
SPIN_STYLE = ("QSpinBox { color : rgb(193, 202, 227); "
    "selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97); }")

COMBO_STYLE = ("QComboBox { color : rgb(193, 202, 227); "
    "selection-color: rgb(211, 194, 78); selection-background-color: rgb(63, 63, 97); "
    "outline: none; }")

LINEEDIT_STYLE = ("QLineEdit { color: rgb(211, 194, 78); "
    "selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97); }")

CHECKBOX_STYLE = """
    QCheckBox { color: rgb(193, 202, 227); background-color: transparent;
        font-weight: bold; spacing: 8px; }
    QCheckBox::indicator { width: 14px; height: 14px;
        background-color: rgb(63, 63, 97); border: 1px solid rgb(83, 83, 117);
        border-radius: 3px; }
    QCheckBox::indicator:hover { border: 1px solid rgb(211, 194, 78); }
    QCheckBox::indicator:checked { background-color: rgb(211, 194, 78);
        border: 3px solid rgb(63, 63, 97); }
"""

TAB_STYLE = """
    QTabWidget::pane { border: 1px solid rgb(43, 43, 77); top: -1px;
        background: rgb(63, 63, 97); }
    QTabBar::tab { height: 22px; font-weight: bold; color: rgb(193, 202, 227);
        background: rgb(63, 63, 97); border: 1px solid rgb(43, 43, 77);
        border-bottom: none; border-top-left-radius: 4px;
        border-top-right-radius: 4px; padding: 2px 10px; margin-right: 2px; }
    QTabBar::tab:selected { color: rgb(211, 194, 78); background: rgb(83, 83, 117);
        border-bottom: 2px solid rgb(211, 194, 78); }
    QTabBar::tab:hover { background: rgb(73, 73, 107); }
"""

WINDOWS = ['None', 'Hann', 'Hamming', 'Blackman', 'Bartlett', 'Flat-top',
           'Kaiser', 'Gaussian', 'Tukey']
ZEROFILL = ['None', '×2', '×4', '×8', 'Next pow₂']

# parametric windows: name -> (label, min, max, decimals, default, step)
WINDOW_PARAM = {
    'Kaiser':   ('Kaiser β', 0.0, 100.0, 2, 8.6, 0.5),
    'Gaussian': ('Gaussian σ (×N)', 0.01, 1.0, 3, 0.15, 0.01),
    'Tukey':    ('Tukey α', 0.0, 1.0, 3, 0.5, 0.05),
}


class MainWindow(QMainWindow):

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        if len(sys.argv) > 1:
            self.test_flag = sys.argv[1]
        else:
            self.test_flag = 'None'

        self.opener = openfile.Saver_Opener()

        # complex data as two real channels, each a [trace, point] matrix.
        # raw_*  = as loaded; src_* = current input to operations (= raw after a
        # load / reset, or a promoted result); res_* = current operation output.
        self.raw_i = self.raw_q = None
        self.src_i = self.src_q = None
        self.src_col = self.src_row = None     # axis dicts (see _axis)
        self.res_i = self.res_q = None
        self.res_col = self.res_row = None
        self.res_frames = ('I', 'Q')
        self.res_meta = []
        self._suppress_live = False

        self.design()

    # ----------------------------------------------------------------- UI
    def design(self):
        self.setWindowTitle('2D Data Treatment')
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 'gui', 'icon_temp.png')
        self.setWindowIcon(QIcon(icon_path))
        self.setMinimumHeight(560)
        self.resize(420, 660)
        # background on the QMainWindow (as in awg_phasing_insys.py) rather than
        # the central widget, so spinboxes keep their full native frame.
        self.setStyleSheet(f"background-color: {BG};")
        central = QWidget()
        self.setCentralWidget(central)
        panel = QVBoxLayout(central)

        # ---- Source ----
        panel.addWidget(self._heading('Source (I/Q 2D)'))
        src_row = QHBoxLayout()
        btn_open = QPushButton('Open I/Q (CSV + _1)…')
        btn_open.setStyleSheet(BUTTON_STYLE)
        btn_open.clicked.connect(self.open_iq)
        btn_clear = QPushButton('Clear')
        btn_clear.setStyleSheet(BUTTON_STYLE)
        btn_clear.clicked.connect(self.clear_all)
        src_row.addWidget(btn_open)
        src_row.addWidget(btn_clear)
        panel.addLayout(src_row)

        self.transpose_check = QCheckBox('Transpose on load (swap trace / point axes)')
        self.transpose_check.setStyleSheet(CHECKBOX_STYLE)
        panel.addWidget(self.transpose_check)

        # ---- Axis metadata (reconstructed by hand; no .param) ----
        panel.addWidget(self._heading('Axes'))
        ax = QGridLayout()
        ax.addWidget(self._label('X (within trace)'), 0, 0)
        self.xname_edit = QLineEdit('Time'); self.xname_edit.setStyleSheet(LINEEDIT_STYLE)
        self.xscale_edit = QLineEdit('ns');  self.xscale_edit.setStyleSheet(LINEEDIT_STYLE)
        ax.addWidget(self.xname_edit, 0, 1); ax.addWidget(self.xscale_edit, 0, 2)
        ax.addWidget(self._label('X start / step'), 1, 0)
        self.x0_spin = self._dspin(-1e12, 1e12, 6, 0.0)
        self.dx_spin = self._dspin(-1e12, 1e12, 9, 1.0)
        ax.addWidget(self.x0_spin, 1, 1); ax.addWidget(self.dx_spin, 1, 2)
        ax.addWidget(self._label('Y (indirect)'), 2, 0)
        self.yname_edit = QLineEdit('Delay'); self.yname_edit.setStyleSheet(LINEEDIT_STYLE)
        self.yscale_edit = QLineEdit('ns');   self.yscale_edit.setStyleSheet(LINEEDIT_STYLE)
        ax.addWidget(self.yname_edit, 2, 1); ax.addWidget(self.yscale_edit, 2, 2)
        ax.addWidget(self._label('Y start / step'), 3, 0)
        self.y0_spin = self._dspin(-1e12, 1e12, 6, 0.0)
        self.dy_spin = self._dspin(-1e12, 1e12, 9, 1.0)
        ax.addWidget(self.y0_spin, 3, 1); ax.addWidget(self.dy_spin, 3, 2)
        panel.addLayout(ax)
        # title / unit edits only relabel the current plot in place (keep the
        # result); start / step edits change the geometry, so they reset to raw.
        for w in (self.xname_edit, self.xscale_edit, self.yname_edit, self.yscale_edit):
            w.textChanged.connect(self.on_axis_labels_changed)
        for s in (self.x0_spin, self.dx_spin, self.y0_spin, self.dy_spin):
            s.valueChanged.connect(self.on_axes_changed)

        self.live_check = QCheckBox('Live update on parameter change')
        self.live_check.setStyleSheet(CHECKBOX_STYLE)
        self.live_check.setChecked(True)
        panel.addWidget(self.live_check)

        panel.addWidget(self._hline())

        # ---- Operation tabs ----
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(TAB_STYLE)
        self.tabs.addTab(self._build_phase_tab(), 'Phase')
        self.tabs.addTab(self._build_fft_tab(), 'FFT')
        self.tabs.currentChanged.connect(self._live_update)
        panel.addWidget(self.tabs, stretch=1)

        panel.addWidget(self._hline())

        # ---- Output ----
        panel.addWidget(self._heading('Output'))
        self.name_edit = QLineEdit('FT Data 2D')
        self.name_edit.setStyleSheet(LINEEDIT_STYLE)
        self.name_edit.editingFinished.connect(self._push_current)
        panel.addWidget(self.name_edit)
        out_row = QHBoxLayout()
        btn_apply = QPushButton('Apply && plot')
        btn_apply.setStyleSheet(BUTTON_STYLE)
        btn_apply.clicked.connect(self._apply_current_op)
        btn_chain = QPushButton('Result → input')
        btn_chain.setStyleSheet(BUTTON_STYLE)
        btn_chain.clicked.connect(self.promote_result)
        btn_reset = QPushButton('Reset to raw')
        btn_reset.setStyleSheet(BUTTON_STYLE)
        btn_reset.clicked.connect(self.reset_to_raw)
        btn_save = QPushButton('Save I/Q…')
        btn_save.setStyleSheet(BUTTON_STYLE)
        btn_save.clicked.connect(self.save_result)
        out_row.addWidget(btn_apply); out_row.addWidget(btn_chain)
        out_row.addWidget(btn_reset); out_row.addWidget(btn_save)
        panel.addLayout(out_row)

        self.status = QLabel('Open an I/Q 2D dataset (name.csv + name_1.csv).')
        self.status.setStyleSheet(LABEL_STYLE)
        self.status.setWordWrap(True)
        panel.addWidget(self.status)

        # Pin spinboxes to a fixed 26 px height (as in awg_phasing_insys.py) so
        # the native +/- frame renders fully; combos / buttons / line edits get
        # the same min height for row alignment.
        row_h = 26
        for wdg in self.findChildren((QComboBox, QPushButton, QLineEdit)):
            pass
            #wdg.setMinimumHeight(row_h)
        for spin in self.findChildren((QSpinBox, QDoubleSpinBox)):
            spin.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
            spin.setFixedHeight(row_h)

    # ---- small helpers ----
    def _hline(self):
        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setStyleSheet('color: rgb(83, 83, 117);')
        return line

    def _heading(self, text):
        lab = QLabel(text)
        lab.setStyleSheet(f"QLabel {{ color: {ACCENT}; font-weight: bold; font-size: 13px; }}")
        return lab

    def _label(self, text):
        lab = QLabel(text); lab.setStyleSheet(LABEL_STYLE)
        return lab

    def _note(self, text):
        lab = QLabel(f'<div style="line-height: 145%;">{text}</div>')
        lab.setStyleSheet(LABEL_STYLE); lab.setWordWrap(True)
        lab.setTextFormat(Qt.TextFormat.RichText)
        return lab

    def _dspin(self, lo, hi, dec, val, step=None):
        s = QDoubleSpinBox(); s.setStyleSheet(DSPIN_STYLE)
        s.setDecimals(dec); s.setRange(lo, hi)
        if step is not None:
            s.setSingleStep(step)
        s.setValue(val)
        return s

    def _combo(self, items):
        c = QComboBox(); c.setStyleSheet(COMBO_STYLE); c.addItems(items)
        return c

    @staticmethod
    def _axis(start, step, name, scale, auto=False):
        # auto=True marks an axis whose label is owned by an operation (e.g. the
        # FFT frequency axis), so manual title/unit edits leave it untouched.
        return {'start': float(start), 'step': float(step),
                'name': str(name), 'scale': str(scale), 'auto': bool(auto)}

    # ---- tabs ----
    def _build_phase_tab(self):
        w = QWidget(); grid = QGridLayout(w)
        grid.addWidget(self._note('Multiply I+iQ by exp(i·(φ₀ + φ₁·x + φ₂·x²)) '
                                  'along the X axis. Run before or after FFT.'),
                       0, 0, 1, 2)
        grid.addWidget(self._label('Zero order (deg)'), 1, 0)
        self.phase_zero = self._dspin(0.0, 360.0, 2, 0.0, step=0.5)
        self.phase_zero.setWrapping(True)   # full cycle: 360 wraps back to 0
        self.phase_zero.valueChanged.connect(self._live_update)
        grid.addWidget(self.phase_zero, 1, 1)
        grid.addWidget(self._label('First order (rad/x)'), 2, 0)
        self.phase_first = self._dspin(-1e6, 1e6, 6, 0.0, step=0.001)
        self.phase_first.valueChanged.connect(self._live_update)
        grid.addWidget(self.phase_first, 2, 1)
        grid.addWidget(self._label('Second order (rad/x²)'), 3, 0)
        self.phase_second = self._dspin(-1e6, 1e6, 6, 0.0, step=0.0001)
        self.phase_second.valueChanged.connect(self._live_update)
        grid.addWidget(self.phase_second, 3, 1)
        btn = QPushButton('Apply phase correction')
        btn.setStyleSheet(BUTTON_STYLE)
        btn.clicked.connect(self.do_phase)
        grid.addWidget(btn, 4, 0, 1, 2)
        grid.setRowStretch(5, 1)
        return w

    def _build_fft_tab(self):
        w = QWidget(); grid = QGridLayout(w)
        grid.addWidget(self._label('Transform axis'), 0, 0)
        self.fft_axis = self._combo(['X (within trace)', 'Y (indirect)'])
        self.fft_axis.currentIndexChanged.connect(self._live_update)
        grid.addWidget(self.fft_axis, 0, 1)

        grid.addWidget(self._label('Window'), 1, 0)
        self.fft_window = self._combo(WINDOWS)
        grid.addWidget(self.fft_window, 1, 1)
        self.fft_winparam_label = self._label('Window param')
        grid.addWidget(self.fft_winparam_label, 2, 0)
        self.fft_winparam = self._dspin(0.0, 100.0, 2, 8.6)
        grid.addWidget(self.fft_winparam, 2, 1)
        self.fft_window.currentIndexChanged.connect(self._update_winparam)
        self.fft_window.currentIndexChanged.connect(self._live_update)
        self.fft_winparam.valueChanged.connect(self._live_update)
        self._update_winparam()

        grid.addWidget(self._label('Echo center (skip pts)'), 3, 0)
        skip_row = QHBoxLayout()
        self.fft_skip = QSpinBox(); self.fft_skip.setStyleSheet(SPIN_STYLE)
        self.fft_skip.setRange(0, 1000000)
        self.fft_skip.valueChanged.connect(self._live_update)
        btn_auto = QPushButton('Auto')
        btn_auto.setStyleSheet(BUTTON_STYLE)
        btn_auto.clicked.connect(self.auto_echo_center)
        skip_row.addWidget(self.fft_skip); skip_row.addWidget(btn_auto)
        grid.addLayout(skip_row, 3, 1)

        grid.addWidget(self._label('Zero fill'), 4, 0)
        self.fft_zerofill = self._combo(ZEROFILL)
        self.fft_zerofill.setCurrentText('×2')
        self.fft_zerofill.currentIndexChanged.connect(self._live_update)
        grid.addWidget(self.fft_zerofill, 4, 1)

        grid.addWidget(self._note('Complex FFT of I+iQ along the chosen axis; that '
                                  'axis becomes frequency. ns → MHz. Skip pts drops '
                                  'leading points so the transform starts at the echo '
                                  'centre (removes the dead-time first-order phase).'),
                       5, 0, 1, 2)
        btn = QPushButton('Compute FFT')
        btn.setStyleSheet(BUTTON_STYLE)
        btn.clicked.connect(self.do_fft)
        grid.addWidget(btn, 6, 0, 1, 2)
        grid.setRowStretch(7, 1)
        return w

    def _update_winparam(self, *args):
        cfg = WINDOW_PARAM.get(self.fft_window.currentText())
        self.fft_winparam.blockSignals(True)
        if cfg is not None:
            txt, lo, hi, dec, default, step = cfg
            self.fft_winparam_label.setText(txt)
            self.fft_winparam.setEnabled(True)
            self.fft_winparam.setDecimals(dec)
            self.fft_winparam.setRange(lo, hi)
            self.fft_winparam.setSingleStep(step)
            self.fft_winparam.setValue(default)
        else:
            self.fft_winparam_label.setText('Window param')
            self.fft_winparam.setEnabled(False)
        self.fft_winparam.blockSignals(False)

    # ------------------------------------------------------------- loading
    def open_iq(self):
        path = self.opener.open_file_dialog(multiprocessing=True)
        if not path or path == 'None':
            return
        try:
            i = np.atleast_2d(np.genfromtxt(path, delimiter=','))
            base = path[:-4] if path.lower().endswith('.csv') else path
            qpath = base + '_1.csv'
            if os.path.isfile(qpath):
                q = np.atleast_2d(np.genfromtxt(qpath, delimiter=','))
                qmsg = os.path.basename(qpath)
            else:
                q = np.zeros_like(i)
                qmsg = 'no _1 file (Q = 0)'
            if self.transpose_check.isChecked():
                i, q = i.T, q.T
            if i.shape != q.shape or min(i.shape) < 2:
                self.set_status('I and Q must be matching 2D matrices (≥ 2×2).')
                return
            self.raw_i, self.raw_q = i, q
            self.reset_to_raw()
            self.set_status(f'Loaded I={os.path.basename(path)}, Q={qmsg} '
                            f'(matrix {i.shape[0]}×{i.shape[1]} [traces × points]).')
        except Exception as e:
            self.set_status(f'Could not read I/Q: {e}')

    def _raw_axes(self):
        return (self._axis(self.x0_spin.value(), self.dx_spin.value(),
                           self.xname_edit.text(), self.xscale_edit.text()),
                self._axis(self.y0_spin.value(), self.dy_spin.value(),
                           self.yname_edit.text(), self.yscale_edit.text()))

    def on_axes_changed(self, *args):
        if self.raw_i is None:
            return
        # start / step edits redefine the raw geometry; restart the chain from raw
        self.reset_to_raw()

    def _relabel_axis(self, ax, name, scale):
        """Update an axis dict's title/unit in place, unless it is operation-owned
        (e.g. an FFT frequency axis)."""
        if ax is not None and not ax.get('auto'):
            ax['name'] = name
            ax['scale'] = scale

    def on_axis_labels_changed(self, *args):
        """Title / unit edit: relabel the current plot in place (X field -> the
        within-trace/col axis, Y field -> the indirect/row axis) without dropping
        the result; frequency axes created by an FFT keep their auto label."""
        if self.raw_i is None:
            return
        xn, xs = self.xname_edit.text(), self.xscale_edit.text()
        yn, ys = self.yname_edit.text(), self.yscale_edit.text()
        self._relabel_axis(self.src_col, xn, xs)
        self._relabel_axis(self.src_row, yn, ys)
        if self.has_result():
            self._relabel_axis(self.res_col, xn, xs)
            self._relabel_axis(self.res_row, yn, ys)
            self._push(self.res_i, self.res_q, self.res_col, self.res_row,
                       self.res_frames)
        else:
            self._push(self.src_i, self.src_q, self.src_col, self.src_row,
                       ('I', 'Q'))

    # ---------------------------------------------------------- live update
    def _live_update(self, *args):
        if self._suppress_live or not self.live_check.isChecked() or self.src_i is None:
            return
        {0: self.do_phase, 1: self.do_fft}[self.tabs.currentIndex()]()

    def _apply_current_op(self):
        if self.src_i is None:
            self.set_status('Open an I/Q dataset first.')
            return
        {0: self.do_phase, 1: self.do_fft}[self.tabs.currentIndex()]()

    # ------------------------------------------------------------- result
    def has_result(self):
        return self.res_i is not None

    def _set_result(self, i, q, col, row, frames, meta):
        self.res_i, self.res_q = np.asarray(i, float), np.asarray(q, float)
        self.res_col, self.res_row = col, row
        self.res_frames = frames
        self.res_meta = list(meta)
        self._push(self.res_i, self.res_q, col, row, frames)

    def reset_to_raw(self):
        if self.raw_i is None:
            return
        self.src_i, self.src_q = self.raw_i.copy(), self.raw_q.copy()
        self.src_col, self.src_row = self._raw_axes()
        self.res_i = self.res_q = None
        self._push(self.src_i, self.src_q, self.src_col, self.src_row, ('I', 'Q'))
        self.set_status('Showing raw I/Q.')

    def promote_result(self):
        if not self.has_result():
            self.set_status('No result to chain — apply an operation first.')
            return
        self.src_i, self.src_q = self.res_i.copy(), self.res_q.copy()
        self.src_col, self.src_row = self.res_col, self.res_row
        self.res_i = self.res_q = None
        self._suppress_live = True
        try:
            self._push(self.src_i, self.src_q, self.src_col, self.src_row,
                       ('Re', 'Im'))
        finally:
            self._suppress_live = False
        self.set_status('Result registered as the new input; apply the next op.')

    def clear_all(self):
        self.raw_i = self.raw_q = self.src_i = self.src_q = None
        self.res_i = self.res_q = None
        self.set_status('Cleared. Open an I/Q 2D dataset.')

    # --------------------------------------------------------------- push
    def _push_current(self, *args):
        if self.has_result():
            self._push(self.res_i, self.res_q, self.res_col, self.res_row,
                       self.res_frames)
        elif self.src_i is not None:
            self._push(self.src_i, self.src_q, self.src_col, self.src_row,
                       ('I', 'Q'))

    def _push(self, i, q, col, row, frames):
        """Push a complex 2D dataset to the main GUI as a (2, nX, nY) frame array
        (frame 0 = real/I, frame 1 = imag/Q) so its cross-section dock shows it."""
        name = self.name_edit.text().strip() or 'FT Data 2D'
        # internal layout is [trace(row), point(col)]; transpose so columns
        # become the X axis (matches general.plot_2d start_step ((x..),(y..))).
        arr = np.array([np.transpose(np.asarray(i, float)),
                        np.transpose(np.asarray(q, float))])
        try:
            general.plot_2d(name, arr,
                            start_step=((col['start'], col['step']),
                                        (row['start'], row['step'])),
                            xname=col['name'], xscale=col['scale'],
                            yname=row['name'], yscale=row['scale'],
                            zname='Intensity', zscale='V')
        except Exception as e:
            self.set_status(f'Could not plot to GUI: {e}')

    def set_status(self, text):
        self.status.setText(text)
        general.message(text)

    # ---------------------------------------------------------- operations
    def do_phase(self):
        if self.src_i is None:
            self.set_status('Open an I/Q dataset first.')
            return
        ncols = self.src_i.shape[1]
        axisx = self.src_col['start'] + self.src_col['step']*np.arange(ncols)
        c1 = float(self.phase_zero.value())*np.pi/180.0
        c2 = float(self.phase_first.value())
        c3 = float(self.phase_second.value())
        ph = np.exp(1j*(c1 + c2*axisx + c3*axisx*axisx))
        Z = (self.src_i + 1j*self.src_q)*ph[None, :]
        meta = ['Phase correction along X',
                f'zero = {self.phase_zero.value():.4g} deg, '
                f'first = {c2:.6g} rad/x, second = {c3:.6g} rad/x^2']
        self._set_result(Z.real, Z.imag, self.src_col, self.src_row,
                         ('Re', 'Im'), meta)
        self.set_status('Phase correction applied.')

    def _freq_axis(self, n, step, scale):
        """Frequency axis + unit for an FFT of `n` points with the given sample
        step/unit. ns/us → MHz (phase_cor convention); s → Hz; else 1/unit."""
        s = scale.strip().lower()
        if s in ('ns',):
            d, funit = step*1e-3, 'MHz'
        elif s in ('us', 'µs', 'μs'):
            d, funit = step, 'MHz'
        elif s in ('ms',):
            d, funit = step*1e3, 'MHz'
        elif s in ('s',):
            d, funit = step, 'Hz'
        else:
            d, funit = step, f'1/{scale}'
        if d == 0:
            d = 1.0
        fr = np.fft.fftshift(np.fft.fftfreq(int(n), d))
        return fr, funit

    def auto_echo_center(self):
        """Fill 'skip pts' with the echo centre along the transform axis: the
        peak of the |I+iQ| envelope, averaged over the other (non-transform)
        axis so the field-offset modulation cancels."""
        if self.src_i is None:
            self.set_status('Open an I/Q dataset first.')
            return
        along_x = (self.fft_axis.currentIndex() == 0)
        axis = 1 if along_x else 0
        mag = np.sqrt(self.src_i**2 + self.src_q**2)
        profile = mag.mean(axis=1 - axis)   # collapse the non-transform axis
        k = sigproc.echo_center(profile)
        self.fft_skip.setValue(int(k))
        self.set_status(f'Echo centre at point {k} along '
                        f'{"X" if along_x else "Y"} (skip set).')

    def do_fft(self):
        if self.src_i is None:
            self.set_status('Open an I/Q dataset first.')
            return
        along_x = (self.fft_axis.currentIndex() == 0)
        axis = 1 if along_x else 0
        src_ax = self.src_col if along_x else self.src_row
        # drop leading points so the transform starts at the echo centre; this
        # sets t = 0 there and removes the dead-time first-order phase ramp.
        skip = max(0, min(int(self.fft_skip.value()), self.src_i.shape[axis] - 2))
        sl = [slice(None), slice(None)]; sl[axis] = slice(skip, None)
        src_i = self.src_i[tuple(sl)]; src_q = self.src_q[tuple(sl)]
        n0 = src_i.shape[axis]
        win = sigproc.apodization_window(
            n0, self.fft_window.currentText(),
            self.fft_winparam.value()
            if self.fft_window.currentText() in WINDOW_PARAM else 8.6)
        shape = [1, 1]; shape[axis] = n0
        Z = (src_i + 1j*src_q)*win.reshape(shape)
        n = sigproc.zerofill_length(n0, self.fft_zerofill.currentText())
        sp = np.fft.fftshift(np.fft.fft(Z, n=n, axis=axis), axes=axis)
        fr, funit = self._freq_axis(n, src_ax['step'], src_ax['scale'])
        df = float(fr[1] - fr[0]) if n > 1 else 1.0
        freq_ax = self._axis(float(fr[0]), df, 'Frequency Offset', funit, auto=True)
        if along_x:
            res_col, res_row = freq_ax, self.src_row
        else:
            res_col, res_row = self.src_col, freq_ax
        meta = [f'FFT along {"X (within trace)" if along_x else "Y (indirect)"}',
                f'skip {skip} leading pts (echo centre)' if skip else 'no leading skip',
                f'window: {self.fft_window.currentText()}, '
                f'points {n0} -> {n} (zero fill {self.fft_zerofill.currentText()})',
                f'frequency in {funit}']
        self._set_result(sp.real, sp.imag, res_col, res_row, ('Re', 'Im'), meta)
        self.set_status(f'FFT along {"X" if along_x else "Y"}; skip {skip}; '
                        f'{n0}→{n} pts.')

    # -------------------------------------------------------------- output
    def save_result(self):
        if not (self.has_result() or self.src_i is not None):
            self.set_status('Nothing to save — load data first.')
            return
        file_path = self.opener.create_file_dialog(multiprocessing=True)
        if not file_path or file_path == 'None':
            return
        if self.has_result():
            i, q, col, row, meta = (self.res_i, self.res_q, self.res_col,
                                    self.res_row, self.res_meta)
        else:
            i, q, col, row, meta = (self.src_i, self.src_q, self.src_col,
                                    self.src_row, ['Raw I/Q'])
        # save_data writes a (2, nX, nY) array as name.csv (real) + name_1.csv
        # (imag), each transposed back to [trace, point] — the load format.
        arr = np.array([np.transpose(i), np.transpose(q)])
        header = '\n'.join(meta + [
            f'X ({col["name"]}/{col["scale"]}): start {col["start"]:.6g} step {col["step"]:.6g}',
            f'Y ({row["name"]}/{row["scale"]}): start {row["start"]:.6g} step {row["step"]:.6g}',
            'channel 0 = real/I (this file), channel 1 = imag/Q (_1 file)'])
        self.opener.save_data(file_path, arr, header=header, mode='w')
        self.set_status(f'Saved I/Q to {os.path.basename(file_path)} (+ _1).')


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
