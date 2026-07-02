#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Data Treatment control-center window.

Standalone QProcess launched from the "EPR Endstation Control" tab. It loads a
1D dataset either from a CSV file (Saver_Opener.open_1d) or from the curves
currently shown in the main GUI (via the libs/treatment_buffer.csv bridge that
the plot sidebar writes), lets the user fit / FFT / phase-correct / smooth it,
then push the result to LivePlot (general.plot_1d) and/or save it to CSV.

The window has its own embedded pyqtgraph preview for live, in-process display:
source curves and the current result are drawn there with smooth setData updates
(no cross-process IPC), so dragging a spinbox while live-update is on stays
responsive. Pushing to the main GUI is done only on demand via "Plot to GUI" —
opened data is never auto-duplicated into the main window's docks.

Operations can run on a single channel or on an I/Q pair (the "I/Q pair" box).
In pair mode an FFT becomes a complex transform and smoothing/baseline is
applied to both channels, so chains like baseline -> FFT -> phase keep both
channels all the way through. Results carrying two channels (e.g. FFT real +
imaginary) feed straight back in via "Result -> input".
"""

import os
import re
import sys
import shutil
import tempfile
import numpy as np
from pathlib import Path

import pyqtgraph as pg
from pyqtgraph.dockarea import DockArea
from PyQt6.QtCore import Qt, QProcess, QUrl
from PyQt6.QtGui import QIcon, QDesktopServices
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QComboBox, QGridLayout, QVBoxLayout, QHBoxLayout, QTabWidget, QDoubleSpinBox,
    QSpinBox, QLineEdit, QCheckBox, QFrame, QSizePolicy, QScrollArea)

import atomize.general_modules.general_functions as general
import atomize.general_modules.csv_opener_saver as openfile
import atomize.general_modules.bruker_opener as bruker
import atomize.math_modules.least_square_fitting_modules as fitting
import atomize.math_modules.signal_processing as sigproc
import atomize.math_modules.fft as fft_module
# Reuse the main-window plot stack so the embedded preview behaves identically
# to the main UI (crosshair, Shift-drag ruler, FFT/log right-click toggles).
from atomize.main.widgets import CrosshairPlotWidget, CloseableDock

# Shared dark-theme palette / widget styles (single source of truth across all
# control-center tools). apply_app_style() pins this process to the Fusion style
# so QComboBox / QSpinBox / QLineEdit render identically on Linux and Windows.
from atomize.general_modules.gui_style import (apply_app_style,
    BG, FG, ACCENT, BUTTON_STYLE, LABEL_STYLE, DSPIN_STYLE, SPIN_STYLE,
    COMBO_STYLE, LINEEDIT_STYLE, CHECKBOX_STYLE, SCROLL_STYLE, TAB_STYLE)

# Path to the buffer file that the main-window plot sidebar writes selected
# curves into (same libs/ runtime-IPC convention as the .param files).
BUFFER_PATH = str(Path(__file__).resolve().parent.parent.parent / 'libs' / 'treatment_buffer.csv')

# remembers the folder of the last file opened/saved here so the next dialog
# starts there — shared with the 2D tool (one working data folder), survives a
# window relaunch (each tool is its own short-lived QProcess). libs/ runtime IPC.
LASTDIR_PATH = str(Path(__file__).resolve().parent.parent.parent / 'libs' / 'treatment_lastdir.txt')


def _load_last_dir():
    try:
        with open(LASTDIR_PATH, 'r', errors='ignore') as fh:
            d = fh.read().strip()
        return d if d and os.path.isdir(d) else ''
    except Exception:
        return ''


def _save_last_dir(path):
    try:
        d = path if os.path.isdir(path) else os.path.dirname(path)
        if d:
            with open(LASTDIR_PATH, 'w') as fh:
                fh.write(d)
    except Exception:
        pass


# Bare SI units worth auto-prefixing on the X axis: a plain 's' axis (e.g. a 2D
# slice transferred in seconds) should read '2 ns', not '2e-9 s'. Already-prefixed
# units ('ns', 'MHz') and dimensionless labels stay verbatim (no 'kns').
SI_BASE_UNITS = {'s', 'hz', 'v', 'a', 'g', 't', 'k', 'm', 'ev'}


def _si_autoprefix(unit):
    """True if `unit` is a bare SI base worth pyqtgraph auto-prefixing."""
    return str(unit).strip().lower() in SI_BASE_UNITS


def _split_unit(label):
    """Split a 'Name (unit)' axis label into ('Name', 'unit'); ('label', '') if
    there's no trailing parenthesised unit."""
    s = str(label).strip()
    if s.endswith(')') and '(' in s:
        i = s.rfind('(')
        return s[:i].strip(), s[i + 1:-1].strip()
    return s, ''


# Solid-accent "busy" variant for a button while a long operation is in
# progress (explicit colours so it stays yellow even while disabled).
BUTTON_BUSY_STYLE = (
    f"QPushButton {{border-radius: 4px; background-color: {ACCENT}; "
    f"border-style: inset; color: {BG}; font-weight: bold; padding: 4px; }} "
    f"QPushButton:disabled {{background-color: {ACCENT}; color: {BG}; }}")


def _html_table(headers, rows):
    """Compact HTML table (Qt rich-text) from a header list and a list of cell-
    string rows; used for the info / fit-result panels."""
    head = ''.join(f'<th style="padding:1px 8px;">{h}</th>' for h in headers)
    body = ''.join('<tr>' + ''.join(f'<td style="padding:1px 8px;">{c}</td>'
                                    for c in r) + '</tr>' for r in rows)
    return f'<table style="border-collapse:collapse;"><tr>{head}</tr>{body}</table>'


