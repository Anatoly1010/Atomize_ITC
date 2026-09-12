"""TR pair progress, native test mode, cancellation and saved results."""

from pathlib import Path
from types import SimpleNamespace
import importlib
import sys

import numpy as np
import pytest

from atomize.control_center.tr_control import Worker
from atomize.control_center.tr_two_fields import acquire, field_axis
from atomize.general_modules.csv_opener_saver import Saver_Opener


class Magnet:
    def __init__(self, state):
        self.state = state

    def magnet_field(self, value=None):
        if value is not None:
            if not 0 <= value <= 15000:
                raise ValueError('Field must be between 0 and 15000 G.')
            self.state.field = value
        return self.state.field

    def magnet_setup(self, start, step):
        if step <= 0:
            raise ValueError('Field step must be positive.')
        self.magnet_field(start)


class Oscilloscope:
    def __init__(self, state, scale=1):
        self.state = state
        self.scale = scale
        self.length = 3839
        self.averages = 10
        self.trigger = 'CH2'
        self.acquisition = 'Average'
        self.rng = np.random.default_rng()

    def oscilloscope_trigger_channel(self, channel=None):
        if channel is not None:
            if channel not in ('CH1', 'CH2', 'Ext'):
                raise ValueError('Invalid simulated trigger channel.')
            self.trigger = channel
        return self.trigger

    def oscilloscope_acquisition_type(self, value=None):
        if value is not None:
            if value != 'Average':
                raise ValueError('TR simulation expects Average acquisition.')
            self.acquisition = value
        return self.acquisition

    def oscilloscope_record_length(self, value=None):
        if value is not None and value != 4000:
            raise ValueError('TR simulation expects 4000 requested points.')
        return self.length

    def oscilloscope_number_of_averages(self, value=None):
        if value is not None:
            if not 2 <= value <= 2000:
                raise ValueError('Acquisitions must be between 2 and 2000.')
            self.averages = value
        return self.averages

    def oscilloscope_time_resolution(self):
        return '2 ns'

    def oscilloscope_run_stop(self):
        pass

    def oscilloscope_start_acquisition(self):
        pass

    def oscilloscope_get_curve(self, channel):
        if channel not in ('CH1', 'CH2'):
            raise ValueError('Invalid simulated signal channel.')
        axis = np.arange(self.length) * 2e-9
        baseline = 0.02 + 0.003 * np.sin(axis * 2e6)
        start, end = self.state.start, self.state.end
        signal_scale = self.scale
        if self.state.half_field and self.state.half_field[0] <= self.state.field <= self.state.half_field[1]:
            start, end, _ = self.state.half_field
            signal_scale *= 0.12
        center = (start + end) / 2
        width = max((end - start) / 7, 0.01)
        detuning = (self.state.field - center) / width
        amplitude = signal_scale * detuning * np.exp(-0.5 * detuning ** 2)
        if self.state.field == self.state.off_field:
            amplitude = 0
        pulse_time = axis - 0.5e-6
        signal = amplitude * np.where(pulse_time >= 0, np.exp(-np.maximum(pulse_time, 0) / 1.2e-6), 0)
        if channel == 'CH2':
            signal = 0.2 * np.exp(-0.5 * (pulse_time / 0.08e-6) ** 2)
        return baseline + signal + self.rng.normal(0, 0.02 / np.sqrt(self.averages), self.length)


class TemperatureController:
    def tc_temperature(self, channel):
        return {'A': 298.1, 'B': 298.3}[channel]


class FrequencyCounter:
    def freq_counter_digits(self, value):
        if value != 8:
            raise ValueError('TR simulation expects 8 frequency-counter digits.')

    def freq_counter_stop_mode(self, value):
        if value != 'Digits':
            raise ValueError('TR simulation expects Digits stop mode.')

    def freq_counter_frequency(self, channel):
        if channel != 'CH3':
            raise ValueError('TR simulation expects frequency-counter CH3.')
        return '9500 MHz'



