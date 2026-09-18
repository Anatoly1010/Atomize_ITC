"""Offline preliminary-tuning checks; run with Python and the `test` argument."""
import copy
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('Run this offline check with the test argument')

from atomize.epr_auto.engine import snapshot
from atomize.epr_auto.errors import PreliminaryAbort
from atomize.epr_auto.params import PRESET_DIR
from atomize.epr_auto.primitives import preliminary as p
from atomize.epr_auto.primitives.resonator import select_frequency
from atomize.epr_auto.protocol import load_protocol
from atomize.epr_auto.runner import RunnerAbort, _run_step
from atomize.epr_auto.session import EPRSession
from atomize.epr_auto.steps import STEPS


def selection_checks():
    rng = np.random.default_rng(32)
    t = np.arange(0, 250, 0.3125)
    f = np.arange(9200, 9601)
    profile = np.exp(-0.5 * ((f - 9440) / 15)**2)
    v = np.zeros((len(t), len(f)))
    v[(t >= 50) & (t < 152.4)] = 15
    tail = t >= 152.4
    v[tail] = 70 * np.exp(-(t[tail, None] - 152.4) / 5) * profile
    v += rng.normal(0, 0.05, v.shape)
    for sign in (1, -1):
        result = select_frequency(t, f, sign * v)
        assert result['accepted'], result['reasons']
        assert abs(result['frequency_mhz'] - 9440) <= 5
    assert not select_frequency(t, f, v, clip_mv=50)['accepted']
    competing = v.copy()
    competing[tail] += 70 * np.exp(-(t[tail, None] - 152.4) / 5) * np.exp(-0.5*((f-9320)/15)**2)
    assert not select_frequency(t, f, competing)['accepted']
    edge = v.copy()
    edge[tail] = 70 * np.exp(-(t[tail, None]-152.4)/5) * np.exp(-0.5*((f-9200)/15)**2)
    assert not select_frequency(t, f, edge)['accepted']
    bad = v.copy()
    bad[0, 0] = np.nan
    try:
        select_frequency(t, f, bad)
    except ValueError:
        pass
    else:
        raise AssertionError('NaN map accepted')
    try:
        noisy = select_frequency(t, f, rng.normal(0,1,v.shape))
        assert not noisy['accepted']
    except ValueError:
        pass
    broad_t = np.arange(0, 220, .3125)
    broad = rng.normal(0, .03, (len(broad_t), len(f)))
    broad[(broad_t >= 40) & (broad_t < 142.4)] += 5
    trailing = broad_t >= 142.4
    broad[trailing] += 100 * np.exp(-(broad_t[trailing, None] - 142.4) / 8) * np.exp(-.5*((f-9400)/110)**2)
    for sign in (1, -1):
        result = select_frequency(broad_t, f, sign * broad)
        assert result['accepted'], result['reasons']
        assert abs(result['frequency_mhz'] - 9400) <= 5
    reference = Path('/home/anatoly/Documents/00_Exp_data/2026_06_24_sifter/01_resonator_tune.csv')
    if reference.exists():
        measured = np.loadtxt(reference, delimiter=',') * 1000
        result = select_frequency(np.arange(len(measured))*.3125, f, measured)
        assert result['accepted'] and abs(result['frequency_mhz']-9440) <= 5, result['reasons']
        print('Real scan:', result['frequency_mhz'], 'MHz;', result['nearby_centers_mhz'])
    print('PASS: resonator polarity, strong broad ringing, precision, competitors, boundary, clipping and invalid data')


