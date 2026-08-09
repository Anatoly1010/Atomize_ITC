# -*- coding: utf-8 -*-
"""
Pulse-EPR Sequence Simulator control-center tool.
=================================================

Standalone QProcess launched from the "EPR Endstation Control" tab. It loads a
saved phasing preset (``*.phase_awg`` from the AWG tool or ``*.phase`` from the
RECT tool), builds the spin system + ensemble you specify, and simulates the
*whole pulse sequence the hardware would play* -- echo / ESEEM / DEER-style
sweeps -- with the density-matrix engine
(:mod:`atomize.math_modules.spin_dynamics`), fed by the preset loader
(:mod:`atomize.math_modules.preset_loader`).

Two panels: the swept signal (real / imaginary / magnitude) over the
experiment's own x-axis on top, and the loaded pulse sequence (pulse blocks +
detection window, at the inspected step) below, so you can see the timing the
preset produced before committing to a measurement.

What it models, faithfully to the engine + loader:
 * an electron with up to three nuclei (secular + pseudo-secular hyperfine ->
   ESEEM / HYSCORE modulation), optionally a dipolar partner electron for
   single-frequency pair experiments (SIFTER);
 * an inhomogeneous line (Gaussian / Lorentzian) and B1 inhomogeneity;
 * phenomenological T1 / Tm;
 * the real pulse shapes (or ideal rotations), optionally filtered through an
   ideal-RLC resonator with ring-down;
 * the preset's phase cycle, expanded exactly as the spectrometer applies it.

The flip angle a preset's amplitude (``coef``) produces is hardware-dependent
(amplifier nonlinearity), so it is pinned here by a one-pulse nutation
calibration -- see the "Flip calibration" controls.

No hardware is touched; nothing is pushed to LivePlot. The sweep can take tens
of seconds, so it runs on the explicit "Simulate" button (with a Stop), not
live on every edit.
"""

import os
import sys

import numpy as np
import pyqtgraph as pg
from pyqtgraph.dockarea import DockArea
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QComboBox, QHBoxLayout, QDoubleSpinBox, QSpinBox,
    QCheckBox, QFrame, QScrollArea)

import atomize.math_modules.spin_dynamics as sd
import atomize.math_modules.preset_loader as pl
import atomize.math_modules.pulse_excitation as pe
import atomize.general_modules.csv_opener_saver as openfile
import atomize.general_modules.gui_forms as gui_forms
from atomize.main.widgets import CrosshairPlotWidget, CloseableDock
from atomize.general_modules.gui_style import (apply_app_style,
    BG, FG, ACCENT, BUTTON_STYLE, DSPIN_STYLE, SPIN_STYLE,
    COMBO_STYLE, CHECKBOX_STYLE, SCROLL_STYLE)

# Panel width. Fields stretch to fill their column rather than taking a
# fixed width, so they end level with the button grids with or without
# the scroll bar.
PANEL_W = 360

SUB_PT = 11
MAX_NUC = 3                       # nuclei the spin-system builder exposes


def _sub(base, sub, pt=SUB_PT):
    """base + an enlarged HTML subscript, at the plot font's size."""
    return gui_forms.sub(base, sub, pt)


def _lsub(base, sub):
    """base + a subscript at the shared control-label size."""
    return gui_forms.sub(base, sub)


def _row(panel, text, widget, bucket=None):
    """One FormPanel row, handing back its (label, widget) pair for show/hide."""
    r = panel.add_row(text, widget)
    lab = panel.grid.itemAtPosition(r, 0).widget()
    if bucket is not None:
        bucket.append((lab, widget))
    return lab, widget


# Remember the last preset/CSV folder across relaunches (this tool is its own
# short-lived QProcess), same libs/ runtime-file convention as the other tools.
LASTDIR_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'libs', 'spin_dynamics_lastdir.txt')


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


# Default preset directory (ships with the repo).
PRESET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'experiments')

# Pulse-block colours by carrier: observer (on-resonance) vs an offset pump.
COL_OBS = (120, 200, 255)
COL_PUMP = (255, 170, 90)
COL_DET = (160, 230, 130, 70)
COL_ECHO = (235, 90, 120)


class GrabbableLine(pg.InfiniteLine):
    """A draggable vertical line with a wider invisible grab band.

    InfiniteLine's pickable area is only a couple of pixels around the drawn
    line, which is fiddly to grab. We widen the bounding rect (used for
    mouse hit-testing) by ``grab_px`` pixels on each side without changing how
    the thin line is painted.
    """

    grab_px = 12

    def boundingRect(self):
        br = super().boundingRect()
        _, ortho = self.pixelVectors(pg.Point(1, 0))
        if ortho is None:
            return br
        pad = abs(self.grab_px * ortho.y())
        return br.adjusted(0, -pad, 0, pad)


