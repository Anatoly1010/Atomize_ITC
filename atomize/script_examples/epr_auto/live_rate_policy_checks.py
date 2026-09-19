"""Offline checks for the live-rate stability policy."""

import numpy as np

from atomize.epr_auto.engine.live_rate import LiveRateStability


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def feed(policy, values):
    result = None
    for value in values:
        result = policy.add(value)
    return result


def main():
    check(feed(LiveRateStability(), [1 + 1j, 1.02 + 1j, .98 + 1j]) is not None,
          'stable group did not converge')
    check(feed(LiveRateStability(), [1, 1.05, 1]) is not None,
          'five percent boundary did not converge')
    policy = LiveRateStability()
    check(feed(policy, [1, 1.01, 1.02, 1.4, 1.01, 1.02]) is None,
          'abrupt outlier was accepted')
    policy = LiveRateStability()
    check(policy.add(0) is None and policy.add(1) is None,
          'zero did not clear pending data')
    check(policy.add(complex(np.nan, 0)) is None,
          'nan did not clear pending data')
    result = feed(LiveRateStability(), [1, -1j, 1j])
    check(result is not None, 'complex phase values were rejected')
    policy = LiveRateStability(points=3, scans=2)
    result = feed(policy, [1, 1.01, .99, 1.02, 1, .98])
    check(result is not None and result.size == 6, 'disjoint groups failed')
    check(np.allclose(np.abs(result), [1, 1.01, .99, 1.02, 1, .98]),
          'accepted groups changed')
    for args in ((2, 1, .05), (3, 0, .05), (True, 1, .05),
                 (3, 1, -0.1), (3, 1, 1.1)):
        try:
            LiveRateStability(*args)
        except ValueError:
            pass
        else:
            raise AssertionError(f'invalid arguments accepted: {args}')
    print('live-rate policy checks passed')


if __name__ == '__main__':
    main()
