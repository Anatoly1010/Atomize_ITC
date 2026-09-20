"""Regression coverage for cancelled save dialogs and derived result files."""

import ast
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from atomize.general_modules.csv_opener_saver import Saver_Opener

REPO_ROOT = Path(__file__).resolve().parents[1]


def _saver(test_flag='None'):
    """Use the saver methods without reading a machine-specific config."""
    saver = Saver_Opener.__new__(Saver_Opener)
    saver.test_flag = test_flag
    saver.save_cancelled = False
    return saver


def test_cancelled_dialog_blocks_derived_and_direct_saves_then_resets(tmp_path):
    saver = _saver()
    direct = tmp_path / 'explicit.csv'
    saver.FileDialog = lambda **kwargs: ''

    assert saver.create_file_dialog(multiprocessing=True, fmt='h5') == 'None'
    assert saver.save_cancelled
    for name in ('None_2d.h5', 'None_cycle1.h5', 'None_osc2', 'None_pulse',
                 'None_2_scans'):
        saver.save_data(tmp_path / name, np.ones((2, 2)))
    saver.save_header(direct, header='must not be written')
    assert not list(tmp_path.iterdir())
    assert not direct.exists()

    csv_path = tmp_path / 'accepted.csv'
    saver.FileDialog = lambda **kwargs: str(csv_path)
    assert saver.create_file_dialog(multiprocessing=True) == str(csv_path)
    assert not saver.save_cancelled
    saver.save_data(csv_path, np.array([[1., 2.], [3., 4.]]), header='accepted')
    assert np.loadtxt(csv_path, delimiter=',').shape == (2, 2)


def test_cancelled_parameters_keep_both_filenames_as_sentinels(tmp_path):
    saver = _saver()
    saver.FileDialog = lambda **kwargs: None

    assert saver.create_file_parameters('_param', multiprocessing=True) == ('None', 'None')
    assert saver.save_cancelled
    assert not (tmp_path / 'None_param.csv').exists()


def test_script_dialog_cancellation_blocks_existing_file_and_valid_selection_resets(monkeypatch, tmp_path):
    saver = _saver()
    existing = tmp_path / 'existing.csv'
    existing.write_text('keep this')
    monkeypatch.setattr('sys.stdin.readline', lambda: 'None\n')

    assert saver.create_file_dialog() == 'None'
    saver.save_header(existing, header='replace this')
    assert existing.read_text() == 'keep this'

    selected = tmp_path / 'selected.csv'
    monkeypatch.setattr('sys.stdin.readline', lambda: f'{selected}\n')
    assert saver.create_file_dialog() == str(selected)
    saver.save_header(existing, header='replaced')
    assert 'replaced' in existing.read_text()


def test_hdf5_save_still_works_after_a_valid_dialog(tmp_path):
    h5py = pytest.importorskip('h5py')
    saver = _saver()
    result = tmp_path / 'accepted.h5'
    saver.FileDialog = lambda **kwargs: str(result)

    saver.create_file_dialog(multiprocessing=True, fmt='h5')
    saver.save_data(result, np.array([[1., 2.], [3., 4.]]), header='accepted')

    with h5py.File(result) as stream:
        assert stream['I'].shape == (2, 2)
        assert stream.attrs['header'] == 'accepted'


def test_test_mode_save_behavior_is_unchanged(tmp_path):
    saver = _saver(test_flag='test')
    target = tmp_path / 'test.csv'

    saver.save_data(target, np.ones((2, 2)))

    assert not target.exists()


class _Connection:
    def __init__(self, filename):
        self.messages = ['FL' + filename]
        self.sent = []

    def poll(self):
        return bool(self.messages)

    def recv(self):
        return self.messages.pop(0)

    def send(self, message):
        self.sent.append(message)


def _worker_method(path, method):
    tree = ast.parse((REPO_ROOT / path).read_text())
    worker = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Worker')
    return next(node for node in worker.body if isinstance(node, ast.FunctionDef) and node.name == method)


