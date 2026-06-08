# -*- coding: utf-8 -*-
"""
Pulse Excitation Profile control-center tool.
=============================================

Standalone QProcess launched from the "EPR Endstation Control" tab. It lets you
pick a pulse shape (rectangular, gaussian, sinc, half-sine, quarter-sine, WURST,
sech/tanh), dial its length / B1 amplitude / shape parameters, and immediately
see (a) the pulse waveform I/Q + envelope in time and (b) the resulting
excitation/inversion profile across resonance offset.

The profile is computed by full Bloch/propagator integration of a single S = 1/2
spin (``atomize.math_modules.pulse_excitation``) — the EasySpin / Doll-Jeschke
approach — so adiabatic pulses (WURST, sech/tanh) come out correctly, not just
the linear-response (FFT) approximation. "Hold" freezes the current profile as a
faint overlay so several pulses can be compared on one axis, the way the original
Julia/Pluto notebook stacked inversion profiles.

No hardware is touched: this is a design/visualisation aid. Everything runs in
this process; nothing is pushed to LivePlot or the main GUI.
"""

import sys

import numpy as np
import pyqtgraph as pg
from pyqtgraph.dockarea import DockArea
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QComboBox, QGridLayout, QVBoxLayout, QHBoxLayout, QDoubleSpinBox, QSpinBox,
    QCheckBox, QFrame, QScrollArea)

import atomize.math_modules.pulse_excitation as pe
# Reuse the main-window plot stack (crosshair, Shift-drag ruler, FFT/log
# right-click toggles) so this preview behaves like the rest of the EPR suite.
from atomize.main.widgets import CrosshairPlotWidget, CloseableDock
from atomize.general_modules.gui_style import (apply_app_style,
    BG, FG, ACCENT, BUTTON_STYLE, LABEL_STYLE, DSPIN_STYLE, SPIN_STYLE,
    COMBO_STYLE, CHECKBOX_STYLE, SCROLL_STYLE)

# Common minimum row height so spinboxes / combos / buttons line up and the
# native +/- spin frame renders fully (repo-wide convention, see data_treatment).
ROW_H = 26

# Point size for HTML <sub> subscripts. The Qt rich-text default (~0.7 em)
# renders subscripts tiny; bump them so they read clearly. The plot axis/legend
# use a larger base font than the 9 pt control labels, hence two sizes.
SUB_PT = 11       # plot axis / legend (pyqtgraph rich text)
LBL_SUB_PT = 10   # control-panel QLabels (base font is 9 pt)


def _sub(base, sub, pt=SUB_PT):
    """base + a slightly-enlarged HTML subscript (rich-text labels)."""
    return '%s<sub><span style="font-size: %dpt">%s</span></sub>' % (base, pt, sub)


def _lsub(base, sub):
    """base + enlarged subscript sized for the 9 pt control-panel labels."""
    return _sub(base, sub, LBL_SUB_PT)


# Hardware timing grid (ns). Pulse length snaps to a multiple of this, matching
# awg_phasing_insys / sequence_calculator so a length set here is realisable.
GRID = 3.2


