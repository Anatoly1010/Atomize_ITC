"""Find a hardware-compatible repetition rate for a prepared T1 worker scan.

This checks sequence timing only. A compatible period does not establish that
the sample has physically recovered between shots.
"""

from copy import deepcopy
import math

from atomize.epr_auto.engine import executor


_TIMING_ERROR = 'Pulse sequence is longer than one period of the repetition rate'
_MIN_TENTHS = 1
_MAX_TENTHS = 1_000_000


def _span_rate_ceiling(wa):
    try:
        start = float(wa.log_start)
        end = float(wa.log_end)
        points = int(wa.points)
        grid = float(wa.awg_grid)
        if not all(map(math.isfinite, (start, end, grid))) or points < 2 or grid <= 0:
            return _MAX_TENTHS
        span_ns = 10 ** end - 10 ** start - points * grid / 2
        if not math.isfinite(span_ns) or span_ns <= 0:
            return _MAX_TENTHS
        return min(_MAX_TENTHS, max(_MIN_TENTHS, math.floor(1e10 / span_ns) + 1))
    except (AttributeError, OverflowError, TypeError, ValueError):
        return _MAX_TENTHS


def maximum_t1_rate(wa):
    """Return the highest valid effective rate, in 0.1 Hz steps, up to 100 kHz.

    ``wa`` must be the finalized Log Time WorkerArgs, including snapped log
    endpoints, pulse overrides, and integration window. Each candidate uses
    the full worker/driver test path, including every shifted sweep point.
    Unrelated preflight errors propagate unchanged.
    """
    fixed_laser = getattr(wa, 'laser_flag', 0) >= 1 and getattr(wa, 'laser_num', 0) == 1
    upper = _span_rate_ceiling(wa)
    candidate = deepcopy(wa)
    candidate.scans = 1

    def valid(tenths):
        candidate.rep_rate = f'{tenths / 10:.1f}'
        try:
            executor.run_worker(candidate, 'Log Time', script_test=True)
        except executor.EngineError as exc:
            if _TIMING_ERROR in str(exc):
                return False
            raise
        return True

    if fixed_laser:
        if not valid(99):
            raise ValueError('T1 sequence does not fit the fixed Nd:YAG rate of 9.9 Hz')
        return 9.9
    if not valid(_MIN_TENTHS):
        raise ValueError('T1 sequence does not fit even at 0.1 Hz')
    if valid(upper):
        if upper == _MAX_TENTHS or valid(_MAX_TENTHS):
            return _MAX_TENTHS / 10
        low, high = upper, _MAX_TENTHS
    else:
        low, high = _MIN_TENTHS, upper
    while high - low > 1:
        mid = (low + high) // 2
        if valid(mid):
            low = mid
        else:
            high = mid
    return low / 10