class MainWindow(QMainWindow):

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        if len(sys.argv) > 1:
            self.test_flag = sys.argv[1]
        else:
            self.test_flag = 'None'

        self.opener = openfile.Saver_Opener()
        self.bruker = bruker.Bruker_Opener()
        self.fitter = fitting.math()
        self.sp = sigproc.Signal_Processing()
        self.fft = fft_module.Fast_Fourier()

        # name -> {channel label: (x, y)} for every loaded file/trace; the trace
        # selector picks one as active and self.datasets references its channels
        # (so derived/promoted channels persist per trace)
        self.traces = {}
        # label -> (x, y) of the *active* trace's source curves
        self.datasets = {}

        # Current result. A result has a shared x-axis and one or two channels
        # (e.g. FFT real + imaginary, or I/Q after smoothing).
        self.result_x = None
        self.result_channels = []      # list of (label, y-array)
        self.result_xname = 'X'        # axis name pushed to the preview dock
        self.result_show_source = True # overlay the source (same x-domain)?
        # description lines written into the CSV header on save
        self.result_meta = []

        # counter for naming chained "Result -> input" steps uniquely
        self.step_counter = 0
        self.fit_table = None              # last 'Fit all traces' parameter table
        # persistent preview curves: label -> pyqtgraph PlotDataItem, reused via
        # setData so live updates never tear down / rebuild plot items
        self._curve_items = {}
        # identity of what is currently plotted (curve labels + x-axis name); a
        # change means a new result / view / unit, which re-fits the axes once.
        self._plot_key = None
        # set while promoting a result so selecting the new input does not
        # immediately re-apply the operation to it
        self._suppress_live = False
        self.last_dir = _load_last_dir()   # start file dialogs in the last folder

        self.design()
        self.load_from_buffer(silent=True)

    # ----------------------------------------------------------------- UI
    def design(self):
        self.setWindowTitle('Data Treatment')
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 'gui', 'icon_temp.png')
        self.setWindowIcon(QIcon(icon_path))
        self.setMinimumHeight(720)
        self.setMinimumWidth(1040)
        self.resize(1160, 800)
        # background on the QMainWindow (as in awg_phasing_insys.py) rather than
        # the central widget, so spinboxes keep their full native frame.
        self.setStyleSheet(f"background-color: {BG};")
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        # ---- Left: embedded live preview (in-process, smooth) ----
        # Same plot stack as the main UI (atomize/main/widgets.py): a
        # CrosshairPlotWidget inside a CloseableDock/DockArea, so the preview
        # shares the crosshair, Shift-drag ruler and FFT/log right-click
        # toggles. The dock can float, but its close button is hidden — the
        # preview is the window's only plot and must not be dismissable.
        pg.setConfigOptions(antialias=True)
        self.plot_area = DockArea()
        self.plot_widget = CrosshairPlotWidget()
        # no setBackground: inherit pyqtgraph's global background (63,63,97, set
        # in atomize/main/widgets.py) so 1D matches the 2D CrossSectionDock.
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.legend = self.plot_widget.addLegend()
        self.plot_dock = CloseableDock(name='Preview', widget=self.plot_widget)
        self.plot_dock.close_button.hide()
        self.plot_area.addDock(self.plot_dock)
        root.addWidget(self.plot_area, stretch=3)

        # ---- Vertical separator between graph and controls ----
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setStyleSheet('color: rgb(83, 83, 117);')
        root.addWidget(sep)

        # ---- Right: controls ----
        panel = QVBoxLayout()
        root.addLayout(panel, stretch=2)

        # ---- Source group ----
        panel.addWidget(self._heading('Source'))
        src_row = QHBoxLayout()
        btn_open = QPushButton('Open CSV…')
        btn_open.setStyleSheet(BUTTON_STYLE)
        btn_open.clicked.connect(self.open_csv)
        btn_bruker = QPushButton('Open Bruker…')
        btn_bruker.setStyleSheet(BUTTON_STYLE)
        btn_bruker.clicked.connect(self.open_bruker)
        btn_buf = QPushButton('Load from plot')
        btn_buf.setStyleSheet(BUTTON_STYLE)
        btn_buf.clicked.connect(lambda: self.load_from_buffer(silent=False))
        btn_clear = QPushButton('Clear')
        btn_clear.setStyleSheet(BUTTON_STYLE)
        btn_clear.clicked.connect(self.clear_all)
        src_row.addWidget(btn_open)
        src_row.addWidget(btn_bruker)
        src_row.addWidget(btn_buf)
        src_row.addWidget(btn_clear)
        panel.addLayout(src_row)

        # trace selector: each opened file (or plot load) is one trace; the combo
        # picks which one is active and feeds the channel selectors / operations.
        trace_row = QHBoxLayout()
        trace_row.addWidget(self._label('Trace'))
        self.trace_combo = QComboBox()
        self.trace_combo.setStyleSheet(COMBO_STYLE)
        self.trace_combo.setToolTip('Active trace. Open several files to compare; '
                                    'each becomes a selectable trace here. Promoted '
                                    'result channels stay with their trace.')
        self.trace_combo.currentIndexChanged.connect(self._activate_trace)
        trace_row.addWidget(self.trace_combo, 1)
        self.trace_remove_btn = QPushButton('Remove')
        self.trace_remove_btn.setStyleSheet(BUTTON_STYLE)
        self.trace_remove_btn.setToolTip('Remove the active trace from the list.')
        self.trace_remove_btn.clicked.connect(self._remove_trace)
        trace_row.addWidget(self.trace_remove_btn)
        panel.addLayout(trace_row)

        # Name of the dataset currently loaded (file basename, or 'Loaded from
        # plot' for the in-memory buffer). Kept on its own line so a long path
        # wraps instead of stretching the panel.
        self.loaded_label = QLabel('File: —')
        self.loaded_label.setStyleSheet(LABEL_STYLE)
        self.loaded_label.setWordWrap(True)
        panel.addWidget(self.loaded_label)

        ch_grid = QGridLayout()
        ch_grid.addWidget(self._label('I / primary channel'), 0, 0)
        self.i_combo = QComboBox()
        self.i_combo.setStyleSheet(COMBO_STYLE)
        self.i_combo.currentIndexChanged.connect(self.on_source_changed)
        ch_grid.addWidget(self.i_combo, 0, 1)
        ch_grid.addWidget(self._label('Q channel'), 1, 0)
        self.q_combo = QComboBox()
        self.q_combo.setStyleSheet(COMBO_STYLE)
        self.q_combo.currentIndexChanged.connect(self.on_source_changed)
        ch_grid.addWidget(self.q_combo, 1, 1)
        panel.addLayout(ch_grid)

        self.pair_check = QCheckBox('I/Q pair (run FFT / smoothing on both channels)')
        self.pair_check.setStyleSheet(CHECKBOX_STYLE)
        self.pair_check.stateChanged.connect(self.on_source_changed)
        # block the signal for the initial state: the rest of the UI (xname_edit,
        # plot) is not built yet, so an on_source_changed -> redraw here would fail
        self.pair_check.blockSignals(True)
        self.pair_check.setChecked(True)
        self.pair_check.blockSignals(False)
        panel.addWidget(self.pair_check)

        # X axis name (preview label / plot xname / CSV header for time-domain results)
        xn_row = QHBoxLayout()
        xn_row.addWidget(self._label('X axis name'))
        self.xname_edit = QLineEdit('X')
        self.xname_edit.setStyleSheet(LINEEDIT_STYLE)
        self.xname_edit.textChanged.connect(lambda *_: self.redraw())
        xn_row.addWidget(self.xname_edit)
        panel.addLayout(xn_row)

        self.live_check = QCheckBox('Live update on parameter change')
        self.live_check.setStyleSheet(CHECKBOX_STYLE)
        #self.live_check.setChecked(True)
        panel.addWidget(self.live_check)

        panel.addWidget(self._hline())

        # ---- Operation tabs (the largest block) ----
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(TAB_STYLE)
        self.tabs.addTab(self._build_fit_tab(), 'Fit')
        self.tabs.addTab(self._build_fft_tab(), 'FFT')
        self.tabs.addTab(self._build_phase_tab(), 'Phase')
        self.tabs.addTab(self._build_smooth_tab(), 'Smooth / Baseline')
        self.tabs.addTab(self._build_filter_tab(), 'Filter')
        # Note: tab changes deliberately do NOT trigger _live_update. Re-running
        # the new tab's op on switch is redundant and, after a "Result → input"
        # chain, would re-transform an already-transformed input (e.g. FFT of an
        # FFT). The preview recomputes only on a parameter change or Apply.
        self.tabs.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        # Floor the tab strip at its full width so all tabs stay visible without
        # the scroll arrows (the 6 tabs need ~465 px); the graph takes the rest.
        self.tabs.setMinimumWidth(525)
        panel.addWidget(self.tabs, stretch=1)

        panel.addWidget(self._hline())

        # ---- Output group ----
        panel.addWidget(self._heading('Output'))
        self.name_edit = QLineEdit('treatment_result')
        self.name_edit.setStyleSheet(LINEEDIT_STYLE)
        panel.addWidget(self.name_edit)
        out_row = QHBoxLayout()
        btn_plot = QPushButton('Plot to GUI')
        btn_plot.setStyleSheet(BUTTON_STYLE)
        btn_plot.clicked.connect(self.plot_result)
        btn_save = QPushButton('Save CSV…')
        btn_save.setStyleSheet(BUTTON_STYLE)
        btn_save.clicked.connect(self.save_result)
        btn_chain = QPushButton('Result → input')
        btn_chain.setStyleSheet(BUTTON_STYLE)
        btn_chain.clicked.connect(self.promote_result)
        btn_undo = QPushButton('Undo step')
        btn_undo.setStyleSheet(BUTTON_STYLE)
        btn_undo.setToolTip('Remove the most recently promoted step channel(s) '
                            '(undo the last "Result → input") and reselect the '
                            'previous input.')
        btn_undo.clicked.connect(self.undo_step)
        btn_clear_res = QPushButton('Clear result')
        btn_clear_res.setStyleSheet(BUTTON_STYLE)
        btn_clear_res.clicked.connect(self.clear_result)
        out_row.addWidget(btn_plot)
        out_row.addWidget(btn_save)
        out_row.addWidget(btn_chain)
        out_row.addWidget(btn_undo)
        out_row.addWidget(btn_clear_res)
        panel.addLayout(out_row)

        # Hand the current curves off to Julia/Makie for a publication figure
        # (vector PDF). Shells out to script_examples/makie/render.jl via QProcess.
        # The mode selector picks what to draw: raw source, the result, or both
        # overlaid (raw + fit on the same axes).
        makie_row = QHBoxLayout()
        self.makie_mode = QComboBox()
        self.makie_mode.addItems(['Raw + result', 'Result only', 'Raw only'])
        self.makie_mode.setStyleSheet(COMBO_STYLE)
        self.makie_mode.setToolTip('What to draw: raw source data, the computed '
                                   'result, or both overlaid (e.g. fit over data).')
        self.makie_btn = QPushButton('Makie figure…')
        self.makie_btn.setStyleSheet(BUTTON_STYLE)
        self.makie_btn.setToolTip('Render the selected curves to a publication-quality '
                                  'PDF with Julia/Makie (first run precompiles).')
        self.makie_btn.clicked.connect(self.make_makie_figure)
        makie_row.addWidget(self.makie_mode)
        makie_row.addWidget(self.makie_btn)
        panel.addLayout(makie_row)

        self.status = QLabel('Load a dataset to begin.')
        self.status.setStyleSheet(LABEL_STYLE)
        self.status.setWordWrap(True)
        panel.addWidget(self.status)

        # +/- buttons on every spinbox (repo-wide convention); give spinboxes,
        # comboboxes and buttons a common minimum row height so they line up
        # Pin spinboxes to a fixed 26 px height (as in awg_phasing_insys.py) so
        # the native +/- frame renders fully; combos / buttons / line edits get
        # the same min height for row alignment.
        row_h = 26
        for wdg in self.findChildren((QComboBox, QPushButton)):
            wdg.setMinimumHeight(row_h)
        for spin in self.findChildren((QSpinBox, QDoubleSpinBox)):
            spin.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
            spin.setMinimumHeight(row_h)
        for le in self.findChildren((QLineEdit)):
            le.setMinimumHeight(21)

    def _hline(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setStyleSheet('color: rgb(83, 83, 117);')
        return line

    def _heading(self, text):
        lab = QLabel(text)
        lab.setStyleSheet(f"QLabel {{ color: {ACCENT}; font-weight: bold; font-size: 13px; }}")
        return lab

    def _label(self, text):
        lab = QLabel(text)
        lab.setStyleSheet(LABEL_STYLE)
        return lab

    def _note(self, text):
        """A wrapped, multi-line hint label with roomier line spacing."""
        lab = QLabel(f'<div style="line-height: 145%;">{text}</div>')
        lab.setStyleSheet(LABEL_STYLE)
        lab.setWordWrap(True)
        lab.setTextFormat(Qt.TextFormat.RichText)
        return lab

    def _build_fit_tab(self):
        w = QWidget()
        grid = QGridLayout(w)
        grid.addWidget(self._label('Model'), 0, 0)
        self.model_combo = QComboBox()
        self.model_combo.setStyleSheet(COMBO_STYLE)
        self.model_combo.addItems(self.fitter.model_names())
        self.model_combo.setCurrentText('Exponential')
        grid.addWidget(self.model_combo, 0, 1)
        # live equation of the selected model, so the user sees what is fitted
        self.fit_formula = QLabel('')
        self.fit_formula.setStyleSheet(LABEL_STYLE)
        self.fit_formula.setWordWrap(True)
        self.fit_formula.setTextFormat(Qt.TextFormat.RichText)
        self.model_combo.currentTextChanged.connect(self._update_fit_formula)
        grid.addWidget(self.fit_formula, 1, 0, 1, 2)
        self._update_fit_formula(self.model_combo.currentText())
        self.fit_no_offset = QCheckBox('Fix offset = 0 (drop the b / c baseline term)')
        self.fit_no_offset.setStyleSheet(CHECKBOX_STYLE)
        grid.addWidget(self.fit_no_offset, 2, 0, 1, 2)
        fit_btn_row = QHBoxLayout()
        btn = QPushButton('Fit')
        btn.setStyleSheet(BUTTON_STYLE)
        btn.clicked.connect(self.do_fit)
        self.fit_all_btn = QPushButton('Fit all traces')
        self.fit_all_btn.setStyleSheet(BUTTON_STYLE)
        self.fit_all_btn.setToolTip(
            'Fit the selected model to the I channel of every loaded trace, overlay '
            'the data + fits, and build a per-trace parameter table (Save table…).')
        self.fit_all_btn.clicked.connect(self.fit_all_traces)
        self.fit_save_table_btn = QPushButton('Save table…')
        self.fit_save_table_btn.setStyleSheet(BUTTON_STYLE)
        self.fit_save_table_btn.setToolTip('Save the per-trace fit parameters as CSV.')
        self.fit_save_table_btn.clicked.connect(self.save_fit_table)
        self.fit_save_table_btn.setEnabled(False)
        fit_btn_row.addWidget(btn)
        fit_btn_row.addWidget(self.fit_all_btn)
        fit_btn_row.addWidget(self.fit_save_table_btn)
        grid.addLayout(fit_btn_row, 3, 0, 1, 2)
        self.fit_result = QLabel('')
        self.fit_result.setStyleSheet(LABEL_STYLE)
        self.fit_result.setWordWrap(True)
        self.fit_result.setTextFormat(Qt.TextFormat.RichText)
        self.fit_result.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        # scroll the parameter readout (the ESEEM models list up to 12 params)
        fit_scroll = QScrollArea()
        fit_scroll.setStyleSheet(SCROLL_STYLE)
        fit_scroll.setWidgetResizable(True)
        fit_scroll.setWidget(self.fit_result)
        grid.addWidget(fit_scroll, 4, 0, 1, 2)
        grid.setRowStretch(4, 1)
        return w

    WINDOWS = ['None', 'Hann', 'Hamming', 'Blackman', 'Bartlett', 'Flat-top',
               'Kaiser', 'Gaussian', 'Tukey']
    FILTERS = ['None', 'Low-pass', 'High-pass', 'Band-pass']

    # parametric windows: name -> (label, min, max, decimals, default, step)
    WINDOW_PARAM = {
        'Kaiser':   ('Kaiser β', 0.0, 100.0, 2, 8.6, 0.5),
        'Gaussian': ('Gaussian σ (×N)', 0.01, 1.0, 3, 0.15, 0.01),
        'Tukey':    ('Tukey α', 0.0, 1.0, 3, 0.5, 0.05),
    }

    def _build_fft_tab(self):
        w = QWidget()
        grid = QGridLayout(w)

        grid.addWidget(self._label('Output'), 0, 0)
        self.fft_mode = QComboBox()
        self.fft_mode.setStyleSheet(COMBO_STYLE)
        self.fft_mode.addItems(['Magnitude', 'Real', 'Imaginary', 'Real + Imaginary'])
        self.fft_mode.currentIndexChanged.connect(self._live_update)
        grid.addWidget(self.fft_mode, 0, 1)

        grid.addWidget(self._label('Window'), 1, 0)
        self.fft_window = QComboBox()
        self.fft_window.setStyleSheet(COMBO_STYLE)
        self.fft_window.addItems(self.WINDOWS)
        # relabel/enable the parameter field first, then recompute
        self.fft_window.currentIndexChanged.connect(self._update_window_param)
        self.fft_window.currentIndexChanged.connect(self._live_update)
        grid.addWidget(self.fft_window, 1, 1)

        self.fft_winparam_label = self._label('Window param')
        grid.addWidget(self.fft_winparam_label, 2, 0)
        self.fft_winparam = QDoubleSpinBox()
        self.fft_winparam.setStyleSheet(DSPIN_STYLE)
        self.fft_winparam.setRange(0.0, 100.0)
        self.fft_winparam.setDecimals(2)
        self.fft_winparam.setValue(8.6)
        self.fft_winparam.setEnabled(False)   # 'None' is selected initially
        self.fft_winparam.valueChanged.connect(self._live_update)
        grid.addWidget(self.fft_winparam, 2, 1)

        grid.addWidget(self._label('Zero fill'), 3, 0)
        self.fft_zerofill = QComboBox()
        self.fft_zerofill.setStyleSheet(COMBO_STYLE)
        self.fft_zerofill.addItems(['None', '×2', '×4', '×8', 'Next pow₂'])
        self.fft_zerofill.setCurrentText('×4')
        self.fft_zerofill.currentIndexChanged.connect(self._live_update)
        grid.addWidget(self.fft_zerofill, 3, 1)

        grid.addWidget(self._label('Echo center (skip pts)'), 4, 0)
        skip_row = QHBoxLayout()
        self.fft_skip = QSpinBox()
        self.fft_skip.setStyleSheet(SPIN_STYLE)
        self.fft_skip.setRange(0, 1000000)
        self.fft_skip.setToolTip(
            'Number of leading <b>points</b> (samples, not time) to drop so the '
            'transform starts at the echo centre.')
        self.fft_skip.valueChanged.connect(self._live_update)
        btn_auto = QPushButton('Auto')
        btn_auto.setStyleSheet(BUTTON_STYLE)
        btn_auto.setToolTip(
            'Estimate the echo centre and fill "skip pts" with its <b>point '
            'index</b> (a sample number, not a time).<br><br>'
            'Found from the magnitude envelope |I+iQ| (I/Q pair) or |I|: the '
            'peak sample, refined by a centre-of-mass over the symmetric core '
            'around it (so a slow one-sided FID decay tail does not drag it off '
            'the peak).<br><br>'
            'Always sanity-check against the plot; type the point in by hand if '
            'a noisy record needs it.')
        btn_auto.clicked.connect(self.auto_echo_center)
        skip_row.addWidget(self.fft_skip); skip_row.addWidget(btn_auto)
        grid.addLayout(skip_row, 4, 1)

        grid.addWidget(self._label('Passband'), 5, 0)
        self.fft_filter = QComboBox()
        self.fft_filter.setStyleSheet(COMBO_STYLE)
        self.fft_filter.addItems(self.FILTERS)
        self.fft_filter.currentIndexChanged.connect(self._live_update)
        grid.addWidget(self.fft_filter, 5, 1)

        grid.addWidget(self._label('Low cutoff (×f_max)'), 6, 0)
        self.fft_cut_lo = QDoubleSpinBox()
        self.fft_cut_lo.setStyleSheet(DSPIN_STYLE)
        self.fft_cut_lo.setRange(0.0, 1.0)
        self.fft_cut_lo.setSingleStep(0.01)
        self.fft_cut_lo.setDecimals(4)
        self.fft_cut_lo.valueChanged.connect(self._live_update)
        grid.addWidget(self.fft_cut_lo, 6, 1)

        grid.addWidget(self._label('High cutoff (×f_max)'), 7, 0)
        self.fft_cut_hi = QDoubleSpinBox()
        self.fft_cut_hi.setStyleSheet(DSPIN_STYLE)
        self.fft_cut_hi.setRange(0.0, 1.0)
        self.fft_cut_hi.setSingleStep(0.01)
        self.fft_cut_hi.setDecimals(4)
        self.fft_cut_hi.setValue(1.0)
        self.fft_cut_hi.valueChanged.connect(self._live_update)
        grid.addWidget(self.fft_cut_hi, 7, 1)

        note = self._note('I/Q pair → complex FFT of I+iQ; otherwise FFT of I. '
                          'Window applied before transform; passband masks the spectrum. '
                          'Skip pts drops leading points so the transform starts at the '
                          'echo centre (removes the dead-time first-order phase).')
        grid.addWidget(note, 8, 0, 1, 2)

        btn = QPushButton('Compute FFT')
        btn.setStyleSheet(BUTTON_STYLE)
        btn.clicked.connect(self.do_fft)
        grid.addWidget(btn, 9, 0, 1, 2)
        grid.setRowStretch(10, 1)

        return w

    def _build_filter_tab(self):
        w = QWidget()
        grid = QGridLayout(w)

        note = self._note('FFT → zero the frequencies outside the passband → '
                          'inverse FFT. Output is the cleaned time-domain signal '
                          '(I/Q pair → both channels filtered together).')
        grid.addWidget(note, 0, 0, 1, 2)

        grid.addWidget(self._label('Type'), 1, 0)
        self.filt_type = QComboBox()
        self.filt_type.setStyleSheet(COMBO_STYLE)
        self.filt_type.addItems(['Low-pass', 'High-pass', 'Band-pass'])
        self.filt_type.currentIndexChanged.connect(self._live_update)
        grid.addWidget(self.filt_type, 1, 1)

        grid.addWidget(self._label('Low cutoff (×f_max)'), 2, 0)
        self.filt_cut_lo = QDoubleSpinBox()
        self.filt_cut_lo.setStyleSheet(DSPIN_STYLE)
        self.filt_cut_lo.setRange(0.0, 1.0)
        self.filt_cut_lo.setSingleStep(0.01)
        self.filt_cut_lo.setDecimals(4)
        self.filt_cut_lo.setValue(0.1)
        self.filt_cut_lo.valueChanged.connect(self._live_update)
        grid.addWidget(self.filt_cut_lo, 2, 1)

        grid.addWidget(self._label('High cutoff (×f_max)'), 3, 0)
        self.filt_cut_hi = QDoubleSpinBox()
        self.filt_cut_hi.setStyleSheet(DSPIN_STYLE)
        self.filt_cut_hi.setRange(0.0, 1.0)
        self.filt_cut_hi.setSingleStep(0.01)
        self.filt_cut_hi.setDecimals(4)
        self.filt_cut_hi.setValue(0.5)
        self.filt_cut_hi.valueChanged.connect(self._live_update)
        grid.addWidget(self.filt_cut_hi, 3, 1)

        hint = self._note('Low-pass uses High cutoff; High-pass uses Low cutoff; '
                          'Band-pass uses both. Cutoffs are fractions of the '
                          'maximum (Nyquist) frequency.')
        grid.addWidget(hint, 4, 0, 1, 2)

        btn = QPushButton('Apply filter')
        btn.setStyleSheet(BUTTON_STYLE)
        btn.clicked.connect(self.do_filter)
        grid.addWidget(btn, 5, 0, 1, 2)
        grid.setRowStretch(6, 1)
        return w

    def _build_phase_tab(self):
        w = QWidget()
        grid = QGridLayout(w)

        note = self._note('Uses the I and Q channels selected above. First/second '
                          'order are a frequency offset: 50 → 50 MHz when x is in ns '
                          '(coeff = 2π·value/1000 per x-unit).')
        grid.addWidget(note, 0, 0, 1, 2)

        grid.addWidget(self._label('Zero order (deg)'), 1, 0)
        self.phase_zero = QDoubleSpinBox()
        self.phase_zero.setStyleSheet(DSPIN_STYLE)
        self.phase_zero.setRange(0.0, 360.0)
        self.phase_zero.setDecimals(2)
        self.phase_zero.setSingleStep(0.5)
        self.phase_zero.setWrapping(True)   # full cycle: 360 wraps back to 0
        self.phase_zero.valueChanged.connect(self._live_update)
        ph0_row = QHBoxLayout()
        ph0_row.addWidget(self.phase_zero)
        btn_autoph = QPushButton('Auto')
        btn_autoph.setStyleSheet(BUTTON_STYLE)
        btn_autoph.setToolTip(
            'Zero-order auto-phase: rotate so the magnitude-weighted real part '
            'is maximal (φ₀ = −angle Σ|S|·S over the significant bins).<br><br>'
            'With "FFT first" on this works on the spectrum; otherwise on the '
            'time-domain I+iQ. Pair it with the FFT-tab skip-pts / echo '
            'centre, which removes the first-order phase ramp — leaving only '
            'this zero-order term. First/second order stay manual.')
        btn_autoph.clicked.connect(self.auto_phase_zero)
        ph0_row.addWidget(btn_autoph)
        grid.addLayout(ph0_row, 1, 1)

        grid.addWidget(self._label('First order (MHz @ ns)'), 2, 0)
        self.phase_first = QDoubleSpinBox()
        self.phase_first.setStyleSheet(DSPIN_STYLE)
        self.phase_first.setRange(-1e6, 1e6)
        self.phase_first.setDecimals(3)
        self.phase_first.setSingleStep(0.05)
        self.phase_first.valueChanged.connect(self._live_update)
        grid.addWidget(self.phase_first, 2, 1)

        grid.addWidget(self._label('Second order (MHz @ ns)'), 3, 0)
        self.phase_second = QDoubleSpinBox()
        self.phase_second.setStyleSheet(DSPIN_STYLE)
        self.phase_second.setRange(-1e6, 1e6)
        self.phase_second.setDecimals(4)
        self.phase_second.setSingleStep(0.001)
        self.phase_second.valueChanged.connect(self._live_update)
        grid.addWidget(self.phase_second, 3, 1)

        self.phase_fft = QCheckBox('FFT first (phase in frequency domain)')
        self.phase_fft.setStyleSheet(CHECKBOX_STYLE)
        self.phase_fft.stateChanged.connect(self._live_update)
        grid.addWidget(self.phase_fft, 4, 0, 1, 2)

        grid.addWidget(self._label('Zero fill (FFT first)'), 5, 0)
        self.phase_zerofill = QComboBox()
        self.phase_zerofill.setStyleSheet(COMBO_STYLE)
        self.phase_zerofill.addItems(['None', '×2', '×4', '×8', 'Next pow₂'])
        self.phase_zerofill.setCurrentText('×4')
        self.phase_zerofill.currentIndexChanged.connect(self._live_update)
        grid.addWidget(self.phase_zerofill, 5, 1)

        grid.addWidget(self._label('Output'), 6, 0)
        self.phase_out = QComboBox()
        self.phase_out.setStyleSheet(COMBO_STYLE)
        self.phase_out.addItems(['Real', 'Imaginary', 'Magnitude', 'Real + Imaginary'])
        # default to the full complex result so phasing an I/Q pair keeps the pair:
        # both channels are shown and carried forward by Result -> Input
        self.phase_out.setCurrentText('Real + Imaginary')
        self.phase_out.currentIndexChanged.connect(self._live_update)
        grid.addWidget(self.phase_out, 6, 1)

        btn = QPushButton('Apply phase correction')
        btn.setStyleSheet(BUTTON_STYLE)
        btn.clicked.connect(self.do_phase)
        grid.addWidget(btn, 7, 0, 1, 2)
        grid.setRowStretch(8, 1)
        return w

    def _build_smooth_tab(self):
        w = QWidget()
        grid = QGridLayout(w)
        grid.addWidget(self._label('Method'), 0, 0)
        self.smooth_method = QComboBox()
        self.smooth_method.setStyleSheet(COMBO_STYLE)
        self.smooth_method.addItems(['Savitzky-Golay', 'Moving average',
            'Baseline subtract', 'Normalize'])
        self.smooth_method.setCurrentText('Baseline subtract')
        self.smooth_method.currentIndexChanged.connect(self._live_update)
        grid.addWidget(self.smooth_method, 0, 1)

        grid.addWidget(self._label('Window / order'), 1, 0)
        self.smooth_window = QSpinBox()
        self.smooth_window.setStyleSheet(SPIN_STYLE)
        self.smooth_window.setRange(1, 99999)
        self.smooth_window.setValue(11)
        self.smooth_window.valueChanged.connect(self._live_update)
        grid.addWidget(self.smooth_window, 1, 1)

        grid.addWidget(self._label('Poly order'), 2, 0)
        self.smooth_order = QSpinBox()
        self.smooth_order.setStyleSheet(SPIN_STYLE)
        self.smooth_order.setRange(0, 20)
        self.smooth_order.setValue(3)
        self.smooth_order.valueChanged.connect(self._live_update)
        grid.addWidget(self.smooth_order, 2, 1)

        grid.addWidget(self._label('Baseline from'), 3, 0)
        self.base_region = QComboBox()
        self.base_region.setStyleSheet(COMBO_STYLE)
        self.base_region.addItems(['All points', 'First N points', 'Last N points',
                                   'First & last N'])
        self.base_region.currentIndexChanged.connect(self._live_update)
        grid.addWidget(self.base_region, 3, 1)

        grid.addWidget(self._label('N points'), 4, 0)
        self.base_npts = QSpinBox()
        self.base_npts.setStyleSheet(SPIN_STYLE)
        self.base_npts.setRange(1, 99999)
        self.base_npts.setValue(20)
        self.base_npts.valueChanged.connect(self._live_update)
        grid.addWidget(self.base_npts, 4, 1)

        note = self._note('I/Q pair → applied to both channels. "Baseline from" '
                          'fits the baseline using only the chosen end points.')
        grid.addWidget(note, 5, 0, 1, 2)

        btn = QPushButton('Apply')
        btn.setStyleSheet(BUTTON_STYLE)
        btn.clicked.connect(self.do_smooth)
        grid.addWidget(btn, 6, 0, 1, 2)
        grid.setRowStretch(7, 1)
        return w

    # ------------------------------------------------------------- loading
    def _unique_trace_name(self, name):
        """A trace name not already in use (append (2), (3), … on collision)."""
        name = name or 'trace'
        if name not in self.traces:
            return name
        i = 2
        while f'{name} ({i})' in self.traces:
            i += 1
        return f'{name} ({i})'

    def _add_traces(self, items):
        """Register one or more (name, channel-mapping) traces and make the last
        one active. `items` is a list of (name, {label: (x, y)})."""
        added = []
        for name, mapping in items:
            if not mapping:
                continue
            uname = self._unique_trace_name(name)
            self.traces[uname] = dict(mapping)
            added.append(uname)
        if not added:
            return
        self.trace_combo.blockSignals(True)
        self.trace_combo.addItems(added)
        self.trace_combo.setCurrentIndex(self.trace_combo.count() - 1)
        self.trace_combo.blockSignals(False)
        self._activate_trace()                     # show the newly added trace

    def _activate_trace(self, *args):
        """Make the selected trace active: point self.datasets at its channels and
        rebuild the I/Q selectors (the per-load workflow reset).

        self.datasets references the stored trace dict (not a copy) so promoted
        result channels stay with their trace when switching back and forth."""
        name = self.trace_combo.currentText()
        # Opening/switching data resets the workflow: turn off live update so the
        # trace is shown as-is, not reprocessed by leftover tab parameters.
        self.live_check.setChecked(False)
        self.datasets = self.traces.get(name, {})
        keys = list(self.datasets)
        self._refresh_combos(select_i=keys[0] if keys else None,
                             select_q=keys[1] if len(keys) > 1 else None)
        if name:
            self._set_loaded_file(f'{name}  ({self.trace_combo.currentIndex() + 1} '
                                  f'of {self.trace_combo.count()})')

    def _remove_trace(self):
        """Drop the active trace; activate the next one, or clear if none remain."""
        name = self.trace_combo.currentText()
        if not name:
            return
        self.traces.pop(name, None)
        idx = self.trace_combo.currentIndex()
        self.trace_combo.blockSignals(True)
        self.trace_combo.removeItem(idx)
        self.trace_combo.blockSignals(False)
        if self.trace_combo.count():
            self.trace_combo.setCurrentIndex(min(idx, self.trace_combo.count() - 1))
            self._activate_trace()
            self.set_status(f'Removed trace "{name}".')
        else:
            self.clear_all()

    def _refresh_combos(self, select_i=None, select_q=None):
        """Repopulate the I/Q selectors from self.datasets without discarding it."""
        keys = list(self.datasets.keys())
        for combo, sel in ((self.i_combo, select_i), (self.q_combo, select_q)):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(keys)
            if sel is not None and sel in self.datasets:
                combo.setCurrentIndex(keys.index(sel))
            combo.blockSignals(False)
        self.on_source_changed()

    @staticmethod
    def _csv_header_labels(file_path):
        """Column labels from a CSV's '#'-comment header, e.g.
        '# Time (ns), Signal (V)' -> ['Time (ns)', 'Signal (V)']. Uses the last
        comment line before the data (the column-name row, by convention) and
        splits on commas; decorative '#'-only lines are ignored. Returns [] when
        the file has no usable comment header."""
        labels = []
        try:
            with open(file_path, 'r', errors='ignore') as fh:
                for line in fh:
                    s = line.strip()
                    if not s:
                        continue
                    if s.startswith('#'):
                        parts = [c.strip() for c in s.lstrip('#').split(',')]
                        if any(parts):
                            labels = parts
                    else:
                        break                     # reached the first data row
        except Exception:
            return []                             # header is best-effort: never
        return labels if any(labels) else []      # block a load over a bad header

    def _remember_dir(self, path):
        """Record the folder of `path` as the next dialog's starting directory."""
        self.last_dir = os.path.dirname(path) or self.last_dir
        _save_last_dir(self.last_dir)

    def _open_dialog(self, multiple=False, **kw):
        result = self.opener.open_file_dialog(multiprocessing=True,
                                              directory=self.last_dir,
                                              multiple=multiple, **kw)
        if multiple:
            paths = [p for p in (result or []) if p and p != 'None']
            if paths:
                self._remember_dir(paths[0])
            return paths
        if result and result != 'None':
            self._remember_dir(result)
        return result

    def _save_dialog(self, **kw):
        path = self.opener.create_file_dialog(multiprocessing=True,
                                              directory=self.last_dir, **kw)
        if path and path != 'None':
            self._remember_dir(path)
        return path

    def _csv_to_mapping(self, file_path):
        """Read a CSV into a {channel label: (x, y)} mapping plus its header
        labels. Raises ValueError on a structurally unusable file.

        Guards against accidentally loading a 2D matrix: open_1d gives one row per
        CSV column, so a [trace × point] dataset arrives as hundreds/thousands of
        "curves". The 1D tool is for a handful of columns (X + a few channels);
        wide files belong in the 2D tool."""
        _, data = self.opener.open_1d(file_path)
        data = np.atleast_2d(data)
        if data.shape[0] < 2:
            raise ValueError('needs at least two columns (X and Y)')
        if data.shape[0] > 6:
            raise ValueError(f'looks like a 2D dataset ({data.shape[0]} columns); '
                             f'use the 2D tool')
        x = data[0]
        labels = self._csv_header_labels(file_path)
        mapping = {}
        for i in range(1, data.shape[0]):
            y = data[i]
            mask = ~(np.isnan(x) | np.isnan(y))
            name = labels[i] if (i < len(labels) and labels[i]) else f'Y{i}'
            while name in mapping:                 # keep the dataset keys unique
                name += "'"
            mapping[name] = (x[mask], y[mask])
        return mapping, labels

    def open_csv(self):
        paths = self._open_dialog(multiple=True)
        if not paths:
            return
        items, failed, xname = [], [], None
        for file_path in paths:
            try:
                mapping, labels = self._csv_to_mapping(file_path)
            except Exception as e:
                failed.append(f'{os.path.basename(file_path)} ({e})')
                continue
            # axis name + unit from the first file's X-column header (col 0)
            if xname is None and labels and labels[0]:
                xname = labels[0]
            items.append((os.path.splitext(os.path.basename(file_path))[0], mapping))
        if xname:
            self.xname_edit.setText(xname)
        if items:
            self._add_traces(items)
        msg = f'Loaded {len(items)} trace(s)' if items else 'No traces loaded'
        if failed:
            msg += '. Skipped: ' + '; '.join(failed)
        self.set_status(msg + '.')

    def open_bruker(self):
        """Load a Bruker native dataset (BES3T .DSC/.DTA or ESP/WinEPR .par/.spc).
        Complex traces register as a real+imag I/Q pair."""
        nf = ['Bruker (*.DSC *.dsc *.DTA *.dta *.par *.spc *.PAR *.SPC)',
              'BES3T (*.DSC *.dsc *.DTA *.dta)',
              'ESP/WinEPR (*.par *.spc *.PAR *.SPC)', 'All files (*)']
        file_path = self._open_dialog(name_filters=nf)
        if not file_path or file_path == 'None':
            return
        try:
            res = self.bruker.open(file_path)
        except Exception as e:
            self.set_status(f'Could not read Bruker file: {e}')
            return
        if res['ndim'] != 1:
            self.set_status(f'{res["format"]} {res["ndim"]}D dataset '
                            f'({res["data"].shape}) — the 1D tool needs a 1D trace; '
                            f'use the 2D Data Treatment window.')
            return
        x = np.asarray(res['x'], dtype=float)
        mapping = {lbl: (x, np.asarray(y, dtype=float)) for lbl, y in res['channels']}
        unit = f' ({res["x_unit"]})' if res['x_unit'] else ''
        self.xname_edit.setText(f'{res["x_name"]}{unit}')
        self._add_traces([(os.path.splitext(os.path.basename(file_path))[0], mapping)])
        if res['complex']:                        # selects first two as I / Q
            self.pair_check.setChecked(True)
        self.set_status(f'Loaded {os.path.basename(file_path)} — {res["format"]}, '
                        f'{len(x)} pts, '
                        + ('complex (I/Q pair).' if res['complex'] else 'real.'))

    def load_from_buffer(self, silent=False):
        if not os.path.isfile(BUFFER_PATH):
            if not silent:
                self.set_status('No plot buffer found. Right-click a plot in the '
                                'main window → "Send to Data Treatment" first.')
            return
        try:
            labels = []
            buf_xname = ''
            header_count = 0
            with open(BUFFER_PATH, 'r') as fh:
                for line in fh:
                    if not line.startswith('#'):
                        break
                    header_count += 1
                    if 'labels:' in line:
                        labels = line.split('labels:', 1)[1].strip().split('|')
                    elif 'xname:' in line:
                        buf_xname = line.split('xname:', 1)[1].strip()
            data = np.genfromtxt(BUFFER_PATH, delimiter=',', skip_header=header_count)
            data = np.atleast_2d(data)
            # The buffer is a one-shot mailbox: consume it now so that closing
            # and reopening the window does NOT reload this (stale) plot data.
            # A fresh "Send to Data Treatment" rewrites it.
            self._consume_buffer()
            # buffer columns are interleaved x0, y0, x1, y1, ...
            ncurves = data.shape[1]//2
            mapping = {}
            for i in range(ncurves):
                x = data[:, 2*i]
                y = data[:, 2*i + 1]
                mask = ~(np.isnan(x) | np.isnan(y))
                label = labels[i] if i < len(labels) else f'curve {i}'
                mapping[label] = (x[mask], y[mask])
            if not mapping:
                if not silent:
                    self.set_status('Plot buffer is empty.')
                return
            # name+unit of the X axis (e.g. a 2D slice's decay axis); lets the
            # preview SI-prefix a 's' axis to ns. Set before registering so the
            # first redraw already uses it.
            if buf_xname:
                self.xname_edit.setText(buf_xname)
            self._add_traces([('Loaded from plot', mapping)])
            self.set_status(f'Loaded {len(mapping)} curve(s) from the current plot.')
        except Exception as e:
            self._consume_buffer()   # drop a malformed buffer so it doesn't recur
            if not silent:
                self.set_status(f'Could not read plot buffer: {e}')

    def _consume_buffer(self):
        """Delete the plot buffer file once read (one-shot mailbox semantics)."""
        try:
            if os.path.isfile(BUFFER_PATH):
                os.remove(BUFFER_PATH)
        except OSError:
            pass

    def on_source_changed(self, *args):
        """Source selection / pair-mode change: drop the result and recompute."""
        self._reset_result()
        self._plot_key = None        # new/changed source data => re-fit the axes
        self.redraw()
        self._live_update()

    def _xname(self):
        return self.xname_edit.text().strip() or 'X'

    # ---------------------------------------------------------- live update
    def _run_current_op(self):
        """Re-run the operation belonging to the currently visible tab.

        The Fit tab (index 0) is intentionally excluded — fitting is an explicit
        button action, not something to recompute on every keystroke.
        """
        ops = {1: self.do_fft, 2: self.do_phase, 3: self.do_smooth, 4: self.do_filter}
        fn = ops.get(self.tabs.currentIndex())
        if fn is not None:
            fn()

    def _apply_current_op(self):
        """Run the current tab's operation NOW (Fit included), so the result
        reflects the current tab and parameters regardless of live-update."""
        ops = {0: self.do_fit, 1: self.do_fft, 2: self.do_phase, 3: self.do_smooth,
               4: self.do_filter}
        ops[self.tabs.currentIndex()]()

    def _live_update(self, *args):
        """Slot wired to every operation parameter; recompute if live mode on."""
        if self._suppress_live:
            return
        if not self.live_check.isChecked() or not self.datasets:
            return
        self._run_current_op()

    def _zerofill_n(self, length, choice):
        """Target FFT length for a zero-fill combo choice ('None', '×2'…, 'Next pow₂')."""
        return sigproc.zerofill_length(length, choice)

    def _window(self, n, name, param=8.6):
        """Apodization window of length n (delegates to the shared helper)."""
        return sigproc.apodization_window(n, name, param)

    def _update_window_param(self, *args):
        """Relabel + reconfigure the window parameter field for the selected
        window (Kaiser β / Gaussian σ / Tukey α), or disable it for the
        zero-parameter windows."""
        name = self.fft_window.currentText()
        cfg = self.WINDOW_PARAM.get(name)
        self.fft_winparam.blockSignals(True)
        if cfg is not None:
            label, lo, hi, dec, default, step = cfg
            self.fft_winparam_label.setText(label)
            self.fft_winparam.setEnabled(True)
            self.fft_winparam.setDecimals(dec)
            self.fft_winparam.setRange(lo, hi)
            self.fft_winparam.setSingleStep(step)
            self.fft_winparam.setValue(default)
        else:
            self.fft_winparam_label.setText('Window param')
            self.fft_winparam.setEnabled(False)
        self.fft_winparam.blockSignals(False)

    def _passband_mask(self, freq, ftype, lo, hi):
        """Boolean keep-mask over `freq`; cutoffs are fractions of f_max (Nyquist)."""
        af = np.abs(np.asarray(freq, dtype=float))
        fmax = float(np.max(af)) or 1.0
        if ftype == 'Low-pass':
            return af <= hi*fmax
        if ftype == 'High-pass':
            return af >= lo*fmax
        if ftype == 'Band-pass':
            return (af >= lo*fmax) & (af <= hi*fmax)
        return np.ones_like(af, dtype=bool)

    # ------------------------------------------------------------- channels
    def _xy(self, combo):
        label = combo.currentText()
        if label in self.datasets:
            return self.datasets[label]
        return None, None

    def i_xy(self):
        return self._xy(self.i_combo)

    def q_xy(self):
        return self._xy(self.q_combo)

    def is_pair(self):
        return self.pair_check.isChecked()

    # ------------------------------------------------------------- result
    def _reset_result(self):
        self.result_x = None
        self.result_channels = []
        self.result_xname = 'X'
        self.result_show_source = True
        self.result_meta = []
        if hasattr(self, 'fit_result'):
            self.fit_result.setText('')

    def _set_result(self, x, channels, meta, show_source=True, xname='X'):
        """Store a result of one or more (label, y) channels and repaint."""
        self.result_x = np.asarray(x, dtype=float)
        self.result_channels = [(lbl, np.asarray(y, dtype=float)) for lbl, y in channels]
        self.result_meta = list(meta)
        self.result_show_source = show_source
        self.result_xname = xname
        self.redraw()

    def has_result(self):
        return bool(self.result_channels)

    def promote_result(self):
        """Register the current result channel(s) as new source curve(s) so the
        next operation chains off them (e.g. baseline → FFT → phase).

        The current tab's operation is applied first, so the promoted data always
        matches the visible tab and its parameters — no need to press Apply."""
        self._apply_current_op()
        if not self.has_result():
            self.set_status('No result to chain — run an operation first.')
            return
        self.step_counter += 1
        new_i = new_q = None
        for idx, (lbl, y) in enumerate(self.result_channels):
            name = f'step{self.step_counter}_{lbl}'
            self.datasets[name] = (self.result_x.copy(), np.asarray(y, dtype=float))
            if idx == 0:
                new_i = name
            elif idx == 1:
                new_q = name
        promoted = ' & '.join(k for k in (new_i, new_q) if k)
        self._reset_result()
        # Select the new input and show ONLY it — do not auto re-apply the
        # operation (that would treat the result a second time).
        self._suppress_live = True
        try:
            self.pair_check.setChecked(new_q is not None)
            self._refresh_combos(select_i=new_i, select_q=new_q)
        finally:
            self._suppress_live = False
        self.redraw()
        self.set_status(f'Result registered as {promoted}; shown as the new '
                        f'input. Choose an operation and apply it.')

    def undo_step(self):
        """Undo the last 'Result → input': remove the most recent stepN_ channel(s)
        from the active trace and reselect the previous input (the prior step group,
        or the original channels). Scoped to the active trace; the global step
        counter is left alone so future step names stay unique."""
        steps = {}
        for k in self.datasets:
            m = re.match(r'step(\d+)_', k)
            if m:
                steps.setdefault(int(m.group(1)), []).append(k)
        if not steps:
            self.set_status('No promoted step to undo.')
            return
        top = max(steps)
        removed = steps[top]
        for k in removed:
            self.datasets.pop(k, None)
        # any pending overlay may have been computed from the removed channels
        self._reset_result()
        # reselect the previous step group, else the original (non-step) channels
        lower = [n for n in steps if n < top]
        if lower:
            sel = steps[max(lower)]
        else:
            sel = [k for k in self.datasets if not re.match(r'step\d+_', k)]
        new_i = sel[0] if sel else next(iter(self.datasets), None)
        new_q = sel[1] if len(sel) > 1 else None
        self._suppress_live = True
        try:
            self.pair_check.setChecked(new_q is not None)
            self._refresh_combos(select_i=new_i, select_q=new_q)
        finally:
            self._suppress_live = False
        self.redraw()
        self.set_status(f'Removed {" & ".join(removed)}; '
                        f'input back to {new_i or "—"}.')

    def clear_result(self):
        """Drop the computed-result overlay, keep the loaded source data."""
        self._reset_result()
        self.redraw()
        self.set_status('Result cleared.')

    def clear_all(self):
        """Reset the window: forget all loaded data, result and selectors."""
        self.datasets = {}
        self.traces = {}
        self._reset_result()
        self.step_counter = 0
        for combo in (self.trace_combo, self.i_combo, self.q_combo):
            combo.blockSignals(True)
            combo.clear()
            combo.blockSignals(False)
        for lbl in list(self._curve_items):
            self.plot_widget.removeItem(self._curve_items.pop(lbl))
            try:
                self.legend.removeItem(lbl)
            except Exception:
                pass
        self._set_loaded_file(None)
        self.set_status('Cleared. Load a dataset to begin.')

    # ----------------------------------------------------- preview (in-process)
    SOURCE_PENS = [(120, 170, 255), (220, 120, 220)]   # I = blue, Q = magenta
    RESULT_PENS = [(211, 194, 78), (120, 220, 150), (230, 140, 90)]
    # one colour per trace for the "Fit all traces" overlay (cycled if more)
    BATCH_COLORS = [(211, 194, 78), (120, 170, 255), (120, 220, 150),
                    (230, 140, 90), (200, 120, 220), (90, 200, 200),
                    (240, 120, 150), (170, 200, 90)]

    def redraw(self):
        """Repaint the embedded preview with the source channel(s) and the
        current result. Curve items are reused (setData) and only stale labels
        are removed, so live tweaking updates in place without rebuilding."""
        curves = []  # (label, x, y, pen)
        xi, yi = self.i_xy()
        xq, yq = self.q_xy()
        show_q = (self.is_pair() and xq is not None and len(xq)
                  and self.q_combo.currentText() != self.i_combo.currentText())

        if self.has_result():
            if self.result_show_source and xi is not None and len(xi):
                curves.append(('source I', xi, yi, self.SOURCE_PENS[0]))
                if show_q:
                    curves.append(('source Q', xq, yq, self.SOURCE_PENS[1]))
            for idx, (lbl, y) in enumerate(self.result_channels):
                curves.append((lbl, self.result_x, y, self.RESULT_PENS[idx % len(self.RESULT_PENS)]))
            xname = self.result_xname
        else:
            if xi is not None and len(xi):
                curves.append(('source I', xi, yi, self.SOURCE_PENS[0]))
            if show_q:
                curves.append(('source Q', xq, yq, self.SOURCE_PENS[1]))
            xname = self._xname()

        wanted = set()
        for lbl, x, y, color in curves:
            wanted.add(lbl)
            is_src = lbl.startswith('source')
            pen = pg.mkPen(color, width=1 if is_src else 2)
            xd, yd = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
            item = self._curve_items.get(lbl)
            if item is None:
                self._curve_items[lbl] = self.plot_widget.plot(xd, yd, pen=pen, name=lbl)
            else:
                item.setData(xd, yd)
                item.setPen(pen)
        # drop curves no longer present (label set changed)
        for lbl in [k for k in self._curve_items if k not in wanted]:
            self.plot_widget.removeItem(self._curve_items.pop(lbl))
            try:
                self.legend.removeItem(lbl)
            except Exception:
                pass
        # Split a "Name (unit)" label so pyqtgraph gets the unit separately, then
        # auto-SI-prefix only bare SI bases — a slice transferred in 's' reads in
        # ns instead of raw 2e-9, while an already-prefixed 'ns'/'MHz' stays as is.
        xlabel, xunit = _split_unit(xname)
        self.plot_widget.setLabel('bottom', xlabel, units=xunit)
        try:
            self.plot_widget.getPlotItem().getAxis('bottom').enableAutoSIPrefix(
                _si_autoprefix(xunit))
        except Exception:
            pass
        self.plot_widget.setLabel('left', '')

        # Auto-scale the view when the plotted *content* changes (new result,
        # time unit, load/clear) — but not on same-view live tweaks, so a manual
        # zoom survives while dragging parameters.
        key = (frozenset(wanted), xname)
        if key != self._plot_key:
            self._plot_key = key
            try:
                self.plot_widget.autoRange()
            except Exception:
                pass

    def set_status(self, text):
        self.status.setText(text)
        general.message(text)

    def _set_loaded_file(self, name):
        """Show the source of the current dataset under the Source buttons."""
        self.loaded_label.setText(f'File: {name}' if name else 'File: —')

    # ---------------------------------------------------------- operations
    def _update_fit_formula(self, model):
        """Refresh the equation shown under the model selector."""
        formula = self.fitter.model_formula(model)
        self.fit_formula.setText(
            f'<span style="color: rgb(160, 160, 190);">{formula}</span>'
            if formula else '')

    def do_fit(self):
        x, y = self.i_xy()
        if x is None or not len(x):
            self.set_status('No I channel selected.')
            return
        model = self.model_combo.currentText()
        no_offset = self.fit_no_offset.isChecked()
        try:
            res = self.fitter.fit(model, x, y, no_offset=no_offset)
        except Exception as e:
            self.set_status(f'Fit failed: {e}')
            return
        meta = ['Fit model: ' + model + (' (offset fixed = 0)' if no_offset else '')]
        meta += [f'{n} = {v:.6g} +/- {e:.3g}'
                 for n, v, e in zip(res['param_names'], res['popt'], res['perr'])]
        meta.append(f'R^2 = {res["r_squared"]:.6f}')
        self._set_result(x, [('fit', res['y_fit'])], meta, show_source=True,
                         xname=self._xname())
        trows = [(f'<b>{n}</b>', f'{v:.5g}', f'{e:.3g}')
                 for n, v, e in zip(res['param_names'], res['popt'], res['perr'])]
        table = _html_table(['param', 'value', '± err'], trows)
        off = ' (offset = 0)' if no_offset else ''
        formula = self.fitter.model_formula(model)
        formula_row = (f'<span style="color: rgb(160, 160, 190);">{formula}</span><br>'
                       if formula else '')
        html = (f'<div style="line-height: 150%;">'
                f'<b style="color: rgb(211, 194, 78);">{model}</b>{off}<br>'
                f'{formula_row}{table}<br>R² = {res["r_squared"]:.5f}</div>')
        self.fit_result.setText(html)
        self.set_status(f'Fit done. R² = {res["r_squared"]:.5f}')

    def fit_all_traces(self):
        """Fit the current model to the I channel of every loaded trace, overlay
        the data + fits, and collect a per-trace parameter table (saveable as CSV).
        Useful for batch lsq fits, e.g. T₂ across a series of traces."""
        n = self.trace_combo.count()
        if n == 0:
            self.set_status('No traces loaded.')
            return
        model = self.model_combo.currentText()
        no_offset = self.fit_no_offset.isChecked()
        names = [self.trace_combo.itemText(i) for i in range(n)]
        rows, overlays, failed = [], [], []
        self.fit_all_btn.setEnabled(False)
        self.fit_all_btn.setStyleSheet(BUTTON_BUSY_STYLE)
        try:
            for i, name in enumerate(names):
                self.trace_combo.setCurrentIndex(i)        # activate -> i_xy()
                x, y = self.i_xy()
                if x is None or not len(x):
                    failed.append(name)
                    continue
                try:
                    res = self.fitter.fit(model, np.asarray(x, float),
                                          np.asarray(y, float), no_offset=no_offset)
                except Exception as e:
                    failed.append(f'{name} ({e})')
                    continue
                rows.append((name, res))
                overlays.append((name, np.asarray(x, float), np.asarray(y, float),
                                 np.asarray(res['y_fit'], float)))
                self.set_status(f'Fit all: {i + 1}/{n} — {name}…')
                QApplication.processEvents()
        finally:
            self.fit_all_btn.setEnabled(True)
            self.fit_all_btn.setStyleSheet(BUTTON_STYLE)
        if not rows:
            self.set_status('Fit all: no trace could be fit.')
            return
        self._reset_result()                  # drop any single-trace result overlay
        self._render_fit_batch(overlays)
        # parameter table (kept per-row so models with different param sets are ok)
        self.fit_table = {'model': model, 'rows': []}
        pnames = []                            # union of param names, first-seen order
        for _, res in rows:
            for p in res['param_names']:
                if p not in pnames:
                    pnames.append(p)
        trows = []
        for name, res in rows:
            self.fit_table['rows'].append(
                (name, list(res['param_names']), list(map(float, res['popt'])),
                 list(map(float, res['perr'])), float(res['r_squared'])))
            d = dict(zip(res['param_names'], res['popt']))
            cells = [f'<b>{name}</b>'] + [f'{d[p]:.4g}' if p in d else '—'
                                          for p in pnames] + [f'{res["r_squared"]:.4f}']
            trows.append(cells)
        table = _html_table(['trace'] + pnames + ['R²'], trows)
        formula = self.fitter.model_formula(model)
        formula_row = (f'<span style="color: rgb(160, 160, 190);">{formula}</span><br>'
                       if formula else '')
        self.fit_result.setText('<div style="line-height: 150%;">'
                                f'<b style="color: rgb(211, 194, 78);">{model}</b> — '
                                f'{len(rows)} trace(s)<br>{formula_row}{table}</div>')
        self.fit_save_table_btn.setEnabled(True)
        msg = f'Fit all: {len(rows)}/{n} trace(s) with {model}.'
        if failed:
            msg += ' Failed: ' + '; '.join(failed)
        self.set_status(msg)

    def _render_fit_batch(self, overlays):
        """Overlay each trace's data (thin) + fit (dashed) on the preview, one
        colour per trace. A later single-trace redraw drops these automatically."""
        for lbl in list(self._curve_items):
            self.plot_widget.removeItem(self._curve_items.pop(lbl))
            try:
                self.legend.removeItem(lbl)
            except Exception:
                pass
        for i, (name, x, y, yfit) in enumerate(overlays):
            col = self.BATCH_COLORS[i % len(self.BATCH_COLORS)]
            self._curve_items[name] = self.plot_widget.plot(
                x, y, pen=pg.mkPen(col, width=1), name=name)
            self._curve_items[f'{name} fit'] = self.plot_widget.plot(
                x, yfit, pen=pg.mkPen(col, width=2, style=Qt.PenStyle.DashLine),
                name=f'{name} fit')
        self._plot_key = None                 # force the next single redraw to refit
        try:
            self.plot_widget.autoRange()
        except Exception:
            pass

    def save_fit_table(self):
        """Save the 'Fit all traces' parameter table as CSV (one row per trace)."""
        tbl = getattr(self, 'fit_table', None)
        if not tbl or not tbl['rows']:
            self.set_status('No fit table — run "Fit all traces" first.')
            return
        path = self._save_dialog()
        if not path or path == 'None':
            return
        # union of parameter names across rows, in first-seen order
        pnames = []
        for _, pn, *_ in tbl['rows']:
            for p in pn:
                if p not in pnames:
                    pnames.append(p)
        header = ['trace'] + [c for p in pnames for c in (p, f'{p}_err')] + ['R2']
        lines = [','.join(header)]
        for name, pn, vals, errs, r2 in tbl['rows']:
            d = {p: (v, e) for p, v, e in zip(pn, vals, errs)}
            cells = [str(name).replace(',', ';')]
            for p in pnames:
                v, e = d.get(p, (float('nan'), float('nan')))
                cells += [f'{v:.6g}', f'{e:.6g}']
            cells.append(f'{r2:.6f}')
            lines.append(','.join(cells))
        try:
            with open(path, 'w') as fh:
                fh.write(f'# Fit-all parameter table, model: {tbl["model"]}\n')
                fh.write('\n'.join(lines) + '\n')
        except OSError as e:
            self.set_status(f'Could not save table: {e}')
            return
        self.set_status(f'Saved fit table ({len(tbl["rows"])} rows) to '
                        f'{os.path.basename(path)}.')

    def _spectrum_channels(self, sp, mode):
        """Map a complex spectrum to a list of (label, y) per the output mode."""
        if mode == 'Magnitude':
            return [('|FFT|', np.abs(sp))]
        if mode == 'Real':
            return [('Re', np.real(sp))]
        if mode == 'Imaginary':
            return [('Im', np.imag(sp))]
        return [('Re', np.real(sp)), ('Im', np.imag(sp))]   # Real + Imaginary

    def auto_echo_center(self):
        """Fill 'skip pts' with the echo centre = peak of the magnitude envelope
        (|I+iQ| for an I/Q pair, else |I|), so the field-offset modulation
        cancels before the peak search."""
        x, i = self.i_xy()
        if x is None or len(i) < 3:
            self.set_status('Load data first (need at least three points).')
            return
        i = np.asarray(i, dtype=float)
        if self.is_pair():
            xq, q = self.q_xy()
            q = np.asarray(q, dtype=float)
            env = np.sqrt(i**2 + q**2) if q.shape == i.shape else np.abs(i)
        else:
            env = np.abs(i)
        k = sigproc.echo_center(env)
        self.fft_skip.setValue(int(k))
        self.set_status(f'Echo centre at point {k} (skip set).')

    @staticmethod
    def _fft_freq_scale(dt, xname):
        """Sample step + frequency unit for an FFT, from the X-axis unit parsed
        out of `xname` (mirrors the 2D tool's _freq_axis): ns/µs/ms → MHz, s → Hz,
        unknown/none → raw 1/(X units). Returns (step_for_fftfreq, freq_unit)."""
        unit = _split_unit(xname)[1].strip().lower()
        if unit == 'ns':
            return dt*1e-3, 'MHz'          # dt in ns -> µs, so 1/d is MHz
        if unit in ('us', 'µs', 'μs'):
            return dt, 'MHz'
        if unit == 'ms':
            return dt*1e3, 'MHz'           # dt in ms -> µs
        if unit == 's':
            return dt, 'Hz'
        return dt, ''                      # unknown unit: keep raw 1/(X units)

    def do_fft(self):
        x, i = self.i_xy()
        if x is None or len(x) < 2:
            self.set_status('Need at least two points for an FFT.')
            return
        x = np.asarray(x, dtype=float)
        i = np.asarray(i, dtype=float)
        dt = float(np.mean(np.diff(x)))
        if dt == 0:
            self.set_status('X axis has zero spacing; cannot compute FFT.')
            return

        pair = self.is_pair()
        if pair:
            xq, q = self.q_xy()
            q = np.asarray(q, dtype=float)
            if q.shape != i.shape:
                self.set_status('I and Q channels must have the same length for a complex FFT.')
                return
            signal = i + 1j*q
        else:
            signal = i

        # drop leading points so the transform starts at the echo centre; this
        # sets t = 0 there and removes the dead-time first-order phase ramp.
        skip = max(0, min(int(self.fft_skip.value()), len(signal) - 2))
        signal = signal[skip:]

        # apodization window applied to the time-domain signal before transform
        win = self.fft_window.currentText()
        wparam = self.fft_winparam.value()
        signal = signal*self._window(len(signal), win, wparam)

        zf = self.fft_zerofill.currentText()
        n = self._zerofill_n(len(signal), zf)
        sp = np.fft.fft(signal, n)
        # Frequency axis in physical units derived from the X (time) unit, so the
        # spectrum is the same whether the trace arrived in 's' (from a plot, where
        # dt≈2e-9) or in 'ns' (from a file, where dt≈2): s→Hz, ns/µs/ms→MHz. Using
        # the raw 1/dt instead leaves the two sources off by 1e9 (see the 2D tool's
        # _freq_axis, the same convention).
        d, funit = self._fft_freq_scale(dt, self._xname())
        freq = np.fft.fftfreq(n, d)
        order = np.argsort(freq)
        freq = freq[order]
        sp = sp[order]

        # optional passband mask on the spectrum
        ftype = self.fft_filter.currentText()
        if ftype != 'None':
            sp = sp*self._passband_mask(freq, ftype, self.fft_cut_lo.value(),
                                        self.fft_cut_hi.value())

        mode = self.fft_mode.currentText()
        channels = self._spectrum_channels(sp, mode)
        fxname = f'Frequency ({funit})' if funit else 'Frequency'
        meta = [f'FFT ({"complex I+iQ" if pair else "real"}), output: {mode}',
                f'frequency in {funit}' if funit else 'frequency in 1/(X units)',
                f'skip {skip} leading pts (echo centre)' if skip else 'no leading skip',
                f'window: {win}' + (f' (param={wparam:.4g})'
                                    if win in self.WINDOW_PARAM else ''),
                f'points: {len(signal)} -> {n} (zero fill: {zf})',
                f'passband: {ftype}' + ('' if ftype == 'None' else
                    f' (lo={self.fft_cut_lo.value():.4g}, hi={self.fft_cut_hi.value():.4g} x f_max)')]
        self._set_result(freq, channels, meta, show_source=False, xname=fxname)
        self.set_status(f'FFT ({mode}); window {win}; passband {ftype}; '
                        f'{len(signal)}→{n} pts.')

    def auto_phase_zero(self):
        """Fill the zero-order phase field with the value that maximises the
        magnitude-weighted real part (see Fast_Fourier.auto_phase_zero). Works on
        the FFT spectrum when 'FFT first' is on, else on the time-domain I+iQ;
        first/second order stay manual (skip-pts removes the φ₁ ramp)."""
        il = self.i_combo.currentText()
        ql = self.q_combo.currentText()
        if il not in self.datasets or ql not in self.datasets:
            self.set_status('Select both I and Q channels above.')
            return
        x, idata = self.datasets[il]
        _, qdata = self.datasets[ql]
        idata = np.asarray(idata, dtype=float)
        qdata = np.asarray(qdata, dtype=float)
        if idata.shape != qdata.shape or idata.size < 2:
            self.set_status('I and Q channels must have the same length (≥ 2).')
            return
        sig = idata + 1j*qdata
        if self.phase_fft.isChecked():
            dt = float(np.mean(np.diff(np.asarray(x, dtype=float))))
            if dt == 0:
                self.set_status('X axis has zero spacing; cannot FFT.')
                return
            n = self._zerofill_n(len(idata), self.phase_zerofill.currentText())
            spec = np.fft.fft(sig, n)
            domain = 'frequency'
        else:
            spec = sig
            domain = 'time'
        phi = self.fft.auto_phase_zero(spec)
        self.phase_zero.setValue(phi)        # fires the live preview update
        self.set_status(f'Auto φ₀ = {phi:.2f}° ({domain} domain).')

    def do_phase(self):
        il = self.i_combo.currentText()
        ql = self.q_combo.currentText()
        if il not in self.datasets or ql not in self.datasets:
            self.set_status('Select both I and Q channels above.')
            return
        x, idata = self.datasets[il]
        _, qdata = self.datasets[ql]
        x = np.asarray(x, dtype=float)
        idata = np.asarray(idata, dtype=float)
        qdata = np.asarray(qdata, dtype=float)
        if idata.shape != qdata.shape:
            self.set_status('I and Q channels must have the same length.')
            return

        # phase polynomial exp( i*(cor1 + cor2*axis + cor3*axis^2) )
        cor1 = float(self.phase_zero.value())*np.pi/180.0   # degrees -> radians
        # first/second order entered as a frequency offset: value/1000 cycles per
        # x-unit (50 -> 50 MHz when x is in ns); coeff = 2*pi*value/1000.
        v1 = float(self.phase_first.value()); v2 = float(self.phase_second.value())
        cor2 = 2*np.pi*v1/1000.0
        cor3 = 2*np.pi*v2/1000.0

        domain = 'time'
        xname = self._xname()
        if self.phase_fft.isChecked():
            # FFT the complex I/Q first, then phase in the frequency domain
            # (the phase_cor.py workflow); axis becomes frequency.
            dt = float(np.mean(np.diff(x)))
            if dt == 0:
                self.set_status('X axis has zero spacing; cannot FFT.')
                return
            zf = self.phase_zerofill.currentText()
            n = self._zerofill_n(len(idata), zf)
            sp = np.fft.fft(idata + 1j*qdata, n)
            freq = np.fft.fftfreq(n, dt)
            order = np.argsort(freq)
            axis = freq[order]
            data_i = np.real(sp[order])
            data_q = np.imag(sp[order])
            domain = f'frequency (FFT first, {len(idata)}->{n} pts, zero fill: {zf})'
            xname = 'Frequency'
        else:
            axis = x
            data_i = idata
            data_q = qdata

        out = self.fft.ph_correction(axis, data_i, data_q, cor1, cor2, cor3)
        real, imag = np.asarray(out[0]), np.asarray(out[1])
        mode = self.phase_out.currentText()
        if mode == 'Real':
            channels = [('Re', real)]
        elif mode == 'Imaginary':
            channels = [('Im', imag)]
        elif mode == 'Magnitude':
            channels = [('|phase|', np.sqrt(real**2 + imag**2))]
        else:  # Real + Imaginary
            channels = [('Re', real), ('Im', imag)]
        meta = [f'Phase correction, output: {mode}; domain: {domain}',
                f'I = {il}, Q = {ql}',
                f'zero order = {self.phase_zero.value():.4g} deg, '
                f'first = {v1:.4g}, second = {v2:.4g} (MHz @ x=ns; coeff = 2π·value/1000 per x)']
        self._set_result(axis, channels, meta,
                         show_source=not self.phase_fft.isChecked(), xname=xname)
        self.set_status(f'Phase correction applied ({mode}).')

    def _apply_smooth(self, x, y, method):
        if method == 'Savitzky-Golay':
            return self.sp.savitzky_golay(y, self.smooth_window.value(),
                                          self.smooth_order.value())
        elif method == 'Moving average':
            return self.sp.moving_average(y, self.smooth_window.value())
        elif method == 'Baseline subtract':
            region = {'All points': 'all', 'First N points': 'first',
                      'Last N points': 'last', 'First & last N': 'ends'}.get(
                          self.base_region.currentText(), 'all')
            return self.sp.baseline_poly(x, y, self.smooth_order.value(),
                                         region=region, npts=self.base_npts.value())
        else:  # Normalize
            return self.sp.normalize(y, 'minmax')

    def do_smooth(self):
        x, i = self.i_xy()
        if x is None or not len(x):
            self.set_status('No I channel selected.')
            return
        x = np.asarray(x, dtype=float)
        i = np.asarray(i, dtype=float)
        method = self.smooth_method.currentText()
        try:
            if self.is_pair():
                xq, q = self.q_xy()
                q = np.asarray(q, dtype=float)
                if q.shape != i.shape:
                    self.set_status('I and Q channels must have the same length.')
                    return
                out_i = self._apply_smooth(x, i, method)
                out_q = self._apply_smooth(x, q, method)
                channels = [('I', out_i), ('Q', out_q)]
            else:
                channels = [('smoothed', self._apply_smooth(x, i, method))]
        except Exception as e:
            self.set_status(f'{method} failed: {e}')
            return
        meta = [f'Smoothing: {method}'
                + (' (I & Q)' if self.is_pair() else ''),
                f'window = {self.smooth_window.value()}, '
                f'poly order = {self.smooth_order.value()}']
        if method == 'Baseline subtract':
            meta.append(f'baseline from: {self.base_region.currentText()} '
                        f'(N = {self.base_npts.value()})')
        self._set_result(x, channels, meta, show_source=True, xname=self._xname())
        self.set_status(f'{method} applied'
                        + (' to I & Q.' if self.is_pair() else '.'))

    def do_filter(self):
        """FFT → zero frequencies outside the passband → inverse FFT, giving a
        cleaned time-domain signal (I/Q pair filtered together)."""
        x, i = self.i_xy()
        if x is None or len(x) < 2:
            self.set_status('Need at least two points to filter.')
            return
        x = np.asarray(x, dtype=float)
        i = np.asarray(i, dtype=float)
        pair = self.is_pair()
        if pair:
            xq, q = self.q_xy()
            q = np.asarray(q, dtype=float)
            if q.shape != i.shape:
                self.set_status('I and Q channels must have the same length.')
                return
            signal = i + 1j*q
        else:
            signal = i

        ftype = self.filt_type.currentText()
        lo = self.filt_cut_lo.value()
        hi = self.filt_cut_hi.value()
        sp = np.fft.fft(signal)
        freq = np.fft.fftfreq(len(signal))     # cutoffs are fractions of f_max
        sp = sp*self._passband_mask(freq, ftype, lo, hi)
        out = np.fft.ifft(sp)

        if pair:
            channels = [('I', np.real(out)), ('Q', np.imag(out))]
        else:
            channels = [('filtered', np.real(out))]
        used = {'Low-pass': f'hi={hi:.4g}', 'High-pass': f'lo={lo:.4g}',
                'Band-pass': f'lo={lo:.4g}, hi={hi:.4g}'}.get(ftype, '')
        meta = [f'Filter: {ftype} (FFT->mask->iFFT)' + (' (I & Q)' if pair else ''),
                f'cutoff {used} x f_max']
        self._set_result(x, channels, meta, show_source=True, xname=self._xname())
        self.set_status(f'{ftype} filter applied ({used} ×f_max)'
                        + (' to I & Q.' if pair else '.'))

    # -------------------------------------------------------------- output
    def plot_result(self):
        """Push the result — and the raw source it was computed from — into a
        keeper dock named in the Output field. The raw curve(s) are included
        only when they share the result's x-axis (fit / smooth / phase-time);
        for FFT / filter the source is a different domain, so it is omitted."""
        if not self.has_result():
            self.set_status('Nothing to plot — run an operation first.')
            return
        name = self.name_edit.text().strip() or 'treatment_result'
        curves = []  # (label, x, y)
        if self.result_show_source:
            xi, yi = self.i_xy()
            if xi is not None and len(xi):
                curves.append(('raw I', xi, yi))
            if self.is_pair():
                xq, yq = self.q_xy()
                if (xq is not None and len(xq)
                        and self.q_combo.currentText() != self.i_combo.currentText()):
                    curves.append(('raw Q', xq, yq))
        for lbl, y in self.result_channels:
            curves.append((lbl, self.result_x, y))
        try:
            for lbl, cx, cy in curves:
                general.plot_1d(name, np.asarray(cx), np.asarray(cy),
                                label=lbl, xname=self.result_xname)
        except Exception as e:
            self.set_status(f'Could not plot to GUI: {e}')
            return
        raw_n = sum(1 for c in curves if c[0].startswith('raw'))
        self.set_status(f'Pushed "{name}" to the main GUI '
                        f'({raw_n} raw + {len(self.result_channels)} result curve(s)).')

    def save_result(self):
        if not self.has_result():
            self.set_status('Nothing to save — run an operation first.')
            return
        file_path = self._save_dialog()
        if not file_path or file_path == 'None':
            return
        cols = [self.result_x] + [np.asarray(y, dtype=float) for _, y in self.result_channels]
        data = np.column_stack(cols)
        col_header = 'X, ' + ', '.join(lbl for lbl, _ in self.result_channels)
        # Prepend operation metadata (fit model + params, FFT/phase settings) as
        # comment lines, then the column header on the last line.
        header = '\n'.join(list(self.result_meta) + [col_header])
        self.opener.save_data(file_path, data, header=header, mode='w')
        self.set_status(f'Saved to {os.path.basename(file_path)} '
                        f'({len(self.result_meta)} metadata line(s), '
                        f'{len(self.result_channels)} channel(s)).')

    def _export_curves(self, mode):
        """Curves to hand to Makie for a given mode, mirroring the preview.

        Returns (xname, [(label, x, y), …]). 'raw' = source channel(s), 'result'
        = the computed result channels, 'both' = raw + result overlaid (e.g. fit
        over its data, which share an X axis)."""
        curves = []
        xi, yi = self.i_xy()
        xq, yq = self.q_xy()
        show_q = (self.is_pair() and xq is not None and len(xq)
                  and self.q_combo.currentText() != self.i_combo.currentText())
        if mode in ('raw', 'both') and xi is not None and len(xi):
            curves.append((self.i_combo.currentText() or 'I', xi, yi))
            if show_q:
                curves.append((self.q_combo.currentText() or 'Q', xq, yq))
        if mode in ('result', 'both') and self.has_result():
            for lbl, y in self.result_channels:
                curves.append((lbl, self.result_x, y))
        # X-axis name: the result domain if a result curve is included, else raw
        xname = (self.result_xname if (mode != 'raw' and self.has_result())
                 else self._xname())
        return xname, curves

    def _write_makie_csvs(self, xname, curves):
        """Write curves to temp CSV(s) for render.jl. Curves that share one X go
        into a single multi-column file (clean overlay with a column legend);
        curves with differing X (e.g. time source + frequency result) are written
        one-per-file so render.jl overlays them as separate inputs."""
        tmpdir = tempfile.gettempdir()
        xs = [np.asarray(x, dtype=float) for _, x, _ in curves]
        shared = all(len(x) == len(xs[0]) for x in xs) and \
                 all(np.allclose(x, xs[0], equal_nan=True) for x in xs)
        if shared:
            cols = [xs[0]] + [np.asarray(y, dtype=float) for _, _, y in curves]
            header = (xname or 'X') + ', ' + ', '.join(lbl for lbl, _, _ in curves)
            path = os.path.join(tmpdir, 'atomize_makie_export.csv')
            self.opener.save_data(path, np.column_stack(cols), header=header, mode='w')
            return [path]
        paths = []
        for k, (lbl, x, y) in enumerate(curves):
            data = np.column_stack([np.asarray(x, dtype=float), np.asarray(y, dtype=float)])
            header = (xname or 'X') + ', ' + lbl
            safe = ''.join(c if c.isalnum() else '_' for c in lbl)[:30] or f'curve{k}'
            path = os.path.join(tmpdir, f'atomize_makie_{k}_{safe}.csv')
            self.opener.save_data(path, data, header=header, mode='w')
            paths.append(path)
        return paths

    def _makie_save_dialog(self):
        """Save dialog for the Makie OUTPUT figure — a PDF/SVG/PNG picker, not the
        CSV picker the Save button uses (this only chooses where the figure goes;
        your data is never saved here)."""
        path = self.opener.FileDialog(
            directory=self.last_dir, mode='Save', fmt='pdf',
            name_filters=['PDF figure (*.pdf)', 'SVG figure (*.svg)', 'PNG image (*.png)'])
        if path and path != 'None':
            self._remember_dir(path)
        return path

    def make_makie_figure(self):
        """Render the selected curves to a publication PDF via Julia/Makie.

        The mode selector decides what to draw (raw / result / both). Curves are
        written to temp CSV(s) and rendered by script_examples/makie/render.jl in
        a QProcess, so the UI stays responsive while Julia precompiles; the PDF
        opens when done. Needs `julia` on PATH; makie/ is its own Julia project,
        so the first render resolves + precompiles its deps (one-off, slow)."""
        if getattr(self, '_makie_proc', None) is not None and \
                self._makie_proc.state() != QProcess.ProcessState.NotRunning:
            self.set_status('A Makie render is already running…')
            return
        mode = ['both', 'result', 'raw'][self.makie_mode.currentIndex()]
        xname, curves = self._export_curves(mode)
        if not curves:
            self.set_status('Nothing to draw for that selection — load data '
                            'or run an operation first.')
            return
        julia = shutil.which('julia') or os.path.expanduser('~/.juliaup/bin/julia')
        if not os.path.exists(julia):
            self.set_status('Julia not found — install Julia to render Makie figures.')
            return
        out_path = self._makie_save_dialog()
        if not out_path or out_path == 'None':
            return
        out_path = str(out_path)
        if not out_path.lower().endswith(('.pdf', '.svg', '.png')):
            out_path += '.pdf'
        inputs = self._write_makie_csvs(xname, curves)
        script = Path(__file__).resolve().parents[1] / 'script_examples' / 'makie' / 'render.jl'
        self._makie_out = out_path
        self._makie_proc = QProcess(self)
        self._makie_proc.finished.connect(self._makie_done)
        self.makie_btn.setEnabled(False)
        self.makie_btn.setStyleSheet(BUTTON_BUSY_STYLE)
        self.set_status(f'Rendering Makie figure ({len(curves)} curve(s))…  (first run '
                        'precompiles CairoMakie — a few minutes; later runs ~15 s).')
        QApplication.processEvents()
        self._makie_proc.start(julia, [str(script), out_path, *inputs])

    def _makie_done(self, code, status):
        self.makie_btn.setEnabled(True)
        self.makie_btn.setStyleSheet(BUTTON_STYLE)
        out = getattr(self, '_makie_out', '')
        if code == 0 and out and os.path.exists(out):
            self.set_status(f'Makie figure saved to {os.path.basename(out)}.')
            try:
                QDesktopServices.openUrl(QUrl.fromLocalFile(out))
            except Exception:
                pass
        else:
            try:
                err = bytes(self._makie_proc.readAllStandardError()).decode(errors='ignore')
            except Exception:
                err = ''
            self.set_status(f'Makie render failed (exit {code}). {err.strip()[-300:]}')


def main():
    app = QApplication(sys.argv)
    apply_app_style(app, app_id='Atomize.ITC.DataTreatment1D')
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
