# -*- coding: utf-8 -*-
"""
TimeLogSpinBox — composite QWidget that lets the user enter a time value
with a unit (ns / μs / ms / s) while exposing the value as log10(time_in_ns).

awg_phasing_insys.py uses the log10(ns) form to parametrise the Log Time
sweep worker. This widget keeps that internal contract unchanged while
making the UI human-readable.

All values are snapped to the current unit's grid — the smallest
2-decimal-visible value that is also a multiple of the Insys FPGA pulser
resolution (3.2 ns). With this scheme the displayed value, read at face
value, is always a literal 3.2 ns multiple in any unit, with no display
round-off "lie". Per-unit grids:

    Unit | grid in unit | grid in ns | ticks
    -----+--------------+------------+--------
    ns   |   3.20       |     3.2    |       1
    μs   |   0.08       |    80      |      25
    ms   |   0.01       | 10000      |    3125
    s    |   0.01       |   1e7      |  3125000

Drop this file at atomize/control_center/time_log_spinbox.py when integrating.
"""

import math

from PyQt6.QtWidgets import QWidget, QDoubleSpinBox, QComboBox, QHBoxLayout
from PyQt6.QtCore import pyqtSignal, Qt


_UNIT_FACTOR = {'ns': 1.0, 'μs': 1e3, 'ms': 1e6, 's': 1e9}
# Per-unit spinbox maximum corresponding to the upper bound of the
# log range (10 s). Sized so any unit-switch can re-display the same
# log10(ns) value without clamping.
_UNIT_MAX = {'ns': 1e10, 'μs': 1e7, 'ms': 1e4, 's': 10.0}
# Per-unit display + arrow-button step: the smallest 2-decimal value
# that is also a 3.2 ns multiple. This is also the grid we snap typed
# / programmatic values onto.
_UNIT_STEP = {'ns': 3.2, 'μs': 0.08, 'ms': 0.01, 's': 0.01}
_UNITS = ('ns', 'μs', 'ms', 's')

_DECIMALS = 2

# Insys FPGA pulser/digitizer time resolution (ns). Kept for reference;
# every entry in _UNIT_STEP is an integer multiple of this.
_SNAP_NS = 3.2


def _snap_to_grid(ns, unit):
    """Snap a time value (in ns) onto the unit's grid (smallest
    2-decimal-visible 3.2 ns multiple). Floor at one grid step."""
    grid = _UNIT_STEP[unit] * _UNIT_FACTOR[unit]
    if ns <= grid:
        return grid
    return round(ns / grid) * grid