def _run(nodes, namespace):
    code = compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), '<save block>', 'exec')
    exec(code, namespace)


def _awg_save_block(method):
    node = _worker_method('atomize/control_center/awg_phasing_insys.py', method)
    branch = next(child for child in ast.walk(node) if isinstance(child, ast.If)
                  and isinstance(child.test, ast.Name) and child.test.id == 'script_test'
                  and any('file_data' in ast.unparse(item) for item in child.orelse))
    return branch.orelse


@pytest.mark.parametrize('method', ['exp', 'exp_field', 'exp_log', 'exp_amplitude'])
@pytest.mark.parametrize('filename', ['', 'None'])
def test_awg_workers_do_not_write_after_cancelled_fl(monkeypatch, tmp_path, method, filename):
    monkeypatch.chdir(tmp_path)
    saver = _saver()
    namespace = {
        'conn': _Connection(filename), 'general': SimpleNamespace(wait=lambda value: None),
        'file_handler': saver, 'np': np, 'os': os, 'points_window': 2,
        'dec_calc': 1., 'x_axis_plot': np.array([0., 1.]), 'x_axis': np.array([0., 1.]),
        'receiver_level': None, 'iq_cor': 1, 'save2d': 1,
        'data': np.ones((2, 2)), 'data_x': np.ones(2), 'data_y': np.ones(2),
        'header': 'header', 'header2': 'header', 'EXP_NAME': 'test',
        'self': SimpleNamespace(save_hdf5=1),
    }

    _run(_awg_save_block(method), namespace)

    assert not list(tmp_path.iterdir())


def test_awg_workers_write_primary_and_2d_files_after_valid_fl(monkeypatch, tmp_path):
    pytest.importorskip('h5py')
    monkeypatch.chdir(tmp_path)
    output = tmp_path / 'result.csv'
    namespace = {
        'conn': _Connection(str(output)), 'general': SimpleNamespace(wait=lambda value: None),
        'file_handler': _saver(), 'np': np, 'os': os, 'points_window': 2,
        'dec_calc': 1., 'x_axis_plot': np.array([0., 1.]), 'iq_cor': 1, 'save2d': 1,
        'data': np.ones((2, 2)), 'data_x': np.ones(2), 'data_y': np.ones(2),
        'header': 'header', 'header2': 'header', 'EXP_NAME': 'test',
        'self': SimpleNamespace(save_hdf5=1),
    }

    _run(_awg_save_block('exp'), namespace)

    assert output.exists()
    assert (tmp_path / 'result_2d.h5').exists()


@pytest.mark.parametrize('filename', ['', 'None'])
def test_eseem_cycle_saves_respect_cancelled_fl(monkeypatch, tmp_path, filename):
    monkeypatch.chdir(tmp_path)
    saver = _saver()
    data = np.ones((2, 2))
    namespace = {
        'conn': _Connection(filename), 'general': SimpleNamespace(wait=lambda value: None),
        'file_handler': saver, 'np': np, 'os': os, 'points_window': 2,
        'dec_calc': 1., 'x_axis_plot': np.array([0., 1.]), 'iq_cor': 0, 'save2d': 0,
        'data': data, 'data_x': np.ones(2), 'data_y': np.ones(2), 'header': 'header',
        'header2': 'header', 'EXP_NAME': 'test', 'save_each': True,
        'cycle_snapshots': [data, data], 'self': SimpleNamespace(save_hdf5=0),
    }

    _run(_awg_save_block('exp_eseem'), namespace)

    assert not list(tmp_path.iterdir())


