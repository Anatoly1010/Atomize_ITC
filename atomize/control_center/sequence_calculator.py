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

It also analyses the **coherence transfer pathways**: every pathway (electron
coherence order -1/0/+1 per delay, detection -1) is enumerated and tested
against the actual phase cycle, so you see which pathways are *kept* and which
are *phased out*, where each surviving echo lands, and whether any artefact echo
overlaps the detection window. The surviving pathways are drawn as a coherence-
order-vs-time diagram (desired bright, artefacts faint). FIDs are tracked too: an
FID is the pathway that becomes observable at a pulse and is not refocused, so it
shows up as a pathway whose echo sits on that pulse (e.g. the Hahn pi-pulse FID,
which a 2-step cycle removes). Method follows Stoll & Kasumaj, Appl. Magn. Reson.
35, 15 (2008) and the DEER artefact analysis of Spindler/Prisner et al., Phys.
Chem. Chem. Phys. 18, 17223 (2016).

Caveat: this is a selection-rule / bookkeeping tool. It lists which pathways the
phase cycle lets through, NOT their amplitudes. Phase-cycle selection depends
only on the coherence-order change dp, so it is exact for real pulses; but
whether a surviving pathway is actually excited, and how strongly, depends on
pulse flip angle / bandwidth / resonator / offset and is NOT modelled here.
Relaxation and nuclear coherences (ESEEM/HYSCORE modulation amplitudes) are out
of scope; electron coherence orders are restricted to -1/0/+1 (S = 1/2).

Pulse length / amplitude / frequency / increments are usually the same across a
sequence, so they are kept out of the way: templates carry faithful values for
them internally and the preset writer uses those; custom pulses fall back to
defaults. Tweak them afterwards in the AWG/RECT tool if needed.

One-click "Open in AWG / RECT": writes the preset and (a) if that tool's window
is already open, it pushes in place via a temp signal file polled by the tool —
the tool applies ONLY the pulse layout (positions, phases, pulse count), leaving
every tuned acquisition parameter (field, rep rate, detection window, scans,
sweep type, amplitudes, ...) untouched; (b) if it is closed, prints an
``open_awg``/``open_rect`` sentinel that the main window turns into a launch
(which loads the preset in full as a fresh starting point). No hardware here.
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
from PyQt6.QtGui import QFont, QPainter, QColor, QPen
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


# Electron-spin coherence orders during a delay (S = 1/2: no multiple quantum).
COH_ORDERS = (-1, 0, 1)
COH_SYM = {-1: '-', 0: '0', 1: '+'}