def ringing_checks():
    pre = snapshot.load_preset(PRESET_DIR / 'ringing_check.phase_awg')
    wa = snapshot.build_worker_args(pre, exp_name='Check')
    assert wa.rect[0][3] == wa.awg[0][7] == ['+x', '+x']
    a = p.protection_end_ns(wa)
    hahn = snapshot.build_worker_args(snapshot.load_preset(PRESET_DIR / 'hahn_echo_4s.phase_awg'), exp_name='Reference')
    assert abs(p.protection_trace_start_ns(hahn) - 147.6) < .01
    assert abs(p.protection_trace_start_ns(wa) - 493.2) < .01
    pre.slots[1].length += 32
    b = p.protection_end_ns(snapshot.build_worker_args(pre, exp_name='Check'))
    assert abs(b-a-32) < 0.01, (a,b)

    def simulate(fail_at=None, if_mhz=50, interrupt=False):
        events = []
        session = EPRSession('check', 'autonomous', True)
        session.log = lambda msg: None
        def home(s):
            events.append(('home',60))
            s.state['bridge'] = {'attenuation_db':60}
        def move(s, attenuation_db=None, frequency_mhz=None):
            events.append(('move',attenuation_db))
        def trace(s, pre, tag):
            args = snapshot.build_worker_args(copy.deepcopy(pre), exp_name='Check')
            assert args.rect[0][3] == args.awg[0][7] == ['+x', '+x']
            assert pre.slots[0].freq == pre.slots[1].freq == if_mhz
            db = events[-1][1]
            events.append(('trace',db))
            if interrupt and db == fail_at:
                raise KeyboardInterrupt
            amplitude = 101 if db == fail_at else 10
            return np.arange(640.), np.full(640,amplitude), np.zeros(640), None
        with patch.object(p, '_home', home), patch.object(p, 'bridge_set', move), \
                patch.object(p, '_trace', trace), patch.object(p.executor, 'acquire_trace'):
            try:
                p.ringing_check(session, if_mhz=if_mhz)
            except PreliminaryAbort:
                assert fail_at is not None
            else:
                assert fail_at is None
        return events
    events = simulate()
    assert events == [('home',60)] + [item for db in (60,40,20,10,5,0)
                                      for item in [('move',db),('trace',db)]]
    assert simulate(if_mhz=80) == events
    events = simulate(20)
    assert events[-1] == ('home',60) and ('move',10) not in events
    assert simulate(20, interrupt=True)[-1] == ('home',60)
    assert p.ringing_peak(np.arange(10), np.full(10,80), np.full(10,80), 3) > 100
    for bad in (np.full(10,np.nan), np.full(10,np.inf)):
        try:
            p.ringing_peak(np.arange(10),bad,np.zeros(10),3)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid ringing passed')
    session = EPRSession('check', 'autonomous', True)
    session.state['ringing_check'] = {'if_mhz': 50, 'max_length_ns': 102.4}
    from atomize.epr_auto.engine import resonator as engine
    with patch.object(engine, 'acquire') as acquire, patch.object(p, '_home') as home:
        for params in ({'if_mhz': 80}, {'pulse_length': '103 ns'}):
            session.state['ringing_check'] = {'if_mhz': 50, 'max_length_ns': 102.4}
            try:
                p.resonator(session, **params)
            except PreliminaryAbort:
                pass
            else:
                raise AssertionError('untested resonator settings passed')
        acquire.assert_not_called()
        assert home.call_count == 2
        session.state['ringing_check'] = {'if_mhz': 50}
        try:
            p.ringing_check(session)
        except PreliminaryAbort:
            pass
        else:
            raise AssertionError('duplicate ringing check passed')
        assert home.call_count == 3
    print('PASS: built-in cycles, explicit IF, pulse-derived timing, every-rung check and early abort')


def homing_checks():
    from atomize.device_modules.Micran_X_band_MW_bridge_v2 import Micran_X_band_MW_bridge_v2
    from unittest.mock import Mock
    for homed, origin, expected, age in ((False, 12, 70.596, 1000), (False, 60, 0, 1000), (False, 60, 50.596, 20), (True, 5, 70.596, 20), (True, 60, 0, 20)):
        clock = [0.0]
        def join():
            clock[0] += 7
        mw = SimpleNamespace(prev_dB=origin if homed else 60, p1='None',
                             calibration=lambda db:Micran_X_band_MW_bridge_v2.calibration(None, db),
                             mw_bridge_rotary_vane=Mock())
        mw.mw_bridge_rotary_vane.side_effect = lambda *args, **kwargs:(
            setattr(mw, 'p1', SimpleNamespace(join=join)) if args else f'{origin} dB')
        session = SimpleNamespace(test=False, mw_bridge=mw, state={'_rv_homed':homed},
                                  invalidate_fine_calibrations=lambda reason:None)
        with patch.object(p, '_claim'), patch.object(p, '_vane_record_age_s', return_value=age), \
                patch.object(p.time, 'monotonic', side_effect=lambda:clock[0]), \
                patch.object(p.time, 'sleep') as sleep:
            p._home(session)
            assert abs(sleep.call_args.args[0] - max(0, expected + .2 - 7)) < 1e-8
            mw.mw_bridge_rotary_vane.assert_called_with(60.0, mode='Limit')
            assert session.state['bridge']['attenuation_db'] == 60
    print('PASS: limit homing waits full travel unless the vane is recorded at 60 dB, in-flight move allowance')