def test_eseem_cycle_saves_after_valid_fl(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / 'eseem.csv'
    data = np.ones((2, 2))
    namespace = {
        'conn': _Connection(str(output)), 'general': SimpleNamespace(wait=lambda value: None),
        'file_handler': _saver(), 'np': np, 'os': os, 'points_window': 2,
        'dec_calc': 1., 'x_axis_plot': np.array([0., 1.]), 'iq_cor': 0, 'save2d': 0,
        'data': data, 'data_x': np.ones(2), 'data_y': np.ones(2), 'header': 'header',
        'header2': 'header', 'EXP_NAME': 'test', 'save_each': True,
        'cycle_snapshots': [data, data], 'self': SimpleNamespace(save_hdf5=0),
    }

    _run(_awg_save_block('exp_eseem'), namespace)

    assert output.exists()
    assert (tmp_path / 'eseem_cycle0.csv').exists()
    assert (tmp_path / 'eseem_cycle1.csv').exists()


def _tr_nodes():
    node = _worker_method('atomize/control_center/tr_control.py', 'exp_on')
    receive = next(item for item in ast.walk(node) if isinstance(item, ast.While)
                   and 'file_save_1 = msg[2:]' in ast.unparse(item))
    base = next(item for item in ast.walk(node) if isinstance(item, ast.Assign)
                and 'os.path.splitext(file_save_1)' in ast.unparse(item))
    names = next(item for item in ast.walk(node) if isinstance(item, ast.If)
                 and 'file_save_2 =' in ast.unparse(item)
                 and 'file_save_3 =' in ast.unparse(item))
    scan = next(item for item in ast.walk(node) if isinstance(item, ast.If)
                and 'file_save_j =' in ast.unparse(item))
    saves = [item for item in ast.walk(node) if isinstance(item, ast.Expr)
             and 'file_handler.save_data(file_save_' in ast.unparse(item)]
    final = sorted(saves, key=lambda item: item.lineno)[-3:]
    assert len(final) == 3
    return receive, base, names, scan, final


@pytest.mark.parametrize('filename', ['', 'None'])
def test_tr_cancelled_fl_blocks_derived_scan_and_secondary_saves(monkeypatch, tmp_path, filename):
    monkeypatch.chdir(tmp_path)
    receive, base, names, scan, final = _tr_nodes()
    saver = _saver()
    namespace = {
        'conn': _Connection(filename), 'general': SimpleNamespace(wait=lambda value: None),
        'file_handler': saver, 'os': os, 'np': np, 'p9': 1, 'p11': 1,
        'p12': 0, 'j': 2, 'data': np.ones((3, 2, 2)), 'data_2': np.ones((2, 2, 2)),
        'header': 'header', 'header_2': 'header', 'axes_2d': None, 'axes_2d_2': None,
        'axes_units_2d': None, 'self': SimpleNamespace(),
    }

    _run([receive, base, scan], namespace)
    namespace['p9'] = 3
    _run([names, *final], namespace)

    assert namespace['file_save_2'] in ('_osc2', 'None_osc2')
    assert namespace['file_save_3'] in ('_pulse', 'None_pulse')
    assert not list(tmp_path.iterdir())


def test_tr_valid_fl_derives_and_writes_scan_and_secondary_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    receive, base, names, scan, final = _tr_nodes()
    output = tmp_path / 'tr.csv'
    namespace = {
        'conn': _Connection(str(output)), 'general': SimpleNamespace(wait=lambda value: None),
        'file_handler': _saver(), 'os': os, 'np': np, 'p9': 1, 'p11': 1,
        'p12': 0, 'j': 2, 'data': np.ones((3, 2, 2)), 'data_2': np.ones((2, 2, 2)),
        'header': 'header', 'header_2': 'header', 'axes_2d': None, 'axes_2d_2': None,
        'axes_units_2d': None, 'self': SimpleNamespace(),
    }

    _run([receive, base, scan], namespace)
    namespace['p9'] = 3
    _run([names, *final], namespace)

    assert (tmp_path / 'tr_2_scans.csv').exists()
    assert (tmp_path / 'tr_osc2.csv').exists()
    assert (tmp_path / 'tr_pulse.csv').exists()
