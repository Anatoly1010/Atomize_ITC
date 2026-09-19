"""Offline preliminary-step schema checks; run with Python."""
from pathlib import Path

from atomize.epr_auto.params import PRESET_DIR, ParamError
from atomize.epr_auto.steps import STEPS


def validate(name, supplied):
    spec = STEPS[name]
    ctx = {'protocol_dir': str(Path.cwd()), 'warnings': []}
    params = {}
    for key, param in spec.params.items():
        if key in supplied:
            params[key] = param.validate(supplied[key], ctx)
        elif param.required:
            raise ParamError(f'{key}: required parameter is missing')
        elif param.default is not None:
            params[key] = param.validate(param.default, {**ctx, 'is_default': True})
        else:
            params[key] = None
    if spec.check:
        spec.check(params, ctx)
    return params


def rejects(name, supplied):
    try:
        validate(name, supplied)
    except ParamError:
        return
    raise AssertionError(f'{name} accepted {supplied!r}')


def main():
    rejects('bridge.set', {})
    rejects('bridge.set', {'video1_db': 1})
    rejects('bridge.set', {'video2_db': 0.25})
    rejects('bridge.set', {'video1_db': float('nan')})
    assert validate('bridge.set', {'video1_db': 2, 'video2_db': 31.5}) == {
        'attenuation_db': None, 'frequency_mhz': None, 'video1_db': 2.0,
        'video2_db': 31.5,
    }

    echo = validate('tune.find_echo', {'center': '3445 G', 'span': '100 G'})
    assert validate('tune.rep_rate', {})['rate_min'] == 10.0
    assert validate('tune.rep_rate', {'rate_min': 10, 'rate_max': 20})['rate_max'] == 20.0
    rejects('tune.rep_rate', {'rate_min': 9.9})
    rejects('tune.rep_rate', {'rate_max': 9.9})
    assert echo['adjust_video'] is True
    assert echo['rep_rate'] is None
    assert validate('tune.find_echo', {
        'center': '3445 G', 'span': '100 G', 'adjust_video': False,
    })['adjust_video'] is False
    rejects('tune.find_echo', {'center': '3445 G', 'span': '100 G', 'rep_rate': 10000.1})
    rejects('tune.maximize_echo', {'rep_rate': 10000.1})
    maximum = validate('tune.maximize_echo', {'adjust_video': False, 'rep_rate': 500})
    assert maximum['adjust_video'] is False and maximum['rep_rate'] == 500.0
    for name, supplied in (('tune.find_echo', {'center': '3445 G', 'span': '100 G'}),
                           ('tune.maximize_echo', {})):
        assert validate(name, {**supplied, 'rep_rate': 'auto'})['rep_rate'] == 'auto'
        for rate in (float('nan'), float('inf'), 0.09, 'invalid', True):
            rejects(name, {**supplied, 'rep_rate': rate})

    assert 'tune.video_attenuation' in STEPS
    video = validate('tune.video_attenuation', {
        'preset': str(PRESET_DIR / 'hahn_echo_4s.phase_awg'), 'adjust_video': False,
    })
    assert video['adjust_video'] is False and video['limit_mv'] == 200.0
    assert 'scans' not in video and 'averages' not in video
    assert validate('tune.video_attenuation', {
        'preset': str(PRESET_DIR / 'hahn_echo_4s.phase_awg'),
    })['adjust_video'] is None
    rejects('tune.video_attenuation', {'preset': str(PRESET_DIR / 'hahn_echo_4s.phase_awg'),
                                       'limit_mv': 200.1})
    print('PASS: preliminary bridge and video-tuning schemas')


if __name__ == '__main__':
    main()