def frequency_shift_checks():
    pre = snapshot.load_preset(PRESET_DIR / 'hahn_echo_4s.phase_awg')
    t = np.arange(640.)
    for scanned in (False, True):
        session = EPRSession('check', 'autonomous', True)
        if scanned:
            session.state['resonator'] = {'synthesizer_mhz': 9440}
        current = [9490]
        expected_reference = 9440 if scanned else 9490
        events = []
        def bridge(s, attenuation_db=None, frequency_mhz=None):
            current[0] = frequency_mhz
            events.append('frequency')
        def sweep(*args):
            assert events[-1] == 'frequency'
            events.append('sweep')
            return 3445, {}
        with patch.object(p, '_echo_preset', return_value=pre), \
                patch.object(p, '_synth_mhz', side_effect=lambda s: current[0]), \
                patch.object(p, 'bridge_set', side_effect=bridge), \
                patch.object(p, '_sweep', side_effect=sweep), \
                patch.object(p, '_field_trace', return_value=(t, t, t, None)), \
                patch.object(p, '_window', return_value={'win_left_ns':240, 'win_right_ns':360}), \
                patch.object(p, '_remember_preset'):
            for shift in (0, -50, -50, 50):
                result, _ = p.find_echo(session, pre.path, '3445 G', '100 G',
                                        frequency_shift_mhz=shift)
                assert current[0] == expected_reference + shift
                assert result['synthesizer_mhz'] == current[0]
                assert result['observation_mhz'] == current[0] - 50
                assert result['frequency_reference_mhz'] == expected_reference
    print('PASS: signed echo frequency shifts, applied before sweeping, without accumulation')


def runner_checks():
    session = EPRSession('check', 'autonomous', True)
    session.log = lambda msg: None
    calls = []
    spec = copy.copy(STEPS['tune.ringing_check'])
    def fail(session, **kwargs):
        calls.append(1)
        raise PreliminaryAbort('threshold exceeded; returned to 60 dB')
    spec.func = fail
    step = SimpleNamespace(name='tune.ringing_check', params={}, retries=4, on_fail='skip')
    manifest = SimpleNamespace(record=lambda *a, **kw: None)
    with patch.dict(STEPS, {'tune.ringing_check': spec}):
        try:
            _run_step(SimpleNamespace(),session,manifest,step,0)
        except RunnerAbort as error:
            assert error.hard
        else:
            raise AssertionError('hard failure was skipped')
    assert len(calls) == 1
    print('PASS: ringing failure bypasses neither retries nor skip policy')


def checkpoint_abort_checks():
    from atomize.epr_auto import runner
    protocol = SimpleNamespace(path=Path('check.yaml'), sample='check',
                               autonomy='supervised', steps=[object()], warnings=[])
    for error in (RunnerAbort('checkpoint abort', hard=True),
                  KeyboardInterrupt(), EOFError(), OSError('manifest failure')):
        session = EPRSession('check', 'supervised', True)
        session.log = session.notify = lambda msg: None
        session.state['ringing_check'] = {'if_mhz':50}
        with patch.object(runner, '_Manifest'), \
                patch.object(runner, '_do_step', side_effect=error), \
                patch.object(p, '_home') as home:
            try:
                runner.run_protocol(protocol, session)
            except BaseException as stopped:
                assert stopped is error
            else:
                raise AssertionError('protocol did not stop')
            home.assert_not_called()
            assert 'ringing_check' in session.state
    for name in ('resonator', 'find_echo', 'maximize_echo'):
        session = EPRSession('check', 'supervised', True)
        session.state['ringing_check'] = {'if_mhz':50, 'max_length_ns':102.4}
        session.state['preliminary_echo'] = {'field_g':3445, 'attenuation_db':8.0}
        if name == 'resonator':
            from atomize.epr_auto.engine import resonator as engine
            target, method, args = engine, 'acquire', {}
        else:
            target, method = p, '_echo_preset'
            args = {'preset':'unused'}
            args.update({'center':'3445 G', 'span':'100 G'} if name == 'find_echo' else {})
        with patch.object(target, method, side_effect=KeyboardInterrupt), patch.object(p, '_home') as home:
            try:
                getattr(p, name)(session, **args)
            except KeyboardInterrupt:
                pass
            else:
                raise AssertionError('interrupt swallowed')
            home.assert_not_called()
    print('PASS: runner abort leaves RV unchanged outside the ringing ladder')


