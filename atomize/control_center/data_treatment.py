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
import sys
import numpy as np
from pathlib import Path

import pyqtgraph as pg
from pyqtgraph.dockarea import DockArea
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QComboBox, QGridLayout, QVBoxLayout, QHBoxLayout, QTabWidget, QDoubleSpinBox,
    QSpinBox, QLineEdit, QCheckBox, QFrame, QSizePolicy, QScrollArea)

import atomize.general_modules.general_functions as general
import atomize.general_modules.csv_opener_saver as openfile
import atomize.general_modules.bruker_opener as bruker
import atomize.math_modules.least_square_fitting_modules as fitting
import atomize.math_modules.signal_processing as sigproc
import atomize.math_modules.fft as fft_module
import atomize.math_modules.deer as deer_module
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

# Solid-accent "busy" variant for the Run-DEER button while an inversion is in
# progress (explicit colours so it stays yellow even while disabled).
BUTTON_BUSY_STYLE = (
    f"QPushButton {{border-radius: 4px; background-color: {ACCENT}; "
    f"border-style: inset; color: {BG}; font-weight: bold; padding: 4px; }} "
    f"QPushButton:disabled {{background-color: {ACCENT}; color: {BG}; }}")


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

        # label -> (x, y) of every loaded source curve
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
        # persistent preview curves: label -> pyqtgraph PlotDataItem, reused via
        # setData so live updates never tear down / rebuild plot items
        self._curve_items = {}
        # identity of what is currently plotted (curve labels + x-axis name); a
        # change means a new result / view / unit, which re-fits the axes once.
        self._plot_key = None
        # set while promoting a result so selecting the new input does not
        # immediately re-apply the operation to it
        self._suppress_live = False

        # DEER/PDS analysis state: last full result dict, the draggable
        # background-start cursor, and a guard against cursor<->spinbox echo.
        self.deer_result = None
        self._bg_cursor = None
        self._bg_cursor_end = None     # draggable background-end cursor
        self._suppress_cursor = False
        self._lcurve_marker = None     # highlighted point on the L-curve view

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
        # click-to-pick alpha on the DEER L-curve view (single-click; the
        # crosshair toggle uses double-click, so the two don't conflict)
        self.plot_widget.scene().sigMouseClicked.connect(self._on_plot_click)
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
        self.pair_check.setChecked(True)
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
        self.tabs.addTab(self._build_deer_tab(), 'DEER / PDS')
        self.tabs.currentChanged.connect(self._on_tab_changed)
        # Note: tab changes deliberately do NOT trigger _live_update. Re-running
        # the new tab's op on switch is redundant and, after a "Result → input"
        # chain, would re-transform an already-transformed input (e.g. FFT of an
        # FFT). The preview recomputes only on a parameter change or Apply.
        self.tabs.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        # Floor the tab strip at its full width so all tabs stay visible without
        # the scroll arrows (the 6 tabs need ~465 px); the graph takes the rest.
        self.tabs.setMinimumWidth(475)
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
        btn_clear_res = QPushButton('Clear result')
        btn_clear_res.setStyleSheet(BUTTON_STYLE)
        btn_clear_res.clicked.connect(self.clear_result)
        out_row.addWidget(btn_plot)
        out_row.addWidget(btn_save)
        out_row.addWidget(btn_chain)
        out_row.addWidget(btn_clear_res)
        panel.addLayout(out_row)

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
        self.fit_no_offset = QCheckBox('Fix offset = 0 (drop the b / c baseline term)')
        self.fit_no_offset.setStyleSheet(CHECKBOX_STYLE)
        grid.addWidget(self.fit_no_offset, 1, 0, 1, 2)
        btn = QPushButton('Fit')
        btn.setStyleSheet(BUTTON_STYLE)
        btn.clicked.connect(self.do_fit)
        grid.addWidget(btn, 2, 0, 1, 2)
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
        grid.addWidget(fit_scroll, 3, 0, 1, 2)
        grid.setRowStretch(3, 1)
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

    # time-unit -> factor that converts the X axis into microseconds (kernel unit)
    DEER_TUNITS = {'µs': 1.0, 'ns': 1e-3, 'ms': 1e3}

    def _build_deer_tab(self):
        w = QWidget()
        grid = QGridLayout(w)
        r = 0
        grid.addWidget(self._note('Background-correct V(t) and invert the dipolar '
                                  'kernel to a distance distribution P(r) by Tikhonov '
                                  '+ NNLS. Uses the I/primary channel as the real '
                                  'V(t) (phase to real first). Needs scipy.'),
                       r, 0, 1, 2); r += 1

        grid.addWidget(self._label('Time unit'), r, 0)
        self.deer_tunit = QComboBox()
        self.deer_tunit.setStyleSheet(COMBO_STYLE)
        self.deer_tunit.addItems(list(self.DEER_TUNITS.keys()))
        self.deer_tunit.currentIndexChanged.connect(self._live_update)
        grid.addWidget(self.deer_tunit, r, 1); r += 1

        grid.addWidget(self._label('Zero time (t0)'), r, 0)
        t0_row = QHBoxLayout()
        self.deer_t0 = QDoubleSpinBox()
        self.deer_t0.setStyleSheet(DSPIN_STYLE)
        self.deer_t0.setRange(-1e9, 1e9)
        self.deer_t0.setDecimals(4)
        self.deer_t0.setSingleStep(0.05)
        self.deer_t0.setValue(0.0)
        self.deer_t0.valueChanged.connect(self._live_update)
        btn_t0 = QPushButton('Max')
        btn_t0.setStyleSheet(BUTTON_STYLE)
        btn_t0.clicked.connect(self._deer_t0_max)
        t0_row.addWidget(self.deer_t0); t0_row.addWidget(btn_t0)
        grid.addLayout(t0_row, r, 1); r += 1

        grid.addWidget(self._label('Background start'), r, 0)
        bg_row = QHBoxLayout()
        self.deer_bgstart = QDoubleSpinBox()
        self.deer_bgstart.setStyleSheet(DSPIN_STYLE)
        self.deer_bgstart.setRange(-1e9, 1e9)
        self.deer_bgstart.setDecimals(4)
        self.deer_bgstart.setSingleStep(0.05)
        self.deer_bgstart.valueChanged.connect(self._live_update)
        btn_mid = QPushButton('Mid')
        btn_mid.setStyleSheet(BUTTON_STYLE)
        btn_mid.clicked.connect(self._deer_bgstart_mid)
        bg_row.addWidget(self.deer_bgstart); bg_row.addWidget(btn_mid)
        grid.addLayout(bg_row, r, 1); r += 1

        grid.addWidget(self._label('Background end'), r, 0)
        bge_row = QHBoxLayout()
        self.deer_bgend = QDoubleSpinBox()
        self.deer_bgend.setStyleSheet(DSPIN_STYLE)
        self.deer_bgend.setRange(-1e9, 1e9)
        self.deer_bgend.setDecimals(4)
        self.deer_bgend.setSingleStep(0.05)
        self.deer_bgend.setValue(0.0)            # 0 / ≤ start ⇒ no upper limit
        self.deer_bgend.valueChanged.connect(self._live_update)
        btn_end = QPushButton('End')
        btn_end.setStyleSheet(BUTTON_STYLE)
        btn_end.clicked.connect(self._deer_bgend_max)
        bge_row.addWidget(self.deer_bgend); bge_row.addWidget(btn_end)
        grid.addLayout(bge_row, r, 1); r += 1

        grid.addWidget(self._label('Background dim.'), r, 0)
        dim_row = QHBoxLayout()
        self.deer_dim = QDoubleSpinBox()
        self.deer_dim.setStyleSheet(DSPIN_STYLE)
        self.deer_dim.setRange(1.0, 6.0)
        self.deer_dim.setDecimals(2)
        self.deer_dim.setSingleStep(0.1)
        self.deer_dim.setValue(3.0)
        self.deer_dim.valueChanged.connect(self._live_update)
        self.deer_fitdim = QCheckBox('fit')
        self.deer_fitdim.setStyleSheet(CHECKBOX_STYLE)
        self.deer_fitdim.stateChanged.connect(self._live_update)
        dim_row.addWidget(self.deer_dim); dim_row.addWidget(self.deer_fitdim)
        grid.addLayout(dim_row, r, 1); r += 1

        grid.addWidget(self._label('Background fit'), r, 0)
        self.deer_engine = QComboBox()
        self.deer_engine.setStyleSheet(COMBO_STYLE)
        self.deer_engine.addItems(['Sequential', 'Joint (global)'])
        self.deer_engine.setToolTip(
            'Sequential: fit the background on the tail window, divide it out, '
            'then invert (fast).\nJoint (global): fit background + modulation '
            'depth together with P(r) in one pass (DeerLab-style) — more robust '
            'when the background window is short or hard to place.')
        self.deer_engine.currentIndexChanged.connect(self._live_update)
        grid.addWidget(self.deer_engine, r, 1); r += 1

        grid.addWidget(self._label('Distance min/max (nm)'), r, 0)
        rr_row = QHBoxLayout()
        self.deer_rmin = QDoubleSpinBox()
        self.deer_rmin.setStyleSheet(DSPIN_STYLE)
        self.deer_rmin.setRange(0.5, 50.0); self.deer_rmin.setDecimals(2)
        self.deer_rmin.setSingleStep(0.1); self.deer_rmin.setValue(1.5)
        self.deer_rmin.valueChanged.connect(self._live_update)
        self.deer_rmax = QDoubleSpinBox()
        self.deer_rmax.setStyleSheet(DSPIN_STYLE)
        self.deer_rmax.setRange(0.5, 50.0); self.deer_rmax.setDecimals(2)
        self.deer_rmax.setSingleStep(0.1); self.deer_rmax.setValue(8.0)
        self.deer_rmax.valueChanged.connect(self._live_update)
        rr_row.addWidget(self.deer_rmin); rr_row.addWidget(self.deer_rmax)
        grid.addLayout(rr_row, r, 1); r += 1

        grid.addWidget(self._label('Distance points'), r, 0)
        self.deer_rn = QSpinBox()
        self.deer_rn.setStyleSheet(SPIN_STYLE)
        self.deer_rn.setRange(20, 2000); self.deer_rn.setValue(200)
        self.deer_rn.valueChanged.connect(self._live_update)
        grid.addWidget(self.deer_rn, r, 1); r += 1

        grid.addWidget(self._label('Regularization α'), r, 0)
        al_row = QHBoxLayout()
        self.deer_alpha_auto = QCheckBox('Auto (GCV)')
        self.deer_alpha_auto.setStyleSheet(CHECKBOX_STYLE)
        self.deer_alpha_auto.setToolTip(
            'Choose the regularization weight automatically by generalized '
            'cross-validation (robust against the spiky P(r) the L-curve corner '
            'gives on DEER data). Uncheck to set α manually, or pick it on the '
            'L-curve view.')
        self.deer_alpha_auto.setChecked(True)
        self.deer_alpha_auto.stateChanged.connect(self._deer_alpha_toggle)
        self.deer_alpha_auto.stateChanged.connect(self._live_update)
        self.deer_alpha = QDoubleSpinBox()
        self.deer_alpha.setStyleSheet(DSPIN_STYLE)
        self.deer_alpha.setRange(1e-4, 1e4); self.deer_alpha.setDecimals(4)
        self.deer_alpha.setSingleStep(0.1); self.deer_alpha.setValue(1.0)
        self.deer_alpha.setEnabled(False)
        self.deer_alpha.valueChanged.connect(self._live_update)
        al_row.addWidget(self.deer_alpha_auto); al_row.addWidget(self.deer_alpha)
        grid.addLayout(al_row, r, 1); r += 1

        grid.addWidget(self._label('Show'), r, 0)
        self.deer_show = QComboBox()
        self.deer_show.setStyleSheet(COMBO_STYLE)
        self.deer_show.addItems(['Distance P(r)', 'Form factor + fit',
                                 'Background fit', 'L-curve'])
        self.deer_show.currentIndexChanged.connect(self._deer_rerender)
        grid.addWidget(self.deer_show, r, 1); r += 1

        run_row = QHBoxLayout()
        btn = QPushButton('Run DEER')
        btn.setStyleSheet(BUTTON_STYLE)
        btn.clicked.connect(self.do_deer)
        self.deer_run_btn = btn               # kept for the busy-highlight toggle
        btn_exp = QPushButton('Export all…')
        btn_exp.setStyleSheet(BUTTON_STYLE)
        btn_exp.clicked.connect(self.save_deer_all)
        run_row.addWidget(btn); run_row.addWidget(btn_exp)
        grid.addLayout(run_row, r, 0, 1, 2); r += 1

        self.deer_info = QLabel('')
        self.deer_info.setStyleSheet(LABEL_STYLE)
        self.deer_info.setWordWrap(True)
        self.deer_info.setTextFormat(Qt.TextFormat.RichText)
        self.deer_info.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        info_scroll = QScrollArea()
        info_scroll.setStyleSheet(SCROLL_STYLE)
        info_scroll.setWidgetResizable(True)
        info_scroll.setWidget(self.deer_info)
        grid.addWidget(info_scroll, r, 0, 1, 2)
        grid.setRowStretch(r, 1)
        return w

    def _deer_alpha_toggle(self, *args):
        self.deer_alpha.setEnabled(not self.deer_alpha_auto.isChecked())

    def _deer_bgstart_mid(self):
        """Set the background start to the middle of the current X axis."""
        x, _ = self.i_xy()
        if x is None or not len(x):
            self.set_status('Load a V(t) trace first.')
            return
        x = np.asarray(x, dtype=float)
        self.deer_bgstart.setValue(float(x[0] + 0.5*(x[-1] - x[0])))

    def _deer_t0_max(self):
        """Set t0 to the position of the |V(t)| maximum (echo centre)."""
        x, v = self.i_xy()
        if x is None or not len(x):
            self.set_status('Load a V(t) trace first.')
            return
        x = np.asarray(x, dtype=float)
        v = np.asarray(v, dtype=float)
        self.deer_t0.setValue(float(x[int(np.argmax(np.abs(v)))]))

    def _deer_bgend_max(self):
        """Set the background end to the last point of the current X axis."""
        x, _ = self.i_xy()
        if x is None or not len(x):
            self.set_status('Load a V(t) trace first.')
            return
        self.deer_bgend.setValue(float(np.asarray(x, dtype=float)[-1]))

    # ------------------------------------------------------------- loading
    def _register_datasets(self, mapping):
        self.datasets = dict(mapping)
        self._refresh_combos(select_i=next(iter(mapping), None),
                             select_q=(list(mapping)[1] if len(mapping) > 1 else None))

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

    def _preset_deer_unit(self, label):
        """If an X label carries a time unit like 'Time (ns)', preset the DEER
        time-unit selector to match (mirrors the Bruker loader)."""
        u = ''
        if label and label.endswith(')') and '(' in label:
            u = label[label.rfind('(') + 1:-1].strip().lower()
        tmap = {'ns': 'ns', 'us': 'µs', 'µs': 'µs', 'μs': 'µs', 'ms': 'ms'}
        if u in tmap:
            self.deer_tunit.setCurrentText(tmap[u])

    def open_csv(self):
        file_path = self.opener.open_file_dialog(multiprocessing=True)
        if not file_path or file_path == 'None':
            return
        try:
            _, data = self.opener.open_1d(file_path)
            data = np.atleast_2d(data)
            if data.shape[0] < 2:
                self.set_status('CSV needs at least two columns (X and Y).')
                return
            # Guard against accidentally loading a 2D matrix here: open_1d gives
            # one row per CSV column, so a [trace × point] dataset arrives as
            # hundreds/thousands of "curves". The 1D tool is for a handful of
            # columns (X + a few channels); send wide files to the 2D tool.
            if data.shape[0] > 6:
                self.set_status(f'This looks like a 2D dataset ({data.shape[0]} '
                                f'columns). The 1D tool takes at most 6 columns — '
                                f'open it in the 2D Data Treatment window instead.')
                return
            x = data[0]
            labels = self._csv_header_labels(file_path)
            mapping = {}
            for i in range(1, data.shape[0]):
                y = data[i]
                mask = ~(np.isnan(x) | np.isnan(y))
                name = labels[i] if (i < len(labels) and labels[i]) else f'Y{i}'
                while name in mapping:            # keep the dataset keys unique
                    name += "'"
                mapping[name] = (x[mask], y[mask])
            # axis name + unit from the X-column header (col 0), like the Bruker path
            if labels and labels[0]:
                self.xname_edit.setText(labels[0])
                self._preset_deer_unit(labels[0])
            self._register_datasets(mapping)
            self.set_status(f'Loaded {os.path.basename(file_path)} '
                            f'({data.shape[0] - 1} curve(s)).')
        except Exception as e:
            self.set_status(f'Could not read CSV: {e}')

    def open_bruker(self):
        """Load a Bruker native dataset (BES3T .DSC/.DTA or ESP/WinEPR .par/.spc).
        Complex traces register as a real+imag I/Q pair; a time axis in ns/µs/ms
        also presets the DEER time-unit selector."""
        nf = ['Bruker (*.DSC *.dsc *.DTA *.dta *.par *.spc *.PAR *.SPC)',
              'BES3T (*.DSC *.dsc *.DTA *.dta)',
              'ESP/WinEPR (*.par *.spc *.PAR *.SPC)', 'All files (*)']
        file_path = self.opener.open_file_dialog(multiprocessing=True, name_filters=nf)
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
        self._register_datasets(mapping)          # selects first two as I / Q
        if res['complex']:
            self.pair_check.setChecked(True)
        unit = f' ({res["x_unit"]})' if res['x_unit'] else ''
        self.xname_edit.setText(f'{res["x_name"]}{unit}')
        u = (res['x_unit'] or '').strip().lower()
        tmap = {'ns': 'ns', 'us': 'µs', 'µs': 'µs', 'μs': 'µs', 'ms': 'ms'}
        if u in tmap:                              # preset the DEER time unit
            self.deer_tunit.setCurrentText(tmap[u])
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
            header_count = 0
            with open(BUFFER_PATH, 'r') as fh:
                for line in fh:
                    if not line.startswith('#'):
                        break
                    header_count += 1
                    if 'labels:' in line:
                        labels = line.split('labels:', 1)[1].strip().split('|')
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
            self._register_datasets(mapping)
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
        self.deer_result = None
        self._clear_bg_cursor()
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
        ops = {1: self.do_fft, 2: self.do_phase, 3: self.do_smooth, 4: self.do_filter,
               5: self.do_deer}
        fn = ops.get(self.tabs.currentIndex())
        if fn is not None:
            fn()

    def _apply_current_op(self):
        """Run the current tab's operation NOW (Fit included), so the result
        reflects the current tab and parameters regardless of live-update."""
        ops = {0: self.do_fit, 1: self.do_fft, 2: self.do_phase, 3: self.do_smooth,
               4: self.do_filter, 5: self.do_deer}
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

    def clear_result(self):
        """Drop the computed-result overlay, keep the loaded source data."""
        self._reset_result()
        self.redraw()
        self.set_status('Result cleared.')

    def clear_all(self):
        """Reset the window: forget all loaded data, result and selectors."""
        self.datasets = {}
        self._reset_result()
        self.deer_result = None
        self._clear_bg_cursor()
        self.step_counter = 0
        for combo in (self.i_combo, self.q_combo):
            combo.blockSignals(True)
            combo.clear()
            combo.blockSignals(False)
        for lbl in list(self._curve_items):
            self.plot_widget.removeItem(self._curve_items.pop(lbl))
            try:
                self.legend.removeItem(lbl)
            except Exception:
                pass
        self.set_status('Cleared. Load a dataset to begin.')

    # ----------------------------------------------------- preview (in-process)
    SOURCE_PENS = [(120, 170, 255), (220, 120, 220)]   # I = blue, Q = magenta
    RESULT_PENS = [(211, 194, 78), (120, 220, 150), (230, 140, 90)]

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
        self.plot_widget.setLabel('bottom', xname)
        # only the DEER L-curve view uses a left-axis label; clear it otherwise
        self.plot_widget.setLabel('left', '')

        # Auto-scale the view when the plotted *content* changes (new result,
        # DEER 'Show' view, time unit, load/clear) — but not on same-view live
        # tweaks, so a manual zoom survives while dragging parameters.
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

    # ---------------------------------------------------------- operations
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
        rows = ''.join(f'{n} = {v:.4g} &plusmn; {e:.2g}<br>'
                       for n, v, e in zip(res['param_names'], res['popt'], res['perr']))
        html = (f'<div style="line-height: 165%;">'
                f'<b style="color: rgb(211, 194, 78);">{model}</b><br>'
                f'{rows}'
                f'R&sup2; = {res["r_squared"]:.5f}</div>')
        self.fit_result.setText(html)
        self.set_status(f'Fit done. R² = {res["r_squared"]:.5f}')

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
        freq = np.fft.fftfreq(n, dt)
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
        meta = [f'FFT ({"complex I+iQ" if pair else "real"}), output: {mode}',
                'frequency in 1/(X units)',
                f'skip {skip} leading pts (echo centre)' if skip else 'no leading skip',
                f'window: {win}' + (f' (param={wparam:.4g})'
                                    if win in self.WINDOW_PARAM else ''),
                f'points: {len(signal)} -> {n} (zero fill: {zf})',
                f'passband: {ftype}' + ('' if ftype == 'None' else
                    f' (lo={self.fft_cut_lo.value():.4g}, hi={self.fft_cut_hi.value():.4g} x f_max)')]
        self._set_result(freq, channels, meta, show_source=False, xname='Frequency')
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

    # ------------------------------------------------------------- DEER / PDS
    def _deer_tfactor(self):
        """Factor converting the X axis (chosen time unit) into microseconds."""
        return self.DEER_TUNITS.get(self.deer_tunit.currentText(), 1.0)

    def do_deer(self):
        """Background-correct V(t) and invert to P(r) (Tikhonov + NNLS)."""
        x, v = self.i_xy()
        if x is None or len(x) < 8:
            self.set_status('Load a V(t) trace first (I/primary channel).')
            return
        x = np.asarray(x, dtype=float)
        v = np.asarray(v, dtype=float)
        tf = self._deer_tfactor()
        t0 = float(self.deer_t0.value())   # zero-time, shifts the kernel axis
        t_us = (x - t0)*tf               # kernel works in microseconds
        bg_us = (float(self.deer_bgstart.value()) - t0)*tf
        # background end: 0 or ≤ start ⇒ no upper limit (fit to the trace end)
        end_disp = float(self.deer_bgend.value())
        bg_end_us = (end_disp - t0)*tf if end_disp > float(self.deer_bgstart.value()) else None
        rmin, rmax = self.deer_rmin.value(), self.deer_rmax.value()
        if rmax <= rmin:
            self.set_status('Distance max must exceed min.')
            return
        r = np.linspace(rmin, rmax, int(self.deer_rn.value()))
        alpha = None if self.deer_alpha_auto.isChecked() else float(self.deer_alpha.value())
        engine = 'joint' if self.deer_engine.currentIndex() == 1 else 'sequential'
        # highlight the button yellow while the (blocking) inversion runs
        self.deer_run_btn.setEnabled(False)
        self.deer_run_btn.setStyleSheet(BUTTON_BUSY_STYLE)
        QApplication.processEvents()
        try:
            res = deer_module.deer_invert(
                t_us, v, r=r, bg_start=bg_us, bg_end=bg_end_us,
                dim=float(self.deer_dim.value()),
                fit_dim=self.deer_fitdim.isChecked(), alpha=alpha, engine=engine)
        except Exception as e:
            self.set_status(f'DEER failed: {e}')
            return
        finally:
            self.deer_run_btn.setStyleSheet(BUTTON_STYLE)
            self.deer_run_btn.setEnabled(True)
        self.deer_result = res
        # display/cursors stay in the original acquisition time; only the
        # kernel used the t0-shifted axis internally.
        res['t'] = x*tf
        if bg_end_us is not None:
            res['background']['bg_end'] = end_disp*tf
        if self.deer_alpha_auto.isChecked():
            self.deer_alpha.blockSignals(True)
            self.deer_alpha.setValue(float(res['alpha']))
            self.deer_alpha.blockSignals(False)

        F, Ff = res['form_factor'], res['F_fit']
        ss_tot = float(np.sum((F - F.mean())**2)) or 1.0
        r2 = 1 - float(np.sum((F - Ff)**2))/ss_tot
        P = res['P_density']
        r_peak = float(res['r'][int(np.argmax(P))])
        r_mean = float(np.sum(res['r']*res['P_norm']))
        self.deer_info.setText(
            '<div style="line-height: 165%;">'
            f'<b style="color: rgb(211, 194, 78);">P(r)</b><br>'
            f'mod. depth λ = {res["lambda"]:.3f}<br>'
            f'bg decay k = {res["k"]:.4g}, dim = {res["dim"]:.2f}<br>'
            f'α = {res["alpha"]:.4g}<br>'
            f'peak r = {r_peak:.3f} nm<br>'
            f'mean r = {r_mean:.3f} nm<br>'
            f'form-factor R² = {r2:.4f}</div>')
        self._deer_render()
        self.set_status(f'DEER: λ={res["lambda"]:.3f}, α={res["alpha"]:.3g}, '
                        f'peak r={r_peak:.2f} nm, R²={r2:.3f}.')

    def _deer_rerender(self, *args):
        """Re-show the stored DEER result under the current 'Show' selection."""
        if self.deer_result is not None:
            self._deer_render()

    def _deer_render(self):
        """Push the chosen DEER view (distance / form factor / background) to the
        single-axis preview, and place the draggable background cursor on the
        time-domain views."""
        res = self.deer_result
        if res is None:
            return
        view = self.deer_show.currentText()
        tf = self._deer_tfactor()
        tunit = self.deer_tunit.currentText()
        t_disp = res['t']/tf
        bge = res['background'].get('bg_end')
        bg_win = (f'bg start {self.deer_bgstart.value():.4g} {tunit}'
                  + (f', bg end {bge/tf:.4g} {tunit}' if bge is not None
                     else ' (to end)'))
        common = [f'DEER/PDS — λ={res["lambda"]:.4g}, k={res["k"]:.4g}, '
                  f'dim={res["dim"]:.3g}, α={res["alpha"]:.4g}',
                  f'time unit {tunit}, r {res["r"][0]:.3g}–{res["r"][-1]:.3g} nm '
                  f'({len(res["r"])} pts), {bg_win}']
        if view == 'Distance P(r)':
            meta = common + ['column: P(r) density (integral = 1)']
            self._set_result(res['r'], [('P(r)', res['P_density'])], meta,
                             show_source=False, xname='Distance (nm)')
            self._show_bg_cursor(False)
            self._show_lcurve_marker(False)
        elif view == 'Form factor + fit':
            meta = common + ['columns: form factor F(t), K·P fit']
            self._set_result(t_disp, [('F(t)', res['form_factor']),
                                      ('K·P fit', res['F_fit'])], meta,
                             show_source=False, xname=f'Time ({tunit})')
            self._show_bg_cursor(True)
            self._show_lcurve_marker(False)
        elif view == 'Background fit':
            bg = res['background']
            level = (1 - res['lambda'])*bg['B']
            meta = common + ['columns: V(t) normalized, fitted background (1-λ)·B(t)']
            self._set_result(t_disp, [('V(t)', bg['V_norm']),
                                      ('(1-λ)·B', level)], meta,
                             show_source=False, xname=f'Time ({tunit})')
            self._show_bg_cursor(True)
            self._show_lcurve_marker(False)
        else:  # L-curve
            self._show_bg_cursor(False)
            lc = res.get('l_curve')
            if lc is None:
                self.set_status('No L-curve available for this result.')
                return
            x, y = self._lcurve_xy(lc)
            meta = common + ['L-curve: log₁₀ residual ‖KP−F‖ vs log₁₀ ‖LP‖ over α',
                             'click a point to pick α (switches to manual)']
            self._set_result(x, [('L-curve', y)], meta, show_source=False,
                             xname='log₁₀ residual  ‖KP−F‖')
            self.plot_widget.setLabel('left', 'log₁₀ roughness  ‖LP‖')
            idx = self._lcurve_index(lc, res['alpha'])
            self._show_lcurve_marker(True, x[idx], y[idx])

    @staticmethod
    def _lcurve_xy(lc):
        x = np.log10(np.asarray(lc['rho'], float) + 1e-300)
        y = np.log10(np.asarray(lc['eta'], float) + 1e-300)
        return x, y

    @staticmethod
    def _lcurve_index(lc, alpha):
        """Index of the L-curve grid point nearest the chosen alpha (log space)."""
        a = np.asarray(lc['alphas'], float)
        return int(np.argmin(np.abs(np.log(a) - np.log(max(alpha, 1e-300)))))

    def _show_lcurve_marker(self, visible, x=None, y=None):
        if self._lcurve_marker is None:
            self._lcurve_marker = pg.ScatterPlotItem(
                size=14, symbol='o', pen=pg.mkPen((20, 20, 30), width=1.5),
                brush=pg.mkBrush(211, 194, 78))
            self._lcurve_marker.setZValue(20)
            self.plot_widget.addItem(self._lcurve_marker)
        if not visible:
            self._lcurve_marker.setVisible(False)
            return
        self._lcurve_marker.setData([x], [y])
        self._lcurve_marker.setVisible(True)

    def _on_plot_click(self, event):
        """On the DEER L-curve view, pick the α of the nearest L-curve point."""
        if (self.tabs.currentIndex() != 5 or self.deer_result is None
                or self.deer_show.currentText() != 'L-curve'):
            return
        lc = self.deer_result.get('l_curve')
        if lc is None:
            return
        vb = self.plot_widget.plotItem.vb
        pt = vb.mapSceneToView(event.scenePos())
        x, y = self._lcurve_xy(lc)
        # nearest point in the (normalized) log-log plane
        rx = (x.max() - x.min()) or 1.0
        ry = (y.max() - y.min()) or 1.0
        d = ((x - pt.x())/rx)**2 + ((y - pt.y())/ry)**2
        idx = int(np.argmin(d))
        alpha = float(lc['alphas'][idx])
        self.deer_alpha_auto.blockSignals(True)
        self.deer_alpha_auto.setChecked(False)
        self.deer_alpha_auto.blockSignals(False)
        self.deer_alpha.setEnabled(True)
        self.deer_alpha.blockSignals(True)
        self.deer_alpha.setValue(alpha)
        self.deer_alpha.blockSignals(False)
        self.do_deer()

    def _show_bg_cursor(self, visible):
        """Show/position (or hide) the draggable background-start cursor on the
        preview. The cursor lives in display time units and drives deer_bgstart."""
        if self._bg_cursor is None:
            self._bg_cursor = pg.InfiniteLine(
                angle=90, movable=True,
                pen=pg.mkPen((211, 194, 78), width=2, style=Qt.PenStyle.DashLine),
                hoverPen=pg.mkPen((255, 230, 120), width=3),
                label='bg start', labelOpts={'color': (211, 194, 78),
                                             'position': 0.92})
            self.plot_widget.addItem(self._bg_cursor)
            self._bg_cursor.sigPositionChangeFinished.connect(self._on_bg_cursor)
        if not visible:
            self._bg_cursor.setVisible(False)
            self._show_bg_cursor_end(False)
            return
        self._suppress_cursor = True
        self._bg_cursor.setValue(float(self.deer_bgstart.value()))
        self._bg_cursor.setVisible(True)
        self._suppress_cursor = False
        self._show_bg_cursor_end(True)      # mirror visibility on time-domain views

    def _on_bg_cursor(self, *args):
        """User dragged the background cursor: update the spin box and re-run."""
        if self._suppress_cursor or self._bg_cursor is None:
            return
        self.deer_bgstart.blockSignals(True)
        self.deer_bgstart.setValue(float(self._bg_cursor.value()))
        self.deer_bgstart.blockSignals(False)
        self.do_deer()

    def _show_bg_cursor_end(self, visible):
        """Show/position (or hide) the draggable background-end cursor. It only
        appears when an end limit is active (deer_bgend > deer_bgstart); dragging
        it drives deer_bgend, in display time units."""
        if self._bg_cursor_end is None:
            self._bg_cursor_end = pg.InfiniteLine(
                angle=90, movable=True,
                pen=pg.mkPen((120, 200, 255), width=2, style=Qt.PenStyle.DashLine),
                hoverPen=pg.mkPen((180, 225, 255), width=3),
                label='bg end', labelOpts={'color': (120, 200, 255),
                                           'position': 0.84})
            self.plot_widget.addItem(self._bg_cursor_end)
            self._bg_cursor_end.sigPositionChangeFinished.connect(self._on_bg_cursor_end)
        active = float(self.deer_bgend.value()) > float(self.deer_bgstart.value())
        if not (visible and active):
            self._bg_cursor_end.setVisible(False)
            return
        self._suppress_cursor = True
        self._bg_cursor_end.setValue(float(self.deer_bgend.value()))
        self._bg_cursor_end.setVisible(True)
        self._suppress_cursor = False

    def _on_bg_cursor_end(self, *args):
        """User dragged the background-end cursor: update the spin box and re-run."""
        if self._suppress_cursor or self._bg_cursor_end is None:
            return
        self.deer_bgend.blockSignals(True)
        self.deer_bgend.setValue(float(self._bg_cursor_end.value()))
        self.deer_bgend.blockSignals(False)
        self.do_deer()

    def _clear_bg_cursor(self):
        """Hide all DEER overlays (background start/end cursors + L-curve marker)."""
        if self._bg_cursor is not None:
            self._bg_cursor.setVisible(False)
        if self._bg_cursor_end is not None:
            self._bg_cursor_end.setVisible(False)
        if self._lcurve_marker is not None:
            self._lcurve_marker.setVisible(False)

    def _on_tab_changed(self, *args):
        """Hide the DEER overlays whenever the DEER tab is not active."""
        if self.tabs.currentIndex() != 5:
            self._clear_bg_cursor()

    def save_deer_all(self):
        """Write every DEER stage to a set of sibling CSVs derived from one
        chosen path: <base>_distance / _formfactor / _background / _lcurve.csv."""
        res = self.deer_result
        if res is None:
            self.set_status('Run DEER first — nothing to export.')
            return
        file_path = self.opener.create_file_dialog(multiprocessing=True)
        if not file_path or file_path == 'None':
            return
        base = file_path[:-4] if file_path.lower().endswith('.csv') else file_path
        tunit = self.deer_tunit.currentText()
        t_disp = res['t']/self._deer_tfactor()
        bg = res['background']
        hdr = ['DEER/PDS analysis (Tikhonov + NNLS)',
               f'lambda = {res["lambda"]:.6g}, k = {res["k"]:.6g}, '
               f'dim = {res["dim"]:.6g}, alpha = {res["alpha"]:.6g}',
               f'r {res["r"][0]:.4g}-{res["r"][-1]:.4g} nm ({len(res["r"])} pts), '
               f'time unit {tunit}, bg start {self.deer_bgstart.value():.6g} {tunit}'
               + (f', bg end {res["background"]["bg_end"]/self._deer_tfactor():.6g} {tunit}'
                  if res['background'].get('bg_end') is not None else ', bg end: trace end')]
        written = []

        def _save(suffix, cols, col_header):
            fn = f'{base}_{suffix}.csv'
            self.opener.save_data(fn, np.column_stack(cols),
                                  header='\n'.join(hdr + [col_header]), mode='w')
            written.append(os.path.basename(fn))

        _save('distance', [res['r'], res['P_density'], res['P_norm']],
              'r (nm), P(r) density, P (masses)')
        _save('formfactor', [t_disp, res['form_factor'], res['F_fit'], res['residuals']],
              f'time ({tunit}), F(t), K*P fit, residuals')
        _save('background', [t_disp, bg['V_norm'], bg['B'], (1 - res['lambda'])*bg['B']],
              f'time ({tunit}), V(t) norm, B(t), (1-lambda)*B(t)')
        lc = res.get('l_curve')
        if lc is not None:
            _save('lcurve', [lc['alphas'], lc['rho'], lc['eta'], lc['curvature']],
                  'alpha, residual norm, solution norm, curvature')
        self.set_status('Exported DEER stages: ' + ', '.join(written))

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
        file_path = self.opener.create_file_dialog(multiprocessing=True)
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


def main():
    app = QApplication(sys.argv)
    apply_app_style(app, app_id='Atomize.ITC.DataTreatment1D')
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
