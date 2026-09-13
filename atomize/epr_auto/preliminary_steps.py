"""Headless parameter schemas for the preliminary AWG steps."""
import math
from atomize.epr_auto.params import (
    PresetFile, Float, Int, TimeStr, FieldStr, PairOf, CalMap,
    ParamError, parse_time_ns, parse_field_g,
)


def _check(params, ctx):
    if any(isinstance(v, float) and not math.isfinite(v) for v in params.values()):
        raise ParamError('numeric parameters must be finite')
    if set(params) == {'attenuation_db', 'frequency_mhz'} and all(v is None for v in params.values()):
        raise ParamError('bridge.set needs attenuation_db and/or frequency_mhz')
    for key in ('rv_range', 'length_range', 'region'):
        pair = params.get(key)
        if pair is None:
            continue
        values = pair if key == 'rv_range' else list(map(parse_time_ns, pair))
        if not all(math.isfinite(v) for v in values):
            raise ParamError(f'{key} bounds must be finite')
        if values[0] >= values[1]:
            raise ParamError(f'{key} must be increasing')
    for db in list(params.get('rv_range', [])) + [params.get('coarse_step_db', 0)]:
        if abs(db * 2 - round(db * 2)) > 1e-8:
            raise ParamError('RV optimization settings must lie on the 0.5 dB grid')
    if params.get('length_range') and (not params.get('pulse_map') or params['pulse_map'] == 'none'):
        raise ParamError('length_range requires an explicit pulse_map')
    for key in ('max_length', 'pulse_length', 'window', 'search_from', 'min_width'):
        if key in params and not math.isfinite(parse_time_ns(params[key])):
            raise ParamError(f'{key} must be finite')
    for key in ('center', 'span', 'field_span'):
        if key in params and not math.isfinite(parse_field_g(params[key])):
            raise ParamError(f'{key} must be finite')
    if 'start_mhz' in params:
        if params['start_mhz'] >= params['end_mhz']:
            raise ParamError('start_mhz must be below end_mhz')
        if (params['end_mhz'] - params['start_mhz']) // params['step_mhz'] < 6:
            raise ParamError('resonator scan needs at least seven frequencies')
    if 'center' in params and parse_field_g(params['span']) / 2 > parse_field_g(params['center']):
        raise ParamError('field search extends below zero')


def register_steps(register, run_primitive):
    def bind(name, summary, params):
        def call(session, **kwargs):
            from atomize.epr_auto.primitives import preliminary
            func = getattr(preliminary, 'bridge_set' if name == 'bridge.set' else name.split('.')[1])
            return run_primitive(session, func, **kwargs)
        register(name, summary, params=params, check=_check)(call)

    def preset():
        return PresetFile(default='hahn_echo_4s.phase_awg', help='AWG SINE echo preset; defines the IF')

    def effort():
        return {'scans': Int(min=1, max=100, default=1),
                'averages': Int(min=1, max=10000, default=10)}

    def echo_gate():
        return {'search_from': TimeStr(default='200 ns'),
                'min_width': TimeStr(default='20 ns')}

    bind('tune.ringing_check', 'Home RV; check magnitude at each of 60,40,20,10,5,0 dB; hard-stop above 100 mV', {
        'if_mhz': Int(min=1, max=280, default=50, help='built-in SINE IF; must match the later echo preset DETECTION IF'),
        'max_length': TimeStr(default='102.4 ns', help='longest MW pulse any preliminary stage may use'),
    })
    bind('bridge.set', 'Set RV and/or synthesizer with mechanical settling', {
        'attenuation_db': Float(min=0, max=60),
        'frequency_mhz': Int(min=7000, max=12000),
    })
    bind('tune.resonator', 'AWG SINE diode scan; choose a stable early-ringing frequency maximum', {
        'if_mhz': Int(min=1, max=280, default=50, help='built-in SINE IF; must match the later echo preset DETECTION IF'),
        'start_mhz': Int(min=7000, max=12000, default=9200),
        'end_mhz': Int(min=7000, max=12000, default=9600),
        'step_mhz': Int(min=1, default=1),
        'pulse_length': TimeStr(default='102.4 ns'),
        'window': TimeStr(default='2 ns'),
        'precision_mhz': Float(min=1, default=5),
        'min_snr': Float(min=3, default=5),
        'competitor_ratio': Float(min=0.1, max=1, default=0.8),
        'region': PairOf(TimeStr(), help='optional trailing-edge region in trace coordinates'),
        'clip_mv': Float(min=0.001, help='scope voltage clipping level, when known'),
        **effort(),
    })
    bind('tune.find_echo', 'Full-window magnitude field search, then resolve the echo window', {
        'preset': preset(), 'center': FieldStr(required=True), 'span': FieldStr(required=True),
        'points': Int(min=7, max=1001, default=41),
        'attenuation_db': Float(min=5, max=10, default=10),
        'frequency_shift_mhz': Int(default=0, help='signed shift from resonator center, or current bridge frequency without a scan'),
        **effort(), **echo_gate(),
    })
    bind('tune.maximize_echo', 'Bounded RV (0.5 dB), field and optional mapped length optimization', {
        'preset': preset(), 'rv_range': PairOf(Float(min=0, max=60), default=[0, 10]),
        'coarse_step_db': Float(min=0.5, max=10, default=2),
        'field_span': FieldStr(default='10 G'),
        'points': Int(min=7, max=1001, default=21),
        'improvement': Float(min=0.001, max=1, default=0.05),
        'length_range': PairOf(TimeStr(), help='pi/2 length bounds; mapped lengths scale together'),
        'length_points': Int(min=2, max=101, default=5),
        'pulse_map': CalMap(help='explicit two-pulse map, e.g. {P2: pi2, P3: pi}'),
        **effort(), **echo_gate(),
    })
    bind('tune.save_presets', 'Export echo/calibration/field preset copies and a fine-tuning YAML handoff', {
        'preset': preset(),
        'calibration_preset': PresetFile(default='ampl_4s.phase_awg'),
        'field_preset': PresetFile(default='ed_4s.phase_awg'),
    })