def bridge_lock_checks():
    import ast
    from unittest.mock import Mock
    path = PRESET_DIR.parent / 'mw_bridge_control.py'
    tree = ast.parse(path.read_text())
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'rot_vane')
    lock = SimpleNamespace(held=False)
    bridge_param = SimpleNamespace(is_locked=lambda: lock.held)
    namespace = {'bridge_param':bridge_param}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), namespace)
    gui = SimpleNamespace(Rot_vane=SimpleNamespace(value=lambda:10), prev_dB=20,
                          calibration=lambda v:v, sock=Mock(), _show_from_file=Mock(),
                          p1=SimpleNamespace(join=lambda:setattr(lock, 'held', True)))
    namespace['rot_vane'](gui)
    gui.sock.sendto.assert_not_called()
    gui._show_from_file.assert_called_once()
    print('PASS: pending manual RV move is discarded when automation acquires the lock')


def export_checks():
    pre = snapshot.load_preset(PRESET_DIR / 'hahn_echo_4s.phase_awg')
    pre.field = 3445
    pre.slots[1].length = 32
    pre.awg_grid = 0.8
    pre.win_left_ns, pre.win_right_ns = 240, 360
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'echo.phase_awg'
        p._write_preset(pre,path)
        restored = snapshot.load_preset(path)
        assert restored.field == 3445 and restored.slots[1].length == 32
        assert restored.awg_grid == 0.8 and restored.step_ampl == pre.step_ampl
        assert (restored.win_left_ns,restored.win_right_ns) == (240,360)
        assert restored.slots[1].phase_text == pre.slots[1].phase_text
        protocol = Path(directory) / 'bad.yaml'
        protocol.write_text('sample: check\nsteps:\n  - tune.maximize_echo:\n      amplitude_range: [40, 20]\n')
        try:
            load_protocol(protocol)
        except Exception as error:
            assert 'increasing' in str(error), error
        else:
            raise AssertionError('decreasing amplitude range accepted')
    print('PASS: preset export and amplitude-range parameter validation')


