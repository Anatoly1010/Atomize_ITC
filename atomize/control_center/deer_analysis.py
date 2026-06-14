#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone DEER / PDS analysis window.

Background-corrects a dipolar (DEER / PELDOR) time trace V(t) and inverts the
dipolar kernel to a distance distribution P(r) by Tikhonov + NNLS — the same
engine (atomize/math_modules/deer.py) that backs the DEER tab of the 1D Data
Treatment tool, but promoted to a dedicated window with a two-plot layout:

    top    — time domain: V(t), the fitted background and the model fit
             (switchable to form factor + fit / background fit / L-curve)
    bottom — the distance distribution P(r)

Load a real V(t) directly, or a complex I/Q pair (CSV, Bruker, or the main
window's "Send to Data Treatment" plot buffer) and zero-order-phase it to a real
trace here. Launched as its own QProcess from the EPR Endstation Control tab,
or run directly:  python3 atomize/control_center/deer_analysis.py
"""

import os
import sys
import numpy as np
from pathlib import Path

import pyqtgraph as pg
from pyqtgraph.dockarea import DockArea
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QComboBox, QGridLayout, QVBoxLayout, QHBoxLayout, QDoubleSpinBox, QSpinBox,
    QCheckBox, QFrame, QScrollArea, QTabWidget)

import atomize.general_modules.general_functions as general
import atomize.general_modules.csv_opener_saver as openfile
import atomize.general_modules.bruker_opener as bruker
import atomize.math_modules.fft as fft_module
import atomize.math_modules.deer as deer_module

from atomize.main.widgets import CrosshairPlotWidget, CloseableDock

# Shared dark-theme palette / widget styles (single source of truth across all
# control-center tools); apply_app_style() pins this process to the Fusion style.
from atomize.general_modules.gui_style import (apply_app_style,
    BG, ACCENT, BUTTON_STYLE, LABEL_STYLE, DSPIN_STYLE, SPIN_STYLE,
    COMBO_STYLE, CHECKBOX_STYLE, SCROLL_STYLE, TAB_STYLE)

# Plot buffer written by the main-window plot sidebar ("Send to Data Treatment");
# shared one-shot mailbox with the Data Treatment tools (libs/ runtime IPC).
BUFFER_PATH = str(Path(__file__).resolve().parent.parent.parent / 'libs' / 'treatment_buffer.csv')
# Folder of the last file opened/saved here — shared working folder with the
# Data Treatment tools so dialogs reopen where you left off.
LASTDIR_PATH = str(Path(__file__).resolve().parent.parent.parent / 'libs' / 'treatment_lastdir.txt')

ROW_H = 28


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


# Bare SI units worth auto-prefixing on an axis ('s' -> '2 ns', not '2e-9 s');
# already-prefixed units ('ns', 'nm') and dimensionless labels stay verbatim.
SI_BASE_UNITS = {'s', 'hz', 'v', 'a', 'g', 't', 'k', 'm', 'ev'}


def _si_autoprefix(unit):
    return str(unit).strip().lower() in SI_BASE_UNITS


def _split_unit(label):
    """Split a 'Name (unit)' axis label into ('Name', 'unit')."""
    s = str(label).strip()
    if s.endswith(')') and '(' in s:
        i = s.rfind('(')
        return s[:i].strip(), s[i + 1:-1].strip()
    return s, ''


# Solid-accent "busy" variant for the Run button while an inversion is running.
BUTTON_BUSY_STYLE = (
    f"QPushButton {{border-radius: 4px; background-color: {ACCENT}; "
    f"border-style: inset; color: {BG}; font-weight: bold; padding: 4px; }} "
    f"QPushButton:disabled {{background-color: {ACCENT}; color: {BG}; }}")

# Curve colours (match the Data Treatment preview convention).
C_DATA = (120, 170, 255)     # V(t) / form factor — blue
C_IM   = (220, 120, 220)     # imaginary (Q) channel after phasing — magenta
C_BG   = (230, 140, 90)      # fitted background — orange
C_FIT  = (211, 194, 78)      # model fit / P(r) / L-curve — gold


class _DeerWorker(QThread):
    """Runs one DEER inversion (optionally zero-time fit + validation) off the GUI
    thread. The work is pure numpy/scipy (the heavy NNLS/least-squares releases the
    GIL), so the window stays responsive during the ~10-60 s joint fit. `fn` is a
    closure that captures plain values only (no Qt widgets); its return value — or
    the Exception it raised — is delivered to the main thread via `done`."""
    done = pyqtSignal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as e:                    # surfaced on the main thread
            self.done.emit(e)


class MainWindow(QMainWindow):

    # time-unit -> factor that converts the X axis into microseconds (kernel unit)
    DEER_TUNITS = {'µs': 1.0, 'ns': 1e-3, 'ms': 1e3}

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        if len(sys.argv) > 1:
            self.test_flag = sys.argv[1]
        else:
            self.test_flag = 'None'

        self.opener = openfile.Saver_Opener()
        self.bruker = bruker.Bruker_Opener()
        self.fft = fft_module.Fast_Fourier()

        # label -> (x, y) of every loaded source curve
        self.datasets = {}
        # phased real trace (x, V) fed to the inversion — the DEER input
        self.real_xy = (None, None)
        # phased imaginary trace (Q after rotation), shown alongside V(t) so the
        # zero-order phase can be tuned to push all signal into the real part;
        # None for a single real channel
        self.imag_y = None

        # DEER/PDS state: last full result dict + validation ensemble
        self.deer_result = None
        self.deer_band = None
        # P(r) validation band items (on the bottom plot)
        self._band_lo = self._band_hi = self._band_fill = None
        # draggable background start/end cursors + L-curve marker (top plot)
        self._bg_cursor = None
        self._bg_cursor_end = None
        self._lcurve_marker = None
        self._suppress_cursor = False     # guard against cursor<->spinbox echo
        self._suppress_live = False
        # background-thread state for the (slow) inversion
        self._deer_worker = None          # keep a ref so a running QThread is not GC'd
        self._deer_busy = False
        self._deer_pending = False        # a request arrived mid-run -> re-run once

        # persistent curve items per plot (label -> PlotDataItem), reused via
        # setData so live updates never tear down / rebuild plot items
        self._time_items = {}
        self._pr_items = {}
        self._time_key = None
        self._pr_key = None

        self.last_dir = _load_last_dir()

        self.design()
        self.load_from_buffer(silent=True)

    # ----------------------------------------------------------------- UI
    def design(self):
        self.setWindowTitle('DEER / PDS Analysis')
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 'gui', 'icon_temp.png')
        self.setWindowIcon(QIcon(icon_path))
        self.setMinimumHeight(740)
        self.setMinimumWidth(1000)
        self.resize(1180, 820)
        # background on the QMainWindow (not the central widget) so spinboxes
        # keep their full native frame
        self.setStyleSheet(f"background-color: {BG};")

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        # Two stacked plots on the left, controls on the right.
        root.addWidget(self._build_plots(), stretch=1)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setStyleSheet('color: rgb(83, 83, 117);')
        root.addWidget(sep)

        root.addWidget(self._build_controls(), stretch=0)

        # +/- buttons on every spinbox and a common minimum row height across
        # spinboxes / combos / buttons (repo-wide compact-row convention).
        for wdg in self.findChildren((QComboBox, QPushButton)):
            wdg.setMinimumHeight(ROW_H)
        for spin in self.findChildren((QSpinBox, QDoubleSpinBox)):
            spin.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
            spin.setMinimumHeight(ROW_H)

    def _build_plots(self):
        # Two CrosshairPlotWidgets stacked in one DockArea (atomize/main/widgets):
        # the time trace on top, P(r) below. No setBackground — inherit
        # pyqtgraph's global background set in widgets.py. Close buttons hidden
        # (the docks are the only plots and must not be dismissable).
        pg.setConfigOptions(antialias=True)
        self.plot_area = DockArea()

        self.p_time = CrosshairPlotWidget()
        self.p_time.showGrid(x=True, y=True, alpha=0.2)
        self.p_time.setLabel('bottom', 'Time', units='s')
        # nudge the legend left of the right edge so it clears the (right-side)
        # background-end cursor line
        self.time_legend = self.p_time.addLegend(offset=(-55, 10))
        dock_time = CloseableDock(name='Time domain', widget=self.p_time)
        dock_time.close_button.hide()

        self.p_pr = CrosshairPlotWidget()
        self.p_pr.showGrid(x=True, y=True, alpha=0.2)
        self.p_pr.setLabel('bottom', 'Distance', units='nm')
        self.p_pr.setLabel('left', 'P(r)')
        self.pr_legend = self.p_pr.addLegend(offset=(-10, 10))
        dock_pr = CloseableDock(name='Distance distribution P(r)', widget=self.p_pr)
        dock_pr.close_button.hide()

        self.plot_area.addDock(dock_time, 'top')
        self.plot_area.addDock(dock_pr, 'bottom', dock_time)

        # click-to-pick alpha on the L-curve view (single-click; the crosshair
        # toggle uses double-click, so the two don't conflict)
        self.p_time.scene().sigMouseClicked.connect(self._on_lcurve_click)
        return self.plot_area

    # ---- small widget helpers (mirror the Data Treatment tools) ----
    def _label(self, text):
        lab = QLabel(text)
        lab.setStyleSheet(LABEL_STYLE)
        return lab

    def _note(self, text):
        lab = QLabel(f'<div style="line-height: 145%;">{text}</div>')
        lab.setStyleSheet(LABEL_STYLE)
        lab.setWordWrap(True)
        lab.setTextFormat(Qt.TextFormat.RichText)
        return lab

    def _heading(self, text):
        lab = QLabel(text)
        lab.setStyleSheet(f"QLabel {{ color: {ACCENT}; font-weight: bold; font-size: 13px; }}")
        return lab

    def _hline(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setStyleSheet('color: rgb(83, 83, 117);')
        return line

    def _build_controls(self):
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget()
        tabs.setStyleSheet(TAB_STYLE)
        tabs.addTab(self._scroll(self._build_source_tab()), 'Source')
        tabs.addTab(self._scroll(self._build_phase_tab()), 'Phase')
        tabs.addTab(self._scroll(self._build_background_tab()), 'Background')
        tabs.addTab(self._scroll(self._build_deer_tab()), 'Tikhonov')
        tabs.addTab(self._scroll(self._build_mellin_tab()), 'Mellin')
        outer.addWidget(tabs, stretch=1)

        # Shared inversion controls (distance grid + top-plot view) used by BOTH
        # the DEER and Mellin engines, kept always visible below the tabs so
        # neither tab has to be left to set them.
        outer.addWidget(self._hline())
        outer.addWidget(self._build_shared_controls())

        # Status line lives below the tabs so it is always visible.
        self.status = QLabel('Load a V(t) trace to begin.')
        self.status.setStyleSheet(LABEL_STYLE)
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        container.setFixedWidth(430)
        return container

    def _build_shared_controls(self):
        """Distance grid (min / max / points) and the top-plot view selector —
        shared by the Tikhonov (DEER) and Mellin engines, so they live in an
        always-visible strip below the tabs rather than inside one engine's tab."""
        w = QWidget()
        grid = QGridLayout(w)
        grid.setContentsMargins(0, 4, 0, 0)
        r = 0

        grid.addWidget(self._label('Distance min/max (nm)'), r, 0)
        rr_row = QHBoxLayout()
        self.deer_rmin = QDoubleSpinBox()
        self.deer_rmin.setStyleSheet(DSPIN_STYLE)
        self.deer_rmin.setRange(0.5, 50.0); self.deer_rmin.setDecimals(2)
        self.deer_rmin.setSingleStep(0.1); self.deer_rmin.setValue(1.5)
        self.deer_rmin.valueChanged.connect(self._live_update)
        self.deer_rmin.valueChanged.connect(self._mellin_live)
        self.deer_rmax = QDoubleSpinBox()
        self.deer_rmax.setStyleSheet(DSPIN_STYLE)
        self.deer_rmax.setRange(0.5, 50.0); self.deer_rmax.setDecimals(2)
        self.deer_rmax.setSingleStep(0.1); self.deer_rmax.setValue(8.0)
        self.deer_rmax.valueChanged.connect(self._live_update)
        self.deer_rmax.valueChanged.connect(self._mellin_live)
        btn_autormax = QPushButton('Auto')
        btn_autormax.setStyleSheet(BUTTON_STYLE)
        btn_autormax.setToolTip(
            'Set the distance max to the longest distance the trace length '
            'supports: r_max ≈ 5·(t_max/2)^⅓ nm (DeerAnalysis/Jeschke rule). '
            'Set automatically on load; mass beyond it is not constrained by the '
            'data.')
        btn_autormax.clicked.connect(self._auto_rmax)
        rr_row.addWidget(self.deer_rmin); rr_row.addWidget(self.deer_rmax)
        rr_row.addWidget(btn_autormax)
        grid.addLayout(rr_row, r, 1); r += 1

        grid.addWidget(self._label('Distance points'), r, 0)
        self.deer_rn = QSpinBox()
        self.deer_rn.setStyleSheet(SPIN_STYLE)
        self.deer_rn.setRange(20, 2000); self.deer_rn.setValue(200)
        self.deer_rn.valueChanged.connect(self._live_update)
        self.deer_rn.valueChanged.connect(self._mellin_live)
        grid.addWidget(self.deer_rn, r, 1); r += 1

        grid.addWidget(self._label('Show (top plot)'), r, 0)
        self.deer_show = QComboBox()
        self.deer_show.setStyleSheet(COMBO_STYLE)
        self.deer_show.addItems(['V(t) + background + fit', 'Form factor + fit',
                                 'Background fit', 'L-curve'])
        self.deer_show.setToolTip('Top-plot view (the L-curve view applies to the '
                                  'Tikhonov engine only).')
        self.deer_show.currentIndexChanged.connect(self._deer_rerender)
        grid.addWidget(self.deer_show, r, 1); r += 1

        # Uncertainty options shared by both engines.
        self.deer_ci_chk = QCheckBox('Show 95% confidence band')
        self.deer_ci_chk.setStyleSheet(CHECKBOX_STYLE)
        self.deer_ci_chk.setChecked(True)
        self.deer_ci_chk.setToolTip(
            'Shade the 95% confidence interval on P(r). Tikhonov: covariance / '
            'curvature CI (as DeerLab shows by default). Mellin: Monte-Carlo band '
            'from re-inverting the form factor with the fit-residual noise. '
            'Superseded by the Validate band when that is on.')
        self.deer_ci_chk.stateChanged.connect(self._ci_toggled)
        grid.addWidget(self.deer_ci_chk, r, 0, 1, 2); r += 1

        self.deer_validate_chk = QCheckBox('Validate (background sweep → P(r) band)')
        self.deer_validate_chk.setStyleSheet(CHECKBOX_STYLE)
        self.deer_validate_chk.setToolTip(
            'Re-run the inversion over a sweep of background-start times and show '
            'the median P(r) with a 5–95% uncertainty band (DeerAnalysis-style). '
            'Works for both the Tikhonov and Mellin engines.')
        self.deer_validate_chk.stateChanged.connect(self._live_update)
        self.deer_validate_chk.stateChanged.connect(self._mellin_live)
        grid.addWidget(self.deer_validate_chk, r, 0, 1, 2); r += 1
        return w

    def _ci_toggled(self, *args):
        """Confidence-band checkbox: Tikhonov keeps its CI in the result so a
        re-render suffices; the Mellin CI is a Monte-Carlo pass computed only when
        requested, so toggling it on needs a re-inversion."""
        if self.deer_result is None:
            return
        if self.deer_result.get('engine') == 'mellin':
            if self.real_xy[0] is not None:
                self.do_mellin()
            else:
                self._render()
        else:
            self._render()

    def _scroll(self, inner):
        """Wrap a tab's content in a scroll area so it never clips on a short
        window."""
        sa = QScrollArea()
        sa.setStyleSheet(SCROLL_STYLE)
        sa.setWidgetResizable(True)
        sa.setWidget(inner)
        return sa

    # ---- Tab 1: Source (load / channels / trim) ----
    def _build_source_tab(self):
        w = QWidget()
        panel = QVBoxLayout(w)
        src_row = QHBoxLayout()
        for text, slot in (('Open CSV…', self.open_csv),
                           ('Open Bruker…', self.open_bruker),
                           ('Load from plot', lambda: self.load_from_buffer(silent=False)),
                           ('Clear', self.clear_all)):
            btn = QPushButton(text)
            btn.setStyleSheet(BUTTON_STYLE)
            btn.clicked.connect(slot)
            src_row.addWidget(btn)
        panel.addLayout(src_row)

        self.loaded_label = QLabel('File: —')
        self.loaded_label.setStyleSheet(LABEL_STYLE)
        self.loaded_label.setWordWrap(True)
        panel.addWidget(self.loaded_label)

        ch_grid = QGridLayout()
        ch_grid.addWidget(self._label('I / primary (V(t))'), 0, 0)
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

        self.pair_check = QCheckBox('I/Q pair — phase to a real V(t)')
        self.pair_check.setStyleSheet(CHECKBOX_STYLE)
        self.pair_check.stateChanged.connect(self.on_source_changed)
        panel.addWidget(self.pair_check)

        # Trim: discard leading/trailing points before phasing/inversion
        trim_row = QHBoxLayout()
        trim_row.addWidget(self._label('Trim start/end (pts)'))
        self.trim_start = QSpinBox()
        self.trim_start.setStyleSheet(SPIN_STYLE)
        self.trim_start.setRange(0, 10**7)
        self.trim_start.setToolTip('Discard this many points from the start of the '
                                   'trace (e.g. dead-time / rising edge) before phasing.')
        self.trim_start.valueChanged.connect(self._trim_changed)
        self.trim_end = QSpinBox()
        self.trim_end.setStyleSheet(SPIN_STYLE)
        self.trim_end.setRange(0, 10**7)
        self.trim_end.setToolTip('Discard this many points from the end of the trace '
                                 '(e.g. a corrupted tail) before phasing.')
        self.trim_end.valueChanged.connect(self._trim_changed)
        trim_row.addWidget(self.trim_start)
        trim_row.addWidget(self.trim_end)
        panel.addLayout(trim_row)
        panel.addStretch(1)
        return w

    # ---- Tab 2: Phase (zero-order) ----
    def _build_phase_tab(self):
        w = QWidget()
        panel = QVBoxLayout(w)
        panel.addWidget(self._note('Rotate the complex I/Q so the real part is the '
                                   'DEER trace. "Auto" maximises the magnitude-'
                                   'weighted real part. Ignored for a single real '
                                   'channel.'))
        ph_row = QHBoxLayout()
        ph_row.addWidget(self._label('φ₀ (deg)'))
        self.phase_zero = QDoubleSpinBox()
        self.phase_zero.setStyleSheet(DSPIN_STYLE)
        self.phase_zero.setRange(0.0, 360.0)
        self.phase_zero.setDecimals(2)
        self.phase_zero.setSingleStep(0.5)
        self.phase_zero.setWrapping(True)
        self.phase_zero.valueChanged.connect(self._phase_changed)
        ph_row.addWidget(self.phase_zero)
        btn_autoph = QPushButton('Auto')
        btn_autoph.setStyleSheet(BUTTON_STYLE)
        btn_autoph.clicked.connect(self.auto_phase_zero)
        ph_row.addWidget(btn_autoph)
        panel.addLayout(ph_row)
        panel.addStretch(1)
        return w

    # ---- Tab 3: Background (zero-time + intermolecular background) ----
    def _build_background_tab(self):
        w = QWidget()
        panel = QVBoxLayout(w)
        panel.addWidget(self._note('Zero-time and the intermolecular background '
                                   'window/model used to correct V(t). Drag the gold '
                                   '(start) / blue (end) lines on the plot, or use '
                                   'the buttons.'))
        grid = QGridLayout()
        r = 0

        grid.addWidget(self._label('Time unit'), r, 0)
        self.deer_tunit = QComboBox()
        self.deer_tunit.setStyleSheet(COMBO_STYLE)
        self.deer_tunit.addItems(list(self.DEER_TUNITS.keys()))
        self.deer_tunit.currentIndexChanged.connect(self._unit_changed)
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
        self.deer_fit_t0 = QCheckBox('Fit')
        self.deer_fit_t0.setStyleSheet(CHECKBOX_STYLE)
        self.deer_fit_t0.setChecked(True)
        self.deer_fit_t0.setToolTip(
            'Automatically fit the zero-time (dipolar reference time) by '
            'minimizing the fit residual before inverting — the equivalent of '
            "DeerLab's reftime. A wrong t0 broadens P(r) and biases it long, so "
            'this matters more than the background depth. Uncheck to set t0 '
            'manually (spin box / Max).')
        self.deer_fit_t0.stateChanged.connect(self._live_update)
        t0_row.addWidget(self.deer_t0); t0_row.addWidget(btn_t0)
        t0_row.addWidget(self.deer_fit_t0)
        grid.addLayout(t0_row, r, 1); r += 1

        grid.addWidget(self._label('Background start'), r, 0)
        bg_row = QHBoxLayout()
        self.deer_bgstart = QDoubleSpinBox()
        self.deer_bgstart.setStyleSheet(DSPIN_STYLE)
        self.deer_bgstart.setRange(-1e9, 1e9)
        self.deer_bgstart.setDecimals(4)
        self.deer_bgstart.setSingleStep(0.05)
        self.deer_bgstart.valueChanged.connect(self._live_update)
        btn_autobg = QPushButton('Auto')
        btn_autobg.setStyleSheet(BUTTON_STYLE)
        btn_autobg.setToolTip(
            'Place the background start where the dipolar modulation has decayed '
            '(end of the last stretch with a significant oscillation envelope). '
            'Set automatically on load; click to re-estimate.')
        btn_autobg.clicked.connect(self._auto_bg_start)
        bg_row.addWidget(self.deer_bgstart); bg_row.addWidget(btn_autobg)
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
        self.deer_engine.setCurrentIndex(1)            # Joint (global) is the default
        self.deer_engine.setToolTip(
            'Sequential: fit the background on the tail window, divide it out, '
            'then invert (fast).\nJoint (global): fit background + modulation '
            'depth together with P(r) in one pass (DeerLab-style) — more robust '
            'when the background window is short or hard to place, and required '
            'for a clean Mellin fit. Default.')
        self.deer_engine.currentIndexChanged.connect(self._live_update)
        self.deer_engine.currentIndexChanged.connect(self._mellin_live)
        grid.addWidget(self.deer_engine, r, 1); r += 1
        panel.addLayout(grid)
        panel.addStretch(1)
        return w

    # ---- Tab 4: Tikhonov inversion ----
    def _build_deer_tab(self):
        w = QWidget()
        panel = QVBoxLayout(w)
        panel.addWidget(self._note('Invert the dipolar kernel to a distance '
                                   'distribution P(r) (Tikhonov + NNLS). Needs scipy. '
                                   'Distance grid and the top-plot view are set in '
                                   'the shared controls below the tabs.'))
        grid = QGridLayout()
        r = 0

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

        grid.addWidget(self._label('α strength ×'), r, 0)
        self.deer_alpha_factor = QDoubleSpinBox()
        self.deer_alpha_factor.setStyleSheet(DSPIN_STYLE)
        self.deer_alpha_factor.setRange(0.1, 50.0)
        self.deer_alpha_factor.setDecimals(2)
        self.deer_alpha_factor.setSingleStep(0.5)
        self.deer_alpha_factor.setValue(1.0)
        self.deer_alpha_factor.setToolTip(
            'Multiply the auto-selected (GCV) α by this factor. GCV under-'
            'regularizes the near-vertical DEER L-curve, leaving spiky P(r); '
            '2–4× reproduces the heavier hand-picked L-corner the DeerAnalysis '
            'ring-test labs used for smooth distributions (JACS 2021). Ignored '
            'when α is set manually.')
        self.deer_alpha_factor.valueChanged.connect(self._live_update)
        grid.addWidget(self.deer_alpha_factor, r, 1); r += 1

        self.live_check = QCheckBox('Live update on parameter change')
        self.live_check.setStyleSheet(CHECKBOX_STYLE)
        grid.addWidget(self.live_check, r, 0, 1, 2); r += 1

        run_row = QHBoxLayout()
        self.deer_run_btn = QPushButton('Run Tikhonov')
        self.deer_run_btn.setStyleSheet(BUTTON_STYLE)
        self.deer_run_btn.clicked.connect(self.do_deer)
        btn_exp = QPushButton('Export all…')
        btn_exp.setStyleSheet(BUTTON_STYLE)
        btn_exp.clicked.connect(self.save_deer_all)
        run_row.addWidget(self.deer_run_btn); run_row.addWidget(btn_exp)
        grid.addLayout(run_row, r, 0, 1, 2); r += 1
        panel.addLayout(grid)

        self.deer_info = QLabel('')
        self.deer_info.setStyleSheet(LABEL_STYLE)
        self.deer_info.setWordWrap(True)
        self.deer_info.setTextFormat(Qt.TextFormat.RichText)
        self.deer_info.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        panel.addWidget(self.deer_info)
        panel.addStretch(1)
        return w

    # ---- Tab 5: Mellin transform (analytic, model-free inversion) ----
    def _build_mellin_tab(self):
        w = QWidget()
        panel = QVBoxLayout(w)
        panel.addWidget(self._note(
            'Model-free inversion by the analytic integral <b>Mellin transform</b> '
            '(Matveeva, Nekrasov, Maryasov, <i>PCCP</i> 2017, '
            'doi 10.1039/C7CP04059H). No Tikhonov, no NNLS, no L-curve: the '
            'distance distribution is recovered analytically, so it is not '
            'broadened and bimodal peaks are not merged. Noise enters P(r) '
            'additively and groups at <b>short r</b> (the method\'s signature), so '
            'ripples below the reliable range are propagated noise, not structure.'))
        panel.addWidget(self._note(
            'Uses the <b>Background</b> tab\'s zero-time / window / dimension / '
            'fit engine and the shared distance grid below the tabs. The Mellin '
            'kernel decays to zero, so it cannot absorb a DC pedestal left by a '
            'too-shallow background — the <b>Joint</b> background engine '
            '(Background tab) is recommended for a clean fit.'))
        grid = QGridLayout()
        r = 0

        grid.addWidget(self._label('Split δ'), r, 0)
        delta_row = QHBoxLayout()
        self.mellin_delta = QDoubleSpinBox()
        self.mellin_delta.setStyleSheet(DSPIN_STYLE)
        self.mellin_delta.setRange(0.0, 1e9)
        self.mellin_delta.setDecimals(5)
        self.mellin_delta.setSingleStep(0.001)
        self.mellin_delta.setValue(0.0)          # 0 ⇒ auto (F(δ) ≈ 0.95)
        self.mellin_delta.setToolTip(
            'Mellin split point δ (display time units), the lone regularizing '
            'knob: on [0, δ] the form factor is taken constant and integrated '
            'analytically; [δ, end] is integrated numerically. The practical '
            'estimate is F(δ) ≈ 0.95 (paper recommendation). 0 = auto. Larger δ '
            'regularizes more (smoother, less short-r noise); too large loses '
            'resolution.')
        self.mellin_delta.valueChanged.connect(self._mellin_live)
        self.mellin_delta_auto = QCheckBox('Auto')
        self.mellin_delta_auto.setStyleSheet(CHECKBOX_STYLE)
        self.mellin_delta_auto.setChecked(True)
        self.mellin_delta_auto.setToolTip('Estimate δ from F(δ) ≈ 0.95.')
        self.mellin_delta_auto.stateChanged.connect(self._mellin_delta_toggle)
        self.mellin_delta.setEnabled(False)
        delta_row.addWidget(self.mellin_delta); delta_row.addWidget(self.mellin_delta_auto)
        grid.addLayout(delta_row, r, 1); r += 1

        grid.addWidget(self._label('τ max'), r, 0)
        tm_row = QHBoxLayout()
        self.mellin_taumax = QDoubleSpinBox()
        self.mellin_taumax.setStyleSheet(DSPIN_STYLE)
        self.mellin_taumax.setRange(2.0, 200.0)
        self.mellin_taumax.setDecimals(1)
        self.mellin_taumax.setSingleStep(5.0)
        self.mellin_taumax.setValue(25.0)
        self.mellin_taumax.setEnabled(False)
        self.mellin_taumax.setToolTip(
            'Upper limit of the Mellin variable τ (the transform runs over '
            '[−τmax, τmax]). The high-τ cutoff is the regularizer: too small '
            'blurs P(r); too large amplifies noise. 20–30 is typical.')
        self.mellin_taumax.valueChanged.connect(self._mellin_live)
        self.mellin_taumax_auto = QCheckBox('Auto')
        self.mellin_taumax_auto.setStyleSheet(CHECKBOX_STYLE)
        self.mellin_taumax_auto.setChecked(True)
        self.mellin_taumax_auto.setToolTip(
            'Choose the cutoff by the discrepancy principle: scan τmax and pick '
            'the smallest one whose V-space fit residual reaches the noise floor '
            '(σ_fit ≈ σ_noise). Smaller under-fits (residual ≫ noise), larger '
            'over-fits (injects noise into P(r)). The chosen value and the '
            'σ_fit/σ_noise ratio are reported below.')
        self.mellin_taumax_auto.stateChanged.connect(self._mellin_taumax_toggle)
        self.mellin_taumax_auto.stateChanged.connect(self._mellin_live)
        tm_row.addWidget(self.mellin_taumax); tm_row.addWidget(self.mellin_taumax_auto)
        grid.addLayout(tm_row, r, 1); r += 1

        grid.addWidget(self._label('τ points'), r, 0)
        self.mellin_ntau = QSpinBox()
        self.mellin_ntau.setStyleSheet(SPIN_STYLE)
        self.mellin_ntau.setRange(101, 20001)
        self.mellin_ntau.setSingleStep(200)
        self.mellin_ntau.setValue(2001)
        self.mellin_ntau.setToolTip(
            'Number of τ samples across [−τmax, τmax]. Must resolve the τ-domain '
            'oscillations (dτ ≲ 0.05); 2001 over ±25 (dτ = 0.025) is ample.')
        self.mellin_ntau.valueChanged.connect(self._mellin_live)
        grid.addWidget(self.mellin_ntau, r, 1); r += 1

        self.mellin_signed_chk = QCheckBox('Overlay signed P(r) (with noise ripples)')
        self.mellin_signed_chk.setStyleSheet(CHECKBOX_STYLE)
        self.mellin_signed_chk.setToolTip(
            'Also draw the raw signed distribution (before clipping negatives), '
            'whose short-r ripples are the propagated noise — the diagnostic the '
            'Mellin method is prized for.')
        self.mellin_signed_chk.stateChanged.connect(self._deer_rerender)
        grid.addWidget(self.mellin_signed_chk, r, 0, 1, 2); r += 1

        self.mellin_live = QCheckBox('Live update on parameter change')
        self.mellin_live.setStyleSheet(CHECKBOX_STYLE)
        grid.addWidget(self.mellin_live, r, 0, 1, 2); r += 1

        run_row = QHBoxLayout()
        self.mellin_run_btn = QPushButton('Run Mellin')
        self.mellin_run_btn.setStyleSheet(BUTTON_STYLE)
        self.mellin_run_btn.clicked.connect(self.do_mellin)
        btn_exp = QPushButton('Export all…')
        btn_exp.setStyleSheet(BUTTON_STYLE)
        btn_exp.clicked.connect(self.save_deer_all)
        run_row.addWidget(self.mellin_run_btn); run_row.addWidget(btn_exp)
        grid.addLayout(run_row, r, 0, 1, 2); r += 1
        panel.addLayout(grid)

        self.mellin_info = QLabel('')
        self.mellin_info.setStyleSheet(LABEL_STYLE)
        self.mellin_info.setWordWrap(True)
        self.mellin_info.setTextFormat(Qt.TextFormat.RichText)
        self.mellin_info.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        panel.addWidget(self.mellin_info)
        panel.addStretch(1)
        return w

    def _mellin_delta_toggle(self, *args):
        self.mellin_delta.setEnabled(not self.mellin_delta_auto.isChecked())

    def _mellin_taumax_toggle(self, *args):
        self.mellin_taumax.setEnabled(not self.mellin_taumax_auto.isChecked())

    def _mellin_live(self, *args):
        if self._suppress_live:
            return
        if (self.mellin_live.isChecked() and self.real_xy[0] is not None
                and self.deer_result is not None
                and self.deer_result.get('engine') == 'mellin'):
            self.do_mellin()

    # ----------------------------------------------------------- status
    def set_status(self, text):
        self.status.setText(text)
        general.message(text)

    def _set_loaded_file(self, name):
        self.loaded_label.setText(f'File: {name}' if name else 'File: —')

    # ----------------------------------------------------------- loading
    def _remember_dir(self, path):
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

    @staticmethod
    def _csv_header_labels(file_path):
        """Column labels from a CSV's '#'-comment header (last comment line before
        the data, split on commas). Best-effort: returns [] on any trouble."""
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
                        break
        except Exception:
            return []
        return labels if any(labels) else []

    def _preset_deer_unit(self, label):
        """If an axis label carries a time unit like 'Time (ns)', preset the
        time-unit selector to match."""
        u = ''
        if label and label.endswith(')') and '(' in label:
            u = label[label.rfind('(') + 1:-1].strip().lower()
        tmap = {'ns': 'ns', 'us': 'µs', 'µs': 'µs', 'μs': 'µs', 'ms': 'ms'}
        if u in tmap:
            self.deer_tunit.setCurrentText(tmap[u])

    def open_csv(self):
        file_path = self._open_dialog()
        if not file_path or file_path == 'None':
            return
        try:
            _, data = self.opener.open_1d(file_path)
            data = np.atleast_2d(data)
            if data.shape[0] < 2:
                self.set_status('CSV needs at least two columns (X and Y).')
                return
            if data.shape[0] > 6:
                self.set_status(f'This looks like a 2D dataset ({data.shape[0]} '
                                f'columns). Load a single V(t) trace (X + 1–2 '
                                f'channels) here.')
                return
            x = data[0]
            labels = self._csv_header_labels(file_path)
            mapping = {}
            for i in range(1, data.shape[0]):
                y = data[i]
                mask = ~(np.isnan(x) | np.isnan(y))
                name = labels[i] if (i < len(labels) and labels[i]) else f'Y{i}'
                while name in mapping:
                    name += "'"
                mapping[name] = (x[mask], y[mask])
            if labels and labels[0]:
                self._preset_deer_unit(labels[0])
            self._register_datasets(mapping)
            self._set_loaded_file(os.path.basename(file_path))
            self.set_status(f'Loaded {os.path.basename(file_path)} '
                            f'({data.shape[0] - 1} curve(s)).')
        except Exception as e:
            self.set_status(f'Could not read CSV: {e}')

    def open_bruker(self):
        """Load a Bruker dataset (BES3T .DSC/.DTA or ESP/WinEPR .par/.spc). A
        complex trace registers as a real+imag I/Q pair; a time axis presets the
        time-unit selector."""
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
                            f'({res["data"].shape}) — load a 1D V(t) trace.')
            return
        x = np.asarray(res['x'], dtype=float)
        mapping = {lbl: (x, np.asarray(y, dtype=float)) for lbl, y in res['channels']}
        self._register_datasets(mapping)
        if res['complex']:
            self.pair_check.setChecked(True)
        u = (res['x_unit'] or '').strip().lower()
        tmap = {'ns': 'ns', 'us': 'µs', 'µs': 'µs', 'μs': 'µs', 'ms': 'ms'}
        if u in tmap:
            self.deer_tunit.setCurrentText(tmap[u])
        self._set_loaded_file(os.path.basename(file_path))
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
            # one-shot mailbox: consume now so reopening the window does not
            # reload this (stale) plot data
            self._consume_buffer()
            ncurves = data.shape[1] // 2
            mapping = {}
            for i in range(ncurves):
                x = data[:, 2 * i]
                y = data[:, 2 * i + 1]
                mask = ~(np.isnan(x) | np.isnan(y))
                label = labels[i] if i < len(labels) else f'curve {i}'
                mapping[label] = (x[mask], y[mask])
            if not mapping:
                if not silent:
                    self.set_status('Plot buffer is empty.')
                return
            if buf_xname:
                self._preset_deer_unit(buf_xname)
            self._register_datasets(mapping)
            self._set_loaded_file('Loaded from plot')
            self.set_status(f'Loaded {len(mapping)} curve(s) from the current plot.')
        except Exception as e:
            self._consume_buffer()
            if not silent:
                self.set_status(f'Could not read plot buffer: {e}')

    def _consume_buffer(self):
        try:
            if os.path.isfile(BUFFER_PATH):
                os.remove(BUFFER_PATH)
        except OSError:
            pass

    def _register_datasets(self, mapping):
        # A fresh load turns off live update so the raw trace is shown as-is.
        self.live_check.setChecked(False)
        for sb in (self.trim_start, self.trim_end):   # new data: no trim carried over
            sb.blockSignals(True)
            sb.setValue(0)
            sb.blockSignals(False)
        self.datasets = dict(mapping)
        keys = list(mapping)
        sel_q = keys[1] if len(keys) > 1 else None
        for combo, sel in ((self.i_combo, keys[0] if keys else None),
                           (self.q_combo, sel_q)):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(keys)
            if sel is not None:
                combo.setCurrentIndex(keys.index(sel))
            combo.blockSignals(False)
        self.pair_check.blockSignals(True)
        self.pair_check.setChecked(len(keys) > 1)
        self.pair_check.blockSignals(False)
        self.on_source_changed()                  # populates self.real_xy
        self._reset_bg_window()                    # default bg start (~2/3) + end (last pt)
        self._show_input()                         # reposition cursors at the new window

    # --------------------------------------------------------- channels
    def on_source_changed(self, *args):
        """I/Q selection or pair-mode change: drop the result, re-phase, re-show."""
        self.deer_result = None
        self.deer_band = None
        self._clear_overlays()
        self._apply_phase()
        self._show_input()

    def _trim_slice(self, n):
        """Slice that drops the leading/trailing points set by the Trim controls
        (clamped so at least 4 points survive)."""
        ts = int(self.trim_start.value()) if hasattr(self, 'trim_start') else 0
        te = int(self.trim_end.value()) if hasattr(self, 'trim_end') else 0
        ts = max(0, min(ts, max(0, n - 4)))
        te = max(0, min(te, max(0, n - 4 - ts)))
        return slice(ts, n - te)

    def _apply_phase(self):
        """Rotate the selected I/Q to a real V(t) (or take I directly if not a
        pair), after trimming the chosen leading/trailing points; store it in
        self.real_xy as the DEER input."""
        il = self.i_combo.currentText()
        if il not in self.datasets:
            self.real_xy = (None, None)
            self.imag_y = None
            return
        x, idata = self.datasets[il]
        x = np.asarray(x, dtype=float)
        idata = np.asarray(idata, dtype=float)
        n = len(x)
        sl = self._trim_slice(n)
        x = x[sl]
        idata = idata[sl]
        ql = self.q_combo.currentText()
        self.imag_y = None
        if (self.pair_check.isChecked() and ql in self.datasets and ql != il):
            _, qdata = self.datasets[ql]
            qdata = np.asarray(qdata, dtype=float)
            if len(qdata) == n:
                qdata = qdata[sl]
                cor1 = float(self.phase_zero.value()) * np.pi / 180.0
                out = self.fft.ph_correction(x, idata, qdata, cor1, 0.0, 0.0)
                v = np.asarray(out[0], dtype=float)
                self.imag_y = np.asarray(out[1], dtype=float)
            else:
                v = idata
        else:
            v = idata
        self.real_xy = (x, v)

    def _trim_changed(self, *args):
        """Trim points changed: re-phase, re-estimate the background start for the
        new span, and refresh the view (or refit if live)."""
        self._apply_phase()
        self._reset_bg_window()
        if self.deer_result is not None and self.live_check.isChecked():
            self.do_deer()
        else:
            self.deer_result = None
            self.deer_band = None
            self._show_input()

    def _phase_changed(self, *args):
        self._apply_phase()
        if self.deer_result is not None and self.live_check.isChecked():
            self.do_deer()
        else:
            self._show_input()

    def auto_phase_zero(self):
        """Fill φ₀ with the value that maximises the magnitude-weighted real part
        of the time-domain I+iQ (see Fast_Fourier.auto_phase_zero)."""
        il = self.i_combo.currentText()
        ql = self.q_combo.currentText()
        if il not in self.datasets or ql not in self.datasets or il == ql:
            self.set_status('Select distinct I and Q channels for auto-phase.')
            return
        _, idata = self.datasets[il]
        _, qdata = self.datasets[ql]
        idata = np.asarray(idata, dtype=float)
        qdata = np.asarray(qdata, dtype=float)
        if idata.shape != qdata.shape or idata.size < 2:
            self.set_status('I and Q must have equal length (≥ 2).')
            return
        sl = self._trim_slice(len(idata))         # phase the trimmed trace
        idata, qdata = idata[sl], qdata[sl]
        phi = self.fft.auto_phase_zero(idata + 1j * qdata)
        self.phase_zero.setValue(phi)        # fires _phase_changed
        self.set_status(f'Auto φ₀ = {phi:.2f}°.')

    # --------------------------------------------------------- plotting
    def _repaint(self, plot, legend, items, curves, xname, key_attr,
                 left_label='', force=False):
        """Repaint one plot: reuse curve items via setData, drop stale labels,
        set the axis labels, and auto-range when the plotted content changes."""
        wanted = set()
        for lbl, x, y, color, width in curves:
            wanted.add(lbl)
            pen = pg.mkPen(color, width=width)
            xd, yd = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
            item = items.get(lbl)
            if item is None:
                items[lbl] = plot.plot(xd, yd, pen=pen, name=lbl)
            else:
                item.setData(xd, yd)
                item.setPen(pen)
        for lbl in [k for k in items if k not in wanted]:
            plot.removeItem(items.pop(lbl))
            try:
                legend.removeItem(lbl)
            except Exception:
                pass
        xlabel, xunit = _split_unit(xname)
        plot.setLabel('bottom', xlabel, units=xunit)
        try:
            plot.getPlotItem().getAxis('bottom').enableAutoSIPrefix(_si_autoprefix(xunit))
        except Exception:
            pass
        plot.setLabel('left', left_label)
        key = (frozenset(wanted), xname, left_label)
        # Only auto-range when there is something to frame; auto-ranging an empty
        # plot (e.g. P(r) before a run is cleared/repainted on every parameter
        # change) makes its limits jump around for no reason.
        if wanted and (key != getattr(self, key_attr) or force):
            try:
                plot.autoRange()
            except Exception:
                pass
        setattr(self, key_attr, key)

    def _show_input(self):
        """Show the current (phased) V(t) on the top plot and clear P(r). The
        draggable background start/end cursors are shown here too, so the window
        can be placed before running the inversion."""
        x, v = self.real_xy
        self._show_deer_band(False)
        self._show_lcurve_marker(False)
        if x is None or not len(x):
            self._show_bg_cursor(False)
            self._repaint(self.p_time, self.time_legend, self._time_items, [],
                          f'Time ({self.deer_tunit.currentText()})', '_time_key')
            self._repaint(self.p_pr, self.pr_legend, self._pr_items, [],
                          'Distance (nm)', '_pr_key', left_label='P(r) (nm⁻¹)')
            return
        tunit = self.deer_tunit.currentText()
        # I/Q pair: overlay the rotated imaginary channel so φ₀ can be tuned to
        # null it; single real channel: just V(t).
        if self.imag_y is not None and len(self.imag_y) == len(x):
            curves = [('V (Re)', x, v, C_DATA, 1),
                      ('Im', x, self.imag_y, C_IM, 1)]
        else:
            curves = [('V(t)', x, v, C_DATA, 1)]
        self._repaint(self.p_time, self.time_legend, self._time_items, curves,
                      f'Time ({tunit})', '_time_key', force=True)
        self._repaint(self.p_pr, self.pr_legend, self._pr_items, [],
                      'Distance (nm)', '_pr_key', left_label='P(r) (nm⁻¹)', force=True)
        self._show_bg_cursor(True)      # background window draggable from the start

    # --------------------------------------------------------- live update
    def _live_update(self, *args):
        if self._suppress_live:
            return
        if self.live_check.isChecked() and self.real_xy[0] is not None:
            self.do_deer()

    def _unit_changed(self, *args):
        """Time-unit change: recompute if live (the kernel axis scales), else just
        relabel the displayed input/result in the new unit."""
        if self.live_check.isChecked() and self.real_xy[0] is not None:
            self.do_deer()
        elif self.deer_result is not None:
            self._render()
        else:
            self._show_input()

    # --------------------------------------------------------- DEER params
    def _deer_tfactor(self):
        return self.DEER_TUNITS.get(self.deer_tunit.currentText(), 1.0)

    def _deer_alpha_toggle(self, *args):
        self.deer_alpha.setEnabled(not self.deer_alpha_auto.isChecked())

    # Default background-start position as a fraction of the post-echo span. The
    # joint fit pins the modulation depth to the baseline of V/B over the window,
    # so it must sit well into the decayed tail: ~2/3 in works (on the YopO set
    # >=65% recovers the correct ~12% background; <=55% collapses it).
    BG_START_FRAC = 0.66
    BG_START_FRAC_MAX = 0.85

    def _auto_bg_start_value(self):
        """Place the background start in the decayed tail: ~2/3 of the post-echo
        span by default, pushed later if the modulation envelope is still
        significant past that point (never earlier). Time in display units."""
        x, v = self.real_xy
        if x is None or len(x) < 16:
            return None
        x = np.asarray(x, dtype=float)
        v = np.asarray(v, dtype=float)
        i0 = int(np.argmax(np.abs(v)))            # echo centre
        xs, vs = x[i0:], v[i0:]
        n = len(xs)
        if n < 16 or vs[0] == 0:
            return float(xs[0] + self.BG_START_FRAC * (x[-1] - xs[0]))
        vn = vs / vs[0]
        # rolling RMS of the oscillation (signal minus a heavy moving average)
        win = max(5, n // 6)
        k = np.ones(win) / win
        osc = vn - np.convolve(vn, k, mode='same')
        amp = np.sqrt(np.convolve(osc ** 2, k, mode='same'))
        a0 = amp[:max(3, n // 10)].max() or float(amp.max()) or 1.0
        sig = np.where(amp[:max(1, n - win)] > 0.15 * a0)[0]   # still-modulated
        env_frac = (int(sig[-1]) / n) if len(sig) else 0.0
        frac = min(max(env_frac, self.BG_START_FRAC), self.BG_START_FRAC_MAX)
        return float(xs[0] + frac * (xs[-1] - xs[0]))

    def _auto_bg_start(self):
        bg = self._auto_bg_start_value()
        if bg is None:
            self.set_status('Load a V(t) trace first.')
            return
        self.deer_bgstart.setValue(bg)
        self.set_status(f'Auto background start = {bg:.4g} '
                        f'{self.deer_tunit.currentText()}.')

    # Longest distance the trace length supports: r_max ≈ 5·(t_max/2)^(1/3) nm
    # (t_max in µs) — the DeerAnalysis/Jeschke rule of thumb for the reliable
    # mean distance; mass beyond it is unconstrained by the data.
    R_MAX_FACTOR = 5.0

    def _auto_rmax_value(self):
        """Trace-length-supported maximum distance (nm), or None if no data."""
        x, _ = self.real_xy
        if x is None or len(x) < 2:
            return None
        x = np.asarray(x, dtype=float)
        t_us = abs(float(x[-1] - x[0]))*self._deer_tfactor()
        if t_us <= 0:
            return None
        rmax = self.R_MAX_FACTOR*(t_us/2.0)**(1.0/3.0)
        return float(np.clip(round(rmax, 1), self.deer_rmin.value() + 0.5, 50.0))

    def _auto_rmax(self):
        rmax = self._auto_rmax_value()
        if rmax is None:
            self.set_status('Load a V(t) trace first.')
            return
        self.deer_rmax.setValue(rmax)
        self.set_status(f'Auto distance max = {rmax:.1f} nm '
                        f'(trace-supported, 5·(t/2)^⅓).')

    def _reset_bg_window(self):
        """Set sensible defaults for the current (trimmed) trace: background start
        ~2/3 in (auto), background end at the last point (so the end cursor shows),
        and the distance max at the trace-length-supported limit."""
        bg = self._auto_bg_start_value()
        rmax = self._auto_rmax_value()
        xr = self.real_xy[0]
        for sb in (self.deer_bgstart, self.deer_bgend, self.deer_rmax):
            sb.blockSignals(True)
        if bg is not None:
            self.deer_bgstart.setValue(bg)
        if xr is not None and len(xr):
            self.deer_bgend.setValue(float(np.asarray(xr, dtype=float)[-1]))
        if rmax is not None:
            self.deer_rmax.setValue(rmax)
        for sb in (self.deer_bgstart, self.deer_bgend, self.deer_rmax):
            sb.blockSignals(False)

    def _deer_t0_max(self):
        x, v = self.real_xy
        if x is None or not len(x):
            self.set_status('Load a V(t) trace first.')
            return
        x = np.asarray(x, dtype=float)
        v = np.asarray(v, dtype=float)
        self.deer_t0.setValue(float(x[int(np.argmax(np.abs(v)))]))

    def _deer_bgend_max(self):
        x, _ = self.real_xy
        if x is None or not len(x):
            self.set_status('Load a V(t) trace first.')
            return
        self.deer_bgend.setValue(float(np.asarray(x, dtype=float)[-1]))

    # --------------------------------------------------------- inversion
    def do_deer(self):
        """Background-correct V(t) and invert to P(r) (Tikhonov + NNLS).

        The fit (zero-time + joint background + inversion) is run on a worker
        thread so the window stays responsive; results are applied back on the
        main thread in `_deer_finished`.
        """
        x, v = self.real_xy
        if x is None or len(x) < 8:
            self.set_status('Load a V(t) trace first (≥ 8 points).')
            return
        if self._deer_busy:
            # a fit is already running; remember to refit once it returns so the
            # latest parameters / cursor positions are not lost
            self._deer_pending = True
            return
        tf = self._deer_tfactor()
        rmin, rmax = self.deer_rmin.value(), self.deer_rmax.value()
        if rmax <= rmin:
            self.set_status('Distance max must exceed min.')
            return
        # snapshot everything the computation needs as plain values (the worker
        # must not touch Qt widgets)
        x = np.asarray(x, dtype=float)
        v = np.asarray(v, dtype=float)
        r = np.linspace(rmin, rmax, int(self.deer_rn.value()))
        alpha = None if self.deer_alpha_auto.isChecked() else float(self.deer_alpha.value())
        afac = float(self.deer_alpha_factor.value())
        engine = 'joint' if self.deer_engine.currentIndex() == 1 else 'sequential'
        dim = float(self.deer_dim.value())
        fit_dim = self.deer_fitdim.isChecked()
        validate = self.deer_validate_chk.isChecked()
        fit_t0 = self.deer_fit_t0.isChecked()
        bgs_disp = float(self.deer_bgstart.value())
        bge_disp = float(self.deer_bgend.value())
        t0_cur = float(self.deer_t0.value())

        def compute():
            t0_disp = t0_cur
            if fit_t0:
                t0u = deer_module.fit_zero_time(
                    x * tf, v, bg_start=bgs_disp * tf,
                    bg_end=(bge_disp * tf if bge_disp > bgs_disp else None),
                    r=r, dim=dim, fit_dim=fit_dim, alpha=alpha,
                    alpha_factor=afac, engine=engine)
                t0_disp = t0u / tf
            t_us = (x - t0_disp) * tf
            bg_us = (bgs_disp - t0_disp) * tf
            bg_end_us = ((bge_disp - t0_disp) * tf if bge_disp > bgs_disp else None)
            if validate:
                val = deer_module.deer_validate(
                    t_us, v, r=r, bg_start=bg_us, bg_end=bg_end_us, dim=dim,
                    fit_dim=fit_dim, alpha=alpha, alpha_factor=afac, engine=engine)
                res, band = val['base'], val
            else:
                res = deer_module.deer_invert(
                    t_us, v, r=r, bg_start=bg_us, bg_end=bg_end_us, dim=dim,
                    fit_dim=fit_dim, alpha=alpha, alpha_factor=afac, engine=engine)
                band = None
            # display/cursors stay in the original acquisition time; only the
            # kernel used the t0-shifted axis internally
            res['t'] = x * tf
            if bg_end_us is not None:
                res['background']['bg_end'] = bge_disp * tf
            return {'t0_disp': t0_disp, 'res': res, 'band': band}

        self._deer_busy = True
        self._deer_pending = False
        self.deer_run_btn.setEnabled(False)
        self.deer_run_btn.setStyleSheet(BUTTON_BUSY_STYLE)
        self.set_status('Fitting zero-time t0…' if fit_t0
                        else ('Tikhonov validation: sweeping background start…'
                              if validate else 'Running Tikhonov…'))
        self._deer_worker = _DeerWorker(compute)
        self._deer_worker.done.connect(self._deer_finished)
        self._deer_worker.start()

    def do_mellin(self):
        """Invert V(t) to P(r) by the analytic Mellin transform (model-free, no
        Tikhonov). Reuses the Background tab's zero-time / window / dimension and
        the shared distance grid; the Mellin tab supplies δ, τmax, τ points.
        Runs on the same worker thread + finisher as `do_deer`."""
        x, v = self.real_xy
        if x is None or len(x) < 8:
            self.set_status('Load a V(t) trace first (≥ 8 points).')
            return
        if self._deer_busy:
            self.set_status('Busy — wait for the running inversion to finish.')
            return
        tf = self._deer_tfactor()
        rmin, rmax = self.deer_rmin.value(), self.deer_rmax.value()
        if rmax <= rmin:
            self.set_status('Distance max must exceed min.')
            return
        # snapshot plain values for the worker (no Qt access inside compute)
        x = np.asarray(x, dtype=float)
        v = np.asarray(v, dtype=float)
        r = np.linspace(rmin, rmax, int(self.deer_rn.value()))
        dim = float(self.deer_dim.value())
        fit_dim = self.deer_fitdim.isChecked()
        fit_t0 = self.deer_fit_t0.isChecked()
        bg_engine = 'joint' if self.deer_engine.currentIndex() == 1 else 'sequential'
        bgs_disp = float(self.deer_bgstart.value())
        bge_disp = float(self.deer_bgend.value())
        t0_cur = float(self.deer_t0.value())
        delta_disp = (0.0 if self.mellin_delta_auto.isChecked()
                      else float(self.mellin_delta.value()))
        tau_max = (None if self.mellin_taumax_auto.isChecked()
                   else float(self.mellin_taumax.value()))
        n_tau = int(self.mellin_ntau.value())
        validate = self.deer_validate_chk.isChecked()
        n_mc = 50 if self.deer_ci_chk.isChecked() else 0

        def compute():
            t0_disp = t0_cur
            if fit_t0:
                t0u = deer_module.fit_zero_time(
                    x * tf, v, bg_start=bgs_disp * tf,
                    bg_end=(bge_disp * tf if bge_disp > bgs_disp else None),
                    r=r, dim=dim, fit_dim=fit_dim)
                t0_disp = t0u / tf
            t_us = (x - t0_disp) * tf
            bg_us = (bgs_disp - t0_disp) * tf
            bg_end_us = ((bge_disp - t0_disp) * tf if bge_disp > bgs_disp else None)
            delta_us = (delta_disp * tf) if delta_disp > 0 else None
            mk = dict(delta=delta_us, tau_max=tau_max, n_tau=n_tau,
                      bg_engine=bg_engine)
            if validate:
                val = deer_module.deer_validate(
                    t_us, v, r=r, bg_start=bg_us, bg_end=bg_end_us, dim=dim,
                    fit_dim=fit_dim, engine='mellin', **mk)
                res, band = val['base'], val
            else:
                res = deer_module.deer_invert_mellin(
                    t_us, v, r=r, bg_start=bg_us, bg_end=bg_end_us, dim=dim,
                    fit_dim=fit_dim, n_mc=n_mc, **mk)
                band = None
            res['t'] = x * tf
            if bg_end_us is not None:
                res['background']['bg_end'] = bge_disp * tf
            return {'t0_disp': t0_disp, 'res': res, 'band': band}

        self._deer_busy = True
        self._deer_pending = False
        self.mellin_run_btn.setEnabled(False)
        self.mellin_run_btn.setStyleSheet(BUTTON_BUSY_STYLE)
        self.set_status('Fitting zero-time t0…' if fit_t0
                        else ('Mellin validation: sweeping background start…'
                              if validate else ('Running Mellin transform '
                              '(+ CI)…' if n_mc else 'Running Mellin transform…')))
        self._deer_worker = _DeerWorker(compute)
        self._deer_worker.done.connect(self._deer_finished)
        self._deer_worker.start()

    def _deer_finished(self, payload):
        """Apply a finished inversion (runs on the main thread via the signal).
        Shared by the Tikhonov (`do_deer`) and Mellin (`do_mellin`) engines."""
        self._deer_busy = False
        for btn in (self.deer_run_btn, self.mellin_run_btn):
            btn.setStyleSheet(BUTTON_STYLE)
            btn.setEnabled(True)
        if isinstance(payload, Exception):
            self.set_status(f'Inversion failed: {payload}')
            return
        if self.real_xy[0] is None:       # data cleared while the fit ran; discard
            self._deer_pending = False
            return
        res, band, t0_disp = payload['res'], payload['band'], payload['t0_disp']
        self.deer_result = res
        self.deer_band = band
        tf = self._deer_tfactor()
        is_mellin = res.get('engine') == 'mellin'
        self.deer_t0.blockSignals(True)
        self.deer_t0.setValue(t0_disp)
        self.deer_t0.blockSignals(False)
        if not is_mellin and self.deer_alpha_auto.isChecked():
            self.deer_alpha.blockSignals(True)
            self.deer_alpha.setValue(float(res['alpha']))
            self.deer_alpha.blockSignals(False)

        F, Ff = res['form_factor'], res['F_fit']
        ss_tot = float(np.sum((F - F.mean()) ** 2)) or 1.0
        r2 = 1 - float(np.sum((F - Ff) ** 2)) / ss_tot
        if band is not None:
            r_peak, r_mean = band['peak'], band['r_mean']
            bgs = band['bg_starts'] / tf
            lo, hi = band['percentiles']
            extra = (f'<br><b style="color: rgb(150, 200, 255);">validation</b><br>'
                     f'{band["n_trials"]} trials, bg start {bgs[0]:.3g}–{bgs[-1]:.3g} '
                     f'{self.deer_tunit.currentText()}<br>band = {lo:g}–{hi:g}%')
            consensus = ' (median)'
        else:
            r_peak = float(res['r'][int(np.argmax(res['P_density']))])
            r_mean = float(np.sum(res['r'] * res['P_norm']))
            extra, consensus = '', ''

        if is_mellin:
            tunit = self.deer_tunit.currentText()
            delta_disp = float(res.get('delta', 0.0)) / tf
            # reflect the auto-chosen δ / τmax back into the (disabled) spin boxes
            self.mellin_delta.blockSignals(True)
            self.mellin_delta.setValue(delta_disp)
            self.mellin_delta.blockSignals(False)
            if res.get('auto_taumax'):
                self.mellin_taumax.blockSignals(True)
                self.mellin_taumax.setValue(float(res.get('tau_max', 0)))
                self.mellin_taumax.blockSignals(False)
            sf, sn = res.get('sigma_fit'), res.get('sigma_noise')
            if sf and sn and np.isfinite(sf) and np.isfinite(sn) and sn > 0:
                ratio = sf / sn
                verdict = ('overfit' if ratio < 0.9
                           else 'matched' if ratio <= 1.6 else 'underfit')
                disc = (f'<br>σ_fit/σ_noise = {ratio:.2f} '
                        f'<i>({verdict})</i>')
            else:
                disc = ''
            tag_auto = ' (auto)' if res.get('auto_taumax') else ''
            reg = (f'split δ = {delta_disp:.4g} {tunit}<br>'
                   f'τ max = {res.get("tau_max", 0):.0f}{tag_auto}{disc}')
        else:
            reg = f'α = {res["alpha"]:.4g}'
        info_html = (
            '<div style="line-height: 165%;">'
            f'<b style="color: rgb(211, 194, 78);">P(r)</b>{consensus}'
            f' &nbsp;<i>({res.get("engine", "—")})</i><br>'
            f'mod. depth λ = {res["lambda"]:.3f}<br>'
            f'bg decay k = {res["k"]:.4g}, dim = {res["dim"]:.2f}<br>'
            f'{reg}<br>'
            f'peak r = {r_peak:.3f} nm<br>'
            f'mean r = {r_mean:.3f} nm<br>'
            f'form-factor R² = {r2:.4f}{extra}</div>')
        self.deer_info.setText(info_html)
        if is_mellin:
            self.mellin_info.setText(info_html)
        self._render()
        if is_mellin:
            self.set_status(f'Mellin: λ={res["lambda"]:.3f}, δ={delta_disp:.3g} '
                            f'{self.deer_tunit.currentText()}, peak r={r_peak:.2f} nm, '
                            f'R²={r2:.3f}.')
        else:
            tag = f' ({band["n_trials"]}-trial band)' if band else ''
            self.set_status(f'Tikhonov: λ={res["lambda"]:.3f}, α={res["alpha"]:.3g}, '
                            f'peak r={r_peak:.2f} nm, R²={r2:.3f}{tag}.')
        # a parameter/cursor change arrived while we were busy -> refit once
        if self._deer_pending:
            self._deer_pending = False
            self.do_deer()

    def _deer_rerender(self, *args):
        """Re-show the stored result under the current top-plot view."""
        if self.deer_result is not None:
            self._render()

    def _render(self):
        """Draw P(r) on the bottom plot and the chosen view on the top plot."""
        res = self.deer_result
        if res is None:
            return
        tf = self._deer_tfactor()
        tunit = self.deer_tunit.currentText()
        t_disp = res['t'] / tf
        bg = res['background']

        # ---- bottom plot: distance distribution ----
        if self.deer_band is not None:
            b = self.deer_band
            self._show_deer_band(True, b['r'], b['P_lower'], b['P_upper'])
            self._repaint(self.p_pr, self.pr_legend, self._pr_items,
                          [('P(r) median', b['r'], b['P_density'], C_FIT, 2)],
                          'Distance (nm)', '_pr_key', left_label='P(r) (nm⁻¹)',
                          force=True)
        else:
            # covariance-based 95% confidence band (DeerLab-style), if available
            if (self.deer_ci_chk.isChecked() and res.get('P_lower') is not None):
                self._show_deer_band(True, res['r'], res['P_lower'], res['P_upper'])
            else:
                self._show_deer_band(False)
            pr_curves = [('P(r)', res['r'], res['P_density'], C_FIT, 2)]
            # Mellin: optionally overlay the raw signed distribution (short-r
            # ripples = propagated noise), the method's diagnostic output.
            if (res.get('engine') == 'mellin'
                    and res.get('P_signed_density') is not None
                    and self.mellin_signed_chk.isChecked()):
                pr_curves.append(('P(r) signed', res['r'],
                                  res['P_signed_density'], C_IM, 1))
            self._repaint(self.p_pr, self.pr_legend, self._pr_items, pr_curves,
                          'Distance (nm)', '_pr_key', left_label='P(r) (nm⁻¹)',
                          force=True)

        # ---- top plot: chosen time-domain / L-curve view ----
        view = self.deer_show.currentText()
        if view == 'Form factor + fit':
            self._repaint(self.p_time, self.time_legend, self._time_items,
                          [('F(t)', t_disp, res['form_factor'], C_DATA, 2),
                           ('K·P fit', t_disp, res['F_fit'], C_FIT, 2)],
                          f'Time ({tunit})', '_time_key', force=True)
            self._show_bg_cursor(True)
            self._show_lcurve_marker(False)
        elif view == 'Background fit':
            level = (1 - res['lambda']) * bg['B']
            self._repaint(self.p_time, self.time_legend, self._time_items,
                          [('V(t)', t_disp, bg['V_norm'], C_DATA, 2),
                           ('(1-λ)·B', t_disp, level, C_BG, 2)],
                          f'Time ({tunit})', '_time_key', force=True)
            self._show_bg_cursor(True)
            self._show_lcurve_marker(False)
        elif view == 'L-curve':
            self._show_bg_cursor(False)
            lc = res.get('l_curve')
            if lc is None:
                self.set_status('No L-curve available for this result.')
                self._show_lcurve_marker(False)
                return
            x, y = self._lcurve_xy(lc)
            self._repaint(self.p_time, self.time_legend, self._time_items,
                          [('L-curve', x, y, C_FIT, 2)],
                          'log₁₀ residual ‖KP−F‖', '_time_key',
                          left_label='log₁₀ roughness ‖LP‖', force=True)
            idx = self._lcurve_index(lc, res['alpha'])
            self._show_lcurve_marker(True, x[idx], y[idx])
        else:  # 'V(t) + background + fit'
            level = (1 - res['lambda']) * bg['B']
            v_fit = bg['B'] * ((1 - res['lambda']) + res['lambda'] * res['F_fit'])
            self._repaint(self.p_time, self.time_legend, self._time_items,
                          [('V(t)', t_disp, bg['V_norm'], C_DATA, 2),
                           ('background', t_disp, level, C_BG, 2),
                           ('fit', t_disp, v_fit, C_FIT, 2)],
                          f'Time ({tunit})', '_time_key', force=True)
            self._show_bg_cursor(True)
            self._show_lcurve_marker(False)

    # --------------------------------------------------------- overlays
    @staticmethod
    def _lcurve_xy(lc):
        x = np.log10(np.asarray(lc['rho'], float) + 1e-300)
        y = np.log10(np.asarray(lc['eta'], float) + 1e-300)
        return x, y

    @staticmethod
    def _lcurve_index(lc, alpha):
        a = np.asarray(lc['alphas'], float)
        return int(np.argmin(np.abs(np.log(a) - np.log(max(alpha, 1e-300)))))

    def _show_lcurve_marker(self, visible, x=None, y=None):
        if self._lcurve_marker is None:
            self._lcurve_marker = pg.ScatterPlotItem(
                size=14, symbol='o', pen=pg.mkPen((20, 20, 30), width=1.5),
                brush=pg.mkBrush(*C_FIT))
            self._lcurve_marker.setZValue(20)
            # ignoreBounds: the marker sits at log-roughness coordinates; if it
            # counted toward autoRange it would corrupt the y-axis of the time-
            # domain views when they are re-shown before the marker is hidden.
            self.p_time.addItem(self._lcurve_marker, ignoreBounds=True)
        if not visible:
            self._lcurve_marker.setVisible(False)
            return
        self._lcurve_marker.setData([x], [y])
        self._lcurve_marker.setVisible(True)

    def _show_deer_band(self, visible, x=None, lo=None, hi=None):
        """Show/hide the P(r) uncertainty band (confidence interval or validation
        band) on the bottom plot."""
        if self._band_fill is None:
            # faint gold edge lines so a narrow band is still visible, plus a
            # translucent fill bright enough to read against the dark background
            edge = pg.mkPen(211, 194, 78, 160, width=1)
            self._band_lo = pg.PlotDataItem(pen=edge)
            self._band_hi = pg.PlotDataItem(pen=edge)
            self._band_fill = pg.FillBetweenItem(
                self._band_lo, self._band_hi, brush=pg.mkBrush(211, 194, 78, 110))
            self._band_fill.setZValue(-10)
            for it in (self._band_lo, self._band_hi, self._band_fill):
                self.p_pr.addItem(it)
        if not visible:
            for it in (self._band_lo, self._band_hi, self._band_fill):
                it.setVisible(False)
            return
        self._band_lo.setData(np.asarray(x, float), np.asarray(lo, float))
        self._band_hi.setData(np.asarray(x, float), np.asarray(hi, float))
        for it in (self._band_lo, self._band_hi, self._band_fill):
            it.setVisible(True)

    def _on_lcurve_click(self, event):
        """On the L-curve view, pick the α of the nearest L-curve point."""
        if (self.deer_result is None
                or self.deer_show.currentText() != 'L-curve'):
            return
        lc = self.deer_result.get('l_curve')
        if lc is None:
            return
        vb = self.p_time.plotItem.vb
        pt = vb.mapSceneToView(event.scenePos())
        x, y = self._lcurve_xy(lc)
        rx = (x.max() - x.min()) or 1.0
        ry = (y.max() - y.min()) or 1.0
        d = ((x - pt.x()) / rx) ** 2 + ((y - pt.y()) / ry) ** 2
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
        top plot. The cursor lives in display time units and drives deer_bgstart."""
        if self._bg_cursor is None:
            self._bg_cursor = pg.InfiniteLine(
                angle=90, movable=True,
                pen=pg.mkPen((211, 194, 78), width=2, style=Qt.PenStyle.DashLine),
                hoverPen=pg.mkPen((255, 230, 120), width=3),
                label='bg start', labelOpts={'color': (211, 194, 78),
                                             'position': 0.93})
            # ignoreBounds: keep the cursor out of autoRange so a view switch
            # refits to the data, not to the cursor's (time) position
            self.p_time.addItem(self._bg_cursor, ignoreBounds=True)
            self._bg_cursor.sigPositionChangeFinished.connect(self._on_bg_cursor)
        if not visible:
            self._bg_cursor.setVisible(False)
            self._show_bg_cursor_end(False)
            return
        self._suppress_cursor = True
        self._bg_cursor.setValue(float(self.deer_bgstart.value()))
        self._bg_cursor.setVisible(True)
        self._suppress_cursor = False
        self._show_bg_cursor_end(True)

    def _on_bg_cursor(self, *args):
        # Update the spin box only; recompute is governed by Live update / Run
        # DEER (don't re-invert on every drag).
        if self._suppress_cursor or self._bg_cursor is None:
            return
        self.deer_bgstart.setValue(float(self._bg_cursor.value()))

    def _show_bg_cursor_end(self, visible):
        """Show/position (or hide) the draggable background-end cursor; only
        appears when an end limit is active (deer_bgend > deer_bgstart)."""
        if self._bg_cursor_end is None:
            self._bg_cursor_end = pg.InfiniteLine(
                angle=90, movable=True,
                pen=pg.mkPen((120, 200, 255), width=2, style=Qt.PenStyle.DashLine),
                hoverPen=pg.mkPen((180, 225, 255), width=3),
                label='bg end', labelOpts={'color': (120, 200, 255),
                                           'position': 0.86})
            self.p_time.addItem(self._bg_cursor_end, ignoreBounds=True)
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
        # Update the spin box only; recompute is governed by Live update / Run
        # DEER (don't re-invert on every drag).
        if self._suppress_cursor or self._bg_cursor_end is None:
            return
        self.deer_bgend.setValue(float(self._bg_cursor_end.value()))

    def _clear_overlays(self):
        """Hide all overlays (background cursors, L-curve marker, P(r) band)."""
        if self._bg_cursor is not None:
            self._bg_cursor.setVisible(False)
        if self._bg_cursor_end is not None:
            self._bg_cursor_end.setVisible(False)
        if self._lcurve_marker is not None:
            self._lcurve_marker.setVisible(False)
        if self._band_fill is not None:
            for it in (self._band_lo, self._band_hi, self._band_fill):
                it.setVisible(False)

    # --------------------------------------------------------- save / clear
    def save_deer_all(self):
        """Write every DEER stage to a set of sibling CSVs derived from one
        chosen path: <base>_distance / _formfactor / _background / _lcurve.csv."""
        res = self.deer_result
        if res is None:
            self.set_status('Run an inversion first — nothing to export.')
            return
        file_path = self._save_dialog()
        if not file_path or file_path == 'None':
            return
        base = file_path[:-4] if file_path.lower().endswith('.csv') else file_path
        tunit = self.deer_tunit.currentText()
        t_disp = res['t'] / self._deer_tfactor()
        bg = res['background']
        is_mellin = res.get('engine') == 'mellin'
        reg_line = (f'lambda = {res["lambda"]:.6g}, k = {res["k"]:.6g}, '
                    f'dim = {res["dim"]:.6g}, '
                    + (f'delta = {res.get("delta", 0)/self._deer_tfactor():.6g} {tunit}, '
                       f'tau_max = {res.get("tau_max", 0):.6g}' if is_mellin
                       else f'alpha = {res["alpha"]:.6g}'))
        hdr = ['DEER/PDS analysis ('
               + ('analytic Mellin transform, doi 10.1039/C7CP04059H)'
                  if is_mellin else 'Tikhonov + NNLS)'),
               reg_line,
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

        if self.deer_band is not None:
            b = self.deer_band
            lo, hi = b['percentiles']
            _save('distance', [b['r'], b['P_density'], b['P_lower'], b['P_upper'],
                               b['P_mean']],
                  f'r (nm), P(r) median density, {lo:g}% band, {hi:g}% band, '
                  f'mean ({b["n_trials"]} trials)')
        elif res.get('P_lower') is not None:
            _save('distance', [res['r'], res['P_density'], res['P_lower'],
                               res['P_upper'], res['P_norm']],
                  'r (nm), P(r) density, 95% CI lower, 95% CI upper, P (masses)')
        elif is_mellin and res.get('P_signed_density') is not None:
            _save('distance', [res['r'], res['P_density'], res['P_signed_density']],
                  'r (nm), P(r) density (clipped, normalized), P(r) signed density')
        else:
            _save('distance', [res['r'], res['P_density'], res['P_norm']],
                  'r (nm), P(r) density, P (masses)')
        _save('formfactor', [t_disp, res['form_factor'], res['F_fit'], res['residuals']],
              f'time ({tunit}), F(t), K*P fit, residuals')
        _save('background', [t_disp, bg['V_norm'], bg['B'], (1 - res['lambda']) * bg['B']],
              f'time ({tunit}), V(t) norm, B(t), (1-lambda)*B(t)')
        lc = res.get('l_curve')
        if lc is not None:
            _save('lcurve', [lc['alphas'], lc['rho'], lc['eta'], lc['curvature']],
                  'alpha, residual norm, solution norm, curvature')
        self.set_status('Exported DEER stages: ' + ', '.join(written))

    def clear_all(self):
        """Reset the window: forget all loaded data, result and selectors."""
        self.datasets = {}
        self.real_xy = (None, None)
        self.imag_y = None
        self.deer_result = None
        self.deer_band = None
        self._deer_pending = False        # cancel any queued refit
        self._clear_overlays()
        for combo in (self.i_combo, self.q_combo):
            combo.blockSignals(True)
            combo.clear()
            combo.blockSignals(False)
        for plot, legend, items in ((self.p_time, self.time_legend, self._time_items),
                                    (self.p_pr, self.pr_legend, self._pr_items)):
            for lbl in list(items):
                plot.removeItem(items.pop(lbl))
                try:
                    legend.removeItem(lbl)
                except Exception:
                    pass
        self._time_key = self._pr_key = None
        self.deer_info.setText('')
        self.mellin_info.setText('')
        self._set_loaded_file(None)
        self.set_status('Cleared. Load a V(t) trace to begin.')


def main():
    app = QApplication(sys.argv)
    apply_app_style(app, app_id='Atomize.ITC.DeerAnalysis')
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
