"""Pure stability policy for fresh live repetition-rate curves."""

import math

import numpy as np


class LiveRateStability:
    """Accept disjoint stable groups of complex curve amplitudes."""

    def __init__(self, points=3, scans=1, tolerance=0.05):
        if isinstance(points, bool) or not isinstance(points, (int, np.integer)) \
                or points < 3:
            raise ValueError('points must be an integer of at least 3')
        if isinstance(scans, bool) or not isinstance(scans, (int, np.integer)) \
                or scans <= 0:
            raise ValueError('scans must be a positive integer')
        try:
            tolerance = float(tolerance)
        except (TypeError, ValueError):
            raise ValueError('tolerance must be between 0 and 1')
        if not math.isfinite(tolerance) or not 0 <= tolerance <= 1:
            raise ValueError('tolerance must be between 0 and 1')
        self.points = int(points)
        self.scans = int(scans)
        self.tolerance = tolerance
        self.reset()

    def reset(self):
        self._window = []
        self._accepted = []
        self._spread = None

    @property
    def spread(self):
        return self._spread

    @property
    def accepted(self):
        return np.asarray(self._accepted, dtype=np.complex128)

    def _stable(self, values):
        amplitudes = np.abs(np.asarray(values, dtype=np.complex128))
        mean = float(np.mean(amplitudes))
        if not np.all(np.isfinite(amplitudes)) or mean <= 0:
            return False, None
        spread = float((np.max(amplitudes) - np.min(amplitudes)) / mean)
        return spread <= self.tolerance, spread

    def add(self, sig):
        """Add one fresh curve signal; return all signals when converged."""
        try:
            value = complex(sig)
        except (TypeError, ValueError, OverflowError):
            self.reset()
            return None
        if not (math.isfinite(value.real) and math.isfinite(value.imag)) \
                or abs(value) == 0:
            self.reset()
            return None

        self._window.append(value)
        if len(self._window) < self.points:
            self._spread = None
            return None
        if len(self._window) > self.points:
            self._window = self._window[-self.points:]

        stable, spread = self._stable(self._window)
        self._spread = spread
        if not stable:
            self._accepted = []
            return None

        candidate = self._accepted + self._window
        combined_stable, combined_spread = self._stable(candidate)
        if not combined_stable:
            self._accepted = []
            self._spread = combined_spread
            return None

        self._accepted = candidate
        self._window = []
        self._spread = combined_spread
        if len(self._accepted) == self.points * self.scans:
            return np.asarray(self._accepted, dtype=np.complex128)
        return None
