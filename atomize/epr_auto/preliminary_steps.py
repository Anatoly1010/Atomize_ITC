"""Headless parameter schemas for the preliminary AWG steps."""
import math
from atomize.epr_auto.params import (
    PresetFile, Float, Int, Bool, TimeStr, FieldStr, PairOf, CalMap, Str, DirStr,
    ParamError, parse_time_ns, parse_field_g,
)


def _check(params, ctx):
    if any(isinstance(v, float) and not math.isfinite(v) for v in params.values()):
        raise ParamError('numeric parameters must be finite')
    if set(params) == {'attenuation_db', 'frequency_mhz'} and all(v is None for v in params.values()):
        raise ParamError('bridge.set needs attenuation_db and/or frequency_mhz')
    for key in ('amplitude_range', 'region'):
        pair = params.get(key)
        if pair is None:
            continue
        values = pair if key == 'amplitude_range' else list(map(parse_time_ns, pair))
        if not all(math.isfinite(v) for v in values):
            raise ParamError(f'{key} bounds must be finite')
        if values[0] >= values[1]:
            raise ParamError(f'{key} must be increasing')
    if 'amplitude_range' in params and params.get('fine_step', 1) > params.get('coarse_step', 5):
        raise ParamError('fine_step must not exceed coarse_step')
    for key in ('pulse_length', 'calibration_length', 'window', 'search_from', 'min_width'):
        if params.get(key) is not None and not math.isfinite(parse_time_ns(params[key])):
            raise ParamError(f'{key} must be finite')
    for key in ('center', 'span', 'field_span', 'field'):
        if params.get(key) is not None and not math.isfinite(parse_field_g(params[key])):
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
        'pulse_length': TimeStr(default='102.4 ns', help='SINE pulse length of the ladder'),
        'field': FieldStr(default='100 G', help='nonresonant field for the ringing ladder'),
        'done': Bool(default=False, help='the ladder already passed at this IF; record the limits, move nothing'),
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
        'attenuation_db': Float(min=0, max=60, default=10, help='fixed RV for the echo search and maximization'),
        'frequency_shift_mhz': Int(default=0, help='signed shift from resonator center, or current bridge frequency without a scan'),
        'pulse_length': TimeStr(help='target pi pulse length; every echo pulse takes it (default: the preset\'s shortest MW pulse)'),
        **effort(), **echo_gate(),
    })
    bind('tune.maximize_echo', 'Fixed-RV amplitude scan (pi/2 at a, pi at 2a), then field refinement', {
        'preset': preset(),
        'attenuation_db': Float(min=0, max=60, help='fixed RV; defaults to the find_echo setting'),
        'pulse_length': TimeStr(help='target pi pulse length for all echo pulses; defaults to the find_echo setting'),
        'amplitude_range': PairOf(Float(min=1, max=50), default=[5, 50], help='pi/2 amplitude bounds in %'),
        'coarse_step': Float(min=1, max=25, default=5),
        'fine_step': Float(min=0.5, max=5, default=1),
        'field_span': FieldStr(default='10 G'),
        'points': Int(min=7, max=1001, default=21),
        'improvement': Float(min=0.001, max=1, default=0.05),
        'pulse_map': CalMap(help='pi2/pi roles, e.g. {P2: pi2, P3: pi}; inferred from the preset when omitted'),
        **effort(), **echo_gate(),
    })
    bind('tune.apply_calibration', 'Write the session calibration, zero-order phase, echo window and field into a preset file', {
        'preset': PresetFile(required=True, help='preset file to rewrite in place, or to copy from when destination is given'),
        'pulse_map': CalMap(help='pi2/pi roles; inferred from the preset when omitted'),
        'destination': Str(help='absolute path of the file to write instead of rewriting the preset in place'),
    })
    bind('tune.save_presets', 'Export echo/calibration/field preset copies and a fine-tuning YAML handoff', {
        'preset': preset(),
        'calibration_preset': PresetFile(default='ampl_4s.phase_awg'),
        'field_preset': PresetFile(default='ed_4s.phase_awg'),
        'field_span': FieldStr(help='EDFS span of the handoff, centered on the tuned field; default: the find_echo span'),
        'field_points': Int(min=2, max=5001, default=200),
        'calibration_length': TimeStr(help='target length of the Rabi pulse the fine calibration sweeps; default: the preliminary pulse length'),
        'publish_dir': DirStr(default='tuned', help='where the handoff (fine_tuning.yaml and its presets) is published; the run directory keeps an archive copy'),
    })