def round_to_closest(x, y):
    """Round x up to the closest multiple of y (awg_phasing/Insys grid rule)."""
    return round((y * ((x // y) + (round(x % y, 2) > 0))), 1)

# Which extra parameter rows each shape exposes (others are hidden). Parameter
# names / units follow the Insys AWG awg_pulse convention so a pulse designed
# here matches the hardware buffer. 'center' is the carrier (MHz) / sweep centre.
SHAPE_PARAMS = {
    'rectangular': ['center'],
    'gaussian':    ['sigma', 'center'],
    'sinc':        ['sigma', 'center'],
    'half-sine':   ['center'],
    'quartersine': ['edge', 'center'],
    'WURST':       ['n', 'bw', 'center'],
    'sech/tanh':   ['b', 'n', 'bw', 'center'],
}

# Initial magnetization presets.
INIT_STATES = {
    '+z (equilibrium)': (0.0, 0.0, 1.0),
    '-z (inverted)':    (0.0, 0.0, -1.0),
    '+x':               (1.0, 0.0, 0.0),
    '+y':               (0.0, 1.0, 0.0),
}

# Distinct colours for overlay "hold" curves.
HOLD_COLORS = [(120, 200, 255), (255, 170, 90), (160, 230, 130),
               (220, 130, 220), (240, 220, 110), (130, 220, 220)]


class MainWindow(QMainWindow):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWindowTitle("EPR Pulse Excitation Profile")
        self.setGeometry(150, 120, 1180, 720)

        self._holds = []          # list of (offsets_MHz, Mz, label, color)
        self._param_rows = {}     # name -> (label_widget, spin_widget)
        self._shape_items = []    # live curve items on the waveform panel
        self._prof_items = []     # live curve items on the profile panel

        # Background on the QMainWindow (as in data_treatment / awg_phasing) so
        # spinboxes keep their full native +/- frame.
        self.setStyleSheet("background-color: %s;" % BG)

        # Debounce recompute so dragging a spinbox stays smooth.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self.recompute)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        # Plot on the left, controls on the right.
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

        # Open on the WURST case (the tool's headline: adiabatic inversion done
        # right), matching the parameters of the reference Pluto notebook.
        self.shape.setCurrentText('WURST')
        self._on_group_shape_changed(self.p1, self.p1_rows)
        self._on_group_shape_changed(self.p2, self.p2_rows)
        self.recompute()

    # ------------------------------------------------------------------ #
    # Controls
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
        s.setFixedWidth(150)
        s.valueChanged.connect(self.schedule)
        return s

    def _ispin(self, lo, hi, val, suffix=''):
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        if suffix:
            s.setSuffix(suffix)
        s.setStyleSheet(SPIN_STYLE)
        s.setFixedWidth(150)
        s.valueChanged.connect(self.schedule)
        return s

    def _label(self, text):
        lab = QLabel(text)
        lab.setStyleSheet(LABEL_STYLE)
        return lab

    def _make_pulse_group(self, title):
        """Build one pulse's control block. Returns (container, store, rows).

        ``store`` maps logical names (shape/tp/nu1/phi0 + shape params) to their
        widgets; ``rows`` maps each shape-specific param to its (label, widget)
        pair for per-shape show/hide. Pulse 1 and Pulse 2 are identical blocks.
        """
        box = QWidget()
        g = QGridLayout(box)
        g.setContentsMargins(0, 0, 0, 0)
        g.setVerticalSpacing(6)
        store, rows = {}, {}
        r = 0

        head = self._label(title)
        head.setStyleSheet("QLabel { color: %s; font-weight: bold; }" % ACCENT)
        g.addWidget(head, r, 0, 1, 2); r += 1

        g.addWidget(self._label("Shape"), r, 0)
        shape = QComboBox()
        shape.addItems(list(SHAPE_PARAMS.keys()))
        shape.setStyleSheet(COMBO_STYLE)
        shape.setFixedWidth(150)
        g.addWidget(shape, r, 1); r += 1
        store['shape'] = shape

        # Length on the 3.2 ns hardware grid (step 3.2, snapped on edit).
        g.addWidget(self._label("Length " + _lsub('t', 'p') + " (ns)"), r, 0)
        tp = self._dspin(GRID, 100000.0, round_to_closest(200.0, GRID), GRID, 1)
        tp.editingFinished.connect(lambda s=tp: self._snap_spin(s))
        g.addWidget(tp, r, 1); r += 1
        store['tp'] = tp

        g.addWidget(self._label("B" + _lsub('', '1') + " peak " + _lsub('ν', '1') + " (MHz)"), r, 0)
        nu1 = self._dspin(0.0, 1000.0, 31.0, 0.1, 2)
        g.addWidget(nu1, r, 1); r += 1
        store['nu1'] = nu1

        g.addWidget(self._label("Phase " + _lsub('φ', '0') + " (deg)"), r, 0)
        phi0 = self._dspin(-360.0, 360.0, 0.0, 1.0, 1)
        g.addWidget(phi0, r, 1); r += 1
        store['phi0'] = phi0

        # Parameters & units match Insys awg_pulse: sigma (ns, 3.2 grid), N
        # (int 1-100), b (1/ns), sweep (MHz), center (MHz). Sigma rows snap to the
        # 3.2 ns grid on edit, like the AWG tool.
        sigma_w = self._dspin(GRID, 1900.0, round_to_closest(40.0, GRID), GRID, 1)
        sigma_w.editingFinished.connect(lambda s=sigma_w: self._snap_spin(s))
        specs = [
            ('sigma',  "σ (ns)",                 sigma_w),
            ('edge',   "Quarter-sine edge (ns)", self._dspin(0.1, 100000.0, 20.0, 2.0, 1)),
            ('n',      "N",                       self._dspin(1.0, 100.0, 10.0, 1.0, 0)),
            ('b',      "b (1/ns)",                self._dspin(0.005, 10.0, 0.02, 0.001, 3)),
            ('bw',     "Sweep Δν (MHz)",          self._dspin(-1000.0, 1000.0, 200.0, 5.0, 1)),
            ('center', "Carrier " + _lsub('ν', '0') + " (MHz)", self._dspin(-2500.0, 2500.0, 0.0, 5.0, 1)),
        ]
        for name, text, widget in specs:
            lab = self._label(text)
            g.addWidget(lab, r, 0)
            g.addWidget(widget, r, 1)
            rows[name] = (lab, widget)
            store[name] = widget
            r += 1

        shape.currentTextChanged.connect(
            lambda _t, st=store, rw=rows: self._on_group_shape_changed(st, rw))
        return box, store, rows

    def _build_controls(self):
        panel = QScrollArea()
        panel.setWidgetResizable(True)
        panel.setStyleSheet(SCROLL_STYLE)
        panel.setFixedWidth(350)

        inner = QWidget()
        panel.setWidget(inner)
        v = QVBoxLayout(inner)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        # ---- Pulse 1 ----
        box1, self.p1, self.p1_rows = self._make_pulse_group("Pulse 1")
        v.addWidget(box1)
        # Aliases so the single-pulse code paths keep working unchanged.
        self.shape = self.p1['shape']
        self.tp = self.p1['tp']
        self.nu1 = self.p1['nu1']
        self.phi0 = self.p1['phi0']
        self._param_rows = self.p1_rows

        # ---- Two-pulse toggle + inter-pulse delay ----
        self.two_pulse = QCheckBox("Two-pulse sequence (P1 → τ → P2)")
        self.two_pulse.setStyleSheet(CHECKBOX_STYLE)
        self.two_pulse.toggled.connect(self._on_two_pulse_toggled)
        v.addWidget(self.two_pulse)

        self.delay_box = QWidget()
        dg = QGridLayout(self.delay_box)
        dg.setContentsMargins(0, 0, 0, 0)
        dg.addWidget(self._label("Delay " + _lsub('τ', '12') + " (ns)"), 0, 0)
        self.delay = self._dspin(0.0, 1e6, 200.0, GRID, 1)
        dg.addWidget(self.delay, 0, 1)
        # Detection delay after P2. Read-out happens here; set = τ12 to sit on the
        # Hahn echo (refocuses the inter-pulse precession → smooth profile). 0 =
        # read immediately after P2 (shows the un-refocused FID/ripple).
        dg.addWidget(self._label("Detect " + _lsub('τ', 'd') + " (ns)"), 1, 0)
        self.det_delay = self._dspin(0.0, 1e6, 200.0, GRID, 1)
        dg.addWidget(self.det_delay, 1, 1)
        # One-click lock: auto-set τ_d to the actual echo time (found numerically,
        # since finite pulses shift it off τ12). QCheckBox is plain-text only.
        self.lock_taud = QCheckBox("auto τd → echo")
        self.lock_taud.setStyleSheet(CHECKBOX_STYLE)
        self.lock_taud.setChecked(True)
        self.lock_taud.setToolTip(
            "Find the detection delay that refocuses the echo (maximises the "
            "coherent transverse signal). For finite pulses this is a few ns "
            "past τ12. Uncheck to set τd by hand.")
        self.lock_taud.toggled.connect(self._on_lock_taud_toggled)
        dg.addWidget(self.lock_taud, 2, 0, 1, 2)
        self.det_delay.setEnabled(False)   # locked by default
        v.addWidget(self.delay_box)

        # Continuous-LO model: reference P2's RF phase to absolute sequence time
        # (it picks up 2*pi*nu0_2*(tp1+tau)). Off = each pulse phase referenced to
        # its own start. Only matters when P2's carrier differs from 0.
        self.cont_phase = QCheckBox("Carrier-phase continuity")
        self.cont_phase.setStyleSheet(CHECKBOX_STYLE)
        self.cont_phase.setChecked(True)
        self.cont_phase.setToolTip(
            "Continuous-LO model: Pulse 2's carrier phase continues through the "
            "delay (phase += 2π·ν₀·(t_p1+τ)). "
            "Off: each pulse's phase starts at its own φ₀.")
        self.cont_phase.toggled.connect(self.schedule)
        v.addWidget(self.cont_phase)

        # ---- Pulse 2 ----
        self.p2_box, self.p2, self.p2_rows = self._make_pulse_group("Pulse 2")
        v.addWidget(self.p2_box)
        self.p2['shape'].setCurrentText('rectangular')

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: %s;" % ACCENT)
        v.addWidget(sep)

        # ---- Offset axis & integration (shared) ----
        shared = QWidget()
        g = QGridLayout(shared)
        g.setContentsMargins(0, 0, 0, 0)
        g.setVerticalSpacing(6)
        r = 0

        axis_title = self._label("Offset axis & integration")
        axis_title.setStyleSheet("QLabel { color: %s; font-weight: bold; }" % ACCENT)
        g.addWidget(axis_title, r, 0, 1, 2); r += 1

        g.addWidget(self._label("Offset span ±Δν (MHz)"), r, 0)
        self.span = self._dspin(1.0, 5000.0, 250.0, 10.0, 1)
        g.addWidget(self.span, r, 1); r += 1

        g.addWidget(self._label("Offset points"), r, 0)
        self.npts = self._ispin(11, 4001, 401)
        g.addWidget(self.npts, r, 1); r += 1

        g.addWidget(self._label("Time step Δt (ns)"), r, 0)
        self.dt = self._dspin(0.01, 50.0, 0.5, 0.1, 2)
        g.addWidget(self.dt, r, 1); r += 1

        g.addWidget(self._label("Initial M"), r, 0)
        self.init = QComboBox()
        self.init.addItems(list(INIT_STATES.keys()))
        self.init.setStyleSheet(COMBO_STYLE)
        self.init.setFixedWidth(150)
        self.init.currentTextChanged.connect(self.schedule)
        g.addWidget(self.init, r, 1); r += 1

        g.addWidget(self._label("Show"), r, 0)
        self.show_mode = QComboBox()
        self.show_mode.addItems(['Mz (inversion)', 'Mxy (transverse)',
                                 'Mx, My', 'Mx, My, Mz', 'all'])
        self.show_mode.setStyleSheet(COMBO_STYLE)
        self.show_mode.setFixedWidth(150)
        self.show_mode.currentTextChanged.connect(self.replot)
        g.addWidget(self.show_mode, r, 1); r += 1
        v.addWidget(shared)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: %s;" % ACCENT)
        v.addWidget(sep2)

        btn_row = QHBoxLayout()
        btn_hold = QPushButton("Hold profile")
        btn_hold.setStyleSheet(BUTTON_STYLE)
        btn_hold.clicked.connect(self.hold_current)
        btn_clear = QPushButton("Clear holds")
        btn_clear.setStyleSheet(BUTTON_STYLE)
        btn_clear.clicked.connect(self.clear_holds)
        btn_row.addWidget(btn_hold); btn_row.addWidget(btn_clear)
        v.addLayout(btn_row)

        self.info = QLabel("")
        self.info.setStyleSheet("QLabel { color: %s; }" % FG)
        self.info.setWordWrap(True)
        v.addWidget(self.info)

        v.addStretch(1)

        # Two-pulse controls start hidden.
        self.delay_box.setVisible(False)
        self.cont_phase.setVisible(False)
        self.p2_box.setVisible(False)
        return panel

    def _build_plots(self):
        # Two CrosshairPlotWidgets stacked in one DockArea (atomize/main/widgets):
        # the waveform on top, the excitation profile below. No setBackground —
        # inherit pyqtgraph's global background set in widgets.py so this matches
        # the rest of the suite. Close buttons hidden (the docks are the only
        # plots and must not be dismissable).
        pg.setConfigOptions(antialias=True)
        self.plot_area = DockArea()

        self.p_shape = CrosshairPlotWidget()
        self.p_shape.showGrid(x=True, y=True, alpha=0.2)
        self.p_shape.setLabel('bottom', 'Time', units='s')
        self.p_shape.setLabel('left', 'Amplitude (norm.)')
        self.shape_legend = self.p_shape.addLegend(offset=(-10, 10))
        dock_shape = CloseableDock(name='Pulse waveform', widget=self.p_shape)
        dock_shape.close_button.hide()

        self.p_prof = CrosshairPlotWidget()
        self.p_prof.showGrid(x=True, y=True, alpha=0.2)
        self.p_prof.setLabel('bottom', 'Resonance offset Δν', units='Hz')
        self.p_prof.setLabel('left', 'M / ' + _sub('M', '0'))
        self.prof_legend = self.p_prof.addLegend(offset=(-10, 10))
        self.p_prof.setYRange(-1.05, 1.05)
        dock_prof = CloseableDock(name='Excitation profile', widget=self.p_prof)
        dock_prof.close_button.hide()

        self.plot_area.addDock(dock_shape, 'top')
        self.plot_area.addDock(dock_prof, 'bottom', dock_shape)
        return self.plot_area

    # ------------------------------------------------------------------ #
    # Reactions
    # ------------------------------------------------------------------ #
    def _snap_spin(self, spin):
        """Snap a length spinbox to the 3.2 ns hardware grid (as the AWG does)."""
        v = round_to_closest(spin.value(), GRID)
        if abs(v - spin.value()) > 1e-9:
            spin.blockSignals(True)
            spin.setValue(v)
            spin.blockSignals(False)
        self.schedule()

    def _on_group_shape_changed(self, store, rows):
        """Show only the shape-specific rows that the chosen shape uses."""
        active = set(SHAPE_PARAMS[store['shape'].currentText()])
        for name, (lab, widget) in rows.items():
            vis = name in active
            lab.setVisible(vis)
            widget.setVisible(vis)
        self.schedule()

    def _echo_taud(self, M2, offsets, tau):
        """Detection delay that refocuses the echo, found numerically.

        After P2 the detection delay is pure free precession, so the transverse
        signal at read-out time td is the coherent sum
        ``|sum_offset (Mx+iMy) exp(i 2pi offset td)|``. The echo is its maximum.
        Cheap: no re-propagation, just a 1D scan of z-rotations. Falls back to
        ``tau`` if there is essentially no transverse magnetization.
        """
        c = M2[:, 0] + 1j * M2[:, 1]
        if np.max(np.abs(c)) < 1e-6:
            return tau
        # subsample the offset axis — echo timing needs no fine resolution
        step = max(1, offsets.size // 401)
        os_, c_ = offsets[::step], c[::step]
        L = max(self.p1['tp'].value(), self.p2['tp'].value())
        cand = np.arange(max(0.0, tau - 0.5 * L), tau + 2.0 * L + 1.0, 0.2)
        S = np.abs(np.exp(1j * 2 * np.pi * np.outer(cand, os_)) @ c_)
        return float(cand[int(np.argmax(S))])

    def _on_lock_taud_toggled(self, on):
        self.det_delay.setEnabled(not on)   # value is driven by recompute when on
        self.schedule()

    def _on_two_pulse_toggled(self, on):
        self.delay_box.setVisible(on)
        self.cont_phase.setVisible(on)
        self.p2_box.setVisible(on)
        # The detection delay is free precession (a z-rotation): it leaves Mz AND
        # |Mxy| invariant and only moves Mx/My individually. So switch away from
        # the Mz default to Mx,My where the echo refocusing (My flattening) shows.
        if on and self.show_mode.currentText() == 'Mz (inversion)':
            self.show_mode.setCurrentText('Mx, My')
        self.schedule()

    def schedule(self):
        self._timer.start()

    def _gather_params_group(self, store):
        shape = store['shape'].currentText()
        params = {name: store[name].value() for name in SHAPE_PARAMS[shape]}
        return shape, params

    def _pulse_waveform(self, store, dt_disp, t0=0.0, phi_offset=0.0):
        """Normalised I/Q + envelope of one pulse on an absolute time axis (ns).

        ``phi_offset`` (rad) is added to the pulse phase — used to carry the
        carrier-phase-continuity term so the displayed waveform matches what the
        spins actually see.
        """
        shape, params = self._gather_params_group(store)
        tp = store['tp'].value()
        phi0 = np.deg2rad(store['phi0'].value()) + phi_offset
        d = min(dt_disp, tp)
        edges = np.arange(0.0, tp + 0.5 * d, d)
        if edges.size < 2:
            edges = np.array([0.0, tp])
        tmid = 0.5 * (edges[:-1] + edges[1:])
        steps = np.diff(edges)
        a, nu = pe.waveform(shape, tmid, tp, params)
        phi = phi0 + 2.0 * np.pi * (np.cumsum(nu * steps) - 0.5 * nu * steps)
        return tmid + t0, a * np.cos(phi), a * np.sin(phi), a

    def recompute(self):
        shape1, params1 = self._gather_params_group(self.p1)
        tp1 = self.p1['tp'].value()
        nu1_1 = self.p1['nu1'].value() / 1000.0      # MHz -> GHz
        phi1 = np.deg2rad(self.p1['phi0'].value())
        dt_disp = self.dt.value()
        dt1 = min(dt_disp, tp1)
        span = self.span.value() / 1000.0            # MHz -> GHz
        npts = self.npts.value()
        init = INIT_STATES[self.init.currentText()]
        two = self.two_pulse.isChecked()

        offsets = np.linspace(-span, span, npts)     # GHz
        self._off_mhz = offsets * 1000.0

        # ---- excitation profile: P1, then optionally  τ  then P2 ----
        M = np.tile(np.asarray(init, dtype=float), (npts, 1))
        M = pe.propagate_pulse(M, shape1, tp1, nu1_1, offsets, params1,
                               dt=dt1, phi0=phi1)

        # ---- waveform (time domain): P1, gap at baseline, P2 ----
        t1, I1, Q1, e1 = self._pulse_waveform(self.p1, dt_disp, 0.0)

        if two:
            tau = self.delay.value()
            shape2, params2 = self._gather_params_group(self.p2)
            tp2 = self.p2['tp'].value()
            nu1_2 = self.p2['nu1'].value() / 1000.0
            phi2 = np.deg2rad(self.p2['phi0'].value())
            dt2 = min(dt_disp, tp2)

            # Carrier-phase continuity: with a continuous LO, P2's phase is
            # referenced to absolute time, so its constant carrier nu0_2 has
            # advanced by 2*pi*nu0_2*(tp1+tau) by the time P2 starts.
            phi2_extra = 0.0
            if self.cont_phase.isChecked():
                nu0_2 = params2.get('center', 0.0) / 1000.0   # MHz -> GHz
                phi2_extra = 2.0 * np.pi * nu0_2 * (tp1 + tau)

            M = pe.free_evolution(M, offsets, tau)
            M = pe.propagate_pulse(M, shape2, tp2, nu1_2, offsets, params2,
                                   dt=dt2, phi0=phi2 + phi2_extra)

            # Detection delay: free precession to the read-out point. When locked,
            # find the actual echo time numerically (finite pulses shift it off
            # tau) and reflect it in the disabled field; else use the typed value.
            if self.lock_taud.isChecked():
                tau_d = self._echo_taud(M, offsets, tau)
                if abs(self.det_delay.value() - tau_d) > 0.05:
                    self.det_delay.blockSignals(True)
                    self.det_delay.setValue(round(tau_d, 1))
                    self.det_delay.blockSignals(False)
            else:
                tau_d = self.det_delay.value()
            if tau_d > 0:
                M = pe.free_evolution(M, offsets, tau_d)

            # baseline markers bracket the free-evolution gap so the trace drops
            # to zero between the two pulses instead of drawing a diagonal; a
            # trailing pair spans the detection delay out to the read-out point.
            gx = np.array([tp1, tp1 + tau])
            gz = np.zeros(2)
            t2, I2, Q2, e2 = self._pulse_waveform(self.p2, dt_disp, tp1 + tau,
                                                  phi_offset=phi2_extra)
            t_end = tp1 + tau + tp2
            dx = np.array([t_end, t_end + tau_d])
            dz = np.zeros(2)
            self._t = np.concatenate([t1, gx, t2, dx])
            self._I = np.concatenate([I1, gz, I2, dz])
            self._Q = np.concatenate([Q1, gz, Q2, dz])
            self._env = np.concatenate([e1, gz, e2, dz])
        else:
            self._t, self._I, self._Q, self._env = t1, I1, Q1, e1

        self._Mx, self._My, self._Mz = M[:, 0], M[:, 1], M[:, 2]

        # ---- info line ----
        fa1 = pe.flip_angle(shape1, tp1, nu1_1, params1, dt=dt1)
        swept1 = shape1 in ('WURST', 'sech/tanh')
        txt = "P1 on-res flip: %.0f° (%.2f π)" % (np.rad2deg(fa1), fa1 / np.pi)
        if two:
            fa2 = pe.flip_angle(shape2, tp2, nu1_2, params2, dt=dt2)
            txt += "   |   P2: %.0f° (%.2f π)" % (np.rad2deg(fa2), fa2 / np.pi)
        elif swept1:
            txt += "  — nominal area; adiabatic inversion is offset-dependent."
        self.info.setText(txt)

        self.replot()

    def _clear_items(self, widget, items, legend):
        # CrosshairPlotWidget.clear() would drop the crosshair / ruler items it
        # installs in __init__, so remove only our own tracked curves (also pops
        # them from the legend).
        for it in items:
            widget.removeItem(it)
            try:
                legend.removeItem(it)
            except Exception:
                pass
        items.clear()

    def replot(self):
        # --- pulse shape panel (x in seconds → axis auto-prefixes to ns) ---
        self._clear_items(self.p_shape, self._shape_items, self.shape_legend)
        t_s = self._t * 1e-9
        self._shape_items.append(self.p_shape.plot(
            t_s, self._I, pen=pg.mkPen((120, 200, 255), width=2), name='I'))
        self._shape_items.append(self.p_shape.plot(
            t_s, self._Q, pen=pg.mkPen((255, 170, 90), width=2), name='Q'))
        self._shape_items.append(self.p_shape.plot(
            t_s, self._env,
            pen=pg.mkPen((160, 230, 130), width=1, style=Qt.PenStyle.DashLine),
            name='envelope'))

        # --- profile panel (x in Hz → axis auto-prefixes to MHz) ---
        self._clear_items(self.p_prof, self._prof_items, self.prof_legend)
        # held overlays first (faint), under the live curves
        for off, mz, label, color in self._holds:
            self._prof_items.append(self.p_prof.plot(
                off * 1e6, mz,
                pen=pg.mkPen(color, width=1, style=Qt.PenStyle.DotLine), name=label))

        mode = self.show_mode.currentText()
        off_hz = self._off_mhz * 1e6
        Mxy = np.hypot(self._Mx, self._My)
        mx_n, my_n = _sub('M', 'x'), _sub('M', 'y')
        mz_n, mxy_n = _sub('M', 'z'), _sub('M', 'xy')
        if mode == 'Mz (inversion)':
            curves = [(self._Mz, mz_n, (255, 90, 90))]
        elif mode == 'Mxy (transverse)':
            curves = [(Mxy, mxy_n, (120, 200, 255))]
        elif mode == 'Mx, My':
            curves = [(self._Mx, mx_n, (120, 200, 255)), (self._My, my_n, (255, 170, 90))]
        elif mode == 'Mx, My, Mz':
            curves = [(self._Mx, mx_n, (120, 200, 255)), (self._My, my_n, (255, 170, 90)),
                      (self._Mz, mz_n, (255, 90, 90))]
        else:  # all
            curves = [(self._Mx, mx_n, (120, 200, 255)), (self._My, my_n, (255, 170, 90)),
                      (self._Mz, mz_n, (255, 90, 90)), (Mxy, mxy_n, (160, 230, 130))]
        for y, name, color in curves:
            self._prof_items.append(self.p_prof.plot(
                off_hz, y, pen=pg.mkPen(color, width=2), name=name))

    def hold_current(self):
        color = HOLD_COLORS[len(self._holds) % len(HOLD_COLORS)]
        shape = self.shape.currentText()
        label = "%s %gns %gMHz" % (shape, self.tp.value(), self.nu1.value())
        # only tag the carrier when this shape actually uses it (sech has none)
        if 'center' in SHAPE_PARAMS[shape]:
            center = self._param_rows['center'][1].value()
            if center:
                label += " @%gMHz" % center
        # store offsets in MHz so replot's *1e6 (MHz -> Hz) matches the live curves
        self._holds.append((self._off_mhz.copy(), self._Mz.copy(), label, color))
        self.replot()

    def clear_holds(self):
        self._holds = []
        self.replot()


def main():
    app = QApplication(sys.argv)
    apply_app_style(app, app_id='Atomize.ITC.ExcitationProfile')
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