class Connection:
    def __init__(self, filename=None):
        self.queue = ['start']
        if filename is not None:
            self.queue.append('FL' + str(filename))
        self.sent = []
        self.closed = False

    def poll(self):
        return bool(self.queue)

    def recv(self):
        return self.queue.pop(0)

    def send(self, message):
        self.sent.append(message)

    def close(self):
        self.closed = True


def run_pair(tmp_path, *, reverse=False, num_osc=1, fmt='csv', stop_at=None):
    worker = Worker()
    worker.half_field = (110, 112, 0.5)
    state = SimpleNamespace(field=100, start=120, end=128, off_field=100, half_field=worker.half_field)
    scopes = [Oscilloscope(state)]
    if num_osc > 1:
        scopes.append(Oscilloscope(state, scale=0.7))
    conn = Connection(tmp_path / f'pair.{fmt}')
    samples = []
    get_curve = scopes[0].oscilloscope_get_curve

    def record(channel):
        if channel == 'CH1':
            samples.append(state.field)
            if state.field == stop_at:
                conn.queue.append('exit')
        return get_curve(channel)

    scopes[0].oscilloscope_get_curve = record
    plots = {}

    def draw(name, data, **kwargs):
        plots[name] = (data.copy(), kwargs)

    general = SimpleNamespace(wait=lambda value: None, plot_2d=draw)
    acquire(worker, conn, general, Saver_Opener(), Magnet(state), scopes,
            TemperatureController(), FrequencyCounter(), ['2 ns'] * len(scopes),
            [3839] * len(scopes), [2e-9] * len(scopes),
            (100, 'Pair', 128, 120, 1, 10, 2, 10, num_osc, 'CH2', 1, int(reverse)))
    return conn, samples, plots, state


@pytest.mark.parametrize('reverse', [False, True])
def test_progress_weights_unequal_steps_and_counts(tmp_path, reverse):
    conn, samples, plots, state = run_pair(tmp_path, reverse=reverse)
    progress = [value for kind, value in conn.sent if kind == 'Status']
    half = [110, 110.5, 111, 111.5, 112]
    main = list(range(120, 129))
    route = [100] + half + (half[::-1] if reverse else []) + main + (main[::-1] if reverse else [])
    assert samples == route * 2
    assert len(progress) == (56 if reverse else 28)
    assert progress[(10 if reverse else 5) - 1] == 17
    assert progress[(28 if reverse else 14) - 1] == 50
    assert progress[(38 if reverse else 19) - 1] == 67
    assert progress[-1] == 100
    assert progress == sorted(progress)
    assert all(value < 100 for value in progress[:-1])
    assert [value for kind, value in conn.sent if kind == 'ScanComplete'] == [1, 2]
    assert plots['Pair_half'][0].shape == (2, 3839, 5)
    assert plots['Pair'][0].shape == (2, 3839, 9)
    assert plots['Pair_half'][1]['start_step'][1] == (110, 0.5)
    assert plots['Pair'][1]['start_step'][1] == (120, 1)
    assert state.field == 100


def test_fractional_endpoint_and_single_point():
    np.testing.assert_allclose(field_axis(100, 100.3, 0.1), [100, 100.1, 100.2, 100.3])
    np.testing.assert_allclose(field_axis(100, 100.25, 0.1), [100, 100.1, 100.2])
    np.testing.assert_equal(field_axis(100, 100, 1), [100])


@pytest.mark.parametrize('parameters', [(1, 2, 0), (2, 1, 0.5), (0, float('nan'), 1)])
def test_invalid_axis(parameters):
    with pytest.raises(ValueError):
        field_axis(*parameters)


def test_stop_between_ranges_does_not_count_pair(tmp_path):
    conn, samples, plots, state = run_pair(tmp_path, stop_at=112)
    assert samples == [100, 110, 110.5, 111, 111.5, 112]
    assert not any(kind == 'ScanComplete' for kind, _ in conn.sent)
    assert set(plots) == {'Pair_half'}
    assert state.field == 100
    assert (tmp_path / 'pair_half.csv').exists()
    assert 'Number of Scans:               0' in (tmp_path / 'pair.csv').read_text()