def analyze_pathways(recv, pulse_phase_strs, positions, det_pos):
    """Enumerate every coherence transfer pathway and decide which the phase
    cycle keeps (Stoll & Kasumaj, Appl. Magn. Reson. 35, 15 (2008); Prisner et
    al. PCCP 18, 17223 (2016) for the DEER artefact analysis).

    A pathway is the list of electron coherence orders p during each delay,
    starting from equilibrium (p = 0) and ending at the detected order -1, so an
    n-pulse sequence has 3**(n-1) pathways. We reuse the project's own
    ``expand_phase_cycling`` to get each pulse's phase and the receiver phase at
    every cycle step, then keep a pathway iff its acquired phase
    ``-sum(dp_i * phi_i)`` tracks the receiver across *all* steps (otherwise the
    steps co-add to zero and it is suppressed). The desired pathway always
    survives by construction; anything else that survives is an artefact the
    cycle fails to remove.

    For each surviving pathway we also place its echo: an isochromat refocuses
    when ``sum_k p_k * dt_k`` over the whole sequence vanishes, i.e. at
    ``t_last_pulse + sum_k p_k * tau_k`` (tau_k = on-grid delay k). Artefact
    echoes landing on the detection position overlap the real signal.

    An FID is just the pathway that becomes observable at one pulse and is not
    refocused afterwards: ``p = 0`` until pulse j, then -1 to the end. Its echo
    time equals pulse j's position (it peaks at the pulse and decays), so any
    surviving pathway whose echo sits on a pulse is flagged ``FID from Pj``. We
    also report, for every pulse, whether its FID is kept or phased out (e.g. the
    Hahn 2-step cycle removes the pi-pulse FID).

    Returns a dict: ``{total, steps, det_pos, survivors:[{p, dp, echo, desired,
    fid, role}], suppressed, fids:[{pulse, echo, survives}]}`` where ``p`` is
    p[1..n] (the per-delay orders, detection last).
    """
    import itertools
    phase_list = ['+x', '+y', '-x', '-y']
    pidx = {s: i for i, s in enumerate(phase_list)}
    n = len(pulse_phase_strs)
    res = expand_phase_cycling(recv, *pulse_phase_strs)
    steps = len(res["receiver"])
    pulse_ix = [[pidx[res["pulses"][i][s]] for s in range(steps)] for i in range(n)]
    rec_ix = [pidx[res["receiver"][s]] for s in range(steps)]

    def survives(p):
        dp = [p[i + 1] - p[i] for i in range(n)]
        offs = {(-sum(dp[i] * pulse_ix[i][s] for i in range(n)) - rec_ix[s]) % 4
                for s in range(steps)}
        return len(offs) == 1

    def echo_of(p):
        return positions[-1] + sum(p[k] * (positions[k] - positions[k - 1])
                                   for k in range(1, n))

    def fid_pulse(echo):                     # echo sitting on a pulse -> that FID
        for k in range(n):
            if abs(echo - positions[k]) <= 1.6:
                return k + 1
        return None

    survivors = []
    suppressed = 0
    for mids in itertools.product(COH_ORDERS, repeat=max(0, n - 1)):
        p = [0] + list(mids) + [-1]          # p[0]=equilibrium ... p[n]=detection
        if not survives(p):
            suppressed += 1
            continue
        echo = echo_of(p)
        desired = abs(echo - det_pos) <= 1.6
        fid = fid_pulse(echo)
        if desired:
            role = "DETECTED (echo on window)"
        elif fid is not None:
            role = f"FID from P{fid}"
        else:
            role = f"artefact echo ({echo - det_pos:+.1f} off window)"
        survivors.append({"p": p[1:], "dp": [p[i + 1] - p[i] for i in range(n)],
                          "echo": echo, "desired": desired, "fid": fid, "role": role})
    survivors.sort(key=lambda s: (not s["desired"], s["echo"]))

    # FID bookkeeping for every pulse, kept or removed by the cycle
    fids = []
    for j in range(1, n + 1):
        p = [0] + [0] * (j - 1) + [-1] * (n - j) + [-1]
        fids.append({"pulse": j, "echo": positions[j - 1], "survives": survives(p)})

    return {"total": 3 ** max(0, n - 1), "steps": steps, "det_pos": det_pos,
            "survivors": survivors, "suppressed": suppressed, "fids": fids}


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


def _qc(css):
    """gui_style colours are CSS strings ('rgb(r, g, b)') for stylesheets;
    QPainter needs a real QColor, so parse them here ('#rgb'/names pass through)."""
    nums = re.findall(r'\d+', css)
    if css.strip().lower().startswith('rgb') and len(nums) >= 3:
        return QColor(int(nums[0]), int(nums[1]), int(nums[2]))
    return QColor(css)


