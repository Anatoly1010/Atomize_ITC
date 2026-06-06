# -*- coding: utf-8 -*-
"""
EPR Sequence Timing & Phase-Cycling Calculator
================================================

A standalone control-center helper whose only job is to make setting up an
experiment in ``awg_phasing_insys.py`` (AWG channel) or ``phasing_insys.py``
(RECT channel) fast and mistake-proof.

You think in delays, not absolute positions. Choose how many pulses you have;
the first pulse sits at 0 and you type only the **tau** gaps between successive
pulses. The detection sits a tau after the last pulse — pick one of the taus you
already entered, or "free" to type a different number. So:

    pulses = 2, tau = 200, det = tau   ->  0, 200, 400
    pulses = 3, tau1 = 1000, tau2 = 200, det = tau2  ->  0, 1000, 1200, 1400

The detection is shown like another pulse; its phase field is the receiver
(coefficients like ``-1,2`` or an explicit notation like ``+x,-x``).

Positions are rounded to the 3.2 ns hardware grid with the *same*
``round_to_closest`` rule awg_phasing uses (ceil to the grid), so off-grid taus
snap exactly as they would there. The short phase notation is expanded into an
explicit per-step table, and the result is written as a ready-to-load
``.phase_awg`` / ``.phase`` preset.

Pulse length / amplitude / frequency / increments are usually the same across a
sequence, so they are kept out of the way: templates carry faithful values for
them internally and the preset writer uses those; custom pulses fall back to
defaults. Tweak them afterwards in the AWG/RECT tool if needed.

One-click "Open in AWG / RECT": writes the preset and (a) if that tool's window
is already open, it reloads in place via a temp signal file polled by the tool;
(b) if it is closed, prints an ``open_awg``/``open_rect`` sentinel that the main
window turns into a launch. No hardware is touched here.
"""

import os
import re
import sys
import math
import time
import tempfile

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QDoubleSpinBox,
    QSpinBox, QComboBox, QPushButton, QHBoxLayout, QVBoxLayout, QGridLayout,
    QPlainTextEdit, QTextEdit, QScrollArea, QFrame, QSizePolicy)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

import atomize.general_modules.general_functions as general
# Shared dark-theme styling so this tool matches the rest of the EPR suite.
from atomize.general_modules.gui_style import (apply_app_style, BUTTON_STYLE,
    LABEL_STYLE, DSPIN_STYLE, SPIN_STYLE, COMBO_STYLE, SCROLL_STYLE, BORDER, BG, FG, ACCENT)