@pytest.mark.parametrize('fmt', ['csv', 'h5'])
def test_save_all_channels_and_completed_scan_snapshots(tmp_path, fmt):
    run_pair(tmp_path, reverse=True, num_osc=3, fmt=fmt)
    for suffix in ('', '_half', '_osc2', '_half_osc2', '_pulse', '_half_pulse'):
        path = tmp_path / f'pair{suffix}.{fmt}'
        rows = 6 if '_half' in suffix else 10
        if fmt == 'csv':
            assert np.loadtxt(path, delimiter=',').shape == (rows, 3839)
            assert (tmp_path / f'pair{suffix}_2_scans.csv').exists()
            assert 'Time Resolved EPR Spectrum' in path.read_text()
        else:
            import h5py
            with h5py.File(path) as stream:
                assert stream['I'].shape == (rows, 3839)
                assert stream['scans'].shape == (2, rows, 3839)
                assert stream['params'].attrs['Number of Scans'] == 2
                assert stream['sweep'][0] == 100
                assert stream['params'].attrs['Field Step'] == (0.5 if '_half' in suffix else 1)


@pytest.mark.parametrize('num_osc,reverse', [(1, False), (2, False), (3, True)])
def test_native_preflight_checks_both_ranges_without_io(monkeypatch, tmp_path, num_osc, reverse):
    import atomize.general_modules.general_functions as general
    import atomize.main.local_config as config
    import atomize.control_center.field_param as field_param
    import pyvisa

    monkeypatch.setattr(sys, 'argv', ['test'])
    monkeypatch.setattr(field_param, 'path', lambda: str(tmp_path / 'missing-field.param'))
    monkeypatch.setattr(general, 'test_flag', general.test_flag)
    monkeypatch.setattr(config, 'load_config_device', lambda: str(Path(__file__).parents[1] / 'atomize/device_modules/config'))

    def forbidden(*args, **kwargs):
        raise AssertionError('Native preflight must not use simulated instruments, VISA, files or LivePlot.')

    monkeypatch.setattr(pyvisa, 'ResourceManager', forbidden)
    monkeypatch.setattr(general, '_plotter', forbidden)
    monkeypatch.setattr(Saver_Opener, 'save_data', forbidden)
    monkeypatch.setattr(Saver_Opener, 'save_header', forbidden)
    magnet_module = importlib.import_module('atomize.device_modules.BH_15')
    set_field = magnet_module.BH_15.magnet_field
    current = [100]
    records = {}

    def field(device, *values):
        result = set_field(device, *values)
        if values:
            current[0] = values[0]
        return result

    monkeypatch.setattr(magnet_module.BH_15, 'magnet_field', field)
    for name in ('Keysight_2000_Xseries', 'Keysight_2000_Xseries_2'):
        module = importlib.import_module('atomize.device_modules.' + name)
        cls = module.Keysight_2000_Xseries
        original = cls.oscilloscope_get_curve

        def curve(device, channel, get_curve=original):
            assert device.test_flag == 'test'
            if channel == 'CH1':
                records.setdefault(id(device), []).append(current[0])
            return get_curve(device, channel)

        monkeypatch.setattr(cls, 'oscilloscope_get_curve', curve)
    worker = Worker()
    worker.half_field = (110, 112, 0.5)
    conn = Connection()
    worker.exp_test_two_fields(conn, 100, 'Pair', 128, 120, 1, 10, 4, 10,
                               num_osc, 'CH2', 1, int(reverse))
    assert conn.closed
    assert len(conn.sent) == 1 and conn.sent[0][0] == 'test', conn.sent
    half = [110, 110.5, 111, 111.5, 112]
    main = list(range(120, 129))
    expected = [100] + half + (half[::-1] if reverse else []) + main + (main[::-1] if reverse else [])
    assert len(records) == (1 if num_osc == 1 else 2)
    assert all(values == expected for values in records.values())
