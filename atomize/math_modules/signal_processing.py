#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import numpy as np

# scipy is an optional dependency (pip install -e .[math]); imported lazily so
# that simply importing this module never fails on a minimal install.
try:
    from scipy.signal import savgol_filter
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


class Signal_Processing():
    """Lightweight 1D signal-processing helpers (smoothing, baseline, scaling).

    Every method takes and returns plain numpy arrays so the result can be
    pushed straight to LivePlot or saved to CSV by the caller.
    """

    def __init__(self):
        if len(sys.argv) > 1:
            self.test_flag = sys.argv[1]
        else:
            self.test_flag = 'None'

    def savitzky_golay(self, y, window=11, order=3):
        """Savitzky-Golay smoothing. window must be odd and > order."""
        if not SCIPY_AVAILABLE:
            raise RuntimeError("scipy is required for Savitzky-Golay smoothing. "
                               "Install with: pip install -e .[math]")
        y = np.asarray(y, dtype=float)
        window = int(window)
        order = int(order)
        if window % 2 == 0:
            window += 1
        window = min(window, len(y) - (1 - len(y) % 2))
        if window <= order:
            window = order + 1 + (order % 2)
        return savgol_filter(y, window, order)

    def moving_average(self, y, window=5):
        """Centered moving-average smoothing; edges padded by reflection."""
        y = np.asarray(y, dtype=float)
        window = max(1, int(window))
        if window == 1:
            return y.copy()
        kernel = np.ones(window)/window
        pad = window//2
        padded = np.pad(y, pad, mode='reflect')
        smoothed = np.convolve(padded, kernel, mode='same')
        return smoothed[pad:pad + len(y)]

    def baseline_poly(self, x, y, order=1, region='all', npts=0):
        """Subtract a polynomial baseline of the given order.

        region: 'all'  -> fit the baseline to every point (default)
                'first' -> fit only the first `npts` points
                'last'  -> fit only the last `npts` points
                'ends'  -> fit only the first and last `npts` points
        The fitted polynomial is then subtracted from the full curve. This lets
        you estimate a baseline from signal-free regions (e.g. the trace tails).
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        n = len(x)
        npts = int(npts)
        if region == 'all' or npts <= 0 or 2*npts >= n:
            sel = np.arange(n)
        elif region == 'first':
            sel = np.arange(0, npts)
        elif region == 'last':
            sel = np.arange(n - npts, n)
        else:   # 'ends'
            sel = np.concatenate([np.arange(0, npts), np.arange(n - npts, n)])
        coeffs = np.polyfit(x[sel], y[sel], int(order))
        baseline = np.polyval(coeffs, x)
        return y - baseline

    def normalize(self, y, mode='minmax'):
        """Normalize y. mode: 'minmax' -> [0, 1], 'max' -> /max(|y|), 'area' -> unit area."""
        y = np.asarray(y, dtype=float)
        if mode == 'minmax':
            span = float(np.max(y) - np.min(y)) or 1.0
            return (y - np.min(y))/span
        elif mode == 'max':
            peak = float(np.max(np.abs(y))) or 1.0
            return y/peak
        elif mode == 'area':
            area = float(np.trapz(np.abs(y))) or 1.0
            return y/area
        return y.copy()

if __name__ == "__main__":
    main()