# --------------------------------------------------------------------------- #
# Pure helpers (copied verbatim from the hardware modules so the grid + phase
# expansion are byte-identical to what the acquisition tools do at runtime).
# --------------------------------------------------------------------------- #
def round_to_closest(x, y):
    """Round x up to the closest multiple of y (awg_phasing/Insys round rule)."""
    return round((y * ((x // y) + (round(x % y, 2) > 0))), 1)


def expand_phase_cycling(p_input, *pulse_args):
    """Expand short phase notation into explicit per-step phase lists.

    Copied verbatim from awg_phasing_insys.MainWindow.expand_phase_cycling
    (identical to Insys_FPGA.digitizer_expand_phase_cycling). Understands
    ``+x/+y/-x/-y``, comma lists, ``[...]`` (4-step quadrature), ``(...)``
    (2-step), and a numeric-coefficient receiver (e.g. ``-1,2``).

    Returns ``{"pulses": [[...] per pulse], "receiver": [...]}``.
    """
    phases = ['+x', '+y', '-x', '-y']
    norm = {'x': 0, 'y': 1, '-x': 2, '-y': 3, '+': 0, '-': 2, 'i': 1, '-i': 3, '0': 0}

    def parse_to_indices(s):
        if not s:
            return [0]
        if isinstance(s, list):
            return [phases.index(p.strip()) if p.strip() in phases else norm.get(p.strip().lower().replace(' ', ''), 0) for p in s]

        s_clean = s.replace(' ', '')
        if ',' in s_clean:
            parts = [p for p in s_clean.split(',') if p]
            return [phases.index(p) if p in phases else norm.get(p.lower(), 0) for p in parts]

        def get_recursive(st):
            st = st.replace('D', '').lower().replace(' ', '')
            if not st:
                return [0]
            if '[' not in st and '(' not in st:
                return [norm.get(st.strip(), 0)]
            is_quad = st.startswith('[')
            inner = get_recursive(st[1:-1])
            steps, shift = (4, 1) if is_quad else (2, 2)
            return [(p_idx + step * shift) % 4 for step in range(steps) for p_idx in inner]

        return get_recursive(s_clean)

    raw_sequences = [parse_to_indices(arg) for arg in pulse_args]

    target_len = 1
    for i, seq in enumerate(raw_sequences):
        arg = pulse_args[i]
        if isinstance(arg, str) and ('(' in arg or '[' in arg):
            if len(seq) > 1:
                target_len *= len(seq)

    if target_len == 1:
        for seq in raw_sequences:
            if len(seq) > 1:
                target_len = abs(target_len * len(seq)) // math.gcd(target_len, len(seq))

    if target_len < 2:
        target_len = 2

    pulses_final = []
    current_repeat = 1
    for i, seq in enumerate(raw_sequences):
        arg = pulse_args[i]
        if isinstance(arg, str) and ('(' in arg or '[' in arg):
            expanded = [p for p in seq for _ in range(current_repeat)]
            final = (expanded * (target_len // len(expanded) + 1))[:target_len]
            current_repeat *= len(seq)
        else:
            final = (seq * (target_len // len(seq) + 1))[:target_len]
        pulses_final.append(final)

    if isinstance(p_input, (list, str)) and not any(ph in str(p_input).lower() for ph in ['x', 'y']):
        if isinstance(p_input, str):
            coeffs = [float(x) for x in re.findall(r'-?\d+\.?\d*', p_input)]
        else:
            coeffs = p_input

        receiver_indices = []
        for step in range(target_len):
            rec_sum = sum(coeffs[i] * pulses_final[i][step]
                          for i in range(min(len(coeffs), len(pulses_final))))
            receiver_indices.append(int(round(rec_sum)) % 4)
    else:
        det_indices = parse_to_indices(p_input)
        receiver_indices = (det_indices * (target_len // len(det_indices) + 1))[:target_len]

    to_str = lambda indices: [phases[i] for i in indices]
    return {"pulses": [to_str(p) for p in pulses_final], "receiver": to_str(receiver_indices)}


# --------------------------------------------------------------------------- #
# Constants and sequence templates
# --------------------------------------------------------------------------- #
MAX_PULSES = 8                       # excitation pulses P2..P9 (P1 = detection)

# "Advanced" per-pulse parameters kept out of the visible UI. Templates set
# faithful values; custom pulses use these defaults. Used only when writing the
# preset (the visible taus + phases drive everything you actually tune).
ADV_DEFAULT = {"len": 16.0, "type": "SINE", "fr": 50, "sw": 350, "amp": 100,
               "sig": 0.0, "sti": 0.0, "li": 0.0}
GLOB_DEFAULT = {"rep": 500.0, "field": 3324.0, "sweep": "Linear Time"}
DET_DEFAULT = {"len": 512.0, "fr": 50, "sti": 0.0, "wl": 0.0, "wr": 320.0}


# Per-pulse template keys: d (tau before this pulse; first is the start = 0),
# ph (phase), plus advanced len/fr/sw/amp/sig/sti/li. det keys: tau (delay after
# last pulse), len (gate), recv (receiver), fr, sti, wl/wr. Seeded from the
# matching experiments/*.phase_awg presets.
def _p(d, length, ph, fr=50, sw=350, amp=100, sig=0.0, sti=0.0, li=0.0, typ="SINE"):
    return {"d": d, "len": length, "ph": ph, "type": typ, "fr": fr, "sw": sw,
            "amp": amp, "sig": sig, "sti": sti, "li": li}


TEMPLATES = {
    "Hahn echo": {
        "pulses": [_p(0.0, 22.4, "(x)", sti=0.0), _p(288.0, 44.8, "x", sti=6.4)],
        "det": {"tau": 288.0, "len": 512.0, "wl": 0.0, "wr": 320.0, "fr": 50, "sti": 12.8, "recv": "-1,2"},
        "glob": {"rep": 500.0, "field": 3493.0, "sweep": "Linear Time"},
    },
    "3p-ESEEM": {
        "pulses": [_p(0.0, 16.0, "(x)", amp=60), _p(208.0, 16.0, "(x)", amp=30),
                   _p(64.0, 16.0, "x", amp=60, sti=12.8)],
        "det": {"tau": 208.0, "len": 512.0, "wl": 0.0, "wr": 320.0, "fr": 50, "sti": 12.8, "recv": "-1,1,-1"},
        "glob": {"rep": 1000.0, "field": 3324.0, "sweep": "Linear Time"},
    },
    "4p-DEER": {
        "pulses": [_p(0.0, 48.0, "(x)", fr=25, amp=15), _p(208.0, 48.0, "x", fr=25, amp=30),
                   _p(112.0, 22.4, "[x]", fr=100, amp=100, sti=3.2), _p(1616.0, 48.0, "x", fr=25, amp=30)],
        "det": {"tau": 1520.0, "len": 512.0, "wl": 0.0, "wr": 320.0, "fr": 25, "sti": 0.0, "recv": "1,-2,0,2"},
        "glob": {"rep": 1000.0, "field": 3324.0, "sweep": "Linear Time"},
    },
    "Inversion recovery": {
        "pulses": [_p(0.0, 32.0, "x", amp=60), _p(204.8, 32.0, "x", amp=30, sti=3.2),
                   _p(236.8, 32.0, "[x]", amp=60, sti=3.2)],
        "det": {"tau": 236.8, "len": 512.0, "wl": 0.0, "wr": 320.0, "fr": 50, "sti": 3.2, "recv": "0,-1,2"},
        "glob": {"rep": 480.0, "field": 3324.0, "sweep": "Log Time"},
    },
    "SIFTER": {
        "pulses": [_p(0.0, 48.0, "x", fr=25, amp=15), _p(208.0, 48.0, "[x]", fr=25, amp=30, sti=3.2),
                   _p(208.0, 48.0, "y", fr=25, amp=15, sti=6.4), _p(1520.0, 48.0, "[x]", fr=25, amp=30, sti=3.2)],
        "det": {"tau": 1520.0, "len": 512.0, "wl": 0.0, "wr": 320.0, "fr": 25, "sti": 0.0, "recv": "1,-2,2,-2"},
        "glob": {"rep": 1000.0, "field": 3324.0, "sweep": "Linear Time"},
    },
}

# Reload-signal file polled by a running awg_phasing_insys / phasing_insys
# window. We write "<channel>\n<preset path>\n<nonce>" here; when the nonce
# changes the matching open tool reloads the preset in place (no relaunch).
SEQCALC_SIGNAL = os.path.join(tempfile.gettempdir(), 'atomize_seqcalc.param')


def _with_horizontal(style):
    """gui_style.SCROLL_STYLE only themes the vertical bar; mirror it for the
    horizontal one so the main window's horizontal scrollbar is styled too."""
    horizontal = (style.replace('vertical', 'horizontal')
                       .replace('width: 10px', 'height: 10px')
                       .replace('min-height: 20px', 'min-width: 20px')
                       .replace('height: 0px', 'width: 0px'))
    return style + horizontal


# Themes both scrollbar orientations; used on the main scroll area and editors.
SCROLLS = _with_horizontal(SCROLL_STYLE)

ROW_H = 26          # fixed height for spinboxes / combos (matches AWG/RECT tools)
TAU_W = 86          # tau spinbox width
PH_W = 84           # phase box width
PH_H = 58           # phase box height (multiline)


class MainWindow(QMainWindow):
    """The calculator window."""

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        self.setWindowTitle("EPR Sequence & Phase-Cycling Calculator")
        self._click_seq = 0            # monotonic counter for reload-signal nonces
        self._building = True          # suppress recompute while wiring widgets

        # Hidden parameters (not part of the tau/phase view) used when writing
        # the preset. adv[i] -> P{i+2}; det/glob -> detection + acquisition.
        self.adv = [dict(ADV_DEFAULT) for _ in range(MAX_PULSES)]
        self.det_int = dict(DET_DEFAULT)
        self.glob = dict(GLOB_DEFAULT)

        self.build_ui()
        self._building = False
        self.combo_template.setCurrentText("Hahn echo")
        self.load_template()           # seed with Hahn and run first recompute

    # ----------------------------- helpers -------------------------------- #
    def r32(self, v):
        return round_to_closest(float(v), 3.2)

    def make_tau(self, value=0.0):
        sp = QDoubleSpinBox()
        sp.setRange(0.0, 1.0e6)
        sp.setDecimals(1)
        sp.setSingleStep(3.2)
        sp.setSuffix(" ns")
        sp.setValue(value)
        sp.setStyleSheet(DSPIN_STYLE)
        sp.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
        sp.setFixedSize(TAU_W, ROW_H)
        sp.valueChanged.connect(self.recompute)
        return sp

    def make_phase(self, text="+x", w=PH_W, h=PH_H):
        te = QTextEdit(text)
        te.setStyleSheet(f"QTextEdit {{ color: {ACCENT}; border: 1px solid {BORDER}; "
                         f"selection-background-color: {ACCENT}; selection-color: {BG}; }}"
                         + SCROLLS)
        te.setFixedSize(w, h)
        te.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        te.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        te.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        te.textChanged.connect(self.recompute)
        return te

    def _ptxt(self, widget):
        """Phase text from a multiline box: newlines become commas, trimmed."""
        t = widget.toPlainText().replace('\n', ',')
        t = re.sub(r',\s*,+', ',', t).strip().strip(',')
        return t

    def _label(self, text, w=None):
        lbl = QLabel(text)
        lbl.setStyleSheet(LABEL_STYLE)
        lbl.setFixedHeight(ROW_H)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if w:
            lbl.setFixedWidth(w)
        return lbl

    # ------------------------------- UI ----------------------------------- #
    def build_ui(self):
        central = QWidget()
        central.setStyleSheet(f"background-color: {BG};")
        outer = QVBoxLayout(central)

        # --- top controls: template + pulse count ---
        top = QHBoxLayout()
        top.addWidget(self._label("Template:", w=70))
        self.combo_template = QComboBox()
        self.combo_template.addItems(list(TEMPLATES.keys()) + ["Custom"])
        self.combo_template.setStyleSheet(COMBO_STYLE)
        self.combo_template.setFixedSize(160, ROW_H)
        top.addWidget(self.combo_template)
        btn_load = QPushButton("Load template")
        btn_load.setStyleSheet(BUTTON_STYLE)
        btn_load.setFixedSize(170, 40)
        btn_load.clicked.connect(self.load_template)
        top.addWidget(btn_load)

        top.addSpacing(20)
        top.addWidget(self._label("Pulses:", w=55))
        self.count = QSpinBox()
        self.count.setRange(1, MAX_PULSES)
        self.count.setValue(2)
        self.count.setStyleSheet(SPIN_STYLE)
        self.count.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
        self.count.setFixedSize(60, ROW_H)
        self.count.valueChanged.connect(self.on_count_changed)
        top.addWidget(self.count)
        top.addStretch(1)
        outer.addLayout(top)

        # --- sequence row: phase boxes interleaved with tau gaps, then DET ---
        # Pools of persistent widgets; rebuild_sequence() arranges the active
        # ones. There is no pulse-name label anywhere: a phase box IS a pulse,
        # a tau spinbox IS the gap to the next one.
        self.phase = [self.make_phase("+x") for _ in range(MAX_PULSES)]
        self.tau = [self.make_tau(0.0) for _ in range(MAX_PULSES - 1)]

        self.det_combo = QComboBox()
        self.det_combo.setStyleSheet(COMBO_STYLE)
        self.det_combo.setFixedSize(TAU_W, ROW_H)
        self.det_combo.currentIndexChanged.connect(self._on_det_combo)
        self.det_free = self.make_tau(288.0)
        # Detection τ chooser (combo) stacked on top of its free-value spinbox.
        self.det_stack = QWidget()
        _dv = QVBoxLayout(self.det_stack)
        _dv.setContentsMargins(0, 0, 0, 0)
        _dv.setSpacing(2)
        _dv.addWidget(self.det_combo)
        _dv.addWidget(self.det_free)
        self.det_recv = self.make_phase("-1,2", w=84)
        self.det_recv.setToolTip("Receiver: coefficients (e.g. -1,2) or explicit "
                                 "notation (e.g. +x,-x).")
        self._seq_labels = []          # transient header/separator widgets

        seq_box = QWidget()
        # Fixed-height pulse strip. Rows: free-above (0), header (1), boxes (2),
        # free-below (3). The free rows are sized so the BOX row sits at the
        # vertical centre of the strip — the full-height divider then lines up
        # with the boxes (the header label sits just above them).
        FREE_ABOVE, FREE_BELOW, HDR_H = 10, 30, 18
        seq_box.setFixedHeight(4 + FREE_ABOVE + HDR_H + PH_H + FREE_BELOW + 4)
        self.seq_grid = QGridLayout(seq_box)
        self.seq_grid.setHorizontalSpacing(4)
        self.seq_grid.setVerticalSpacing(0)
        self.seq_grid.setContentsMargins(6, 4, 6, 4)
        self.seq_grid.setColumnStretch(60, 1)   # keep columns left-packed
        self.seq_grid.setRowMinimumHeight(0, FREE_ABOVE)
        self.seq_grid.setRowMinimumHeight(3, FREE_BELOW)

        outer.addSpacing(14)
        seq_lbl = QLabel("Pulse sequence — phase boxes are pulses, τ the gaps, detection last")
        seq_lbl.setStyleSheet(f"color: {ACCENT}; font-weight: bold; font-size: 15px;")
        outer.addWidget(seq_lbl)
        outer.addWidget(seq_box)
        outer.addSpacing(10)

        # --- results panel ---
        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)
        self.results.setFont(QFont("Monospace", 10))
        # Match awg_phasing's main text window: no explicit border/background,
        # so the theme default frame/palette is used; just colour + scrollbars.
        self.results.setStyleSheet(
            f"QPlainTextEdit {{ color: {FG}; "
            f"selection-background-color: {ACCENT}; selection-color: {BG}; }}" + SCROLLS)
        self.results.setMinimumHeight(260)
        outer.addWidget(self.results)

        # --- action buttons (pinned below the scroll area, always visible) ---
        # The preset is intentionally incomplete here (no per-pulse length /
        # amplitude / acquisition settings), so we don't offer "save to file" —
        # you push it straight into the AWG/RECT tool and finish it there.
        btns_widget = QWidget()
        btns_widget.setStyleSheet(f"background-color: {BG};")
        btns = QHBoxLayout(btns_widget)
        btns.setContentsMargins(6, 6, 6, 6)
        for text, slot in [("Open in AWG", self.open_in_awg),
                           ("Open in RECT", self.open_in_rect)]:
            b = QPushButton(text)
            b.setStyleSheet(BUTTON_STYLE)
            b.setFixedSize(170, 40)
            b.clicked.connect(slot)
            btns.addWidget(b)
        btns.addStretch(1)

        # The content above scrolls both ways (vertically when the window is
        # short, horizontally when a long sequence runs past the right edge);
        # the action buttons sit outside the scroll area so they never vanish.
        main_scroll = QScrollArea()
        main_scroll.setWidget(central)
        main_scroll.setWidgetResizable(True)
        main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        main_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # Pure selector-based sheet (no leading bare property — that stops Qt
        # applying the QScrollBar rules); the QScrollArea rule keeps it transparent.
        main_scroll.setStyleSheet(SCROLLS)

        container = QWidget()
        container.setStyleSheet(f"background-color: {BG};")
        cvbox = QVBoxLayout(container)
        cvbox.setContentsMargins(0, 0, 0, 0)
        cvbox.setSpacing(0)
        cvbox.addWidget(main_scroll)        # takes all the stretch
        cvbox.addWidget(btns_widget)        # pinned at the bottom
        self.setCentralWidget(container)
        self.resize(1000, 640)
        self.rebuild_det_combo()
        self.rebuild_sequence()

    # --------------------------- behaviour -------------------------------- #
    def _seq_hdr(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {FG}; font-weight: bold;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setFixedHeight(18)
        self._seq_labels.append(lbl)
        return lbl

    def rebuild_det_combo(self):
        """Detection-tau chooser: '= τk' for each entered tau, plus 'free'."""
        n = self.count.value()
        prev = self.det_combo.currentText()
        self.det_combo.blockSignals(True)
        self.det_combo.clear()
        for k in range(max(0, n - 1)):
            self.det_combo.addItem(f"= τ{k + 1}")
        self.det_combo.addItem("free")
        # keep selection if still valid, else default to the last tau (or free)
        idx = self.det_combo.findText(prev)
        if idx < 0:
            idx = max(0, self.det_combo.count() - 2)   # last "= τk", else "free"
        self.det_combo.setCurrentIndex(idx)
        self.det_combo.blockSignals(False)
        self._sync_det_free()

    def rebuild_sequence(self):
        """Two-row grid: headers (P1, τ1, P2, …, DET) over the boxes.

        Columns left-to-right: P1 | τ1 | P2 | τ2 | … | Pn | sep | DET(chooser,
        free, receiver). A phase box IS a pulse; a τ spinbox IS the gap to it.
        """
        n = self.count.value()
        # detach persistent widgets and delete the previous transient labels
        for w in self.phase + self.tau + [self.det_stack, self.det_recv]:
            self.seq_grid.removeWidget(w)
            w.setParent(None)
            w.setVisible(False)
        for lbl in self._seq_labels:
            lbl.deleteLater()
        self._seq_labels = []

        # Header row is 1 and the box row is 2; rows 0 and 3 are equal stretch
        # spacers (set in build_ui) that vertically centre the block.
        HDR, BOX = 1, 2
        col = 0
        self.seq_grid.addWidget(self._seq_hdr("P1"), HDR, col)
        self.seq_grid.addWidget(self.phase[0], BOX, col)
        for i in range(n - 1):
            col += 1
            self.seq_grid.addWidget(self._seq_hdr(f"τ{i + 1}"), HDR, col)
            self.seq_grid.addWidget(self.tau[i], BOX, col, Qt.AlignmentFlag.AlignVCenter)
            col += 1
            self.seq_grid.addWidget(self._seq_hdr(f"P{i + 2}"), HDR, col)
            self.seq_grid.addWidget(self.phase[i + 1], BOX, col)

        col += 1
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {ACCENT};")
        # Fill the full pulse-strip height (the centred block plus both spacers).
        sep.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._seq_labels.append(sep)
        self.seq_grid.addWidget(sep, 0, col, 4, 1)

        dc = col + 1
        self.seq_grid.addWidget(self._seq_hdr("DET"), HDR, dc, 1, 2)
        self.seq_grid.addWidget(self.det_stack, BOX, dc, Qt.AlignmentFlag.AlignVCenter)
        self.seq_grid.addWidget(self.det_recv, BOX, dc + 1)

        for w in self.phase[:n] + self.tau[:max(0, n - 1)] + [self.det_stack, self.det_recv]:
            w.setVisible(True)
        self.recompute()

    def on_count_changed(self):
        self.rebuild_det_combo()
        self.rebuild_sequence()

    def _on_det_combo(self):
        self.recompute()

    def _sync_det_free(self):
        """If a τ is chosen for detection, mirror that τ's value into the free
        spinbox and lock it (read-only) so it always shows the actual detection
        τ; for 'free' it is editable."""
        n = self.count.value()
        ntau = max(0, n - 1)
        idx = self.det_combo.currentIndex()
        is_free = self.det_combo.currentText() == "free" or idx >= ntau
        self.det_free.setReadOnly(not is_free)
        if not is_free:
            self.det_free.blockSignals(True)
            self.det_free.setValue(self.tau[idx].value())
            self.det_free.blockSignals(False)

    def _det_tau(self):
        """Resolve the detection tau from the chooser (an entered tau or free)."""
        n = self.count.value()
        ntau = max(0, n - 1)
        idx = self.det_combo.currentIndex()
        if self.det_combo.currentText() == "free" or idx >= ntau:
            return self.det_free.value()
        return self.tau[idx].value()

    def compute_positions(self):
        """Cumulative-tau positions: pulse 0 at 0, each += its tau; det += det tau.

        Rounded with the same round_to_closest rule awg_phasing uses.
        """
        n = self.count.value()
        pos = [0.0]
        for i in range(n - 1):
            pos.append(self.r32(pos[-1] + self.tau[i].value()))
        det = self.r32(pos[-1] + self._det_tau())
        return pos, det

    def recompute(self):
        if self._building:
            return
        self._sync_det_free()      # keep the locked detection spinbox in sync
        n = self.count.value()
        pos, det = self.compute_positions()
        phases = [self._ptxt(self.phase[i]) or '+x' for i in range(n)]
        recv = self._ptxt(self.det_recv) or '+x'

        lines = ["Absolute positions (cumulative τ):", ""]
        for i in range(n):
            lines.append(f"  pulse {i + 1:>2}  @ {pos[i]:>9.1f} ns   phase = {phases[i]}")
        lines.append(f"  detection @ {det:>9.1f} ns   receiver = {recv}")
        lines.append("")

        lines.append("Timeline (ns):")
        marks = [f"p{i + 1}@{pos[i]:.1f}" for i in range(n)] + [f"DET@{det:.1f}"]
        lines.append("  " + "  ->  ".join(marks))
        lines.append("")

        try:
            res = expand_phase_cycling(recv, *phases)
            steps = len(res["receiver"])
            lines.append(f"Phase cycle: {steps} steps")
            header = "  step | " + " | ".join(f"p{i + 1}" for i in range(n)) + " | recv"
            lines.append(header)
            lines.append("  " + "-" * (len(header) - 2))
            for s in range(steps):
                cells = " | ".join(f"{res['pulses'][i][s]:>3}" for i in range(n))
                lines.append(f"  {s:>4} | {cells} | {res['receiver'][s]:>4}")
        except Exception as e:
            lines.append(f"Phase cycle: could not expand ({e})")

        self.results.setPlainText("\n".join(lines))

    # --------------------------- templates -------------------------------- #
    def load_template(self):
        name = self.combo_template.currentText()
        if name == "Custom" or name not in TEMPLATES:
            self.recompute()
            return
        tpl = TEMPLATES[name]
        self._building = True
        pulses = tpl["pulses"]
        n = len(pulses)
        self.count.setValue(n)
        for i, p in enumerate(pulses):
            self.phase[i].setPlainText(p["ph"])
            self.adv[i] = {"len": p["len"], "type": p["type"], "fr": p["fr"], "sw": p["sw"],
                           "amp": p["amp"], "sig": p["sig"], "sti": p["sti"], "li": p["li"]}
            if i >= 1:
                self.tau[i - 1].setValue(p["d"])   # tau before pulse i+1
        for i in range(n, MAX_PULSES):
            self.adv[i] = dict(ADV_DEFAULT)
        d = tpl["det"]
        self.det_recv.setPlainText(d["recv"])
        self.det_int = {"len": d["len"], "fr": d["fr"], "sti": d["sti"], "wl": d["wl"], "wr": d["wr"]}
        self.glob = dict(tpl["glob"])

        # Point the detection chooser at a matching tau if one exists, else free.
        self.rebuild_det_combo()
        match = -1
        for k in range(n - 1):
            if self.r32(self.tau[k].value()) == self.r32(d["tau"]):
                match = k
                break
        self.det_combo.blockSignals(True)
        if match >= 0:
            self.det_combo.setCurrentIndex(match)
        else:
            self.det_combo.setCurrentIndex(self.det_combo.count() - 1)   # free
            self.det_free.setValue(d["tau"])
        self.det_combo.blockSignals(False)

        self._building = False
        self.rebuild_sequence()

    # --------------------------- formatting ------------------------------- #
    def _fl(self, v):
        return str(self.r32(v))

    def _it(self, v):
        return str(int(round(float(v))))

    def _pulse_awg(self, typ, st, ln, sig, fr, sw, cf, ph, sti, li):
        return (f"{typ},  {self._fl(st)},  {self._fl(ln)},  {self._fl(sig)},  "
                f"{self._it(fr)},  {self._it(sw)},  {self._it(cf)},  [{ph}],  "
                f"{self._fl(sti)},  {self._fl(li)},  0.0")

    def _pulse_rect(self, typ, st, ln, ph, sti, li):
        return (f"{typ},  {self._fl(st)},  {self._fl(ln)},  [{ph}],  "
                f"{self._fl(sti)},  {self._fl(li)}")

    def _pulse_block(self, mode):
        """Build the nine P1..P9 lines for the given mode ('awg' or 'rect')."""
        n = self.count.value()
        pos, det = self.compute_positions()
        recv = self._ptxt(self.det_recv) or '+x'
        di = self.det_int
        out = []
        if mode == 'awg':
            out.append("P1:  " + self._pulse_awg('DETECTION', det, di["len"],
                       0.0, di["fr"], 350, 100, recv, di["sti"], 0.0))
        else:
            out.append("P1:  " + self._pulse_rect('DETECTION', det, di["len"],
                       recv, di["sti"], 0.0))
        for c in range(MAX_PULSES):
            pno = c + 2
            if c < n:
                ph = self._ptxt(self.phase[c]) or '+x'
                a = self.adv[c]
                if mode == 'awg':
                    out.append(f"P{pno}:  " + self._pulse_awg(a["type"], pos[c],
                               a["len"], a["sig"], a["fr"], a["sw"], a["amp"],
                               ph, a["sti"], a["li"]))
                else:
                    out.append(f"P{pno}:  " + self._pulse_rect('MW', pos[c],
                               a["len"], ph, a["sti"], a["li"]))
            else:
                if mode == 'awg':
                    out.append(f"P{pno}:  " + self._pulse_awg('SINE', 0.0, 0.0, 0.0, 50, 350, 100, '+x,+x', 0.0, 0.0))
                else:
                    out.append(f"P{pno}:  " + self._pulse_rect('MW', 0.0, 0.0, '+x,+x', 0.0, 0.0))
        return out

    def build_awg_lines(self):
        di, g = self.det_int, self.glob
        lines = self._pulse_block('awg')
        lines += [
            f"Rep rate:  {g['rep']}",
            f"Field:  {g['field']}",
            "Delay:  0",
            "Ampl 1:  260",
            "Ampl 2:  260",
            "Phase:  90.0",
            "N WURST; SECH/TANH:  10",
            "B SECH/TANH:  0.02",
            "Points:  2016",
            "Horizontal offset:  1024",
            f"Window left:  {self._fl(di['wl'])}",
            f"Window right:  {self._fl(di['wr'])}",
            "Acquisitions:  1",
            "Points to Drop:  0",
            "Zero order:  0.0",
            "First order:  0.0",
            "Second order:  0.0",
            "Laser:  Nd:YaG",
            "Decimation:  1",
            "Points:  500",
            "Scans:  1",
            "Log Start:  1.0",
            "Log End:  7.0",
            "Start Field:  3000.0",
            "End Field:  4000.0",
            "Field Step:  0.5",
            f"Sweep Type:  {g['sweep']}",
            "IQ Correction:  2",
            "X0:  0.0",
            "dX:  0.0",
            "Amplitude Step:  1.0",
            "Cycles:  8",
            "Save Each Cycle:  0",
        ]
        return lines

    def build_rect_lines(self):
        di, g = self.det_int, self.glob
        lines = self._pulse_block('rect')
        lines += [
            f"Rep rate:  {g['rep']}",
            f"Field:  {g['field']}",
            "Points:  2016",
            "Horizontal offset:  1024",
            f"Window left:  {self._fl(di['wl'])}",
            f"Window right:  {self._fl(di['wr'])}",
            "Acquisitions:  1",
            "Points to Drop:  0",
            "Zero order:  0.0",
            "First order:  0.0",
            "Second order:  0.0",
            "Laser:  Nd:YaG",
            "Decimation:  1",
            "Points:  500",
            "Scans:  1",
            "Log Start:  1.0",
            "Log End:  7.0",
            "Start Field:  3000.0",
            "End Field:  4000.0",
            "Field Step:  0.5",
            f"Sweep Type:  {g['sweep']}",
            "X0:  0.0",
            "dX:  0.0",
        ]
        return lines

    def _write(self, path, mode):
        lines = self.build_awg_lines() if mode == 'awg' else self.build_rect_lines()
        with open(path, 'w') as f:
            f.write("\n".join(lines) + "\n")

    # ----------------------------- actions -------------------------------- #
    def _signal_reload(self, channel, preset_path):
        """Write the reload-signal file so an already-open tool picks it up."""
        self._click_seq += 1
        nonce = f"{time.time():.6f}-{self._click_seq}"
        try:
            with open(SEQCALC_SIGNAL, 'w') as f:
                f.write(f"{channel}\n{preset_path}\n{nonce}\n")
        except OSError:
            pass

    def open_in_awg(self):
        path = os.path.join(tempfile.gettempdir(), '_seqcalc_tmp.phase_awg')
        self._write(path, 'awg')
        self._signal_reload('awg', path)            # update an already-open window
        print(f"open_awg {path}", flush=True)       # or launch one if none is open

    def open_in_rect(self):
        path = os.path.join(tempfile.gettempdir(), '_seqcalc_tmp.phase')
        self._write(path, 'rect')
        self._signal_reload('rect', path)
        print(f"open_rect {path}", flush=True)


def _self_test():
    """Headless sanity check used by `python sequence_calculator.py test`."""
    def positions(taus, det):
        pos = [0.0]
        for t in taus:
            pos.append(round_to_closest(pos[-1] + t, 3.2))
        return pos + [round_to_closest(pos[-1] + det, 3.2)]

    # Grid-aligned taus (multiples of 3.2) give exact cumulative positions...
    assert positions([288], 288) == [0.0, 288.0, 576.0]               # Hahn echo
    assert positions([208, 64], 208) == [0.0, 208.0, 272.0, 480.0]    # 3p-ESEEM
    # ...off-grid taus snap up to the 3.2 grid exactly as awg_phasing does.
    assert positions([200], 200) == [0.0, 201.6, 403.2], positions([200], 200)

    # Phase-cycle expansion + auto receiver for Hahn ([-1,2], (x), x).
    res = expand_phase_cycling('-1,2', '(x)', 'x')
    assert res["pulses"] == [['+x', '-x'], ['+x', '+x']], res["pulses"]
    assert res["receiver"] == ['+x', '-x'], res["receiver"]

    print("print SELF-TEST PASSED: cumulative-tau grid + phase expansion OK")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        _self_test()
        return
    app = QApplication(sys.argv)
    apply_app_style(app, app_id='Atomize.ITC.SeqCalc')
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