class CoherenceDiagram(QWidget):
    """Coherence-order vs time plot of the surviving coherence transfer pathways.

    y axis = electron coherence order (+1 / 0 / -1); x axis = the real sequence
    timeline (pulses as dashed verticals at their absolute positions, detection
    as a filled dot at p = -1). Each surviving pathway is drawn as a step line;
    the desired one(s) — whose echo lands on the detection position — are bright
    (ACCENT), unsuppressed artefacts are translucent. Suppressed pathways are not
    drawn (there can be many); the text report below counts them.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFixedHeight(160)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._paths, self._pos, self._det, self._n = [], [], 0.0, 0

    def set_data(self, survivors, positions, det_pos, n):
        self._paths = survivors
        self._pos = list(positions)
        self._det = float(det_pos)
        self._n = int(n)
        self.update()

    def paintEvent(self, _evt):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        c_bg, c_fg, c_accent, c_border = _qc(BG), _qc(FG), _qc(ACCENT), _qc(BORDER)
        qp.fillRect(0, 0, W, H, c_bg)
        L, R, T, B = 38, 16, 22, 26          # margins (left has room for y labels)
        if self._n < 1 or not self._pos:
            return
        xmax = max(self._det, self._pos[-1], 1.0)
        pw, ph = W - L - R, H - T - B

        def X(t):
            return L + (t / xmax) * pw

        def Y(p):
            return T + ((1 - p) / 2.0) * ph   # +1 -> top, 0 -> middle, -1 -> bottom

        # coherence-level gridlines + labels
        qp.setFont(QFont("Monospace", 8))
        for p in (1, 0, -1):
            y = int(Y(p))
            qp.setPen(QPen(c_border, 1, Qt.PenStyle.DotLine))
            qp.drawLine(L, y, W - R, y)
            qp.setPen(QPen(c_fg))
            qp.drawText(4, y + 4, f"{p:+d}" if p else " 0")

        # pulse verticals + labels, and the detection marker
        for i in range(self._n):
            x = int(X(self._pos[i]))
            qp.setPen(QPen(c_fg, 1, Qt.PenStyle.DashLine))
            qp.drawLine(x, T, x, T + ph)
            qp.setPen(QPen(c_fg))
            qp.drawText(x - 8, T - 6, f"P{i + 1}")
        xd = int(X(self._det))
        qp.setPen(QPen(c_accent, 1, Qt.PenStyle.DashLine))
        qp.drawLine(xd, T, xd, T + ph)
        qp.setPen(QPen(c_accent))
        qp.drawText(xd - 10, T - 6, "DET")

        # pathways: artefacts first (translucent), desired on top (bright).
        # A small per-pathway vertical jitter keeps overlapping levels legible.
        artefact = QColor(c_fg); artefact.setAlpha(135)
        ordered = sorted(self._paths, key=lambda s: s["desired"])
        arts = [s for s in ordered if not s["desired"]]
        for path in ordered:
            p = path["p"]                     # p[1..n], detection (-1) last
            # nudge each artefact a few px off its level so co-running pathways
            # at the same coherence order don't collapse onto one line
            j = 0.0 if path["desired"] else (arts.index(path) - (len(arts) - 1) / 2.0) * 3.0
            yj = lambda v: Y(v) + j
            pts = [(X(self._pos[0]), yj(0))]  # equilibrium at the first pulse
            for k in range(1, self._n):       # delay k between pulse k and k+1
                pts.append((X(self._pos[k - 1]), yj(p[k - 1])))
                pts.append((X(self._pos[k]), yj(p[k - 1])))
            pts.append((X(self._pos[self._n - 1]), yj(-1)))  # jump at last pulse
            pts.append((X(self._det), yj(-1)))               # to detection
            if path["desired"]:
                qp.setPen(QPen(c_accent, 2.4))
            else:
                qp.setPen(QPen(artefact, 1.4))
            for a, b in zip(pts[:-1], pts[1:]):
                qp.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))

        qp.setBrush(c_accent)
        qp.setPen(QPen(c_accent))
        qp.drawEllipse(xd - 4, int(Y(-1)) - 4, 8, 8)
        qp.end()


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

    def make_tau_stack(self, i):
        """A τ cell mirroring the detection style: a link chooser stacked over
        the free-value spinbox. τ{i+1} may link to any earlier τ (= τ1…= τi) or
        be 'free'. τ1 (i == 0) is always free, so its chooser is disabled."""
        combo = QComboBox()
        combo.setStyleSheet(COMBO_STYLE)
        combo.setFixedSize(TAU_W, ROW_H)
        for j in range(i):
            combo.addItem(f"= τ{j + 1}")
        combo.addItem("free")
        combo.setCurrentText("free")
        if i == 0:
            combo.setEnabled(False)
        combo.currentIndexChanged.connect(self._on_tau_combo)
        sp = self.make_tau(0.0)
        stack = QWidget()
        v = QVBoxLayout(stack)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        v.addWidget(combo)
        v.addWidget(sp)
        return combo, sp, stack

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

    def _hsep(self):
        """Horizontal divider between sections (same style as the pulse-profile
        plot/controls separator)."""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setStyleSheet(f'color: {BORDER};')
        return line

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
        # Each gap τ{i+1} is a stack: a link chooser over a free spinbox. A
        # linked τ mirrors (and locks to) the τ it points at; τ1 is always free.
        self.tau, self.tau_combo, self.tau_stack = [], [], []
        for i in range(MAX_PULSES - 1):
            combo, sp, stack = self.make_tau_stack(i)
            self.tau_combo.append(combo)
            self.tau.append(sp)
            self.tau_stack.append(stack)

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

        seq_box = self.seq_box = QWidget()
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

        outer.addSpacing(8)
        outer.addWidget(self._hsep())          # presets | pulses
        outer.addSpacing(8)
        seq_lbl = QLabel("Pulse sequence — phase boxes are pulses, τ the gaps, detection last")
        seq_lbl.setStyleSheet(f"color: {ACCENT}; font-weight: bold; font-size: 15px;")
        outer.addWidget(seq_lbl)
        outer.addWidget(seq_box)
        outer.addSpacing(8)
        outer.addWidget(self._hsep())          # pulses | coherence pathways
        outer.addSpacing(8)

        # --- coherence transfer pathway diagram ---
        coh_lbl = QLabel("Coherence transfer pathways — bright = detected, faint = "
                         "surviving artefact")
        coh_lbl.setStyleSheet(f"color: {ACCENT}; font-weight: bold; font-size: 15px;")
        outer.addWidget(coh_lbl)
        self.coh_diagram = CoherenceDiagram()
        # Left-aligned so its width can be pinned to the pulse-strip content width.
        outer.addWidget(self.coh_diagram, alignment=Qt.AlignmentFlag.AlignLeft)
        outer.addSpacing(8)
        outer.addWidget(self._hsep())          # coherence pathways | main text
        outer.addSpacing(8)

        # --- results panel ---
        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)
        self.results.setFont(QFont("Monospace", 10))
        # Match awg_phasing's main text window: no explicit border/background,
        # so the theme default frame/palette is used; just colour + scrollbars.
        self.results.setStyleSheet(
            f"QPlainTextEdit {{ color: {FG}; "
            f"selection-background-color: {ACCENT}; selection-color: {BG}; }}" + SCROLLS)
        self.results.setMinimumHeight(160)
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

        # The content area scrolls horizontally when a long sequence runs past
        # the right edge; vertically it does NOT scroll — the results panel below
        # is the single vertical scroller, so we never show two stacked vertical
        # bars. The action buttons sit outside the scroll area so they never vanish.
        main_scroll = QScrollArea()
        main_scroll.setWidget(central)
        main_scroll.setWidgetResizable(True)
        main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        main_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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
        self.setMinimumHeight(680)
        self.resize(1000, 700)
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
        for w in self.phase + self.tau_stack + [self.det_stack, self.det_recv]:
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
            self.seq_grid.addWidget(self.tau_stack[i], BOX, col, Qt.AlignmentFlag.AlignVCenter)
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

        for w in self.phase[:n] + self.tau_stack[:max(0, n - 1)] + [self.det_stack, self.det_recv]:
            w.setVisible(True)
        self._sync_diagram_width()
        self.recompute()

    def _sync_diagram_width(self):
        """Pin the coherence diagram to the same content width as the pulse
        strip, so the two line up and it doesn't stretch across the window."""
        if hasattr(self, 'coh_diagram') and hasattr(self, 'seq_box'):
            self.coh_diagram.setFixedWidth(max(self.seq_box.sizeHint().width(), 360))

    def on_count_changed(self):
        self.rebuild_det_combo()
        self.rebuild_sequence()

    def _on_det_combo(self):
        self.recompute()

    def _on_tau_combo(self):
        self.recompute()

    def _linked_target(self, i):
        """Gap index that τ{i+1} links to, or None when it is free."""
        if i == 0:
            return None
        txt = self.tau_combo[i].currentText()
        if txt == "free":
            return None
        return int(txt.split('τ')[1]) - 1        # "= τk" -> gap index k-1

    def _tau_value(self, i):
        """Effective value of gap i, following links back to a free τ.

        Links only point to earlier gaps (j < i), so this always terminates.
        """
        j = self._linked_target(i)
        if j is None:
            return self.tau[i].value()
        return self._tau_value(j)

    def _sync_tau_free(self):
        """Lock and mirror each linked τ's spinbox to the τ it points at, so it
        always shows the value actually used; free τ stay editable."""
        for i in range(MAX_PULSES - 1):
            linked = self._linked_target(i) is not None
            self.tau[i].setReadOnly(linked)
            if linked:
                self.tau[i].blockSignals(True)
                self.tau[i].setValue(self._tau_value(i))
                self.tau[i].blockSignals(False)

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
            self.det_free.setValue(self._tau_value(idx))
            self.det_free.blockSignals(False)

    def _det_tau(self):
        """Resolve the detection tau from the chooser (an entered tau or free)."""
        n = self.count.value()
        ntau = max(0, n - 1)
        idx = self.det_combo.currentIndex()
        if self.det_combo.currentText() == "free" or idx >= ntau:
            return self.det_free.value()
        return self._tau_value(idx)

    def compute_positions(self):
        """Cumulative-tau positions: pulse 0 at 0, each += its tau; det += det tau.

        Rounded with the same round_to_closest rule awg_phasing uses.
        """
        n = self.count.value()
        pos = [0.0]
        for i in range(n - 1):
            pos.append(self.r32(pos[-1] + self._tau_value(i)))
        det = self.r32(pos[-1] + self._det_tau())
        return pos, det

    def recompute(self):
        if self._building:
            return
        self._sync_tau_free()      # keep linked τ spinboxes mirrored + locked
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

        # --- coherence transfer pathways: what the cycle keeps / phases out ---
        try:
            an = analyze_pathways(recv, phases, pos, det)
            self.coh_diagram.set_data(an["survivors"], pos, det, n)
            kept = len(an["survivors"])
            lines.append("")
            lines.append(f"Coherence transfer pathways  (electron p in -1,0,+1; "
                         f"detection -1)")
            lines.append(f"  {an['total']} pathways, {an['steps']}-step cycle  ->  "
                         f"{kept} survive, {an['suppressed']} phased out")
            lines.append(f"  pathway (per delay, detection last) | echo @ ns | role")
            lines.append("  " + "-" * 52)
            for s in an["survivors"]:
                notation = "".join(COH_SYM[x] for x in s["p"])
                lines.append(f"  {notation:<12} | {s['echo']:>8.1f} | {s['role']}")
            lines.append("")
            lines.append("  FIDs (decay from each pulse; ideally only the echo is kept):")
            for f in an["fids"]:
                state = "kept" if f["survives"] else "phased out"
                lines.append(f"    P{f['pulse']} FID @ {f['echo']:>8.1f} ns  ->  {state}")
            lines.append("")
            lines.append("  Note: lists the pathways the phase cycle lets through, not their")
            lines.append("  amplitudes. Whether each is actually excited (and how strongly)")
            lines.append("  depends on pulse flip angle / bandwidth / offset, which is NOT")
            lines.append("  modelled here; no relaxation; electron coherence only (S = 1/2).")
        except Exception as e:
            self.coh_diagram.set_data([], pos, det, n)
            lines.append(f"\nCoherence pathways: could not analyze ({e})")

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
        for c in self.tau_combo:          # templates are explicit: clear links
            c.setCurrentText("free")
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

    # Coherence transfer pathways. Hahn: 3 pathways, 2 survive the 2-step cycle,
    # only 0->+1->-1 refocuses on the detection window (the other lands at t=0).
    h = analyze_pathways('-1,2', ['(x)', 'x'], [0.0, 288.0], 576.0)
    assert h["total"] == 3 and len(h["survivors"]) == 2, h
    des = [s for s in h["survivors"] if s["desired"]]
    assert len(des) == 1 and des[0]["p"] == [1, -1] and des[0]["echo"] == 576.0, des

    # 4p-DEER: 27 pathways, 6 survive the 8-step cycle, desired echo "-++-" on the
    # window; the other five are the artefact echoes the DEER paper discusses.
    d = analyze_pathways('1,-2,0,2', ['(x)', 'x', '[x]', 'x'],
                         [0.0, 208.0, 320.0, 1936.0], 3456.0)
    assert d["total"] == 27 and len(d["survivors"]) == 6, d
    des = [s for s in d["survivors"] if s["desired"]]
    assert len(des) == 1 and des[0]["p"] == [-1, 1, 1, -1], des

    print("print SELF-TEST PASSED: cumulative-tau grid + phase expansion + pathways OK")


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