class MainWindow(QMainWindow):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWindowTitle("EPR Sequence Simulator")
        self.setGeometry(140, 110, 1240, 760)

        self.preset = None         # parsed preset_loader.Preset
        self.preset_path = None
        self._axis = None          # last simulated x-axis (ns for time, MHz for field)
        self._axis_unit = 's'      # 's' (time sweep) or 'Hz' (offset/field sweep)
        self._x_log = False        # log x-axis (log-time sweep, e.g. T1 recovery)
        self._sig = None           # last simulated complex trace
        self._stop = False
        self._busy = False
        self.opener = openfile.Saver_Opener()
        self.last_dir = _load_last_dir() or PRESET_DIR
        self._nuc_rows = []        # per-nucleus [(label,widget)...] groups
        self._sig_items = []       # tracked curve items on the signal panel
        self._seq_items = []       # tracked items on the sequence panel
        self._echo_line = None     # movable echo marker on the sequence panel

        self.setStyleSheet("background-color: %s;" % BG)

        # Debounced redraw of the (cheap) sequence diagram on parameter edits.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self.redraw_sequence)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setSpacing(gui_forms.PANEL_GAP)
        root.addWidget(self._build_plots(), stretch=1)

        root.addWidget(gui_forms.vline())
        root.addWidget(self._build_controls(), stretch=0)

        gui_forms.apply_row_metrics(self)

        self._on_nuc_count_changed()
        self._on_partner_toggled(False)
        self._on_line_changed()
        self._on_b1_toggled(False)
        self._on_relax_toggled(False)
        self._on_reson_toggled(False)
        self._on_sweep_mode_changed()
        self._update_status("Load a .phase_awg / .phase preset to begin.")

    # ------------------------------------------------------------------ #
    # Small widget factories
    # ------------------------------------------------------------------ #
    def _dspin(self, lo, hi, val, step, dec=3, suffix=''):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setDecimals(dec)
        s.setValue(val)
        if suffix:
            s.setSuffix(suffix)
        s.setStyleSheet(DSPIN_STYLE)
        s.valueChanged.connect(self.schedule)
        return s

    def _ispin(self, lo, hi, val):
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        s.setStyleSheet(SPIN_STYLE)
        s.valueChanged.connect(self.schedule)
        return s

    def _label(self, text):
        return gui_forms.label(text)

    # ------------------------------------------------------------------ #
    # Plots
    # ------------------------------------------------------------------ #
    def _build_plots(self):
        pg.setConfigOptions(antialias=True)
        self.plot_area = DockArea()

        self.p_sig = CrosshairPlotWidget()
        self.p_sig.showGrid(x=True, y=True, alpha=0.2)
        self.p_sig.setLabel('bottom', 'Sweep axis', units='s')
        self.p_sig.setLabel('left', 'Echo signal (norm.)')
        # The signal axis is normalised/unitless: SI auto-prefix would scale
        # 0.6 -> "600 m", so turn it off (the time axis keeps it for ns/us).
        self.p_sig.getPlotItem().getAxis('left').enableAutoSIPrefix(False)
        self.sig_legend = self.p_sig.addLegend(offset=(-10, 10))
        dock_sig = CloseableDock(name='Simulated signal', widget=self.p_sig)
        dock_sig.close_button.hide()

        self.p_seq = CrosshairPlotWidget()
        self.p_seq.showGrid(x=True, y=True, alpha=0.2)
        self.p_seq.setLabel('bottom', 'Time', units='s')
        self.p_seq.setLabel('left', 'Pulse (norm. amp)')
        self.p_seq.getPlotItem().getAxis('left').enableAutoSIPrefix(False)
        dock_seq = CloseableDock(name='Pulse sequence (inspected step)', widget=self.p_seq)
        dock_seq.close_button.hide()

        self.plot_area.addDock(dock_sig, 'top')
        self.plot_area.addDock(dock_seq, 'bottom', dock_sig)
        return self.plot_area

    # ------------------------------------------------------------------ #
    # Controls
    # ------------------------------------------------------------------ #
    def _build_controls(self):
        panel = QScrollArea()
        panel.setWidgetResizable(True)
        panel.setStyleSheet(SCROLL_STYLE)
        panel.setFixedWidth(PANEL_W)
        p = gui_forms.FormPanel(margins=gui_forms.PANEL_MARGINS,
                                button_width=gui_forms.BTN_W)
        panel.setWidget(p)

        # ---- Preset ----
        p.add_heading("Preset")
        self.load_btn = QPushButton("Load preset…")
        self.load_btn.setStyleSheet(BUTTON_STYLE)
        self.load_btn.clicked.connect(self.open_preset)
        p.add_button_row(self.load_btn, width=gui_forms.ACTION_W)
        self.preset_lbl = QLabel("(no preset)")
        self.preset_lbl.setStyleSheet("QLabel { color: %s; }" % FG)
        self.preset_lbl.setWordWrap(True)
        p.add_widget(self.preset_lbl)

        # ---- Flip calibration ----
        p.add_sep()
        p.add_heading("Flip calibration")
        cal_tip = (
            "Pins the one hardware-dependent number: the flip angle a pulse "
            "amplitude actually produces (the amplifier is nonlinear, so it "
            "can't be read from the preset). State one nutation-calibrated "
            "fact — 'a pulse at amplitude COEF %, length LENGTH ns, rotates the "
            "spin by FLIP degrees' — from your own nutation measurement. Every "
            "AWG pulse's amplitude is then scaled by its coef relative to this. "
            "Defaults give π/2 at amplitude 100 %, length 22.4 ns.")
        self.cal_coef = self._dspin(0.1, 100.0, 100.0, 1.0, 1, ' %')
        tip = (cal_tip + "\n\nReference amplitude in % of full AWG drive — the "
               "'coef' field of the pulse you calibrated against.")
        self.cal_coef.setToolTip(tip)
        p.add_row("Ref amplitude coef", self.cal_coef, tooltip=tip)
        self.cal_len = self._dspin(1.0, 1000.0, 22.4, 0.1, 1, ' ns')
        tip = cal_tip + "\n\nLength (ns) of that reference pulse."
        self.cal_len.setToolTip(tip)
        p.add_row("Ref length", self.cal_len, tooltip=tip)
        self.cal_flip = self._dspin(1.0, 720.0, 90.0, 5.0, 1, ' deg')
        tip = (cal_tip + "\n\nFlip angle (deg) that reference pulse produces on "
               "resonance — 90 for a π/2, 180 for a π.")
        self.cal_flip.setToolTip(tip)
        p.add_row("Ref flip", self.cal_flip, tooltip=tip)
        self.ideal_chk = QCheckBox("Ideal pulses")
        self.ideal_chk.setStyleSheet(CHECKBOX_STYLE)
        self.ideal_chk.setToolTip(
            "Replace each shaped pulse with an instantaneous rotation of the same "
            "on-resonance flip angle. Faster, and isolates the sequence/phase-cycle "
            "physics from finite-pulse bandwidth effects.")
        p.add_widget(self.ideal_chk)

        # ---- Spin system ----
        p.add_sep()
        p.add_heading("Spin system")
        self.nuc_count = QComboBox()
        self.nuc_count.addItems([str(i) for i in range(MAX_NUC + 1)])
        self.nuc_count.setStyleSheet(COMBO_STYLE)
        self.nuc_count.currentTextChanged.connect(self._on_nuc_count_changed)
        p.add_row("Number of nuclei", self.nuc_count)

        # Per-nucleus rows (I, Larmor, A, B), shown/hidden by the count.
        for k in range(MAX_NUC):
            shown = []
            head = self._label("Nucleus %d" % (k + 1))
            head.setStyleSheet("QLabel { color: %s; }" % ACCENT)
            p.add_widget(head)
            shown.append((head, head))
            I = QComboBox(); I.addItems(['1/2', '1']); I.setStyleSheet(COMBO_STYLE)
            I.currentTextChanged.connect(self.schedule)
            _row(p, "I", I, shown)
            tip = ("Nuclear Larmor (Zeeman) frequency = γ_n·B0/2π. It is a "
                   "FREQUENCY (MHz), not the field itself — the external field B0 "
                   "enters only through it. E.g. ¹H at 348 mT ≈ 14.9 MHz, ¹⁴N ≈ "
                   "1.07 MHz. This is what sets the ESEEM/modulation frequency.")
            nu = self._dspin(-200.0, 200.0, 14.9, 0.1, 3, ' MHz')
            nu.setToolTip(tip)
            _row(p, "Larmor " + _lsub('ν', 'I'), nu, shown)[0].setToolTip(tip)
            tip = ("Secular hyperfine coupling A (MHz): the A·Sz·Iz term — shifts "
                   "the nuclear frequency depending on the electron state.")
            A = self._dspin(-200.0, 200.0, 4.0, 0.1, 3, ' MHz')
            A.setToolTip(tip)
            _row(p, "A", A, shown)[0].setToolTip(tip)
            tip = ("Pseudo-secular hyperfine coupling B (MHz): the B·Sz·Ix term — "
                   "the anisotropic/dipolar part that mixes nuclear states and "
                   "DRIVES the ESEEM modulation. NOT the external magnetic field. "
                   "B = 0 gives no two-/three-pulse ESEEM.")
            B = self._dspin(-200.0, 200.0, 3.0, 0.1, 3, ' MHz')
            B.setToolTip(tip)
            _row(p, "B", B, shown)[0].setToolTip(tip)
            self._nuc_rows.append({'I': I, 'nu': nu, 'A': A, 'B': B, 'rows': shown})

        # Dipolar partner (2nd electron) for single-frequency pair experiments.
        self.partner_chk = QCheckBox("Dipolar partner electron")
        self.partner_chk.setStyleSheet(CHECKBOX_STYLE)
        self.partner_chk.setToolTip(
            "Add a second electron coupled by a secular dipolar term d·Sz1·Sz2. "
            "Both electrons are driven by every pulse (single rotating frame), so "
            "this is valid for single-frequency pair experiments (SIFTER), NOT a "
            "frequency-selective DEER pump.")
        self.partner_chk.toggled.connect(self._on_partner_toggled)
        p.add_widget(self.partner_chk)
        self.partner_box = gui_forms.FormPanel(spacing=4,
                                               )
        self.partner_d = self._dspin(-50.0, 50.0, 3.0, 0.1, 3, ' MHz')
        self.partner_box.add_row("Dipolar d", self.partner_d)
        p.add_widget(self.partner_box)

        # ---- Ensemble ----
        p.add_sep()
        p.add_heading("Ensemble")
        self.line_shape = QComboBox()
        self.line_shape.addItems(['Single packet', 'Gaussian', 'Lorentzian'])
        self.line_shape.setStyleSheet(COMBO_STYLE)
        self.line_shape.currentTextChanged.connect(self._on_line_changed)
        p.add_row("Line shape", self.line_shape)
        self._line_rows = []
        self.line_fwhm = self._dspin(1.0, 2000.0, 100.0, 5.0, 1, ' MHz')
        _row(p, "Line FWHM", self.line_fwhm, self._line_rows)
        self.off_span = self._dspin(1.0, 5000.0, 250.0, 10.0, 1, ' MHz')
        _row(p, "Offset span ±", self.off_span, self._line_rows)
        self.off_pts = self._ispin(11, 2001, 301)
        _row(p, "Offset points", self.off_pts, self._line_rows)

        self.b1_chk = QCheckBox("B₁ inhomogeneity")
        self.b1_chk.setStyleSheet(CHECKBOX_STYLE)
        self.b1_chk.toggled.connect(self._on_b1_toggled)
        p.add_widget(self.b1_chk)
        self.b1_box = gui_forms.FormPanel(spacing=4,
                                          )
        self.b1_spread = self._dspin(0.0, 80.0, 10.0, 1.0, 1, ' %')
        tip = "Width of the Gaussian B1 distribution, as a FWHM in % of nominal B1."
        self.b1_spread.setToolTip(tip)
        self.b1_box.add_row(_lsub('B', '1') + " spread", self.b1_spread, tooltip=tip)
        self.b1_pts = self._ispin(3, 31, 5)
        self.b1_box.add_row(_lsub('B', '1') + " points", self.b1_pts)
        p.add_widget(self.b1_box)

        # ---- Relaxation ----
        p.add_sep()
        self.relax_chk = QCheckBox("Relaxation (T₁ / Tₘ)")
        self.relax_chk.setStyleSheet(CHECKBOX_STYLE)
        self.relax_chk.toggled.connect(self._on_relax_toggled)
        p.add_widget(self.relax_chk)
        self.relax_box = gui_forms.FormPanel(spacing=4,
                                             )
        self.t1 = self._dspin(0.001, 1e6, 100.0, 0.1, 3, ' µs')
        self.relax_box.add_row(_lsub('T', '1'), self.t1)
        self.tm = self._dspin(0.001, 1e6, 2.0, 0.1, 3, ' µs')
        self.relax_box.add_row(_lsub('T', 'm'), self.tm)
        p.add_widget(self.relax_box)

        # ---- Resonator ----
        p.add_sep()
        self.reson_chk = QCheckBox("Resonator (ideal RLC)")
        self.reson_chk.setStyleSheet(CHECKBOX_STYLE)
        self.reson_chk.setToolTip(
            "Filter every shaped pulse through an ideal RLC resonator "
            "H = 1/(1 + iQ(ν/ν₀ − ν₀/ν)) before the spins see it — the same model "
            "the AWG correction uses. Disabled for ideal pulses.")
        self.reson_chk.toggled.connect(self._on_reson_toggled)
        p.add_widget(self.reson_chk)
        self.reson_box = gui_forms.FormPanel(spacing=4,
                                             )
        self.reson_nu0 = self._dspin(0.1, 300.0, 9.7, 0.1, 3, ' GHz')
        self.reson_box.add_row("Centre " + _lsub('ν', '0'), self.reson_nu0)
        self.reson_q = self._dspin(5.0, 100000.0, 100.0, 5.0, 1)
        self.reson_box.add_row("Q", self.reson_q)
        self.reson_det = self._dspin(-2500.0, 2500.0, 0.0, 5.0, 1, ' MHz')
        self.reson_box.add_row("Detuning", self.reson_det)
        self.reson_ring = QCheckBox("Include ring-down")
        self.reson_ring.setStyleSheet(CHECKBOX_STYLE)
        self.reson_ring.toggled.connect(self.schedule)
        self.reson_box.add_widget(self.reson_ring)
        p.add_widget(self.reson_box)

        # ---- Sweep / run ----
        p.add_sep()
        p.add_heading("Sweep & run")
        self.sweep_mode = QComboBox()
        self.sweep_mode.addItems(['Time delay (preset)', 'Offset / field (EDFS)'])
        self.sweep_mode.setStyleSheet(COMBO_STYLE)
        self.sweep_mode.setToolTip(
            "Time delay: replay the preset, stepping its swept delay (ESEEM / "
            "DEER / echo decay).\nOffset / field: keep the sequence fixed and "
            "sweep the spin packets' offset past the fixed excitation — an "
            "echo-detected field sweep (EDFS). The x-axis becomes frequency "
            "offset; the line shape is the EPR spectrum being mapped.")
        self.sweep_mode.currentTextChanged.connect(self._on_sweep_mode_changed)
        p.add_row("Sweep mode", self.sweep_mode)
        self.sweep_pts = self._ispin(1, 4000, 80)
        p.add_row("Sweep points", self.sweep_pts)
        self.field_span = self._dspin(1.0, 20000.0, 500.0, 10.0, 1, ' MHz')
        tip = ("Half-width of the offset/field sweep (MHz). The echo is recorded "
               "as the spin packets are shifted from −span to +span past the fixed "
               "excitation.")
        self.field_span.setToolTip(tip)
        self.field_lbl, _ = _row(p, "Field sweep ±", self.field_span)
        self.field_lbl.setToolTip(tip)
        self.win_left = self._dspin(-6400.0, 6400.0, 0.0, 1.0, 1, ' ns')
        tip = ("Echo-integration window, left edge — an offset from the detection "
               "pulse's start, exactly the spectrometer's 'Window left'. The "
               "detection-pulse length is only the digitizer record; the echo is "
               "integrated over [left, right] inside it.")
        self.win_left.setToolTip(tip)
        self.win_left.valueChanged.connect(self.redraw_sequence)
        p.add_row("Window left", self.win_left, tooltip=tip)
        self.win_right = self._dspin(-6400.0, 6400.0, 320.0, 1.0, 1, ' ns')
        tip = ("Echo-integration window, right edge — an offset from the detection "
               "pulse's start ('Window right'). Loaded from the preset; adjust to "
               "match the echo position you see in the sequence panel.")
        self.win_right.setToolTip(tip)
        self.win_right.valueChanged.connect(self.redraw_sequence)
        p.add_row("Window right", self.win_right, tooltip=tip)
        self.detect_dt = self._dspin(0.1, 50.0, 2.0, 0.1, 2, ' ns')
        p.add_row("Detect sample dt", self.detect_dt)
        self.integ = QComboBox()
        self.integ.addItems(['Peak |V|', 'Window integral', 'Center point'])
        self.integ.setStyleSheet(COMBO_STYLE)
        p.add_row("Echo integrate", self.integ)
        self.show_mode = QComboBox()
        self.show_mode.addItems(['Magnitude', 'Real', 'Imag', 'Real & Imag'])
        self.show_mode.setStyleSheet(COMBO_STYLE)
        self.show_mode.currentTextChanged.connect(self._replot_only)
        p.add_row("Show", self.show_mode)
        self.step_spin = self._ispin(0, 4000, 0)
        self.step_spin.valueChanged.connect(self.redraw_sequence)
        p.add_row("Inspect step", self.step_spin)

        self.snap_chk = QCheckBox("Snap pulses to 3.2 ns grid")
        self.snap_chk.setStyleSheet(CHECKBOX_STYLE)
        self.snap_chk.setChecked(True)
        self.snap_chk.setToolTip(
            "Round every pulse start/length and the detection start to the "
            "3.2 ns AWG time quantum, so the simulated sequence matches what the "
            "spectrometer actually plays (the other tools use the same grid).")
        self.snap_chk.toggled.connect(self.redraw_sequence)
        p.add_widget(self.snap_chk)
        self.echo_chk = QCheckBox("Echo marker")
        self.echo_chk.setStyleSheet(CHECKBOX_STYLE)
        self.echo_chk.setChecked(True)
        self.echo_chk.setToolTip(
            "Show a movable marker for the ideal echo position on the sequence "
            "panel. Drag it (or type below) to where you expect the echo from "
            "the pulse positions; use it to place Window left/right.")
        self.echo_chk.toggled.connect(self.redraw_sequence)
        p.add_widget(self.echo_chk)
        self.echo_pos = self._dspin(0.0, 100000.0, 480.0, 3.2, 1, ' ns')
        tip = ("Ideal echo time, measured from the first pulse (t = 0 on the "
               "sequence panel). Set it manually or drag the marker.")
        self.echo_pos.setToolTip(tip)
        p.add_row("Echo position", self.echo_pos, tooltip=tip)

        self.run_btn = QPushButton("Simulate")
        self.run_btn.setStyleSheet(BUTTON_STYLE)
        self.run_btn.clicked.connect(self.simulate)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet(BUTTON_STYLE)
        self.stop_btn.clicked.connect(self._on_stop)
        self.stop_btn.setEnabled(False)
        self.save_btn = QPushButton("Save trace…")
        self.save_btn.setStyleSheet(BUTTON_STYLE)
        self.save_btn.clicked.connect(self.save_trace)
        p.add_button_row(self.run_btn, self.stop_btn, self.save_btn)

        self.status = QLabel("")
        self.status.setStyleSheet("QLabel { color: %s; }" % FG)
        self.status.setWordWrap(True)
        p.add_widget(self.status)
        p.add_stretch()
        return panel

    # ------------------------------------------------------------------ #
    # Reactions
    # ------------------------------------------------------------------ #
    def schedule(self):
        if not self._busy:
            self._timer.start()

    def _on_nuc_count_changed(self, *_):
        n = int(self.nuc_count.currentText())
        for k, rows in enumerate(self._nuc_rows):
            for lab, wdg in rows['rows']:
                lab.setVisible(k < n)
                wdg.setVisible(k < n)
        self.schedule()

    def _on_partner_toggled(self, on):
        self.partner_box.setVisible(on)
        self.schedule()

    def _on_line_changed(self, *_):
        on = self.line_shape.currentText() != 'Single packet'
        for lab, wdg in self._line_rows:
            lab.setVisible(on)
            wdg.setVisible(on)
        self.schedule()

    def _on_b1_toggled(self, on):
        self.b1_box.setVisible(on)
        self.schedule()

    def _on_relax_toggled(self, on):
        self.relax_box.setVisible(on)
        self.schedule()

    def _on_reson_toggled(self, on):
        self.reson_box.setVisible(on)
        self.schedule()

    def _on_sweep_mode_changed(self, *_):
        field = self.sweep_mode.currentText().startswith('Offset')
        self.field_lbl.setVisible(field)
        self.field_span.setVisible(field)

    def _on_stop(self):
        self._stop = True

    def _update_status(self, msg):
        self.status.setText(msg)
        QApplication.processEvents()

    # ------------------------------------------------------------------ #
    # Preset loading
    # ------------------------------------------------------------------ #
    def open_preset(self):
        path = self.opener.open_file_dialog(
            multiprocessing=True, directory=self.last_dir,
            name_filters=['Phasing presets (*.phase_awg *.phase)',
                          'AWG presets (*.phase_awg)', 'RECT presets (*.phase)',
                          'All files (*)'])
        if not path or path == 'None':
            return
        try:
            pre = pl.parse_preset(path)
        except Exception as e:
            self.preset_lbl.setText("✗ %s" % e)
            return
        if not pre.pulses:
            self.preset_lbl.setText("✗ no active pulses in this preset")
            return
        self.preset = pre
        self.preset_path = path
        self.last_dir = os.path.dirname(path) or self.last_dir
        _save_last_dir(self.last_dir)
        # Phase-cycle step count + sweep points for the summary.
        _, cyc = pre.build(step=0)
        nsteps = 1 if cyc is None else len(cyc)
        npts = int(pre.globals.get('sweep_points', 0)) or 0
        self.preset_lbl.setText(
            "✓ %s\n%s · %d pulse(s) · %d-step cycle · obs %.0f MHz · %d sweep pts"
            % (os.path.basename(path), pre.kind.upper(), len(pre.pulses), nsteps,
               pre.globals.get('freq_obs', 0.0), npts))
        if npts > 0:
            self.sweep_pts.setValue(min(npts, self.sweep_pts.maximum()))
        # Seed the integration window from the preset's Window left/right.
        det = pre.detection or {}
        self.win_left.blockSignals(True); self.win_right.blockSignals(True)
        self.win_left.setValue(float(det.get('win_left', 0.0)))
        self.win_right.setValue(float(det.get('win_right', det.get('length', 320.0))))
        self.win_left.blockSignals(False); self.win_right.blockSignals(False)
        # Default the echo marker to the centre of the integration window
        # (t = 0 at the first pulse, matching the sequence panel).
        _, det_lay = pre.layout(step=0, det_window=self._det_window(),
                                time_grid=self._time_grid())
        if det_lay is not None:
            self.echo_pos.blockSignals(True)
            self.echo_pos.setValue(det_lay['start'] + 0.5 * det_lay['length'])
            self.echo_pos.blockSignals(False)
        # Seed the calibration from the project convention for the preset kind.
        if pre.kind == 'rect':
            self.cal_coef.setValue(100.0); self.cal_len.setValue(22.4); self.cal_flip.setValue(90.0)
        self.step_spin.setValue(0)
        self.redraw_sequence()
        self._update_status("Preset loaded. Set the spin system and press Simulate.")

    # ------------------------------------------------------------------ #
    # Build engine inputs
    # ------------------------------------------------------------------ #
    def _build_system(self):
        """SpinSystem from the controls (electron + nuclei + optional partner)."""
        n = int(self.nuc_count.currentText())
        partner = self.partner_chk.isChecked()
        spins = [0.5]
        electrons = [0]
        if partner:
            spins.append(0.5)             # 2nd electron right after the 1st
            electrons.append(1)
        nuc_base = len(spins)
        for k in range(n):
            spins.append(0.5 if self._nuc_rows[k]['I'].currentText() == '1/2' else 1.0)
        sysm = sd.SpinSystem(tuple(spins), electrons=tuple(electrons))
        if partner:
            sysm.zz_coupling(0, 1, self.partner_d.value() / 1000.0)   # MHz -> GHz
        for k in range(n):
            idx = nuc_base + k
            r = self._nuc_rows[k]
            sysm.zeeman(idx, r['nu'].value() / 1000.0)
            sysm.hyperfine(0, idx, A=r['A'].value() / 1000.0, B=r['B'].value() / 1000.0)
        return sysm

    def _build_ensemble(self):
        """(offsets, weights) in GHz from the line-shape controls."""
        shape = self.line_shape.currentText()
        if shape == 'Single packet':
            return np.array([0.0]), None
        span = self.off_span.value() / 1000.0          # MHz -> GHz
        npts = int(self.off_pts.value())
        offs = np.linspace(-span, span, npts)
        fwhm = self.line_fwhm.value() / 1000.0
        sigma = fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0)))
        if shape == 'Lorentzian':
            w = sd.lorentzian_weights(offs, 0.5 * fwhm)
        else:
            w = sd.gaussian_weights(offs, sigma)
        return offs, w

    def _apply_b1(self, offsets, weights):
        """Tensor the offset ensemble with a Gaussian B1 distribution."""
        if not self.b1_chk.isChecked():
            return offsets, 1.0, weights
        spread = self.b1_spread.value() / 100.0
        nb = int(self.b1_pts.value())
        if spread <= 0 or nb < 2:
            return offsets, 1.0, weights
        sigma = spread / (2.0 * np.sqrt(2.0 * np.log(2.0)))
        b1 = np.linspace(max(0.05, 1 - 3 * sigma), 1 + 3 * sigma, nb)
        wb = np.exp(-0.5 * ((b1 - 1.0) / sigma) ** 2)
        wb /= wb.sum()
        off2 = np.repeat(offsets, nb)
        b12 = np.tile(b1, offsets.size)
        wo = np.ones(offsets.size) if weights is None else weights
        w2 = np.repeat(wo, nb) * np.tile(wb, offsets.size)
        return off2, b12, w2

    def _resonator(self):
        if not self.reson_chk.isChecked() or self.ideal_chk.isChecked():
            return None
        nu0 = self.reson_nu0.value()
        res = {'nu0': nu0, 'Q': self.reson_q.value(),
               'detuning': self.reson_det.value() / 1000.0, 'mode': 'simulate'}
        if self.reson_ring.isChecked():
            res['ringdown'] = pe.ringdown_time(nu0, self.reson_q.value())
        return res

    def _flip_cal(self):
        return (self.cal_coef.value(), self.cal_len.value(),
                np.deg2rad(self.cal_flip.value()))

    def _det_window(self):
        return (self.win_left.value(), self.win_right.value())

    def _time_grid(self):
        return pl.TIME_GRID if self.snap_chk.isChecked() else None

    def _idealize(self, events):
        """Replace each shaped Pulse with an ideal rotation of the same flip."""
        out = []
        for ev in events:
            if isinstance(ev, sd.Pulse) and ev.flip is None:
                flip = pe.flip_angle(ev.shape, ev.tp, ev.nu1, ev.params, dt=ev.dt)
                out.append(sd.Pulse(flip=flip, phase=ev.phase))
            else:
                out.append(ev)
        return out

    # ------------------------------------------------------------------ #
    # Simulation
    # ------------------------------------------------------------------ #
    def simulate(self):
        if self.preset is None:
            self._update_status("Load a preset first.")
            return
        if self._busy:
            return
        self._busy = True
        self._stop = False
        self.run_btn.setEnabled(False)
        self.run_btn.setText("Simulating…")
        self.stop_btn.setEnabled(True)
        try:
            self._run_sweep()
        except Exception as e:
            self._update_status("✗ %s" % e)
        finally:
            self.run_btn.setText("Simulate")
            self.run_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self._busy = False

    def _relaxation(self):
        if not self.relax_chk.isChecked():
            return None
        return {'T1': self.t1.value() * 1000.0, 'Tm': self.tm.value() * 1000.0}

    def _integrate(self, win, integ):
        """Reduce one detection window to a single complex echo value."""
        v = win['v']
        if integ == 'Peak |V|':
            return v[int(np.argmax(np.abs(v)))]
        if integ == 'Window integral':
            return np.trapz(v, win['t'])
        return v[v.size // 2]                            # center point

    def _build_events(self, step):
        """Events + phase cycle for one preset step (with ideal-pulse option)."""
        events, cyc = self.preset.build(
            step=step, flip_cal=self._flip_cal(), resonator=self._resonator(),
            detect_dt=self.detect_dt.value(), det_window=self._det_window(),
            time_grid=self._time_grid(), npoints=int(self.sweep_pts.value()))
        if self.ideal_chk.isChecked():
            events = self._idealize(events)
        return events, cyc

    def _run_sweep(self):
        if self.sweep_mode.currentText().startswith('Offset'):
            self._run_field_sweep()
        else:
            self._run_time_sweep()

    def _run_time_sweep(self):
        sysm = self._build_system()
        offs, weights = self._build_ensemble()
        offs, b1, weights = self._apply_b1(offs, weights)
        eng = sd.Engine(sysm, offsets=offs, b1=b1, weights=weights,
                        relaxation=self._relaxation())

        npts = int(self.sweep_pts.value())
        axis = self.preset.sweep_axis(npoints=npts)
        integ = self.integ.currentText()

        sig = np.full(npts, np.nan, dtype=complex)
        self._axis_unit = 's'
        self._x_log = self.preset.globals.get('sweep_type') == 'log'
        self._update_status("Simulating 0 / %d…" % npts)
        for i in range(npts):
            if self._stop:
                self._update_status("Stopped at %d / %d." % (i, npts))
                break
            events, cyc = self._build_events(step=i)
            sig[i] = self._integrate(eng.run(events, phase_cycle=cyc)[0], integ)
            if i % 4 == 0 or i == npts - 1:
                self._axis, self._sig = axis, sig
                self._replot_only()
                self._update_status("Simulating %d / %d…" % (i + 1, npts))
                QApplication.processEvents()
        self._axis, self._sig = axis, sig
        self._replot_only()
        if not self._stop:
            self._update_status("Done: %d points.%s" % (npts, self._aliasing_warning(npts)))

    def _aliasing_warning(self, npts):
        """Warn if the discrete offset grid is too coarse for the sequence.

        A uniform offset grid of N points over +/-span makes every signal
        (notably the first pulse's FID) recur at 1/Delta_offset; when that
        recurrence lands within a detection window it corrupts the echo with a
        spurious ripple. Returns '' if fine, else an actionable message."""
        if self.line_shape.currentText() == 'Single packet':
            return ''
        span = self.off_span.value()                     # MHz
        n = int(self.off_pts.value())
        if span <= 0 or n < 2:
            return ''
        recur = 1000.0 * (n - 1) / (2.0 * span)          # ns
        try:
            _, det = self.preset.layout(step=npts - 1, det_window=self._det_window(),
                                        time_grid=self._time_grid(), npoints=npts)
            tmax = (det['start'] + det['length']) if det else 0.0
        except Exception:
            tmax = 0.0
        if tmax > 0 and recur < tmax:
            need = int(np.ceil(1 + 2.0 * span * tmax / 1000.0))
            return ("  ⚠ offset-grid recurrence %.0f ns < sequence %.0f ns "
                    "→ aliasing ripple; raise Offset points to ≥%d or lower "
                    "Offset span." % (recur, tmax, need))
        return ''

    def _run_field_sweep(self):
        """Echo-detected field sweep: fixed sequence, sweep the spin packets'
        offset past the excitation. The line shape is the EPR spectrum; the
        result is that spectrum convolved with the pulses' excitation profile."""
        sysm = self._build_system()
        base, weights = self._build_ensemble()           # GHz line about 0
        relax = self._relaxation()
        integ = self.integ.currentText()
        events, cyc = self._build_events(step=0)          # sequence fixed

        npts = int(self.sweep_pts.value())
        fspan = self.field_span.value()                   # MHz
        axis = np.linspace(-fspan, fspan, npts)           # MHz (x-axis)
        faxis = axis / 1000.0                             # GHz shift per point

        sig = np.full(npts, np.nan, dtype=complex)
        self._axis_unit = 'Hz'
        self._x_log = False
        self._update_status("Field sweep 0 / %d…" % npts)
        for i in range(npts):
            if self._stop:
                self._update_status("Stopped at %d / %d." % (i, npts))
                break
            offs, b1, w = self._apply_b1(base + faxis[i], weights)
            eng = sd.Engine(sysm, offsets=offs, b1=b1, weights=w, relaxation=relax)
            sig[i] = self._integrate(eng.run(events, phase_cycle=cyc)[0], integ)
            if i % 4 == 0 or i == npts - 1:
                self._axis, self._sig = axis, sig
                self._replot_only()
                self._update_status("Field sweep %d / %d…" % (i + 1, npts))
                QApplication.processEvents()
        self._axis, self._sig = axis, sig
        self._replot_only()
        if not self._stop:
            self._update_status("Done: %d points." % npts)

    # ------------------------------------------------------------------ #
    # Plotting
    # ------------------------------------------------------------------ #
    def _clear_items(self, widget, items, legend=None):
        # CrosshairPlotWidget.clear() drops the crosshair/ruler items it installs
        # in __init__, so remove only our own tracked curves (and legend entries).
        for it in items:
            widget.removeItem(it)
            if legend is not None:
                try:
                    legend.removeItem(it)
                except Exception:
                    pass
        items.clear()

    def _replot_only(self, *_):
        self._clear_items(self.p_sig, self._sig_items, self.sig_legend)
        if self._axis is None or self._sig is None:
            return
        if self._axis_unit == 'Hz':
            x = self._axis * 1e6                         # MHz -> Hz
            self.p_sig.setLabel('bottom', 'Field / offset', units='Hz')
        else:
            x = self._axis * 1e-9                        # ns -> s
            self.p_sig.setLabel('bottom', 'Sweep axis', units='s')
        v = self._sig
        good = ~np.isnan(v.real)
        if good.sum() == 0:
            return
        x, v = x[good], v[good]
        mode = self.show_mode.currentText()
        if mode == 'Magnitude':
            ys = [np.abs(v)]
            self._sig_items.append(self.p_sig.plot(x, ys[0], pen=pg.mkPen(COL_OBS, width=2), name='|V|'))
        elif mode == 'Real':
            ys = [v.real]
            self._sig_items.append(self.p_sig.plot(x, ys[0], pen=pg.mkPen(COL_OBS, width=2), name='Re'))
        elif mode == 'Imag':
            ys = [v.imag]
            self._sig_items.append(self.p_sig.plot(x, ys[0], pen=pg.mkPen(COL_PUMP, width=2), name='Im'))
        else:
            ys = [v.real, v.imag]
            self._sig_items.append(self.p_sig.plot(x, ys[0], pen=pg.mkPen(COL_OBS, width=2), name='Re'))
            self._sig_items.append(self.p_sig.plot(x, ys[1], pen=pg.mkPen(COL_PUMP, width=2), name='Im'))
        # A log-time sweep (T1 recovery) spans decades -> show it on a log x-axis.
        self.p_sig.setLogMode(x=self._x_log, y=False)
        # Fit the view explicitly (infinite-extent crosshair/legend items keep
        # auto-range from settling on a sensible scale, leaving ugly tick labels).
        if x.size:
            if self._x_log:
                xp = np.log10(x[x > 0])
                if xp.size:
                    self.p_sig.setXRange(xp.min(), xp.max(), padding=0.03)
            else:
                xspan = float(x.max() - x.min())
                xpad = 0.02 * xspan if xspan > 1e-15 else max(abs(float(x.max())), 1e-9)
                self.p_sig.setXRange(x.min() - xpad, x.max() + xpad, padding=0)
            lo = min(float(np.min(a)) for a in ys)
            hi = max(float(np.max(a)) for a in ys)
            yspan = hi - lo
            # A flat trace (single packet -> no echo envelope) has zero span;
            # give it a real window so the line is visible and the Y ticks stay
            # clean instead of collapsing to long-decimal labels.
            ypad = 0.08 * yspan if yspan > 1e-9 else max(0.1 * max(abs(lo), abs(hi)), 0.05)
            self.p_sig.setYRange(lo - ypad, hi + ypad, padding=0)

    def redraw_sequence(self, *_):
        """Draw the loaded sequence (pulse blocks + detection window) for a step."""
        self._clear_items(self.p_seq, self._seq_items)
        if self.preset is None:
            return
        step = int(self.step_spin.value())
        pulses, det = self.preset.layout(step=step, det_window=self._det_window(),
                                         time_grid=self._time_grid(),
                                         npoints=int(self.sweep_pts.value()))
        if not pulses:
            return
        self._echo_line = None
        for k, p in enumerate(pulses):
            s = p['start'] * 1e-9
            e = (p['start'] + p['length']) * 1e-9
            h = 1.0 if self.preset.kind == 'rect' else max(0.1, p['coef'] / 100.0)
            col = COL_PUMP if abs(p['center']) > 1e-6 else COL_OBS
            self._seq_items.append(self.p_seq.plot(
                [s, s, e, e], [0, h, h, 0], pen=pg.mkPen(col, width=2),
                fillLevel=0, brush=pg.mkBrush(col[0], col[1], col[2], 60)))
            # Mark the pulse position (start time, ns) above the block.
            txt = pg.TextItem('P%d @ %.0f' % (k + 1, p['start']),
                              color=col, anchor=(0.5, 1.0))
            txt.setPos(0.5 * (s + e), h)
            self.p_seq.addItem(txt, ignoreBounds=True)
            self._seq_items.append(txt)
        if det is not None:
            region = pg.LinearRegionItem(
                values=(det['start'] * 1e-9, (det['start'] + det['length']) * 1e-9),
                brush=pg.mkBrush(*COL_DET), movable=False)
            region.setZValue(-10)
            self.p_seq.addItem(region, ignoreBounds=True)
            self._seq_items.append(region)

        if self.echo_chk.isChecked():
            t_echo = self.echo_pos.value()
            line = GrabbableLine(
                pos=t_echo * 1e-9, angle=90, movable=True,
                pen=pg.mkPen(COL_ECHO, width=2, style=Qt.PenStyle.DashLine),
                hoverPen=pg.mkPen(COL_ECHO, width=3),
                label='echo %.1f ns' % t_echo,
                labelOpts={'position': 0.88, 'color': (255, 255, 255),
                           'fill': pg.mkBrush(COL_ECHO[0], COL_ECHO[1],
                                              COL_ECHO[2], 200),
                           'border': pg.mkPen(COL_ECHO, width=1),
                           'movable': False, 'rotateAxis': (1, 0)})
            line.sigPositionChanged.connect(self._on_echo_moving)
            line.sigPositionChangeFinished.connect(self._on_echo_dragged)
            self.p_seq.addItem(line, ignoreBounds=True)
            self._seq_items.append(line)
            self._echo_line = line
        # Fit the view to the actual sequence. The infinite-extent items (region,
        # marker, text) can't drive auto-range, so set the x-range explicitly
        # from the finite pulse/detection/echo extents — otherwise the view stays
        # at the default [0, 1] s and the SI auto-prefix shows ugly tick labels.
        xs_hi = [p['start'] + p['length'] for p in pulses]
        xs_lo = [p['start'] for p in pulses] + [0.0]
        if det is not None:
            xs_hi.append(det['start'] + det['length'])
            xs_lo.append(det['start'])
        if self.echo_chk.isChecked():
            xs_hi.append(self.echo_pos.value())
            xs_lo.append(self.echo_pos.value())
        xmax, xmin = max(xs_hi), min(xs_lo)
        pad = 0.05 * max(xmax - xmin, 1.0)
        self.p_seq.setXRange((xmin - pad) * 1e-9, (xmax + pad) * 1e-9, padding=0)
        self.p_seq.setYRange(-0.05, 1.2, padding=0)

    def _on_echo_moving(self):
        """Live-update the marker's label while it is being dragged."""
        if self._echo_line is not None:
            self._echo_line.label.setFormat(
                'echo %.1f ns' % (self._echo_line.value() * 1e9))

    def _on_echo_dragged(self):
        """Write a dragged marker back to the Echo position box (no redraw)."""
        if self._echo_line is None:
            return
        self.echo_pos.blockSignals(True)
        self.echo_pos.setValue(self._echo_line.value() * 1e9)
        self.echo_pos.blockSignals(False)

    # ------------------------------------------------------------------ #
    def save_trace(self):
        if self._axis is None or self._sig is None:
            self._update_status("Nothing to save yet.")
            return
        path = self.opener.create_file_dialog(multiprocessing=True,
                                              directory=self.last_dir)
        if not path or path == 'None':
            return
        good = ~np.isnan(self._sig.real)
        data = np.column_stack((self._axis[good], self._sig[good].real,
                                self._sig[good].imag))
        axis_col = 'offset_MHz' if self._axis_unit == 'Hz' else 'axis_ns'
        header = ("Spin-dynamics simulation of %s\n%s, Re, Im"
                  % (os.path.basename(self.preset_path or 'preset'), axis_col))
        try:
            self.opener.save_data(path, data.T, header=header)
            self.last_dir = os.path.dirname(path) or self.last_dir
            _save_last_dir(self.last_dir)
            self._update_status("Saved: %s" % os.path.basename(path))
        except Exception as e:
            self._update_status("✗ save failed: %s" % e)


def main():
    app = QApplication(sys.argv)
    apply_app_style(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