def optimization_checks():
    session = EPRSession('check', 'autonomous', False)
    session.log = lambda msg: None
    session.state.update({'echo_window': {'win_left_ns':240,'win_right_ns':360},
                          'ringing_check': {'if_mhz':50,'max_length_ns':102.4,
                                            'min_attenuation_db':0,'ampl_1':260,'ampl_2':260},
                          'preliminary_echo': {'field_g':3493, 'attenuation_db':8.0,
                                               'sweep': {'fields_g': [3400.0, 3500.0]}}})
    moves = []
    optimum = [30.0]
    def bridge(s, attenuation_db=None, **kw):
        moves.append(attenuation_db)
        s.state['bridge'] = {'attenuation_db':attenuation_db, 'frequency_mhz':9490}
    def trace(s, candidate, tag):
        t = np.arange(0,512,0.4)
        assert candidate.slots[2].coef == min(100, 2*candidate.slots[1].coef)
        amplitude = 100 * np.sin(min(np.pi, np.pi/2 * candidate.slots[1].coef / optimum[0]))**3
        return t, amplitude*np.exp(-0.5*((t-300)/25)**2), np.zeros_like(t), None
    def sweep(s,candidate,fields,window,tag):
        return float(np.median(fields)), {'fields_g':fields.tolist()}
    with patch.object(p,'bridge_set',bridge), patch.object(p,'_trace',trace), patch.object(p,'_sweep',sweep):
        result,_ = p.maximize_echo(session,str(PRESET_DIR/'hahn_echo_4s.phase_awg'),
                                   pulse_map={'P2':'pi2','P3':'pi'})
    assert moves == [8.0] and result['pi2_amplitude'] == 30 and result['pi_amplitude'] == 60, result
    assert all(tr['pi_amplitude'] == 2*tr['pi2_amplitude'] for tr in result['amplitude_trials'])
    for optimum[0], word in ((70.0, 'reduce'), (4.0, 'increase')):
        edge = EPRSession('check', 'autonomous', False); edge.log = lambda msg: None
        edge.state.update(session.state)
        with patch.object(p,'bridge_set',bridge), patch.object(p,'_trace',trace), \
                patch.object(p,'_sweep',sweep), patch.object(p,'_home'):
            try:
                p.maximize_echo(edge,str(PRESET_DIR/'hahn_echo_4s.phase_awg'), pulse_map={'P2':'pi2','P3':'pi'})
            except PreliminaryAbort as error:
                assert word in str(error), error
            else:
                raise AssertionError('amplitude edge accepted')
    session.commit_staged_state()
    chosen = session.state['_preliminary_preset']
    source = snapshot.load_preset(PRESET_DIR/'hahn_echo_4s.phase_awg')
    assert chosen.slots[0].st_inc == source.slots[0].st_inc
    assert (chosen.slots[1].coef, chosen.slots[2].coef) == (30, 60)
    with tempfile.TemporaryDirectory() as directory:
        session._run_dir=Path(directory)
        with patch.object(p.executor,'run_worker'):
            result,_=p.save_presets(session,str(PRESET_DIR/'hahn_echo_4s.phase_awg'),
                                    str(PRESET_DIR/'ampl_4s.phase_awg'),str(PRESET_DIR/'ed_4s.phase_awg'))
        protocol=load_protocol(result['protocol'])
        assert protocol.steps[0].params['frequency_mhz']==9490
        edfs=next(st.params for st in protocol.steps if st.name=='field.edfs')
        assert [float(x.split()[0]) for x in edfs['range']]==[3443.0, 3543.0], edfs
        loaded=snapshot.load_preset(result['presets'][0])
        assert (loaded.slots[1].coef, loaded.slots[2].coef) == (30, 60)
        cal=snapshot.load_preset(result['presets'][1])
        assert cal.slots[1].typ == 'SINE' and cal.slots[1].length == chosen.slots[2].length
        assert sorted(s.coef for s in cal.slots[2:4]) == [30, 60]
        assert len(result['presets']) == 4 and result['calibration_length_ns'] == chosen.slots[2].length
        session._run_dir=Path(directory)/'second'; session._run_dir.mkdir()
        with patch.object(p.executor,'run_worker'):
            short,_=p.save_presets(session,str(PRESET_DIR/'hahn_echo_4s.phase_awg'),
                                   str(PRESET_DIR/'ampl_4s.phase_awg'),str(PRESET_DIR/'ed_4s.phase_awg'),
                                   calibration_length='16 ns', publish_dir=str(Path(directory)/'tuned'))
        cal16=snapshot.load_preset(short['presets'][1]); echo16=snapshot.load_preset(short['presets'][3])
        assert cal16.slots[1].length == 16 and sorted(s.coef for s in cal16.slots[2:4]) == [30, 60]
        assert all(s.length == 16 for s in echo16.slots[1:3]) and echo16.slots[2].coef > 60
        steps16=[st.name for st in load_protocol(short['protocol']).steps]
        assert steps16[3:6] == ['tune.pi_calibration','tune.apply_calibration','tune.apply_calibration'], steps16
        assert steps16[-4:] == ['tune.echo_window','tune.auto_phase','tune.pi_calibration','tune.apply_calibration'], steps16
        session.state['pi_calibration']={'mode':'amplitude','pi':48.0,'pi2':24.0,'length_ns':16.0,'shape_factor':1.0}
        with patch.object(p.executor,'run_worker'):
            applied,_=p.apply_calibration(session, short['presets'][3], {'P2':'pi2','P3':'pi'})
        written=snapshot.load_preset(short['presets'][3])
        assert (written.slots[1].coef, written.slots[2].coef) == (24.0, 48.0), applied
        session.state['auto_phase']={'zero_order_deg':12.5}; session.state['field']='3436.5 G'
        published=Path(directory)/'tuned'/'echo_cal.phase_awg'
        with patch.object(p.executor,'run_worker'):
            p.apply_calibration(session, short['presets'][3], {'P2':'pi2','P3':'pi'}, destination=str(published))
        final=snapshot.load_preset(published)
        window=session.state['echo_window']
        assert final.zero_order_deg == 12.5 and final.field == 3436.5, (final.zero_order_deg, final.field)
        assert np.allclose((final.win_left_ns, final.win_right_ns), (window['win_left_ns'], window['win_right_ns']), atol=0.01)
        assert (final.slots[1].coef, final.slots[2].coef) == (24.0, 48.0)
        t2=Path(directory)/'t2.yaml'
        t2.write_text('sample: check\nsteps:\n  - exp.t2:\n      preset: tuned/echo_cal.phase_awg\n      points: 50\n      window: preset\n      apply_cal: none\n')
        assert load_protocol(t2).steps[0].params['preset'] == str(published)
        for path in result['presets']:
            saved=snapshot.load_preset(path)
            wa=snapshot.build_worker_args(saved, exp_name='ExportCheck')
            assert wa.awg[0][1]=='50 MHz'
    print('PASS: fixed-RV amplitude scan, range-edge aborts, calibration export and handoff reload')


selection_checks()
ringing_checks()
homing_checks()
frequency_shift_checks()
runner_checks()
checkpoint_abort_checks()
bridge_lock_checks()
export_checks()
optimization_checks()
print('ALL PASS')
