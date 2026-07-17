"""Temperature primitives: setpoint setter and band waiter (Lakeshore 335).

Mirrors the temp_control tool's proven setter-waiter semantics: consecutive
in-band polls (hold count) at a slow cadence — GPIB is slow — inside a
wall-clock timeout. The session's temp_param lock (source 'epr_auto')
already keeps the interactive tool off the bus during a run; the waiter
mirrors its readings into temp.param so an open temp_control window keeps
displaying live values.
"""
import time

from atomize.epr_auto.primitives.judges import JudgeReport

_POLL_S = 1.0                 # keep slow: GPIB is slow
HEATER_RANGES = ('Off', '0.5 W', '5 W', '50 W')
REPHASE_DELTA_K = 5.0         # default 'rephase_delta'; see _rephase_check


def _rephase_check(session, setpoint, delta, reason):
    """Cooling/warming detunes the resonator, so the demod zero-order drifts:
    the 2026-07-03 oTP series measured a monotonic 215 deg -> 25 deg swing
    over 80..280 K at constant B1 (pulse amplitudes untouched throughout).
    Drop auto_phase once the setpoint moves more than `delta` K from where it
    was measured, so the run re-phases instead of silently carrying a stale
    zero-order. pi_calibration survives on purpose — temperature does not
    move B1; only a vane move does (invalidate_fine_calibrations)."""
    ap = session.state.get('auto_phase')
    if not ap:
        return
    was = ap.get('temperature_k')
    if was is None:
        # phased before any temp step ran: nothing to compare against, so the
        # phase cannot be shown to still hold once a setpoint is commanded
        session.invalidate_phase(f'{reason} {setpoint} K, phase measured at an '
                                 'unrecorded temperature')
        return
    if abs(float(setpoint) - float(was)) > float(delta):
        session.invalidate_phase(f'{reason} {was} K -> {setpoint} K '
                                 f'(> {delta} K)')


def set_temperature(session, setpoint, heater_range=None, rephase_delta=REPHASE_DELTA_K):
    """Set the Lakeshore setpoint (and optionally the heater range) and
    return immediately — pair with temp.wait to block until it holds.
    The device module's test branch range-checks both against the config."""
    setpoint = float(setpoint)
    ls = session.temp_controller
    if heater_range is not None:
        if heater_range not in HEATER_RANGES:
            raise ValueError(f'heater_range must be one of {HEATER_RANGES}, '
                             f'got {heater_range!r}')
        ls.tc_heater_range(heater_range)
    ls.tc_setpoint(setpoint)
    if not session.test:
        _write_status(setpoint=setpoint)
    # before the state update: _rephase_check compares against auto_phase's own
    # stamp, and the run is already committed to the new setpoint
    _rephase_check(session, setpoint, rephase_delta, 'temperature set')
    result = {'setpoint': setpoint,
              'heater_range': heater_range or 'unchanged'}
    session.state['temperature'] = result
    return result, []


def wait_temperature(session, band=0.2, channels='B', hold=3,
                     timeout='1800 s', setpoint=None,
                     rephase_delta=REPHASE_DELTA_K):
    """Poll until every requested channel sits inside +/-band (K) around the
    setpoint for `hold` consecutive polls. The wall-clock timeout fails the
    'temperature_band' judge -> StepFailure in a live run, so the step's
    retries / on_fail policy applies."""
    from atomize.epr_auto.params import parse_time_ns
    band = float(band)
    if band <= 0:
        raise ValueError(f'band must be positive, got {band}')
    timeout_s = parse_time_ns(timeout) / 1e9
    ls = session.temp_controller
    sp = float(setpoint) if setpoint is not None else float(ls.tc_setpoint())
    chans = tuple(channels)               # 'AB' -> ('A', 'B')
    # also checked here, not just in temp.set: a protocol may reach a new
    # temperature without a temp.set (external setpoint), and a dry-run must
    # surface the pending re-phase too
    _rephase_check(session, sp, rephase_delta, 'temperature reached')

    if session.test:
        temps = {c: ls.tc_temperature(c) for c in chans}   # arg validation
        result = {'setpoint': sp, 'temperature': temps, 'elapsed_s': 0.0,
                  'canned': True}
        return result, [JudgeReport('temperature_band', True, band,
                                    {'note': 'dry-run, not judged'})]

    t0 = time.monotonic()
    deadline = t0 + timeout_s
    held = 0
    temps = {}
    while time.monotonic() < deadline:
        temps = {c: ls.tc_temperature(c) for c in chans}
        _write_status(setpoint=sp,
                      temp_a=temps.get('A'), temp_b=temps.get('B'))
        ok = all(t is not None and abs(float(t) - sp) < band
                 for t in temps.values())
        held = held + 1 if ok else 0
        if held >= int(hold):
            break
        time.sleep(min(_POLL_S, max(0.0, deadline - time.monotonic())))

    elapsed = round(time.monotonic() - t0, 1)
    reached = held >= int(hold)
    result = {'setpoint': sp,
              'temperature': {c: round(float(t), 3) for c, t in temps.items()
                              if t is not None},
              'elapsed_s': elapsed}
    judge = JudgeReport(
        'temperature_band', reached, elapsed,
        {'band_k': band, 'hold': int(hold), 'timeout_s': timeout_s,
         **({} if reached else {'note': 'timeout before the band held'})})
    if reached:
        session.state['temperature'] = {'setpoint': sp, **result['temperature']}
    return result, [judge]


def _write_status(**kwargs):
    """Mirror readings into temp.param for an open temp_control window;
    never let display plumbing take down a run."""
    try:
        from atomize.control_center import temp_param
        temp_param.write_status(**{k: v for k, v in kwargs.items()
                                   if v is not None})
    except Exception:
        pass
