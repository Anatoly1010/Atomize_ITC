"""Run-local range recommendations keyed to the measured pulse/field context."""
from dataclasses import asdict
import copy
import hashlib
import json
from pathlib import Path


STATE_KEY = '_relaxation_ranges'


def context_key(session, pre, kind, seed, max_points):
    """Exclude temperature, receiver phase/window, averaging and shot rate."""
    bridge = session.state.get('bridge', {})
    identity = {
        'sample': session.sample, 'kind': kind,
        'preset': str(Path(pre.path).resolve()), 'field_g': round(pre.field, 6),
        'pulses': [asdict(slot) for slot in pre.slots],
        'awg_grid': pre.awg_grid, 'laser': pre.laser,
        'amplitudes': [pre.ampl_1, pre.ampl_2], 'iq_phase': pre.phase_deg,
        'n_wurst': pre.n_wurst, 'b_sech': pre.b_sech,
        'axis': [pre.x0, pre.xdelta], 'seed': seed, 'max_points': max_points,
        'bridge': {name: bridge.get(name) for name in ('attenuation_db', 'frequency_mhz')},
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def temperature(session):
    value = session.state.get('temperature', {})
    return float(value['setpoint']) if value.get('reached') else None


def settled(session):
    value = session.state.get('temperature')
    return value is None or bool(value.get('reached'))


def choose(session, key):
    """Cooling or an unrecorded temperature must not shorten the last range."""
    previous = session.state.get(STATE_KEY, {}).get(key)
    if previous is None or not settled(session):
        return None
    now, was = temperature(session), previous['temperature_k']
    protected = now is None or was is None or now < was
    recommendation = previous['next_range']
    if protected and recommendation['span_ns'] < previous['measured_range']['span_ns']:
        recommendation = previous['measured_range']
    return {'range': copy.deepcopy(recommendation),
            'source_data_file': previous['data_file'],
            'source_temperature_k': was, 'temperature_k': now,
            'cooling_or_unknown_guard': protected}


def stage(session, key, measured_range, next_range, path):
    """The existing step judge gate commits this copy only after success."""
    if session.test or not settled(session):
        return
    entries = dict(session.state.get(STATE_KEY, {}))
    entries[key] = {'temperature_k': temperature(session), 'data_file': str(path),
                    'measured_range': measured_range, 'next_range': next_range}
    session.stage_state(STATE_KEY, entries)
