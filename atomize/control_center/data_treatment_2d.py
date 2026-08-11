#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
2D Data Treatment control-center window.

Standalone QProcess launched from the "EPR Endstation Control" tab, the 2D
sibling of data_treatment.py, for I/Q 2D datasets (echo decay / FID vs a
parameter). It mirrors the phase_cor.py workflow:

  * I/Q loading by name convention — open `name.csv` (I); `name_1.csv` (Q) is
    loaded automatically. Each file is a matrix [trace, point] (rows = the
    slow/indirect parameter, columns = the fast within-trace axis). An `.h5`
    file holds both quadratures, and its axis datasets fill the axis fields.
  * Axis metadata is set by hand (start / step / name / unit per axis) — there
    is no .param sidecar.
  * Independent, chainable operations:
      - Phase correction: multiply I+iQ by exp(i·(φ₀ + φ₁·x + φ₂·x²)) along the
        X axis (φ₀ in degrees, φ₁/φ₂ in rad per X-unit / X-unit²).
      - FFT (selectable axis): complex FFT of I+iQ along the within-trace (X) or
        the indirect (Y) axis, with optional apodization + zero fill; the
        transformed axis becomes frequency.
      - Filter (selectable axis): FFT → passband mask → inverse FFT along X, Y or
        both axes, each with its own type and cutoffs; the axes stay unchanged.
      - Shear: V′(t_dip, t) = V(t_dip + k·(t − t_ref), t) as an exact phase ramp on
        the dipolar-axis spectrum, straightening a dipolar ridge tilted across the
        echo (k = 1/2 for SIFTER), with a shear-scan estimator of k.