class TimeLogSpinBox(QWidget):
    """
    Composite widget: QDoubleSpinBox + QComboBox(ns/μs/ms/s).

    The snapped time in ns (`_ns_value`) is the source of truth. It is
    always:
      * a multiple of 3.2 ns (Insys FPGA pulser resolution), AND
      * a multiple of the current unit's grid step (so the 2-decimal
        display renders the value exactly with no rounding lie).

    Public API mirrors the parts of QDoubleSpinBox that
    awg_phasing_insys.py uses:
        value()          -> float  log10(time_in_ns)
        setValue(log_ns) -> None   accepts log10(time_in_ns); picks the
                                   largest unit with display >= 1 and
                                   snaps to that unit's grid
        valueChanged     -> Signal(float)  emitted when the stored value
                                           actually changes (typed value,
                                           external setValue, or unit
                                           switch that re-snaps to a
                                           coarser grid).

    Behaviour notes:
    - Every input (typed or programmatic) is snapped to the current
      unit's grid step. The grid in each unit is itself a 3.2 ns
      multiple, so all stored values are 3.2 ns multiples.
    - Switching to a COARSER unit (e.g. ns → ms) re-snaps the stored
      value onto the coarser grid, which loses precision. Switching to
      a finer unit is lossless (the finer grid is a refinement of the
      coarser one).
    - setKeyboardTracking(False): valueChanged fires on Enter /
      focus-out / arrow buttons.
    """

    valueChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Source of truth: snapped time in ns. Initialised at one ns
        # grid step (= 3.2 ns) so an uninitialised widget reads as a
        # legal value.
        self._ns_value = _UNIT_STEP['ns'] * _UNIT_FACTOR['ns']

        self._spin = QDoubleSpinBox()
        self._spin.setMinimum(0.0)
        self._spin.setMaximum(_UNIT_MAX['ns'])
        self._spin.setDecimals(_DECIMALS)
        self._spin.setSingleStep(_UNIT_STEP['ns'])
        self._spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
        self._spin.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self._spin.setKeyboardTracking(False)
        self._spin.setFixedHeight(26)
        self._spin.setStyleSheet(
            "QDoubleSpinBox { color: rgb(193, 202, 227); "
            "selection-background-color: rgb(211, 194, 78); "
            "selection-color: rgb(63, 63, 97); }"
        )

        self._unit = QComboBox()
        self._unit.addItems(_UNITS)
        self._unit.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self._unit.setFixedHeight(26)
        self._unit.setFixedWidth(48)
        self._unit.setStyleSheet(
            "QComboBox { color: rgb(193, 202, 227); "
            "selection-background-color: rgb(63, 63, 97); "
            "selection-color: rgb(211, 194, 78); }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._spin, 1)
        layout.addWidget(self._unit, 0)

        self._silent = False
        self._prev_unit = self._unit.currentText()

        self._spin.valueChanged.connect(self._on_spin_changed)
        self._unit.currentIndexChanged.connect(self._on_unit_changed)

    # ----- Public API -----

    def value(self):
        """Return log10(time_in_ns), rounded to 3 decimals."""
        return round(math.log10(self._ns_value), 3)

    def setValue(self, log_ns):
        """
        Set the widget to log10(time_in_ns). Picks the largest unit
        with a display value >= 1 and snaps the stored time to that
        unit's grid. Emits valueChanged once after the inner widgets
        settle.
        """
        ns_raw = 10.0 ** float(log_ns)
        new_unit = self._pick_unit(ns_raw)
        self._ns_value = _snap_to_grid(ns_raw, new_unit)
        self._refresh_display(new_unit)
        self.valueChanged.emit(self.value())

    # ----- Internal -----

    @staticmethod
    def _pick_unit(ns):
        if ns >= 1e9:
            return 's'
        if ns >= 1e6:
            return 'ms'
        if ns >= 1e3:
            return 'μs'
        return 'ns'

    def _refresh_display(self, unit):
        """Display self._ns_value in `unit`."""
        display_val = self._ns_value / _UNIT_FACTOR[unit]
        self._silent = True
        try:
            self._unit.setCurrentText(unit)
            self._prev_unit = unit
            self._spin.setMaximum(_UNIT_MAX[unit])
            self._spin.setSingleStep(_UNIT_STEP[unit])
            self._spin.setValue(display_val)
        finally:
            self._silent = False

    def _on_spin_changed(self, _):
        if self._silent:
            return
        cur_unit = self._unit.currentText()
        ns_raw = self._spin.value() * _UNIT_FACTOR[cur_unit]
        self._ns_value = _snap_to_grid(ns_raw, cur_unit)
        # Re-display the snapped value (may differ from typed value).
        self._refresh_display(cur_unit)
        self.valueChanged.emit(self.value())

    def _on_unit_changed(self, _):
        """
        Unit switch re-snaps the stored value onto the new unit's grid.
        Switching to a coarser unit (e.g. ns → ms) discards precision;
        switching to a finer unit is lossless (its grid is a refinement
        of the coarser one).
        """
        new_unit = self._unit.currentText()
        old_unit = self._prev_unit

        if self._silent or old_unit == new_unit:
            self._prev_unit = new_unit
            return

        old_log = self.value()
        self._ns_value = _snap_to_grid(self._ns_value, new_unit)
        self._refresh_display(new_unit)
        new_log = self.value()
        if new_log != old_log:
            self.valueChanged.emit(new_log)