The window embeds the same CrossSectionDock the main GUI uses (heatmap + X/Y
cross-section sub-docks), fed in-process — no LivePlot IPC. Real and imaginary
parts ride along as the two toggleable frames of a (2, nX, nY) array (the frame
slider switches between them).
"Result → input" chains one operation into the next (e.g. phase → FFT).
"""

import os
import re
import sys
import numpy as np
from pathlib import Path

from PyQt6.QtCore import Qt, QFileSystemWatcher, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QComboBox, QGridLayout, QVBoxLayout, QHBoxLayout, QTabWidget, QDoubleSpinBox,
    QSpinBox, QLineEdit, QCheckBox, QFrame)

import atomize.general_modules.general_functions as general
import atomize.general_modules.csv_opener_saver as openfile
import atomize.general_modules.bruker_opener as bruker
import atomize.math_modules.signal_processing as sigproc
import atomize.math_modules.least_square_fitting_modules as fitting
import atomize.math_modules.fft as fft_module
# Reuse the main-window 2D plot stack (heatmap + X/Y cross-sections) so the
# embedded preview matches the main UI; fed in-process, no LivePlot IPC.
from pyqtgraph.dockarea import DockArea
from atomize.main.widgets import CrossSectionDock
# Shared look and form primitives — one source of truth for every tool.
from atomize.general_modules.gui_style import (BG, FG, ACCENT, BUTTON_STYLE,
                                               LABEL_STYLE, CHECKBOX_STYLE,
                                               DSPIN_STYLE, SPIN_STYLE,
                                               COMBO_STYLE, LINEEDIT_STYLE,
                                               TAB_STYLE)
import atomize.general_modules.gui_forms as gf

# Parameter-header viewer shared with the 1D tool (separate non-modal window).
from atomize.control_center.header_view import (HeaderWindow, read_header,
                                                params_to_lines)

# solid-yellow "busy" variant for the Run-fit button while a fit is in progress
# (explicit colour so it stays yellow even while the button is disabled).
BUTTON_BUSY_STYLE = ("QPushButton {border-radius: 4px; background-color: rgb(211, 194, 78); "
    "border-style: inset; color: rgb(42, 42, 64); font-weight: bold; padding: 4px; } "
    "QPushButton:disabled {background-color: rgb(211, 194, 78); color: rgb(42, 42, 64); }")

def _html_table(headers, rows):
    """Compact HTML table (Qt rich-text) from a header list and a list of cell-
    string rows; used for the fit-info panel."""
    head = ''.join(f'<th style="padding:1px 8px;">{h}</th>' for h in headers)
    body = ''.join('<tr>' + ''.join(f'<td style="padding:1px 8px;">{c}</td>'
                                    for c in r) + '</tr>' for r in rows)
    return f'<table style="border-collapse:collapse;"><tr>{head}</tr>{body}</table>'

WINDOWS = ['None', 'Hann', 'Hamming', 'Blackman', 'Bartlett', 'Flat-top',
           'Kaiser', 'Gaussian', 'Tukey']
ZEROFILL = ['None', '×2', '×4', '×8', 'Next pow₂']
FILTERS = ['Low-pass', 'High-pass', 'Band-pass']

# Bare SI units worth auto-prefixing on the plot axes: a plain 's' axis with a
# 2e-9 step should read '2 ns', not '2e-9 s'. Already-prefixed units ('ns',
# 'MHz', 'mV') and dimensionless labels are shown verbatim, since auto-prefixing
# them would double up ('kns', 'GMHz').
SI_BASE_UNITS = {'s', 'hz', 'v', 'a', 'g', 't', 'k', 'm', 'ev'}


def _si_autoprefix(unit):
    """True if `unit` is a bare SI base worth pyqtgraph auto-prefixing."""
    return str(unit).strip().lower() in SI_BASE_UNITS

# relaxation models exposed in the per-trace Fit tab (a curated subset of the
# shared fitter; for T1/T2 decays k / k1 / k2 are the time constants).
RELAX_MODELS = ['Exponential', 'Bi-exponential', 'Stretched exponential']

# one-shot mailbox the 1D Data Treatment window reads on "Load from plot";
# same path the main window writes on right-click → "Send to Data Treatment".
BUFFER_PATH = str(Path(__file__).resolve().parent.parent.parent / 'libs' / 'treatment_buffer.csv')
# the 2D counterpart: an .npz the main window writes for 2D image plots
# (i, q matrices + axis geometry/labels), consumed by this window's "Load from plot".
BUFFER_2D_PATH = str(Path(__file__).resolve().parent.parent.parent / 'libs' / 'treatment_buffer_2d.npz')

# remembers the folder of the last file opened/saved here so the next dialog
# starts there — shared with the 1D tool (one working data folder), survives a
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

# Per-tab explanations. These live behind the '?' chip on each tab rather than
# on the layout, where they used to outweigh the controls they describe.
_HELP_PHASE = (
    'Multiply I+iQ by exp(i·(φ₀ + φ₁·x + φ₂·x²)) along the X axis. '
    'First/second order are entered as a frequency offset: 50 → 50 MHz when x '
    'is in ns (coeff = 2π·value/1000 per x-unit). Run before FFT.')

_HELP_FFT = (
    'Complex FFT of I+iQ along the chosen axis (or both for a 2D transform); '
    'that axis becomes frequency. ns → MHz. Skip pts drops leading X points so '
    'the transform starts at the echo centre (removes the dead-time '
    'first-order phase).<br><br>'
    'The advanced passband masks the spectrum and leaves the result in the '
    'frequency domain; the Filter tab transforms back instead. Cutoffs are '
    'fractions of that axis\' maximum (Nyquist) frequency.')

_HELP_FILTER = (
    'FFT → zero the frequencies outside the passband → inverse FFT, along the '
    'chosen axis. Output is the cleaned I/Q data on the same axes; "Both" '
    'applies the X and Y filters independently.<br><br>'
    'Low-pass uses the high cutoff; High-pass uses the low cutoff; Band-pass '
    'uses both. Cutoffs are fractions of that axis\' maximum (Nyquist) '
    'frequency, set by its own point step.')

_HELP_SHEAR = (
    'Straightens a tilted dipolar ridge: V′(t_dip, t) = V(t_dip + k·(t − '
    't_ref), t), done as the exact phase ramp exp(2πi·ν_dip·k·(t − t_ref)) on '
    'the dipolar-axis spectrum — unitary, no interpolation loss. k is the '
    'ridge slope dt_dip/dt (1/2 for SIFTER).<br><br>'
    'Order matters, chaining each step with "Result → input": Phase tab, first '
    'order = the nominal IF in MHz → Filter tab, X low-pass → back to the '
    'Phase tab for Auto φ₁ (it re-runs Auto φ₀ after it) → shear. φ₁ is not '
    'optional: the nominal IF is off by a few hundred kHz, which twists the '
    'phase across the echo and cancels part of the very modulation the shear '
    'is recovering. Measure it <b>after</b> the low-pass — on a raw IF record '
    'the carrier estimate is swamped by out-of-band noise. Afterwards collapse '
    'the sheared map with the Slice tab — slice along the dipolar axis and '
    'average over the echo window. The ramp is circular, so rows wrap at the '
    'ends of the dipolar axis; keep the edges out of the analysis.')

_HELP_FIT = (
    'Fit every trace along the decay axis with a relaxation model. The chosen '
    'parameter is plotted vs the other axis as a 1D map (e.g. T<sub>m</sub> vs '
    'field). For k / k1 / k2 the value is the time constant in the decay-axis '
    'units.')

_HELP_SLICE = (
    'Send one trace to the standalone 1D Data Treatment window for fitting / '
    'phasing there. Pick the slice direction and the trace number (1-based, '
    'matching the heatmap cursor label). The trace is written to the transfer '
    'buffer only (not the main GUI). Then click "Load from plot" in the 1D '
    'window (I = slice Re, Q = slice Im).')

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
        self.bruker = bruker.Bruker_Opener()
        self.fitter = fitting.math()
        self.fit_map = None        # last per-trace fit result (dict)
        self._fitting = False      # re-entry guard for the per-trace fit loop
        self._cancel_fit = False   # set by the Cancel button to stop the loop

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
        self.last_dir = _load_last_dir()   # start file dialogs in the last folder

        # '#'-header of the loaded dataset + its name (empty for a plot load)
        self.header_lines = []
        self.header_name = ''
        self.header_window = None          # created on first use, then reused

        self.design()
        self.load_from_plot(silent=True)   # consume a pending buffer on startup
        self._init_buffer_watch()          # auto-load new data while open

    def _init_buffer_watch(self):
        """Watch the libs/ folder so a 2D plot sent from the main GUI while this
        window is already open is picked up automatically (no "Load from plot"
        click needed). A short debounce lets the writer finish before we read;
        the timer also coalesces the create/modify/delete burst into one load."""
        self._buf_timer = QTimer(self)
        self._buf_timer.setSingleShot(True)
        self._buf_timer.setInterval(200)
        self._buf_timer.timeout.connect(self._on_buffer_ready)
        self._buf_watcher = QFileSystemWatcher(self)
        watch_dir = os.path.dirname(BUFFER_2D_PATH)
        if os.path.isdir(watch_dir):
            self._buf_watcher.addPath(watch_dir)
        self._buf_watcher.directoryChanged.connect(lambda _p: self._buf_timer.start())

    def _on_buffer_ready(self):
        if os.path.isfile(BUFFER_2D_PATH):
            self.load_from_plot(silent=True)

    # ----------------------------------------------------------------- UI
    def design(self):
        self.setWindowTitle('2D Data Treatment')
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 'gui', 'icon_treat2d.ico')
        self.setWindowIcon(QIcon(icon_path))
        self.setMinimumHeight(560)
        self.setMinimumWidth(900)
        self.resize(1040, 720)
        # background on the QMainWindow (as in awg_phasing_insys.py) rather than
        # the central widget, so spinboxes keep their full native frame.
        self.setStyleSheet(f"background-color: {BG};")
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setSpacing(gf.PANEL_GAP)

        # ---- Left: embedded preview (in-process) — same CrossSectionDock
        # (heatmap + X/Y cross-sections) as the main GUI, for consistency. ----
        self.plot_area = DockArea()
        self.cross_dock = CrossSectionDock(name='Preview')
        self.cross_dock.close_button.hide()
        self.plot_area.addDock(self.cross_dock)
        # Follow the heatmap crosshair with the Slice-tab "Trace #": the dock's
        # own handler updates its cross indices first (connected in __init__), so
        # this slot, connected after, reads the fresh values. (Slice widgets are
        # built later in design(); the slot only fires on user mouse moves.)
        self.cross_dock.imageItem.scene().sigMouseMoved.connect(self._sync_slice_from_cursor)
        root.addWidget(self.plot_area, stretch=3)
        self._disable_si_prefix()
        # ---- end preview ----

        # ---- Vertical separator between graph and controls ----
        root.addWidget(gf.vline())

        # ---- Right: controls ----
        panel = QVBoxLayout()
        panel.setContentsMargins(*gf.PANEL_MARGINS)
        panel.setSpacing(8)
        root.addLayout(panel, stretch=2)

        # ---- Source ----
        panel.addWidget(self._heading('Source (I/Q 2D)'))
        btn_open = QPushButton('Open I/Q (CSV / HDF5)…')
        btn_open.setStyleSheet(BUTTON_STYLE)
        btn_open.clicked.connect(self.open_iq)
        btn_bruker = QPushButton('Open Bruker…')
        btn_bruker.setStyleSheet(BUTTON_STYLE)
        btn_bruker.clicked.connect(self.open_bruker)
        btn_buf = QPushButton('Load from plot')
        btn_buf.setStyleSheet(BUTTON_STYLE)
        btn_buf.clicked.connect(lambda: self.load_from_plot(silent=False))
        btn_clear = QPushButton('Clear')
        btn_clear.setStyleSheet(BUTTON_STYLE)
        btn_clear.clicked.connect(self.clear_all)
        # source actions and the File row share a 4-column grid, so Header…
        # comes out exactly as wide as Clear (a 3:1 stretch cannot: it has one
        # gap where the button row has three)
        src_grid = gf.equal_grid(4)
        for i, b in enumerate((btn_open, btn_bruker, btn_buf, btn_clear)):
            src_grid.addWidget(b, 0, i)
        panel.addLayout(src_grid)

        # Name of the dataset currently loaded (file basename, or 'Loaded from
        # plot' for the in-memory buffer).
        self.loaded_label = gf.hint('File: —')
        self.header_btn = QPushButton('Header…')
        self.header_btn.setStyleSheet(BUTTON_STYLE)
        self.header_btn.clicked.connect(self.show_header)
        src_grid.addWidget(self.loaded_label, 1, 0, 1, 3)
        src_grid.addWidget(self.header_btn, 1, 3)

        head = gf.FormPanel(field_width=gf.FIELD_W,
                            button_width=gf.BTN_W)
        self.transpose_check = head.add_check(
            'Transpose on load',
            tooltip='Swap the trace and point axes as the file is read.')
        self.tr_epr_check = head.add_check(
            'TR EPR: drop row 0',
            tooltip='Row 0 of a TR EPR file is the off-resonance reference '
                    'trace, not a field point. Drop it as the file is read, so '
                    'every trace lands on the field it was measured at — the '
                    'same rows the acquisition window plots live.')

        # ---- Axis metadata (reconstructed by hand; no .param) ----
        head.add_heading('Axes')
        self.xname_edit = QLineEdit('Time'); self.xname_edit.setStyleSheet(LINEEDIT_STYLE)
        self.xscale_edit = QLineEdit('ns');  self.xscale_edit.setStyleSheet(LINEEDIT_STYLE)
        head.add_row('X (within trace)', self.xname_edit, self.xscale_edit,
                     stretch=[2, 1])
        self.x0_spin = self._dspin(-1e12, 1e12, 3, 0.0)
        self.dx_spin = self._dspin(-1e12, 1e12, 3, 0.4)
        head.add_row('X start / step', self.x0_spin, self.dx_spin)
        self.yname_edit = QLineEdit('Delay'); self.yname_edit.setStyleSheet(LINEEDIT_STYLE)
        self.yscale_edit = QLineEdit('ns');   self.yscale_edit.setStyleSheet(LINEEDIT_STYLE)
        head.add_row('Y (indirect)', self.yname_edit, self.yscale_edit,
                     stretch=[2, 1])
        self.y0_spin = self._dspin(-1e12, 1e12, 3, 0.0)
        self.dy_spin = self._dspin(-1e12, 1e12, 3, 3.2)
        head.add_row('Y start / step', self.y0_spin, self.dy_spin)
        panel.addWidget(head)
        # title / unit edits only relabel the current plot in place (keep the
        # result); start / step edits change the geometry, so they reset to raw.
        for w in (self.xname_edit, self.xscale_edit, self.yname_edit, self.yscale_edit):
            w.textChanged.connect(self.on_axis_labels_changed)
        for s in (self.x0_spin, self.dx_spin, self.y0_spin, self.dy_spin):
            s.valueChanged.connect(self.on_axes_changed)

        self.live_check = gf.live_update_checkbox()
        panel.addWidget(self.live_check)

        panel.addWidget(self._hline())

        # ---- Operation tabs ----
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(TAB_STYLE)
        self.tabs.addTab(self._build_phase_tab(), 'Phase')
        self.tabs.addTab(self._build_fft_tab(), 'FFT')
        self.tabs.addTab(self._build_filter_tab(), 'Filter')
        self.tabs.addTab(self._build_shear_tab(), 'Shear')
        self.tabs.addTab(self._build_fit_tab(), 'Fit')
        self.tabs.addTab(self._build_slice_tab(), 'Slice')
        # Tab changes deliberately do NOT trigger _live_update: re-running the
        # new tab's op on switch is redundant and, after a "Result → input"
        # chain, would re-transform an already-transformed input (e.g. FFT of an
        # FFT). The preview recomputes only on a parameter change or Apply.
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

        self.status = gf.hint('Open an I/Q 2D dataset (name.csv + name_1.csv, or name.h5).')
        panel.addWidget(self.status)

        gf.apply_row_metrics(self)

    # ---- small helpers ----
    def _hline(self):
        return gf.hline()

    def _heading(self, text):
        return gf.heading(text)

    def _label(self, text):
        return gf.label(text)

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
        p = gf.FormPanel(field_width=gf.FIELD_W,
                         button_width=gf.BTN_W)
        p.add_title('Phase-correct I+iQ along X', help=_HELP_PHASE)

        self.phase_zero = self._dspin(0.0, 360.0, 2, 0.0, step=0.5)
        self.phase_zero.setSuffix(' deg')
        self.phase_zero.setWrapping(True)   # full cycle: 360 wraps back to 0
        self.phase_zero.valueChanged.connect(self._live_update)
        btn_autoph = QPushButton('Auto')
        btn_autoph.setStyleSheet(BUTTON_STYLE)
        btn_autoph.setToolTip(
            'Zero-order auto-phase: the principal axis of the echo samples '
            '(φ₀ = −½·angle Σ z² over the points above 25 % of the |I+iQ| '
            'envelope peak).<br><br>'
            'Measured on the trace itself, in the same frame the correction is '
            'applied in — the FFT-tab skip is <b>not</b> used here, since a '
            'skipped spectrum reports φ₀ in a shifted time origin (off by '
            '360·f·dt per skipped point for a line at offset f).<br><br>'
            'First/second order stay manual, and must be set <b>first</b> on '
            'undemodulated data: a carrier leaves nothing for φ₀ to fix. The '
            'status line reports any residual offset and the First-order value '
            'that removes it.')
        btn_autoph.clicked.connect(self.auto_phase_zero)
        p.add_row('Zero order', self.phase_zero, btn_autoph, stretch=[3, 1])

        self.phase_first = self._dspin(-1e6, 1e6, 3, 0.0, step=0.05)
        self.phase_first.setSuffix(' MHz')
        self.phase_first.valueChanged.connect(self._live_update)
        btn_autoph1 = QPushButton('Auto')
        btn_autoph1.setStyleSheet(BUTTON_STYLE)
        btn_autoph1.setToolTip(
            'First-order auto-phase: set it to the carrier the record actually '
            'sits at, from the phase increment per sample over the echo window, '
            'iterated to the fixed point — then re-run the zero-order Auto.<br><br>'
            'Do this <b>before</b> φ₀ on undemodulated data. The nominal IF is '
            'not accurate enough: an offset of a few hundred kHz twists the phase '
            'across the echo by tens of degrees, which no φ₀ can absorb, and it '
            'leaves a large imaginary residue.')
        btn_autoph1.clicked.connect(self.auto_phase_first)
        p.add_row('First order', self.phase_first, btn_autoph1, stretch=[3, 1],
                  tooltip='Frequency offset per x-unit: 50 → 50 MHz for x in ns.')

        self.phase_second = self._dspin(-1e6, 1e6, 4, 0.0, step=0.001)
        self.phase_second.setSuffix(' MHz')
        self.phase_second.valueChanged.connect(self._live_update)
        adv = p.add_advanced()
        adv.field_width, adv.button_width = gf.FIELD_W, gf.BTN_W
        adv.add_row('Second order', self.phase_second)

        btn = QPushButton('Apply correction')
        btn.setStyleSheet(BUTTON_STYLE)
        btn.clicked.connect(self.do_phase)
        p.add_button_row(btn, width=gf.ACTION_W)
        p.add_stretch()
        return p

    def _build_fft_tab(self):
        p = gf.FormPanel(field_width=gf.FIELD_W,
                         button_width=gf.BTN_W)
        p.add_title('Complex FFT of I+iQ along an axis', help=_HELP_FFT)

        self.fft_axis = self._combo(['X (within trace)', 'Y (indirect)', 'Both (2D)'])
        self.fft_axis.currentIndexChanged.connect(self._update_fft_passband)
        self.fft_axis.currentIndexChanged.connect(self._live_update)
        p.add_row('Transform axis', self.fft_axis)

        self.fft_window = self._combo(WINDOWS)
        p.add_row('Window', self.fft_window)
        self.fft_winparam_label = self._label('Window param')
        self.fft_winparam = self._dspin(0.0, 100.0, 2, 8.6)
        p.add_row(self.fft_winparam_label, self.fft_winparam)
        self.fft_window.currentIndexChanged.connect(self._update_winparam)
        self.fft_window.currentIndexChanged.connect(self._live_update)
        self.fft_winparam.valueChanged.connect(self._live_update)

        self.fft_skip = QSpinBox(); self.fft_skip.setStyleSheet(SPIN_STYLE)
        self.fft_skip.setRange(0, 1000000)
        self.fft_skip.setSuffix(' pts')
        self.fft_skip.setToolTip(
            'Number of leading <b>points</b> (samples, not time) to drop along '
            'the transform axis so it starts at the echo centre.')
        self.fft_skip.valueChanged.connect(self._live_update)
        btn_auto = QPushButton('Auto')
        btn_auto.setStyleSheet(BUTTON_STYLE)
        btn_auto.setToolTip(
            'Estimate the echo centre and fill "skip pts" with its <b>point '
            'index</b> (a sample number, not a time).<br><br>'
            'Taken from the |I+iQ| envelope averaged over the non-transform '
            'axis (so the field-offset modulation cancels): the peak sample, '
            'refined by a centre-of-mass over the symmetric core around it (so '
            'a slow one-sided FID decay tail does not drag it off the peak).')
        btn_auto.clicked.connect(self.auto_echo_center)
        p.add_row('Echo center', self.fft_skip, btn_auto, stretch=[3, 1])

        self.fft_zerofill = self._combo(ZEROFILL)
        self.fft_zerofill.setCurrentText('×2')
        self.fft_zerofill.currentIndexChanged.connect(self._live_update)
        p.add_row('Zero fill', self.fft_zerofill)

        adv = p.add_advanced()
        adv.field_width, adv.button_width = gf.FIELD_W, gf.BTN_W
        (self.fft_x_head, self.fft_x_type, self.fft_x_lo_label, self.fft_x_lo,
         self.fft_x_hi_label, self.fft_x_hi) = self._passband_rows(adv, 'X')
        (self.fft_y_head, self.fft_y_type, self.fft_y_lo_label, self.fft_y_lo,
         self.fft_y_hi_label, self.fft_y_hi) = self._passband_rows(adv, 'Y')

        btn = QPushButton('Compute FFT')
        btn.setStyleSheet(BUTTON_STYLE)
        btn.clicked.connect(self.do_fft)
        p.add_button_row(btn, width=gf.ACTION_W)
        p.add_stretch()
        self._update_winparam()
        self._update_fft_passband()
        return p

    def _passband_rows(self, panel, name):
        """Passband type + low/high cutoff rows for one axis of the FFT tab;
        returns the widgets so the inactive axis' rows can be hidden."""
        head = self._label(f'{name} passband')
        ftype = self._combo(['None'] + FILTERS)
        ftype.currentIndexChanged.connect(self._live_update)
        panel.add_row(head, ftype)
        lo_label = self._label(f'{name} low cutoff')
        lo = self._dspin(0.0, 1.0, 4, 0.0, 0.01)
        lo.setSuffix(' ×f_max')
        lo.valueChanged.connect(self._live_update)
        panel.add_row(lo_label, lo)
        hi_label = self._label(f'{name} high cutoff')
        hi = self._dspin(0.0, 1.0, 4, 1.0, 0.01)
        hi.setSuffix(' ×f_max')
        hi.valueChanged.connect(self._live_update)
        panel.add_row(hi_label, hi)
        return head, ftype, lo_label, lo, hi_label, hi

    def _update_fft_passband(self, *args):
        mode = self.fft_axis.currentIndex()       # 0 = X, 1 = Y, 2 = both
        for wdg in (self.fft_x_head, self.fft_x_type, self.fft_x_lo_label,
                    self.fft_x_lo, self.fft_x_hi_label, self.fft_x_hi):
            wdg.setEnabled(mode != 1)
            wdg.setVisible(mode != 1)
        for wdg in (self.fft_y_head, self.fft_y_type, self.fft_y_lo_label,
                    self.fft_y_lo, self.fft_y_hi_label, self.fft_y_hi):
            wdg.setEnabled(mode != 0)
            wdg.setVisible(mode != 0)

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
        # the row is meaningless for the non-parametric windows: hide it rather
        # than leave a greyed field on the tab
        self.fft_winparam_label.setVisible(cfg is not None)
        self.fft_winparam.setVisible(cfg is not None)

    def _build_filter_tab(self):
        p = gf.FormPanel(field_width=gf.FIELD_W,
                         button_width=gf.BTN_W)
        p.add_title('Mask a frequency band and transform back', help=_HELP_FILTER)

        self.filt_axis = self._combo(['X (within trace)', 'Y (indirect)',
                                      'Both (independent)'])
        self.filt_axis.currentIndexChanged.connect(self._update_filter_enable)
        self.filt_axis.currentIndexChanged.connect(self._live_update)
        p.add_row('Filter axis', self.filt_axis)

        self.filt_x_head = self._label('X filter')
        self.filt_x_type = self._combo(FILTERS)
        self.filt_x_type.currentIndexChanged.connect(self._live_update)
        p.add_row(self.filt_x_head, self.filt_x_type)
        self.filt_x_lo_label = self._label('X low cutoff')
        self.filt_x_lo = self._dspin(0.0, 1.0, 4, 0.1, 0.01)
        self.filt_x_lo.setSuffix(' ×f_max')
        self.filt_x_lo.valueChanged.connect(self._live_update)
        p.add_row(self.filt_x_lo_label, self.filt_x_lo)
        self.filt_x_hi_label = self._label('X high cutoff')
        self.filt_x_hi = self._dspin(0.0, 1.0, 4, 0.5, 0.01)
        self.filt_x_hi.setSuffix(' ×f_max')
        self.filt_x_hi.valueChanged.connect(self._live_update)
        p.add_row(self.filt_x_hi_label, self.filt_x_hi)

        self.filt_y_head = self._label('Y filter')
        self.filt_y_type = self._combo(FILTERS)
        self.filt_y_type.currentIndexChanged.connect(self._live_update)
        p.add_row(self.filt_y_head, self.filt_y_type)
        self.filt_y_lo_label = self._label('Y low cutoff')
        self.filt_y_lo = self._dspin(0.0, 1.0, 4, 0.1, 0.01)
        self.filt_y_lo.setSuffix(' ×f_max')
        self.filt_y_lo.valueChanged.connect(self._live_update)
        p.add_row(self.filt_y_lo_label, self.filt_y_lo)
        self.filt_y_hi_label = self._label('Y high cutoff')
        self.filt_y_hi = self._dspin(0.0, 1.0, 4, 0.5, 0.01)
        self.filt_y_hi.setSuffix(' ×f_max')
        self.filt_y_hi.valueChanged.connect(self._live_update)
        p.add_row(self.filt_y_hi_label, self.filt_y_hi)

        btn = QPushButton('Apply filter')
        btn.setStyleSheet(BUTTON_STYLE)
        btn.clicked.connect(self.do_filter)
        p.add_button_row(btn, width=gf.ACTION_W)
        p.add_stretch()
        self._update_filter_enable()
        return p

    def _update_filter_enable(self, *args):
        mode = self.filt_axis.currentIndex()      # 0 = X, 1 = Y, 2 = both
        # the inactive axis' rows are hidden, not greyed: in single-axis mode
        # that is four dead rows off the tab
        for wdg in (self.filt_x_head, self.filt_x_type, self.filt_x_lo_label,
                    self.filt_x_lo, self.filt_x_hi_label, self.filt_x_hi):
            wdg.setEnabled(mode != 1)
            wdg.setVisible(mode != 1)
        for wdg in (self.filt_y_head, self.filt_y_type, self.filt_y_lo_label,
                    self.filt_y_lo, self.filt_y_hi_label, self.filt_y_hi):
            wdg.setEnabled(mode != 0)
            wdg.setVisible(mode != 0)

    def _build_shear_tab(self):
        p = gf.FormPanel(field_width=gf.FIELD_W,
                         button_width=gf.BTN_W)
        p.add_title('Straighten a tilted dipolar ridge', help=_HELP_SHEAR)

        self.shear_axis = self._combo(['Y (indirect)', 'X (within trace)'])
        self.shear_axis.currentIndexChanged.connect(self._live_update)
        p.add_row('Dipolar axis', self.shear_axis,
                  tooltip='The axis the ramp shifts.')

        self.shear_k = self._dspin(-5.0, 5.0, 4, 0.5, 0.01)
        self.shear_k.valueChanged.connect(self._live_update)
        btn_fit = QPushButton('Fit k')
        btn_fit.setStyleSheet(BUTTON_STYLE)
        btn_fit.setToolTip('Scan k, shear, sum over the echo axis and take the k that '
                           'maximises the recovered peak (parabolic refine around the '
                           'grid maximum). Uses the fit window below.')
        btn_fit.clicked.connect(self.fit_shear_slope)
        p.add_row('Slope k', self.shear_k, btn_fit, stretch=[3, 1],
                  tooltip='Ridge slope dt_dip/dt (1/2 for SIFTER).')

        self.shear_tref = self._dspin(-1e12, 1e12, 3, 0.0, 1.0)
        self.shear_tref.valueChanged.connect(self._live_update)
        btn_ref = QPushButton('Auto')
        btn_ref.setStyleSheet(BUTTON_STYLE)
        btn_ref.setToolTip('Set t_ref to the echo centre of the |I+iQ| envelope averaged '
                           'over the dipolar axis. t_ref only translates the dipolar '
                           'axis — it does not change the recovered amplitude, but it '
                           'does set the absolute zero of the dipolar time.')
        btn_ref.clicked.connect(self.auto_shear_ref)
        p.add_row('Shear origin t_ref', self.shear_tref, btn_ref, stretch=[3, 1])

        self.shear_fitwin = self._dspin(0.0, 1e12, 1, 140.0, 10.0)
        self.shear_fitwin.setToolTip('Echo-axis half-width used by "Fit k" only '
                                     '(0 = the whole window). The low-S/N wings of the '
                                     'echo otherwise dilute the figure of merit.')
        adv = p.add_advanced()
        adv.field_width, adv.button_width = gf.FIELD_W, gf.BTN_W
        adv.add_row('Fit window ±', self.shear_fitwin)

        btn = QPushButton('Apply shear')
        btn.setStyleSheet(BUTTON_STYLE)
        btn.clicked.connect(self.do_shear)
        p.add_button_row(btn, width=gf.ACTION_W)
        p.add_stretch()
        return p

    def _build_fit_tab(self):
        p = gf.FormPanel(field_width=gf.FIELD_W,
                         button_width=gf.BTN_W)
        p.add_title('Fit each trace and map a parameter', help=_HELP_FIT)

        self.fit_axis = self._combo(['X (within trace)', 'Y (indirect)'])
        p.add_row('Decay axis', self.fit_axis)

        self.fit_channel = self._combo(['Real (I)', 'Magnitude', 'Imag (Q)'])
        p.add_row('Channel', self.fit_channel)

        self.fit_model = self._combo(RELAX_MODELS)
        self.fit_model.setCurrentText('Stretched exponential')
        self.fit_model.currentIndexChanged.connect(self._update_fit_params)
        p.add_row('Model', self.fit_model)

        # live equation of the selected model, so the user sees what is fitted
        self.fit_formula = gf.hint('')
        p.add_widget(self.fit_formula)

        self.fit_no_offset = p.add_check(
            'Fix offset = 0',
            tooltip='Drop the b baseline term from the model.')
        self.fit_no_offset.stateChanged.connect(self._update_fit_params)

        self.fit_param = self._combo([])
        p.add_row('Map parameter', self.fit_param)

        self.fit_minr2 = self._dspin(0.0, 1.0, 3, 0.0, step=0.05)
        adv = p.add_advanced()
        adv.field_width, adv.button_width = gf.FIELD_W, gf.BTN_W
        adv.add_row('Min R²', self.fit_minr2,
                    tooltip='Traces fitting worse than this are dropped from the map.')

        self.fit_run_btn = QPushButton('Run fit')
        self.fit_run_btn.setStyleSheet(BUTTON_STYLE)
        self.fit_run_btn.setToolTip(self._FIT_STATS_TOOLTIP)
        self.fit_run_btn.clicked.connect(self.do_fit_2d)
        self.fit_cancel_btn = QPushButton('Cancel')
        self.fit_cancel_btn.setStyleSheet(BUTTON_STYLE)
        self.fit_cancel_btn.clicked.connect(self.cancel_fit)
        self.fit_cancel_btn.setEnabled(False)
        btn_savemap = QPushButton('Save map…')
        btn_savemap.setStyleSheet(BUTTON_STYLE)
        btn_savemap.clicked.connect(self.save_fit_map)
        p.add_button_row(self.fit_run_btn, self.fit_cancel_btn, btn_savemap,
                         width=gf.ACTION_W)

        self.fit_info = gf.hint('')
        p.add_widget(self.fit_info)
        p.add_stretch()

        self._update_fit_params()
        return p

    def _build_slice_tab(self):
        p = gf.FormPanel(field_width=gf.FIELD_W,
                         button_width=gf.BTN_W)
        p.add_title('Send one trace to the 1D tool', help=_HELP_SLICE)

        self.slice_axis = self._combo(['X (within trace)', 'Y (indirect)'])
        self.slice_axis.currentIndexChanged.connect(self._update_slice_label)
        self.slice_axis.currentIndexChanged.connect(self._sync_slice_from_cursor)
        p.add_row('Slice along', self.slice_axis)

        # 1-based to match the heatmap cursor label (which counts traces/points
        # from 1); converted to a 0-based array index where the data is sliced.
        self.slice_spin = QSpinBox(); self.slice_spin.setStyleSheet(SPIN_STYLE)
        self.slice_spin.setRange(1, 1000000)
        self.slice_spin.valueChanged.connect(self._update_slice_label)
        self.slice_label = gf.hint('')
        p.add_row('Trace #', self.slice_spin, self.slice_label, stretch=[1, 2])

        self.slice_avg = QCheckBox('Average up to')
        self.slice_avg.setStyleSheet(CHECKBOX_STYLE)
        self.slice_avg.setToolTip('Average all traces between "Trace #" and this '
                                  'index (inclusive) before sending — improves SNR.')
        self.slice_avg.stateChanged.connect(self._update_slice_label)
        # label column less the cell spacing: its spinbox then sits in the field column
        self.slice_avg.setFixedWidth(gf.LABEL_COL_W - 6 + 8)
        self.slice_spin2 = QSpinBox(); self.slice_spin2.setStyleSheet(SPIN_STYLE)
        self.slice_spin2.setRange(1, 1000000)
        self.slice_spin2.valueChanged.connect(self._update_slice_label)
        p.add_row(self.slice_avg, self.slice_spin2)

        btn_send = QPushButton('Send slice → 1D')
        btn_send.setStyleSheet(BUTTON_STYLE)
        btn_send.clicked.connect(self.send_slice_to_1d)
        btn_save = QPushButton('Save slice…')
        btn_save.setStyleSheet(BUTTON_STYLE)
        btn_save.clicked.connect(self.save_slice)
        p.add_button_row(btn_send, btn_save, width=gf.ACTION_W)
        p.add_stretch()
        return p

    def _update_fit_params(self, *args):
        """Repopulate the map-parameter combo from the current model, honouring
        the fix-offset checkbox (which drops the b/c baseline term)."""
        model = self.fit_model.currentText()
        formula = self.fitter.model_formula(model)
        self.fit_formula.setText(
            f'<span style="color: rgb(160, 160, 190);">{formula}</span>'
            if formula else '')
        names = list(self.fitter.param_names(model))
        if self.fit_no_offset.isChecked():
            names = [n for n in names if n not in ('b', 'c')]
        cur = self.fit_param.currentText()
        self.fit_param.blockSignals(True)
        self.fit_param.clear(); self.fit_param.addItems(names)
        default = next((n for n in names if n.startswith('k') or n == 'Tm'),
                       names[0] if names else '')
        self.fit_param.setCurrentText(cur if cur in names else default)
        self.fit_param.blockSignals(False)

    # ------------------------------------------------------- file dialogs
    def _remember_dir(self, path):
        """Record the folder of `path` as the next dialog's starting directory."""
        self.last_dir = os.path.dirname(path) or self.last_dir
        _save_last_dir(self.last_dir)

    def _open_dialog(self, **kw):
        path = self.opener.open_file_dialog(multiprocessing=True,
                                            directory=self.last_dir, **kw)
        if path and path != 'None':
            self._remember_dir(path)
        return path

    def _save_dialog(self, **kw):
        path = self.opener.create_file_dialog(multiprocessing=True,
                                              directory=self.last_dir, **kw)
        if path and path != 'None':
            self._remember_dir(path)
        return path

    # ------------------------------------------------------------- loading
    def open_iq(self):
        path = self._open_dialog(name_filters=['Data (*.csv *.h5)', 'All files (*)'])
        if not path or path == 'None':
            return
        try:
            xarr = yarr = None
            if str(path).endswith('.h5'):
                # one file holds both quadratures; the axes come as datasets
                arr = self.opener.open_2d(path)[1]
                if np.ndim(arr) == 3:
                    i = np.atleast_2d(np.asarray(arr[0], dtype=float))
                    q = np.atleast_2d(np.asarray(arr[1], dtype=float))
                    qmsg = 'Q dataset'
                else:
                    i = np.atleast_2d(np.asarray(arr, dtype=float))
                    q = np.zeros_like(i)
                    qmsg = 'no Q dataset (Q = 0)'
                axes = self.opener.open_h5_axes(path)
                xarr, yarr = axes.get('t'), axes.get('sweep')
            else:
                i = np.atleast_2d(np.genfromtxt(path, delimiter=','))
                base = path[:-4] if path.lower().endswith('.csv') else path
                qpath = base + '_1.csv'
                if os.path.isfile(qpath):
                    q = np.atleast_2d(np.genfromtxt(qpath, delimiter=','))
                    qmsg = os.path.basename(qpath)
                else:
                    q = np.zeros_like(i)
                    qmsg = 'no _1 file (Q = 0)'
            header_lines = read_header(path)    # one read: axis steps + viewer
            dx, xu, dy, yu = self._parse_axis_header(header_lines)
            dropped = self.tr_epr_check.isChecked() and i.shape[0] > 1
            if dropped:
                # the off-resonance reference row; the stored sweep axis already
                # labels the field rows that follow it, so it needs no shift
                i, q = i[1:], q[1:]
            if self.transpose_check.isChecked():
                i, q = i.T, q.T
                dx, xu, dy, yu = dy, yu, dx, xu   # axes swap with the matrix
                xarr, yarr = yarr, xarr
            if i.shape != q.shape or min(i.shape) < 2:
                self.set_status('I and Q must be matching 2D matrices (≥ 2×2).')
                return
            self.raw_i, self.raw_q = i, q
            # auto-fill X/Y step + unit from the acquisition header when present;
            # files without it keep the current axis fields (see _parse_axis_header).
            parsed = self._apply_header_axes(dx, xu, dy, yu)
            # an .h5 axis dataset fills only what the header could not give: it
            # carries no unit, so it must never overwrite a header-set axis
            filled = self._apply_axis_arrays(None if dx is not None else xarr,
                                             None if dy is not None else yarr)
            parsed = ', '.join(p for p in (parsed, filled) if p)
            self.live_check.setChecked(False)   # new data: don't auto-reprocess
            self.reset_to_raw()
            self._set_loaded_file(os.path.basename(path))
            self._set_header(os.path.basename(path), header_lines)
            msg = (f'Loaded I={os.path.basename(path)}, Q={qmsg} '
                   f'(matrix {i.shape[0]}×{i.shape[1]} [traces × points]'
                   f'{", off-resonance row dropped" if dropped else ""}).')
            if parsed:
                msg += f' Axes from header: {parsed}.'
            self.set_status(msg)
        except Exception as e:
            self.set_status(f'Could not read I/Q: {e}')

    @staticmethod
    def _axis_start_step(arr):
        """(start, step) for a 1D abscissa; step is the average increment."""
        a = np.asarray(arr, dtype=float)
        if a.size < 2:
            return (float(a[0]) if a.size else 0.0), 1.0
        return float(a[0]), float((a[-1] - a[0])/(a.size - 1))

    @staticmethod
    def _parse_axis_header(header_lines):
        """Best-effort scan of an already-read comment header (header_view.
        read_header) for the acquisition steps.

        Atomize-saved CSVs carry lines like::

            # Horizontal Resolution:    2 ns
            # Vertical Resolution:      1004.8 ns

        Horizontal → X (within-trace / columns), Vertical → Y (traces / rows).
        Returns ``(dx, x_unit, dy, y_unit)`` with any field ``None`` when it is
        absent, so a file without such a header simply leaves every axis widget
        untouched.
        """
        dx = dy = xu = yu = None
        for ln in header_lines:
            m = re.search(r'(horizontal|vertical)\s+resolution\s*:\s*'
                          r'([-+0-9.eE]+)\s*([a-zA-Zµ]*)', ln, re.IGNORECASE)
            if not m:
                continue
            val, unit = float(m.group(2)), (m.group(3) or None)
            if m.group(1).lower() == 'horizontal':
                dx, xu = val, unit
            else:
                dy, yu = val, unit
        return dx, xu, dy, yu

    def _apply_axis_arrays(self, xarr, yarr):
        """Push stored axis vectors (an .h5 file's t / sweep datasets) into the
        start + step widgets. A step the spin box cannot hold — a raw SI time
        axis against a 3-decimal box — is left alone rather than rounded to a
        zero step, which would collapse the image."""
        done = []
        pairs = [('X', xarr, self.x0_spin, self.dx_spin),
                 ('Y', yarr, self.y0_spin, self.dy_spin)]
        for name, arr, zspin, dspin in pairs:
            if arr is None or np.size(arr) < 2:
                continue
            start, step = self._axis_start_step(arr)
            if abs(step) < 10 ** -dspin.decimals():
                continue
            zspin.blockSignals(True); zspin.setValue(float(start)); zspin.blockSignals(False)
            dspin.blockSignals(True); dspin.setValue(float(step)); dspin.blockSignals(False)
            done.append(f'{name} start={start:g} Δ={step:g}')
        return ', '.join(done)

    def _apply_header_axes(self, dx, xu, dy, yu):
        """Push any parsed (step, unit) into the axis widgets without firing the
        live-update loops. The start spin is zeroed for any axis whose step we
        set (a resolution-based axis runs from 0). Returns a short summary of
        what was filled, or '' when the header carried nothing usable."""
        done = []
        pairs = [('X', dx, xu, self.dx_spin, self.x0_spin, self.xscale_edit),
                 ('Y', dy, yu, self.dy_spin, self.y0_spin, self.yscale_edit)]
        for name, step, unit, dspin, zspin, uedit in pairs:
            if step is None:
                continue
            dspin.blockSignals(True); dspin.setValue(float(step)); dspin.blockSignals(False)
            zspin.blockSignals(True); zspin.setValue(0.0); zspin.blockSignals(False)
            if unit:
                uedit.blockSignals(True); uedit.setText(unit); uedit.blockSignals(False)
            done.append(f'{name} Δ={step} {unit or ""}'.strip())
        return ', '.join(done)

    def open_bruker(self):
        """Load a 2D Bruker native dataset (BES3T .DSC/.DTA or ESP/WinEPR
        .par/.spc). Rows = traces (Y/indirect), cols = points (X/within trace);
        complex data fills I & Q, real data sets Q = 0. The axis fields are
        populated from the descriptor."""
        nf = ['Bruker (*.DSC *.dsc *.DTA *.dta *.par *.spc *.PAR *.SPC)',
              'BES3T (*.DSC *.dsc *.DTA *.dta)',
              'ESP/WinEPR (*.par *.spc *.PAR *.SPC)', 'All files (*)']
        path = self._open_dialog(name_filters=nf)
        if not path or path == 'None':
            return
        try:
            res = self.bruker.open(path)
        except Exception as e:
            self.set_status(f'Could not read Bruker file: {e}')
            return
        if res['ndim'] != 2:
            self.set_status(f'{res["format"]} {res["ndim"]}D dataset — the 2D tool '
                            f'needs a 2D matrix; use the 1D Data Treatment window.')
            return
        data = np.asarray(res['data'])               # (ny traces, nx points)
        i = np.real(data).astype(float)
        q = np.imag(data).astype(float) if res['complex'] else np.zeros_like(i)
        # X = within-trace (cols), Y = indirect (rows); transpose swaps them
        xarr, yarr = res['x'], res['y']
        xn, xs = res['x_name'] or 'X', res['x_unit'] or ''
        yn, ys = res['y_name'] or 'Y', res['y_unit'] or ''
        if self.transpose_check.isChecked():
            i, q = i.T, q.T
            xarr, yarr = yarr, xarr
            xn, xs, yn, ys = yn, ys, xn, xs
        if min(i.shape) < 2:
            self.set_status('Bruker matrix too small (need ≥ 2×2).')
            return
        x0, dx = self._axis_start_step(xarr)
        y0, dy = self._axis_start_step(yarr)
        edits = [(self.xname_edit, xn), (self.xscale_edit, xs),
                 (self.yname_edit, yn), (self.yscale_edit, ys)]
        spins = [(self.x0_spin, x0), (self.dx_spin, dx),
                 (self.y0_spin, y0), (self.dy_spin, dy)]
        for w, v in edits:                           # set without firing reset loops
            w.blockSignals(True); w.setText(str(v)); w.blockSignals(False)
        for s, v in spins:
            s.blockSignals(True); s.setValue(float(v)); s.blockSignals(False)
        self.raw_i, self.raw_q = i, q
        self.live_check.setChecked(False)   # new data: don't auto-reprocess
        self.reset_to_raw()
        self._set_loaded_file(os.path.basename(path))
        self._set_header(os.path.basename(path),
                         params_to_lines(res.get('params', {})))
        self.set_status(f'Loaded {os.path.basename(path)} — {res["format"]}, '
                        f'{i.shape[0]}×{i.shape[1]} [traces × points], '
                        + ('complex.' if res['complex'] else 'real (Q = 0).'))

    def load_from_plot(self, silent=False):
        """Load a 2D image sent from the main GUI (right-click a 2D plot →
        "Send to Data Treatment"), which writes libs/treatment_buffer_2d.npz:
        i/q [trace, point] matrices + axis geometry/labels. The buffer is a
        one-shot mailbox — consumed on read."""
        if not os.path.isfile(BUFFER_2D_PATH):
            if not silent:
                self.set_status('No 2D plot buffer found. Right-click a 2D plot in '
                                'the main window → "Send to Data Treatment" first.')
            return
        try:
            with np.load(BUFFER_2D_PATH, allow_pickle=False) as d:
                i = np.atleast_2d(np.asarray(d['i'], dtype=float))
                q = np.atleast_2d(np.asarray(d['q'], dtype=float))
                geom = np.asarray(d['geom'], dtype=float).ravel().tolist()
                labels = [str(s) for s in np.asarray(d['labels']).ravel().tolist()]
            self._consume_2d_buffer()
            if i.shape != q.shape or min(i.shape) < 2:
                if not silent:
                    self.set_status('2D buffer is not a valid matrix (need ≥ 2×2).')
                return
            x0, dx, y0, dy = (geom + [0.0, 1.0, 0.0, 1.0])[:4]
            xn, xs, yn, ys = (labels + ['X', '', 'Y', ''])[:4]
            # A 0 (or non-finite) step collapses the image scale → a blank plot.
            # The main-window plot doesn't always carry a real step, so fall back
            # to 1; the user can type the true step into the Axes fields after.
            zeroed = []
            if not np.isfinite(dx) or dx == 0:
                dx = 1.0; zeroed.append('X')
            if not np.isfinite(dy) or dy == 0:
                dy = 1.0; zeroed.append('Y')
            if self.transpose_check.isChecked():     # swap trace / point axes
                i, q = i.T, q.T
                x0, dx, y0, dy = y0, dy, x0, dx
                xn, xs, yn, ys = yn, ys, xn, xs
            edits = [(self.xname_edit, xn), (self.xscale_edit, xs),
                     (self.yname_edit, yn), (self.yscale_edit, ys)]
            spins = [(self.x0_spin, x0), (self.dx_spin, dx),
                     (self.y0_spin, y0), (self.dy_spin, dy)]
            for w, v in edits:                       # set without firing reset loops
                w.blockSignals(True); w.setText(str(v)); w.blockSignals(False)
            for s, v in spins:
                s.blockSignals(True); s.setValue(float(v)); s.blockSignals(False)
            self.raw_i, self.raw_q = i, q
            self.live_check.setChecked(False)   # new data: don't auto-reprocess
            self.reset_to_raw()
            self._set_loaded_file('Loaded from plot')
            self._set_header('Loaded from plot', [])
            msg = (f'Loaded 2D plot from buffer '
                   f'({i.shape[0]}×{i.shape[1]} [traces × points]).')
            if zeroed:
                msg += (f' No {"/".join(zeroed)} step in the plot — set to 1; '
                        f'adjust in the Axes fields.')
            self.set_status(msg)
        except Exception as e:
            self._consume_2d_buffer()                # drop a malformed buffer
            if not silent:
                self.set_status(f'Could not read 2D plot buffer: {e}')

    def _consume_2d_buffer(self):
        """Delete the 2D plot buffer once read (one-shot mailbox semantics)."""
        try:
            if os.path.isfile(BUFFER_2D_PATH):
                os.remove(BUFFER_2D_PATH)
        except OSError:
            pass

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
        # Fit (index 4) is excluded — per-trace fitting is too heavy to run on
        # every parameter tweak; it is explicit ("Run fit") only.
        op = {0: self.do_phase, 1: self.do_fft, 2: self.do_filter,
              3: self.do_shear}.get(self.tabs.currentIndex())
        if op is not None:
            op()

    def _apply_current_op(self):
        if self.src_i is None:
            self.set_status('Open an I/Q dataset first.')
            return
        op = {0: self.do_phase, 1: self.do_fft, 2: self.do_filter,
              3: self.do_shear, 4: self.do_fit_2d}.get(self.tabs.currentIndex())
        if op is not None:
            op()
        else:
            self.set_status('Slice tab: use "Send slice → 1D".')

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
        # newly loaded data / deliberate reset => re-fit the view even when the
        # geometry is unchanged (the dock only auto-ranges on first render or a
        # geometry change, so force it here, mirroring the 1D tool).
        self.cross_dock.first_render = True
        self._push(self.src_i, self.src_q, self.src_col, self.src_row, ('I', 'Q'))
        self._update_slice_label()
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
        self._clear_preview()
        self._set_loaded_file(None)
        self._set_header('', [])
        self.set_status('Cleared. Open an I/Q 2D dataset.')

    # ------------------------------------------------------- header viewer
    def _set_header(self, name, lines):
        """Store the parameter header of the dataset just loaded and refresh the
        viewer. A load never opens the window — only the 'Header…' button does."""
        self.header_name, self.header_lines = name, list(lines or [])
        if self.header_window is not None:
            self.header_window.set_sources([(self.header_name or 'dataset',
                                             self.header_lines)])

    def show_header(self):
        """'Header…' button: open (or raise) the viewer on the loaded dataset."""
        if self.header_window is None:
            self.header_window = HeaderWindow(self)
        self.header_window.set_sources([(self.header_name or 'dataset',
                                         self.header_lines)])
        if not self.header_lines:
            self.set_status('The loaded dataset carries no parameter header.')
        self.header_window.show_source()

    def _clear_preview(self):
        """Wipe the embedded heatmap + X/Y cross-section traces and reset the
        dock's render state so the next load re-autoranges from scratch."""
        cd = self.cross_dock
        try:
            # close the floating X-trace / Y-trace cross-section docks if open
            # (Clear should leave no stale section plots behind).
            if getattr(cd, 'cross_section_enabled', False):
                cd.hide_cross_section()
        except Exception:
            pass
        try:
            cd.img_view.clear()
            cd.h_cross_section_widget_data.setData([], [])
            cd.v_cross_section_widget_data.setData([], [])
            cd.first_render = True
            cd.set_image = 0
            cd.setTitle('')
        except Exception:
            pass

    def _disable_si_prefix(self):
        """Initial state: turn off pyqtgraph's automatic SI-prefixing on this
        tool's preview axes (before any data is loaded). Per push, _apply_si_prefix
        re-enables it only for bare SI-base axes.

        Scoped to *this* tool's CrossSectionDock instance (own QProcess): the
        shared widget keeps auto-prefixing for the main GUI, which depends on it."""
        cd = self.cross_dock
        plots = (cd.plot_item,
                 cd.h_cross_section_widget.plotItem,
                 cd.v_cross_section_widget.plotItem)
        for p in plots:
            for side in ('bottom', 'left'):
                try:
                    p.getAxis(side).enableAutoSIPrefix(False)
                except Exception:
                    pass

    def _apply_si_prefix(self, xunit, yunit, zunit):
        """Auto-SI-prefix only the axes whose unit is a bare SI base, so a 's'
        axis with a 2e-9 step reads '2 ns'; leave already-prefixed units ('ns',
        'MHz') verbatim to avoid double-prefixing ('kns'). X is the heatmap bottom
        + the X-trace bottom; Y is the heatmap left + the Y-trace bottom; Z
        (intensity) is both cross-section left axes."""
        cd = self.cross_dock
        x_on, y_on, z_on = (_si_autoprefix(xunit), _si_autoprefix(yunit),
                            _si_autoprefix(zunit))
        axes = [(cd.plot_item, 'bottom', x_on),
                (cd.plot_item, 'left', y_on),
                (cd.h_cross_section_widget.plotItem, 'bottom', x_on),
                (cd.h_cross_section_widget.plotItem, 'left', z_on),
                (cd.v_cross_section_widget.plotItem, 'bottom', y_on),
                (cd.v_cross_section_widget.plotItem, 'left', z_on)]
        for p, side, on in axes:
            try:
                p.getAxis(side).enableAutoSIPrefix(on)
            except Exception:
                pass

    # --------------------------------------------------------------- push
    def _push_current(self, *args):
        if self.has_result():
            self._push(self.res_i, self.res_q, self.res_col, self.res_row,
                       self.res_frames)
        elif self.src_i is not None:
            self._push(self.src_i, self.src_q, self.src_col, self.src_row,
                       ('I', 'Q'))

    def _push(self, i, q, col, row, frames):
        """Render a complex 2D dataset in the embedded CrossSectionDock as a
        (2, nX, nY) frame stack (frame 0 = real/I, frame 1 = imag/Q); the frame
        slider toggles between them."""
        name = self.name_edit.text().strip() or 'FT Data 2D'
        # internal layout is [trace(row), point(col)]; transpose so columns
        # become the X axis (CrossSectionDock pos/scale are ((x..),(y..))).
        arr = np.array([np.transpose(np.asarray(i, float)),
                        np.transpose(np.asarray(q, float))])
        # a 0 step collapses the image scale and renders nothing; never let that
        # reach setImage (axis geometry may carry a 0 from a source without steps).
        sx = col['step'] if col['step'] else 1.0
        sy = row['step'] if row['step'] else 1.0
        try:
            self.cross_dock.setTitle(name)
            self.cross_dock.setAxisLabels(xname=col['name'], xscale=col['scale'],
                                          yname=row['name'], yscale=row['scale'],
                                          zname='Intensity', zscale='V')
            self._apply_si_prefix(col['scale'], row['scale'], 'V')
            self.cross_dock.setImage(arr, pos=(col['start'], row['start']),
                                     scale=(sx, sy), autoLevels=False)
        except Exception as e:
            self.set_status(f'Could not render preview: {e}')

    def set_status(self, text):
        self.status.setText(text)
        general.message(text)

    def _set_loaded_file(self, name):
        """Show the source of the current dataset under the Source buttons."""
        self.loaded_label.setText(f'File: {name}' if name else 'File: —')

    # ---------------------------------------------------------- operations
    @staticmethod
    def _is_freq_axis(ax):
        """True if an axis dict already describes a frequency axis — i.e. the
        input has been FFT'd (e.g. via 'Result → input'). Lets auto-φ₀ tell a
        spectrum from a time-domain FID so it doesn't transform twice."""
        if not ax:
            return False
        name = str(ax.get('name', '')).lower()
        unit = str(ax.get('scale', '')).strip().lower()
        return ('freq' in name) or (unit in ('hz', 'khz', 'mhz', 'ghz', 'thz'))

    def auto_phase_zero(self):
        """Fill the zero-order phase with the principal-axis value for the
        current source.

        `do_phase` corrects the trace in the time domain, from the *start* of the
        window, so φ₀ has to be measured in that same frame — on the echo
        (Fast_Fourier.auto_phase_zero_echo), with the first/second-order phase
        already applied and with the FFT-tab skip deliberately left out of it. A
        spectrum built from a skipped trace reports φ₀ in the shifted frame
        instead, which for an off-centre line is wrong by 360·f·dt per skipped
        point. Input that is already a spectrum ('Result → input') is phased on
        that spectrum as-is. First/second order stay manual, but a leftover
        carrier — which no φ₀ can absorb — is reported."""
        if self.src_i is None:
            self.set_status('Open an I/Q dataset first.')
            return
        if self._is_freq_axis(self.src_col):
            # Input is already a spectrum (FFT'd, then 'Result → input'): use it
            # straight, with NO second FFT — transforming again is what produced
            # a meaningless φ₀. Echo/carrier are time-domain concepts here.
            S = self.src_i + 1j*self.src_q
            phi = fft_module.Fast_Fourier.auto_phase_zero(S.ravel())
            self.phase_zero.setValue(phi)
            self.set_status(f'Auto φ₀ = {phi:.2f}° — X spectrum '
                            f'(input already frequency-domain).')
            return

        ncols = self.src_i.shape[1]
        axisx = self.src_col['start'] + self.src_col['step']*np.arange(ncols)
        v1 = float(self.phase_first.value()); v2 = float(self.phase_second.value())
        Z = (self.src_i + 1j*self.src_q)*np.exp(
            1j*(2*np.pi*v1/1000.0*axisx + 2*np.pi*v2/1000.0*axisx*axisx))[None, :]
        phi = fft_module.Fast_Fourier.auto_phase_zero_echo(Z)
        self.phase_zero.setValue(phi)        # fires the live preview update

        note = ' (first/second order applied)' if (v1 or v2) else ''
        step = float(self.src_col['step'])
        f0 = self._carrier(Z, step)*1000.0
        # a carrier that turns by more than ~45 deg across the echo cannot be
        # absorbed into phi0 at all; report the first-order value that kills it
        env = np.abs(Z).mean(axis=0)
        width = abs(step)*max(1, int(np.count_nonzero(env >= 0.25*env.max())))
        if abs(f0)*width/1000.0 > 0.125:
            self.set_status(f'Auto φ₀ = {phi:.2f}° — echo window{note}, but the '
                            f'signal still sits at {f0:+.2f} MHz: set First order '
                            f'= {v1 - f0:.2f} and press Auto again.')
        else:
            self.set_status(f'Auto φ₀ = {phi:.2f}° — echo window{note}.')

    @staticmethod
    def _carrier(Z, dt):
        """Carrier offset of the echo, measured on a band-limited copy.

        `carrier_offset` reads the phase increment between neighbouring samples,
        which the out-of-band noise of an undemodulated record swamps: the raw
        SIFTER map reads +0.28 MHz where the true offset is −0.46. An echo of
        width W cannot be spectrally wider than a few times 1/W, so everything
        beyond 10/W is noise and is dropped before measuring."""
        env = np.abs(Z).mean(axis=0)
        width = abs(dt)*max(1, int(np.count_nonzero(env >= 0.25*env.max())))
        S = np.fft.fft(Z, axis=1)
        S[:, np.abs(np.fft.fftfreq(Z.shape[1], dt)) > 10.0/width] = 0
        return fft_module.Fast_Fourier.carrier_offset(np.fft.ifft(S, axis=1), dt)

    @staticmethod
    def _imag_fraction(W):
        """Imaginary energy left in `W` after its best zero-order rotation."""
        W = W*np.exp(-1j*np.angle((W**2).sum())/2)
        denom = np.abs(W).sum()
        return float(np.abs(W.imag).sum()/denom) if denom else 1.0

    def _refine_first(self, Z, tvec, v1):
        """Grid-search the first order about `v1` for the least imaginary residue
        over the echo region, parabolically refined.

        The carrier estimate is the intensity centroid of the line, which is not
        where the trace phases best when the line is asymmetric — on the SIFTER
        records the centroid lands at about half the residue-optimal value. The
        residue is what phasing is actually for, so it decides the final number."""
        env = np.abs(Z).mean(axis=0)
        echo = env >= 0.25*env.max()
        Ze = Z[:, echo]
        te = tvec[echo] - tvec[int(env.argmax())]
        grid = v1 + np.arange(-1.0, 1.0001, 0.02)
        res = np.array([self._imag_fraction(Ze*np.exp(2j*np.pi*g/1000.0*te)[None, :])
                        for g in grid])
        j = int(res.argmin())
        best = float(grid[j])
        if 0 < j < grid.size - 1:
            p = np.polyfit(grid[j-1:j+2], res[j-1:j+2], 2)
            if p[0] > 0:
                best = float(-p[1]/(2*p[0]))
        return best, float(res[j])

    def auto_phase_first(self):
        """Fill the first-order term with the carrier the record actually sits at,
        and re-run the zero-order Auto on top of it.

        The nominal IF is only a starting point: a residual of a few hundred kHz
        turns the phase by tens of degrees across the echo, which φ₀ cannot absorb
        and which shows up as a large imaginary residue. Two stages — the carrier
        is iterated to its fixed point (it survives a badly wrong starting value),
        then `_refine_first` takes over for the last few hundred kHz."""
        if self.src_i is None:
            self.set_status('Open an I/Q dataset first.')
            return
        step = float(self.src_col['step'])
        if step == 0 or self._is_freq_axis(self.src_col):
            self.set_status('First-order Auto needs a time-domain X axis with a '
                            'non-zero step.')
            return
        ncols = self.src_i.shape[1]
        axisx = self.src_col['start'] + self.src_col['step']*np.arange(ncols)
        v1 = v1_in = float(self.phase_first.value())
        v2 = float(self.phase_second.value())
        Z0 = self.src_i + 1j*self.src_q
        for _ in range(8):
            Z = Z0*np.exp(1j*(2*np.pi*v1/1000.0*axisx
                              + 2*np.pi*v2/1000.0*axisx*axisx))[None, :]
            f0 = self._carrier(Z, step)*1000.0
            v1 -= f0
            if abs(f0) < 1e-3:
                break
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            v1, res = self._refine_first(Z0, axisx, v1)
        finally:
            QApplication.restoreOverrideCursor()
        self._suppress_live = True                 # one preview, after φ₀ lands
        try:
            self.phase_first.setValue(v1)
        finally:
            self._suppress_live = False
        self.auto_phase_zero()
        phi0_msg = self.status.text()
        self.set_status(f'Auto φ₁ = {v1:.3f} MHz ({v1 - v1_in:+.3f} on the entered '
                        f'value), {100*res:.1f} % imaginary left over the echo; '
                        f'then {phi0_msg[0].lower()}{phi0_msg[1:]}')

    def do_phase(self):
        if self.src_i is None:
            self.set_status('Open an I/Q dataset first.')
            return
        ncols = self.src_i.shape[1]
        axisx = self.src_col['start'] + self.src_col['step']*np.arange(ncols)
        c1 = float(self.phase_zero.value())*np.pi/180.0
        # first/second order entered as a frequency offset: value/1000 cycles per
        # x-unit, i.e. 50 -> 50 MHz when x is in ns (coeff = 2*pi*value/1000).
        v1 = float(self.phase_first.value()); v2 = float(self.phase_second.value())
        c2 = 2*np.pi*v1/1000.0
        c3 = 2*np.pi*v2/1000.0
        ph = np.exp(1j*(c1 + c2*axisx + c3*axisx*axisx))
        Z = (self.src_i + 1j*self.src_q)*ph[None, :]
        meta = ['Phase correction along X',
                f'zero = {self.phase_zero.value():.4g} deg, '
                f'first = {v1:.4g}, second = {v2:.4g} (MHz @ x=ns; coeff = 2π·value/1000 per x)']
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
        # X for the X-only and 2D modes; Y only for the Y-only mode. The echo
        # centre is a property of the direct (X) time axis.
        along_x = (self.fft_axis.currentIndex() != 1)
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
        mode = self.fft_axis.currentIndex()   # 0 = X, 1 = Y, 2 = both (2D)
        win_name = self.fft_window.currentText()
        wparam = (self.fft_winparam.value()
                  if win_name in WINDOW_PARAM else 8.6)
        zf = self.fft_zerofill.currentText()

        if mode == 2:
            # full 2D FFT: both X (columns) and Y (rows) become frequency. The
            # echo-centre skip drops leading columns (the direct/echo X axis).
            skip = max(0, min(int(self.fft_skip.value()), self.src_i.shape[1] - 2))
            src_i = self.src_i[:, skip:]; src_q = self.src_q[:, skip:]
            nrows, ncols = src_i.shape
            win_x = sigproc.apodization_window(ncols, win_name, wparam)
            win_y = sigproc.apodization_window(nrows, win_name, wparam)
            Z = (src_i + 1j*src_q)*win_y[:, None]*win_x[None, :]
            nx = sigproc.zerofill_length(ncols, zf)
            ny = sigproc.zerofill_length(nrows, zf)
            sp = np.fft.fftshift(np.fft.fft2(Z, s=(ny, nx)), axes=(0, 1))
            frx, funx = self._freq_axis(nx, self.src_col['step'], self.src_col['scale'])
            fry, funy = self._freq_axis(ny, self.src_row['step'], self.src_row['scale'])
            dfx = float(frx[1] - frx[0]) if nx > 1 else 1.0
            dfy = float(fry[1] - fry[0]) if ny > 1 else 1.0
            res_col = self._axis(float(frx[0]), dfx, 'Frequency Offset', funx, auto=True)
            res_row = self._axis(float(fry[0]), dfy, 'Frequency Offset', funy, auto=True)
            mx, tx = self._fft_mask(frx, self.fft_x_type, self.fft_x_lo, self.fft_x_hi)
            my, ty = self._fft_mask(fry, self.fft_y_type, self.fft_y_lo, self.fft_y_hi)
            if mx is not None:
                sp = sp*mx[None, :]
            if my is not None:
                sp = sp*my[:, None]
            meta = ['2D FFT (X and Y)',
                    f'skip {skip} leading pts on X (echo centre)' if skip else 'no leading skip',
                    f'window: {win_name}, X {ncols}→{nx}, Y {nrows}→{ny} '
                    f'(zero fill {zf})',
                    f'frequency in {funx} (X), {funy} (Y)']
            meta += [f'passband {n}: {t}' for n, t in (('X', tx), ('Y', ty)) if t]
            bands = '; '.join(f'{n} {t}' for n, t in (('X', tx), ('Y', ty)) if t)
            self._set_result(sp.real, sp.imag, res_col, res_row, ('Re', 'Im'), meta)
            self.set_status(f'2D FFT; skip {skip}; X {ncols}→{nx}, Y {nrows}→{ny}'
                            + (f'; passband {bands}.' if bands else '.'))
            return

        along_x = (mode == 0)
        axis = 1 if along_x else 0
        src_ax = self.src_col if along_x else self.src_row
        # drop leading points so the transform starts at the echo centre; this
        # sets t = 0 there and removes the dead-time first-order phase ramp.
        skip = max(0, min(int(self.fft_skip.value()), self.src_i.shape[axis] - 2))
        sl = [slice(None), slice(None)]; sl[axis] = slice(skip, None)
        src_i = self.src_i[tuple(sl)]; src_q = self.src_q[tuple(sl)]
        n0 = src_i.shape[axis]
        win = sigproc.apodization_window(n0, win_name, wparam)
        shape = [1, 1]; shape[axis] = n0
        Z = (src_i + 1j*src_q)*win.reshape(shape)
        n = sigproc.zerofill_length(n0, zf)
        sp = np.fft.fftshift(np.fft.fft(Z, n=n, axis=axis), axes=axis)
        fr, funit = self._freq_axis(n, src_ax['step'], src_ax['scale'])
        df = float(fr[1] - fr[0]) if n > 1 else 1.0
        freq_ax = self._axis(float(fr[0]), df, 'Frequency Offset', funit, auto=True)
        if along_x:
            res_col, res_row = freq_ax, self.src_row
            mask, tag = self._fft_mask(fr, self.fft_x_type, self.fft_x_lo, self.fft_x_hi)
        else:
            res_col, res_row = self.src_col, freq_ax
            mask, tag = self._fft_mask(fr, self.fft_y_type, self.fft_y_lo, self.fft_y_hi)
        if mask is not None:
            mshape = [1, 1]; mshape[axis] = n
            sp = sp*mask.reshape(mshape)
        meta = [f'FFT along {"X (within trace)" if along_x else "Y (indirect)"}',
                f'skip {skip} leading pts (echo centre)' if skip else 'no leading skip',
                f'window: {self.fft_window.currentText()}, '
                f'points {n0} -> {n} (zero fill {self.fft_zerofill.currentText()})',
                f'frequency in {funit}']
        if tag:
            meta.append(f'passband: {tag}')
        self._set_result(sp.real, sp.imag, res_col, res_row, ('Re', 'Im'), meta)
        self.set_status(f'FFT along {"X" if along_x else "Y"}; skip {skip}; '
                        f'{n0}→{n} pts' + (f'; passband {tag}.' if tag else '.'))

    @staticmethod
    def _passband_mask(freq, ftype, lo, hi):
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

    def _fft_mask(self, freq, type_widget, lo_widget, hi_widget):
        """(keep-mask, description) for one FFT-tab passband; (None, '') when the
        axis is set to 'None'."""
        ftype = type_widget.currentText()
        if ftype == 'None':
            return None, ''
        lo, hi = lo_widget.value(), hi_widget.value()
        used = {'Low-pass': f'hi={hi:.4g}', 'High-pass': f'lo={lo:.4g}',
                'Band-pass': f'lo={lo:.4g}, hi={hi:.4g}'}.get(ftype, '')
        return (self._passband_mask(freq, ftype, lo, hi),
                f'{ftype}, cutoff {used} x f_max')

    def do_filter(self):
        """FFT → zero the frequencies outside the passband → inverse FFT, along X,
        Y or both axes with an independent filter each. The result stays in the
        original domain, so the axes are untouched."""
        if self.src_i is None:
            self.set_status('Open an I/Q dataset first.')
            return
        mode = self.filt_axis.currentIndex()   # 0 = X, 1 = Y, 2 = both
        Z = self.src_i + 1j*self.src_q
        specs = []
        if mode != 1:
            specs.append(('X', 1, self.filt_x_type.currentText(),
                          self.filt_x_lo.value(), self.filt_x_hi.value()))
        if mode != 0:
            specs.append(('Y', 0, self.filt_y_type.currentText(),
                          self.filt_y_lo.value(), self.filt_y_hi.value()))

        meta = ['Filter (FFT->mask->iFFT) along '
                + {0: 'X (within trace)', 1: 'Y (indirect)',
                   2: 'X and Y (independent)'}[mode]]
        parts = []
        for name, axis, ftype, lo, hi in specs:
            n = Z.shape[axis]
            if n < 2:
                self.set_status(f'Need at least two points along {name} to filter.')
                return
            mask = self._passband_mask(np.fft.fftfreq(n), ftype, lo, hi)
            shape = [1, 1]; shape[axis] = n
            sp = np.fft.fft(Z, axis=axis)*mask.reshape(shape)
            Z = np.fft.ifft(sp, axis=axis)
            used = {'Low-pass': f'hi={hi:.4g}', 'High-pass': f'lo={lo:.4g}',
                    'Band-pass': f'lo={lo:.4g}, hi={hi:.4g}'}.get(ftype, '')
            meta.append(f'{name}: {ftype}, cutoff {used} x f_max')
            parts.append(f'{name} {ftype} ({used})')

        self._set_result(Z.real, Z.imag, self.src_col, self.src_row, ('I', 'Q'), meta)
        self.set_status('Filter applied — ' + '; '.join(parts) + ' ×f_max.')

    # --------------------------------------------------------------- shear
    def _shear_geometry(self):
        """(dipolar axis index, its step, echo-coordinate vector, axis names) for
        the current Dipolar-axis choice. Rows (axis 0) are the indirect Y axis."""
        dip = 0 if self.shear_axis.currentIndex() == 0 else 1
        dax = self.src_row if dip == 0 else self.src_col
        eax = self.src_col if dip == 0 else self.src_row
        n_echo = self.src_i.shape[1 - dip]
        tvec = eax['start'] + eax['step']*np.arange(n_echo)
        step = float(dax['step']) or 1.0
        return dip, step, tvec, (dax['name'], eax['name'], eax['scale'])

    @staticmethod
    def _shear_ramp(n_dip, dstep, tvec, k, tref, dip):
        """exp(2πi·ν_dip·k·(t − t_ref)), oriented to multiply the (row, col) map."""
        nu = np.fft.fftfreq(n_dip, dstep)
        ramp = np.exp(2j*np.pi*k*np.outer(nu, tvec - tref))
        return ramp if dip == 0 else ramp.T

    def auto_shear_ref(self):
        """Set t_ref to the echo centre along the echo axis (the |I+iQ| envelope
        averaged over the dipolar axis, so the dipolar modulation cancels)."""
        if self.src_i is None:
            self.set_status('Open an I/Q dataset first.')
            return
        dip, _step, tvec, (_dn, ename, escale) = self._shear_geometry()
        profile = np.sqrt(self.src_i**2 + self.src_q**2).mean(axis=dip)
        idx = int(sigproc.echo_center(profile))
        idx = min(max(idx, 0), len(tvec) - 1)
        self.shear_tref.setValue(float(tvec[idx]))
        self.set_status(f'Shear origin at the echo centre: {ename} = '
                        f'{tvec[idx]:.4g} {escale} (point {idx}).')

    def fit_shear_slope(self):
        """Shear-scan estimator of k: for each k on a grid, shear and sum over the
        echo axis, and take the k maximising the peak of the recovered dipolar
        trace; parabolic refine on the grid maximum. The dipolar-axis transform
        does not depend on k, so it is done once and only the ramp-weighted sum
        is repeated."""
        if self.src_i is None:
            self.set_status('Open an I/Q dataset first.')
            return
        dip, step, tvec, (dname, ename, escale) = self._shear_geometry()
        n_dip = self.src_i.shape[dip]
        tref = float(self.shear_tref.value())
        half = float(self.shear_fitwin.value())
        gate = (np.abs(tvec - tref) <= half) if half > 0 else np.ones(tvec.size, bool)
        if gate.sum() < 2:
            self.set_status('Fit window too narrow — widen it (0 = whole window).')
            return
        Z = self.src_i + 1j*self.src_q
        sp = np.fft.fft(Z, axis=dip)
        sp = sp[:, gate] if dip == 0 else sp[gate, :]
        if dip == 1:
            sp = sp.T                                  # -> (freq, echo) either way
        dt = tvec[gate] - tref
        nu = np.fft.fftfreq(n_dip, step)
        phase = 2j*np.pi*np.outer(nu, dt)

        ks = np.arange(-1.0, 1.0001, 0.01)
        amp = np.empty(ks.size)
        # the ramp steps by a constant factor along the k grid, so it is advanced
        # by one multiply per point instead of re-exponentiating the whole map
        ramp = np.exp(ks[0]*phase)
        dramp = np.exp((ks[1] - ks[0])*phase)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for j in range(ks.size):
                tr = np.abs(np.fft.ifft((sp*ramp).sum(axis=1)))  # phase-blind
                amp[j] = tr.max() - np.median(tr)
                ramp *= dramp
        finally:
            QApplication.restoreOverrideCursor()
        j = int(amp.argmax())
        kbest = float(ks[j])
        if 3 <= j < ks.size - 3:                       # parabolic refine off the grid
            p = np.polyfit(ks[j-3:j+4], amp[j-3:j+4], 2)
            if p[0] < 0:
                kbest = float(-p[1]/(2*p[0]))
        gain = amp[j]/amp[np.abs(ks).argmin()] if amp[np.abs(ks).argmin()] else float('nan')
        self.shear_k.setValue(kbest)                   # fires the live preview
        win = f'±{half:.4g} {escale}' if half > 0 else 'whole window'
        self.set_status(f'Fitted slope k = {kbest:+.4f} ({dname} per {ename}), '
                        f'peak ×{gain:.2f} over k = 0; {win}, {int(gate.sum())} pts.')

    @staticmethod
    def _trace_quality(trace, step):
        """Peak above the median baseline, and S/N against the noise read off the
        top 40 % of the trace's own spectrum — well above any dipolar frequency,
        so it is signal-independent and gated and sheared traces are compared on
        the same footing."""
        tr = np.asarray(trace, dtype=float)
        tr = tr - np.median(tr)
        nu = np.abs(np.fft.fftfreq(tr.size, step))
        band = nu >= 0.6*nu.max()
        sp = np.fft.fft(tr - tr.mean())
        noise = np.sqrt((np.abs(sp[band])**2).mean()/tr.size) if band.any() else 0.0
        return float(tr.max()), (float(tr.max()/noise) if noise else float('nan'))

    def do_shear(self):
        """V′(t_dip, t) = V(t_dip + k·(t − t_ref), t), as the exact phase ramp
        exp(2πi·ν_dip·k·(t − t_ref)) on the dipolar-axis spectrum. Unitary and
        interpolation-free; the axes are unchanged, so it chains like the rest."""
        if self.src_i is None:
            self.set_status('Open an I/Q dataset first.')
            return
        dip, step, tvec, (dname, ename, escale) = self._shear_geometry()
        n_dip = self.src_i.shape[dip]
        if n_dip < 2:
            self.set_status(f'Need at least two points along {dname} to shear.')
            return
        k = float(self.shear_k.value())
        tref = float(self.shear_tref.value())
        Z = self.src_i + 1j*self.src_q
        ramp = self._shear_ramp(n_dip, step, tvec, k, tref, dip)
        Z = np.fft.ifft(np.fft.fft(Z, axis=dip)*ramp, axis=dip)
        pk, sn = self._trace_quality(Z.real.sum(axis=1 - dip), step)
        pk0, _ = self._trace_quality(self.src_i.sum(axis=1 - dip), step)
        gain = pk/pk0 if pk0 else float('nan')
        meta = [f'Shear of {dname} against {ename} (FFT phase ramp, no interpolation)',
                f'k = {k:+.4f} {dname}-units per {ename}-unit, '
                f't_ref = {tref:.4g} {escale}',
                f'flat sum over {ename}: peak {pk:.6g} (x{gain:.2f} unsheared), '
                f'S/N {sn:.0f}']
        self._set_result(Z.real, Z.imag, self.src_col, self.src_row, ('Re', 'Im'), meta)
        self.set_status(f'Shear applied: k = {k:+.4f}, t_ref = {tref:.4g} {escale}; '
                        f'flat sum peak {pk:.6g} (×{gain:.2f} over unsheared), '
                        f'S/N {sn:.0f}.')

    # -------------------------------------------------------------- output
    # ---------------------------------------------------------- per-trace fit
    def _current_iq(self):
        """The dataset operations act on: the result if one exists, else the
        current source (raw or a promoted result)."""
        if self.has_result():
            return self.res_i, self.res_q, self.res_col, self.res_row
        return self.src_i, self.src_q, self.src_col, self.src_row

    @staticmethod
    def _channel(i, q, name):
        if name == 'Magnitude':
            return np.hypot(i, q)
        if name.startswith('Imag'):
            return q
        return i                                # Real (I) — default

    @staticmethod
    def _param_unit(pname, decay_scale):
        if pname.startswith('k') or pname == 'Tm':
            return decay_scale                  # a time constant in decay units
        if pname == 'beta':
            return ''
        return 'V'                              # amplitudes / offset

    def _fit_geometry(self):
        """Resolve (channel matrix as rows-of-decays, decay-axis values,
        other-axis values, other-axis dict, decay-axis dict) for the current
        data and the chosen decay axis."""
        i, q, col, row = self._current_iq()
        chan = self._channel(i, q, self.fit_channel.currentText())
        if self.fit_axis.currentIndex() == 0:            # X = decay (rows are decays)
            xaxis = col['start'] + col['step']*np.arange(chan.shape[1])
            traces = chan
            other = row['start'] + row['step']*np.arange(chan.shape[0])
            return traces, xaxis, other, row, col
        # Y = decay (columns are decays)
        xaxis = row['start'] + row['step']*np.arange(chan.shape[0])
        traces = chan.T
        other = col['start'] + col['step']*np.arange(chan.shape[1])
        return traces, xaxis, other, col, row

    _FIT_STATS_TOOLTIP = (
        '<div style="max-width: 380px;">'
        '<b>Per-trace fit quality</b><br>'
        'Every trace along the decay axis is fit independently; the summary '
        'reports the spread (min / median / max) of two diagnostics across the '
        'series:'
        '<ul style="margin: 4px 0 0 -22px;">'
        '<li><b>R²</b> — fraction of variance explained per trace (1 = '
        'perfect). A low <i>median</i> means the model does not suit the data; '
        'a wide min–max spread means some traces (often the noisy late/early '
        'ones) fit far worse than others.</li>'
        '<li><b>Durbin–Watson</b> — residual-autocorrelation test. <b>≈ 2</b> '
        'means random residuals; well below 2 means the residuals drift '
        'systematically — the model is the wrong shape even where R² looks '
        'high. A median far from 2 is a red flag for the whole series.</li>'
        '</ul>'
        'Traces below <b>Min R²</b> are dropped from the parameter map.'
        '</div>')

    def do_fit_2d(self):
        if self._fitting:                          # don't stack a second fit
            return
        if self.src_i is None:
            self.set_status('Open an I/Q dataset first.')
            return
        model = self.fit_model.currentText()
        pname = self.fit_param.currentText()
        no_offset = self.fit_no_offset.isChecked()
        minr2 = float(self.fit_minr2.value())
        traces, xaxis, other, other_ax, decay_ax = self._fit_geometry()
        n = traces.shape[0]
        params = np.full(n, np.nan)
        r2 = np.full(n, np.nan)
        dw = np.full(n, np.nan)
        fails = 0
        # The fit loop is CPU-bound and would freeze the window ("not responding")
        # for many traces, so we pump the Qt event loop every few traces and show
        # progress. The Run-fit button is disabled meanwhile (the _fitting guard
        # also blocks re-entry from the pumped events); `traces` is a snapshot, so
        # loading new data mid-fit cannot corrupt the running loop.
        self._fitting = True
        self._cancel_fit = False
        self.fit_run_btn.setEnabled(False)
        self.fit_run_btn.setStyleSheet(BUTTON_BUSY_STYLE)
        self.fit_run_btn.setText('Fitting…')
        self.fit_cancel_btn.setEnabled(True)
        chunk = 8
        done = 0
        cancelled = False
        try:
            for k in range(n):
                y = np.asarray(traces[k], float)
                try:
                    res = self.fitter.fit(model, xaxis, y, no_offset=no_offset)
                    names = list(res['param_names'])
                    if pname in names:
                        params[k] = res['popt'][names.index(pname)]
                    r2[k] = res['r_squared']
                    dw[k] = res.get('stats', {}).get('durbin_watson', np.nan)
                    if not np.isfinite(r2[k]) or r2[k] < minr2:
                        params[k] = np.nan
                except Exception:
                    fails += 1
                done = k + 1
                if k % chunk == 0 or k == n - 1:
                    self.status.setText(f'Fitting trace {done}/{n}…')
                    QApplication.processEvents()
                    if self._cancel_fit:           # set by the Cancel button
                        cancelled = True
                        break
        finally:
            self._fitting = False
            self._cancel_fit = False
            self.fit_run_btn.setEnabled(True)
            self.fit_run_btn.setStyleSheet(BUTTON_STYLE)
            self.fit_run_btn.setText('Run fit')
            self.fit_cancel_btn.setEnabled(False)
        valid = np.isfinite(params)
        ngood = int(valid.sum())
        self.fit_map = {'x': other, 'param': params, 'r2': r2, 'pname': pname,
                        'model': model, 'channel': self.fit_channel.currentText(),
                        'no_offset': no_offset, 'other_name': other_ax['name'],
                        'other_scale': other_ax['scale'], 'decay_scale': decay_ax['scale']}
        tag = ' (cancelled)' if cancelled else ''
        if ngood == 0:
            self.fit_info.setText(f'<b>No valid fits{tag}.</b> '
                                  + ('Cancelled before any trace converged. '
                                     if cancelled else
                                     'Try another model, the Magnitude channel, '
                                     'or relax Min R².'))
            self.set_status(f'Fit produced no valid traces{tag}.')
            return
        punit = self._param_unit(pname, decay_ax['scale'])
        name = (self.name_edit.text().strip() or 'FT Data 2D') + f' — {pname} map'
        try:
            general.plot_1d(name, other[valid], params[valid], label=pname,
                            xname=other_ax['name'], xscale=other_ax['scale'],
                            yname=pname, yscale=punit)
        except Exception as e:
            self.set_status(f'Fit done but could not plot map: {e}')
        pv = params[valid]
        rv = r2[valid]
        dwv = dw[valid]
        scope = f"{done}/{n} traces" if cancelled else f"{n} traces"
        rows = [[f'<b>{pname}</b> ({punit})', f'{np.nanmin(pv):.4g}',
                 f'{np.nanmedian(pv):.4g}', f'{np.nanmax(pv):.4g}'],
                ['R²', f'{np.nanmin(rv):.3f}', f'{np.nanmedian(rv):.3f}',
                 f'{np.nanmax(rv):.3f}']]
        if np.any(np.isfinite(dwv)):
            dw_med = np.nanmedian(dwv)
            colour = ('rgb(120, 200, 120)' if 1.5 <= dw_med <= 2.5
                      else 'rgb(214, 160, 78)')
            rows.append([f'<span style="color:{colour};">Durbin–Watson</span>',
                         f'{np.nanmin(dwv):.2f}', f'{dw_med:.2f}',
                         f'{np.nanmax(dwv):.2f}'])
        table = _html_table(['', 'min', 'median', 'max'], rows)
        self.fit_info.setText(
            f'<div style="line-height: 150%;"><b style="color: rgb(211, 194, 78);">'
            f'{model}</b>{tag} · {self.fit_channel.currentText()} · '
            f'{ngood} valid of {scope}'
            + (f', {fails} failed' if fails else '')
            + f'<br>{table}</div>')
        self.set_status(f'Per-trace fit{tag}: {ngood} valid of {scope}; '
                        f'{pname} map plotted.')

    def cancel_fit(self):
        """Ask the running per-trace fit loop to stop at the next chunk boundary;
        traces already fit are kept and mapped."""
        if self._fitting:
            self._cancel_fit = True
            self.status.setText('Cancelling fit…')

    def _sync_slice_from_cursor(self, *args):
        """Follow the heatmap crosshair with the Slice-tab "Trace #". The image
        is (nX points, nY traces); a slice along X picks a trace (the Y/indirect
        index), a slice along Y picks a point (the X index). The crosshair sets
        both at once, so "Slice along" stays user-controlled and only the index
        for the chosen direction is synced. No-ops unless the cross-section is
        active (otherwise the indices don't track the cursor)."""
        cd = self.cross_dock
        if not getattr(cd, 'cross_section_enabled', False) or not hasattr(self, 'slice_spin'):
            return
        if self.slice_axis.currentIndex() == 0:        # along X → trace = Y index
            idx = int(getattr(cd, 'y_cross_index', 0))
        else:                                          # along Y → trace = X index
            idx = int(getattr(cd, 'x_cross_index', 0))
        val = idx + 1                                  # cross index is 0-based; spin is 1-based
        if val != self.slice_spin.value():
            self.slice_spin.setValue(val)              # fires _update_slice_label

    def _update_slice_label(self, *args):
        if not hasattr(self, 'slice_spin'):
            return
        if self.src_i is None:
            self.slice_label.setText('')
            return
        i, q, col, row = self._current_iq()
        if self.slice_axis.currentIndex() == 0:
            ntr, axis = i.shape[0], row
        else:
            ntr, axis = i.shape[1], col
        self.slice_spin.blockSignals(True)
        self.slice_spin.setRange(1, max(1, ntr))       # 1-based: traces 1…ntr
        self.slice_spin.blockSignals(False)
        idx = int(self.slice_spin.value()) - 1         # 0-based for the coordinate
        coord = axis['start'] + axis['step']*idx
        if getattr(self, 'slice_avg', None) is not None and self.slice_avg.isChecked():
            self.slice_spin2.blockSignals(True)
            self.slice_spin2.setRange(1, max(1, ntr))
            self.slice_spin2.blockSignals(False)
            idx2 = int(self.slice_spin2.value()) - 1
            lo, hi = sorted((idx, idx2))
            c2 = axis['start'] + axis['step']*idx2
            self.slice_label.setText(f"{axis['name']} = {coord:.4g}…{c2:.4g} "
                                     f"{axis['scale']} (avg {hi - lo + 1} of {ntr})")
        else:
            self.slice_label.setText(f"{axis['name']} = {coord:.4g} {axis['scale']} (of {ntr})")

    def _write_buffer(self, curves, xname=''):
        """Write a one-shot 1D-tool mailbox (libs/treatment_buffer.csv): interleaved
        x0,y0,x1,y1,… columns padded with NaN, '# labels:' header naming the curves.
        An optional '# xname:' line carries the X axis name+unit so the 1D tool can
        label and SI-prefix the axis (e.g. a 's' slice axis then reads in ns)."""
        maxlen = max(np.asarray(x).size for _, x, _ in curves)
        buf = np.full((maxlen, 2*len(curves)), np.nan)
        labels = []
        for j, (lab, x, y) in enumerate(curves):
            x = np.asarray(x, float); y = np.asarray(y, float)
            buf[:x.size, 2*j] = x
            buf[:y.size, 2*j + 1] = y
            labels.append(str(lab).replace('|', '/'))
        header_lines = ['Atomize data treatment buffer', 'labels: ' + '|'.join(labels)]
        if xname:
            header_lines.append('xname: ' + str(xname).replace('\n', ' '))
        header = '\n'.join(header_lines)
        np.savetxt(BUFFER_PATH, buf, delimiter=',', fmt='%.6e', header=header, comments='# ')

    def _compute_slice(self):
        """Build the current slice (Re/Im vs the decay axis), averaging the
        selected index range when 'Average up to #' is on. Returns a dict, or
        None (with a status set) when no dataset is loaded."""
        if self.src_i is None:
            self.set_status('Open an I/Q dataset first.')
            return None
        i, q, col, row = self._current_iq()
        averaging = self.slice_avg.isChecked()
        along_x = self.slice_axis.currentIndex() == 0
        if along_x:                                      # X = slice; row(s)
            ntr = i.shape[0]
            x = col['start'] + col['step']*np.arange(i.shape[1])
            dax, oax = col, row
        else:                                            # Y = slice; column(s)
            ntr = i.shape[1]
            x = row['start'] + row['step']*np.arange(i.shape[0])
            dax, oax = row, col
        # Trace # is 1-based in the UI (matches the cursor label); -1 here for the
        # 0-based array index. lo/hi/tag are reported 1-based to the user.
        idx = min(max(int(self.slice_spin.value()) - 1, 0), ntr - 1)
        self.slice_spin.setValue(idx + 1)
        idx2 = min(max(int(self.slice_spin2.value()) - 1, 0), ntr - 1)
        lo, hi = sorted((idx, idx2))
        mean = averaging and hi > lo
        if mean:
            if along_x:
                re = i[lo:hi + 1].mean(axis=0); im = q[lo:hi + 1].mean(axis=0)
            else:
                re = i[:, lo:hi + 1].mean(axis=1); im = q[:, lo:hi + 1].mean(axis=1)
            tag = f'{lo + 1}-{hi + 1}'
            coord = oax['start'] + oax['step']*0.5*(lo + hi)
        else:
            # Not averaging: use the selected Trace # directly. lo = min(idx, idx2)
            # would snap to the (default-0) "average up to #" spin and always send
            # trace 0 instead of the indicated one.
            re = i[idx] if along_x else i[:, idx]
            im = q[idx] if along_x else q[:, idx]
            lo = hi = idx                  # report the actual trace, not the spin2 default
            tag = str(idx + 1)
            coord = oax['start'] + oax['step']*idx
        return {'x': x, 're': re, 'im': im, 'dax': dax, 'oax': oax,
                'tag': tag, 'coord': coord, 'mean': mean, 'lo': lo, 'hi': hi}

    def save_slice(self):
        """Save the current (optionally averaged) slice to a CSV: decay axis, Re, Im."""
        sl = self._compute_slice()
        if sl is None:
            return
        file_path = self._save_dialog()
        if not file_path or file_path == 'None':
            return
        dax, oax = sl['dax'], sl['oax']
        arr = np.column_stack([np.asarray(sl['x'], float),
                               np.asarray(sl['re'], float),
                               np.asarray(sl['im'], float)])
        kind = (f'mean of traces {sl["lo"] + 1}–{sl["hi"] + 1}' if sl['mean']
                else f'trace {sl["lo"] + 1}')
        header = '\n'.join([
            f'2D slice ({kind}); {oax["name"]} = {sl["coord"]:.6g} {oax["scale"]}',
            f'columns: {dax["name"]} ({dax["scale"]}), Re/I, Im/Q'])
        self.opener.save_data(file_path, arr, header=header, mode='w')
        self.set_status(f'Saved slice {sl["tag"]} to {os.path.basename(file_path)}.')

    def send_slice_to_1d(self):
        sl = self._compute_slice()
        if sl is None:
            return
        x, re, im = sl['x'], sl['re'], sl['im']
        dax, oax, tag, coord, mean = (sl['dax'], sl['oax'], sl['tag'],
                                      sl['coord'], sl['mean'])
        # carry the decay axis name+unit so the 1D tool labels and SI-prefixes it
        # (a slice taken in 's' then displays in ns rather than raw 2e-9).
        xname = f"{dax['name']} ({dax['scale']})" if dax['scale'] else dax['name']
        try:
            self._write_buffer([('slice Re', x, re), ('slice Im', x, im)], xname=xname)
        except Exception as e:
            self.set_status(f'Could not write transfer buffer: {e}')
            return
        # Deliberately not plotted in the main GUI: the slice goes only to the 1D
        # tool's transfer buffer, so it doesn't clutter the main window's docks.
        what = (f'Mean slice {tag}' if mean else f'Slice #{tag}')
        self.set_status(f'{what} ({oax["name"]} = {coord:.4g} {oax["scale"]}) '
                        f'sent to buffer. In the 1D Data Treatment window click '
                        f'"Load from plot" (I = slice Re, Q = slice Im).')

    def save_fit_map(self):
        if not self.fit_map:
            self.set_status('Run a fit first — no map to save.')
            return
        file_path = self._save_dialog()
        if not file_path or file_path == 'None':
            return
        m = self.fit_map
        arr = np.column_stack([m['x'], m['param'], m['r2']])
        punit = self._param_unit(m['pname'], m['decay_scale'])
        header = '\n'.join([
            '2D per-trace fit map',
            f'model = {m["model"]}, channel = {m["channel"]}, fix_offset = {m["no_offset"]}',
            f'columns: {m["other_name"]} ({m["other_scale"]}), '
            f'{m["pname"]} ({punit}), R^2'])
        self.opener.save_data(file_path, arr, header=header, mode='w')
        self.set_status(f'Saved fit map to {os.path.basename(file_path)}.')

    def save_result(self):
        if not (self.has_result() or self.src_i is not None):
            self.set_status('Nothing to save — load data first.')
            return
        file_path = self._save_dialog()
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
    from atomize.general_modules.gui_style import apply_app_style
    apply_app_style(app, app_id='Atomize.ITC.DataTreatment2D', desktop='treat2d')
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
