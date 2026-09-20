import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
import pytest
from PyQt6.QtCore import QObject, QItemSelectionModel, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMainWindow

from atomize.main.main_window import MainWindow
from atomize.main import local_config as lconf


@pytest.fixture
def liveplot(monkeypatch, tmp_path):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    monkeypatch.setattr(lconf, 'load_scripts', lambda path: str(tmp_path))
    app = QApplication.instance() or QApplication([])
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.design_setting()
    window.insert_dock_right = True
    yield window
    for name in list(window.namelist.keys()):
        del window.namelist[name]
    window.deleteLater()
    app.processEvents()


def push(window, source, name, offset=0):
    window.meta = dict(operation='plot_y', name=name, rank=1, start_step=None, label='signal')
    window.do_operation(np.arange(5) + offset, source=source)


def push_iq(window, source, name='Dig', offset=0, pair=True, pid=42, parent_pid=7, x=None):
    if x is None:
        x = np.arange(5, dtype=float) * (1e-9 if name == 'Dig' else 1e6)
    y = np.arange(len(x), dtype=float) + offset
    window.meta = dict(operation='plot_xy', name=name, rank=1, pid=pid, parent_pid=parent_pid,
                       label='ch' if name == 'Dig' else 'FFT',
                       Xname='Time' if name == 'Dig' else 'Frequency',
                       X='s' if name == 'Dig' else 'Hz', Yname='Intensity', Y='mV', Scatter='False',
                       TimeAxis='False', Vline='False', value='')
    data = np.array([[x, x], [y, -y]]) if pair else np.array([x, y])
    window.do_operation(data, source=source)


def track_controller(window):
    from types import MethodType, SimpleNamespace
    from unittest.mock import Mock
    from atomize.main.main import MainExtended

    controller = SimpleNamespace(namelist=window.namelist, text_errors=Mock(),
                                 process_phasing=Mock(), process_awg_phasing=Mock())
    controller.process_phasing.processId.return_value = 7
    controller.process_awg_phasing.processId.return_value = 7
    controller.clear_track = MethodType(MainExtended.clear_track, controller)
    controller.handle_track = MethodType(MainExtended.handle_track, controller)
    return controller


@pytest.mark.parametrize('fft_pair', [False, True])
def test_track_copies_dig_and_hidden_fft_without_changing_live_data(liveplot, fft_pair):
    import json

    source = QObject()
    push_iq(liveplot, source)
    push_iq(liveplot, source, 'FFT', pair=fft_pair)
    liveplot.namelist['FFT'].close()
    original = liveplot.namelist['Dig'].curves['ch']
    original.setPos(2e-9, 3)
    original.setTransform(original.transform().scale(1, 2))
    controller = track_controller(liveplot)
    owner = controller.process_awg_phasing
    controller.handle_track(owner, json.dumps(dict(action='capture', pid=42, fft=True, quad=int(fft_pair))))
    snapshots = {}
    for name, count in [('Dig', 2), ('FFT', 2 if fft_pair else 1)]:
        dock = liveplot.namelist[name]
        assert len(dock.track_curves) == count
        assert len(dock.curves) == count
        snapshots[name] = [(curve.xData.copy(), curve.yData.copy()) for curve in dock.track_curves]
        for reference, original in zip(dock.track_curves, dock.curves.values()):
            assert reference.opacity() == pytest.approx(0.3)
            assert reference.opts['pen'].color() == original.opts['pen'].color()
            assert reference.zValue() < original.zValue()
            assert reference.pos() == original.pos()
            assert reference.transform() == original.transform()
            assert not np.shares_memory(reference.yData, original.yData)
    assert liveplot.namelist['FFT'].closed
    push_iq(liveplot, source, offset=10)
    push_iq(liveplot, source, 'FFT', offset=20, pair=fft_pair)
    for name in snapshots:
        for reference, (x, y) in zip(liveplot.namelist[name].track_curves, snapshots[name]):
            np.testing.assert_array_equal(reference.xData, x)
            np.testing.assert_array_equal(reference.yData, y)
    controller.clear_track(owner)
    for name in snapshots:
        assert not liveplot.namelist[name].track_curves
        assert liveplot.namelist[name].curves
    np.testing.assert_array_equal(liveplot.namelist['Dig'].curves['ch'].yData, np.arange(5) + 10)


def test_track_rejects_stale_and_missing_data_and_clears_only_its_owner(liveplot):
    import json

    controller = track_controller(liveplot)
    request = json.dumps(dict(action='capture', pid=42, fft=False))
    controller.handle_track(controller.process_phasing, request)
    assert 'Dig' not in liveplot.namelist
    source = QObject()
    push_iq(liveplot, source, pid=41)
    controller.handle_track(controller.process_phasing, request)
    assert not liveplot.namelist['Dig'].track_curves
    push_iq(liveplot, source)
    controller.handle_track(controller.process_phasing, request)
    assert len(liveplot.namelist['Dig'].track_curves) == 2
    controller.clear_track(controller.process_awg_phasing)
    assert len(liveplot.namelist['Dig'].track_curves) == 2
    liveplot.namelist.source_disconnected(source)
    assert len(liveplot.namelist['Dig'].track_curves) == 2
    controller.clear_track(controller.process_phasing)
    controller.handle_track(controller.process_phasing, request)
    assert not liveplot.namelist['Dig'].track_curves


def test_track_fft_mode_change_and_new_source(liveplot):
    import json

    source = QObject()
    controller = track_controller(liveplot)
    owner = controller.process_phasing
    push_iq(liveplot, source)
    push_iq(liveplot, source, 'FFT', pair=True)
    controller.handle_track(owner, json.dumps(dict(action='capture', pid=42, fft=True, quad=1)))
    controller.handle_track(owner, json.dumps(dict(action='clear_fft', pid=42)))
    assert not liveplot.namelist['FFT'].track_curves
    assert len(liveplot.namelist['Dig'].track_curves) == 2
    controller.handle_track(owner, json.dumps(dict(action='capture', pid=42, fft=True, quad=0)))
    assert not liveplot.namelist['FFT'].track_curves
    push_iq(liveplot, QObject(), pid=43, parent_pid=8)
    assert not liveplot.namelist['Dig'].track_curves


def test_track_survives_worker_restart_in_same_phasing_window(liveplot):
    import json

    source = QObject()
    controller = track_controller(liveplot)
    owner = controller.process_phasing
    push_iq(liveplot, source)
    push_iq(liveplot, source, 'FFT', pair=False)
    controller.handle_track(owner, json.dumps(dict(action='capture', pid=42, fft=True, quad=0)))
    saved = {name: tuple(liveplot.namelist[name].track_curves) for name in ('Dig', 'FFT')}
    liveplot.namelist.source_disconnected(source)
    new_source = QObject()
    push_iq(liveplot, new_source, pid=43, offset=20)
    push_iq(liveplot, new_source, 'FFT', pid=43, offset=30, pair=False)
    for name, references in saved.items():
        assert tuple(liveplot.namelist[name].track_curves) == references
        np.testing.assert_array_equal(references[0].yData, np.arange(5))
    controller.clear_track(owner)
    assert all(not liveplot.namelist[name].track_curves for name in saved)


@pytest.mark.parametrize('fft_pair', [False, True], ids=['magnitude', 'phase_corrected'])
@pytest.mark.parametrize('new_samples', [
    np.arange(1, 4),
    np.arange(-2, 8),
    np.arange(8, 13),
    np.arange(5) * 0.5,
], ids=['shorter', 'longer', 'shifted', 'different_spacing'])
def test_track_preserves_independent_axes_after_worker_restart(liveplot, fft_pair, new_samples):
    import json

    source = QObject()
    controller = track_controller(liveplot)
    owner = controller.process_phasing
    old_axes = {'Dig': np.arange(5) * 1e-9, 'FFT': (np.arange(5) - 2) * 1e6}
    new_axes = {'Dig': new_samples * 1e-9, 'FFT': (new_samples - 2) * 1e6}
    for name, x in old_axes.items():
        push_iq(liveplot, source, name, pair=name == 'Dig' or fft_pair, x=x)
    controller.handle_track(owner, json.dumps(dict(action='capture', pid=42, fft=True, quad=int(fft_pair))))
    saved = {name: tuple(liveplot.namelist[name].track_curves) for name in old_axes}
    liveplot.namelist.source_disconnected(source)
    new_source = QObject()
    for name, x in new_axes.items():
        push_iq(liveplot, new_source, name, pid=43, offset=20,
                pair=name == 'Dig' or fft_pair, x=x)
        dock = liveplot.namelist[name]
        assert tuple(dock.track_curves) == saved[name]
        assert len(dock.track_curves) == len(dock.curves) == (2 if name == 'Dig' or fft_pair else 1)
        for index, (reference, current) in enumerate(zip(dock.track_curves, dock.curves.values())):
            sign = 1 if index == 0 else -1
            np.testing.assert_array_equal(reference.xData, old_axes[name])
            np.testing.assert_array_equal(reference.yData, sign * np.arange(5))
            np.testing.assert_array_equal(current.xData, x)
            np.testing.assert_array_equal(current.yData, sign * (np.arange(len(x)) + 20))
            assert not np.shares_memory(reference.xData, current.xData)
            assert not np.shares_memory(reference.yData, current.yData)
        view = dock.plot_item.getViewBox()
        view.enableAutoRange(x=True, y=True)
        view.updateAutoRange()
        lower, upper = view.viewRange()[0]
        assert lower <= min(old_axes[name].min(), x.min())
        assert upper >= max(old_axes[name].max(), x.max())


def visible(window):
    return {name for name, plot in window.namelist.plot_dict.items()
            if plot.area is window.dockarea and not plot.closed}


def test_following_shows_all_connected_sources_and_excludes_inactive_pins(liveplot):
    first, second = QObject(), QObject()
    push(liveplot, first, 'A')
    push(liveplot, first, 'B')
    assert visible(liveplot) == {'A', 'B'}
    liveplot.namelist.select_plot('A')
    liveplot.namelist.toggle_pin()
    push(liveplot, second, 'C')
    push(liveplot, second, 'D')
    assert visible(liveplot) == {'A', 'B', 'C', 'D'}
    assert not liveplot.namelist['B'].closed
    push(liveplot, first, 'B', offset=10)
    push(liveplot, first, 'Late plot')
    assert visible(liveplot) == {'A', 'B', 'C', 'D', 'Late plot'}
    np.testing.assert_array_equal(liveplot.namelist['B'].curves['signal'].yData, np.arange(5) + 10)
    liveplot.namelist.source_disconnected(first)
    assert visible(liveplot) == {'A', 'B', 'C', 'D', 'Late plot'}
    assert not liveplot.namelist.show_run_button.isChecked()
    liveplot.namelist.show_run_button.click()
    assert visible(liveplot) == {'C', 'D'}
    assert liveplot.namelist.show_run_button.isChecked()
    assert 'A' in liveplot.namelist.pinned


def test_reused_names_reopen_once_without_overriding_manual_selection(liveplot):
    first, second = QObject(), QObject()
    push(liveplot, first, 'A')
    plot = liveplot.namelist['A']
    plot.close_button.click()
    push(liveplot, second, 'A', offset=20)
    push(liveplot, second, 'B')
    assert liveplot.namelist['A'] is plot
    assert visible(liveplot) == {'A', 'B'}
    liveplot.namelist.grid_button.setChecked(True)
    index = liveplot.namelist.namelist_model.findItems('A')[0].index()
    liveplot.namelist.namelist_view.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Deselect)
    push(liveplot, second, 'A', offset=30)
    assert visible(liveplot) == {'B'}
    np.testing.assert_array_equal(plot.curves['signal'].yData, np.arange(5) + 30)


def test_run_start_hides_old_plots_before_first_data(liveplot):
    first, second = QObject(), QObject()
    push(liveplot, first, 'Old')
    liveplot.namelist.source_disconnected(first)
    liveplot.namelist.begin_run()
    assert visible(liveplot) == set()
    assert 'Old' in liveplot.namelist
    push(liveplot, second, 'New A')
    push(liveplot, second, 'New B')
    assert visible(liveplot) == {'New A', 'New B'}


@pytest.mark.parametrize('grid', [False, True])
def test_run_resets_grid_mode_and_hidden_plot_keeps_updating(liveplot, grid):
    plots = liveplot.namelist
    plots.grid_button.setChecked(grid)
    source = QObject()
    push(liveplot, source, 'A')
    push(liveplot, source, 'B')
    assert not plots.grid_button.isChecked()
    assert plots.selection_hint.isHidden()
    assert plots.namelist_view.selectionMode() == plots.namelist_view.SelectionMode.SingleSelection
    assert visible(liveplot) == {'A', 'B'}
    plots.grid_button.setChecked(grid)
    plots['A'].close_button.click()
    push(liveplot, source, 'A', offset=40)
    assert plots.grid_button.isChecked() == grid
    assert visible(liveplot) == {'B'}
    np.testing.assert_array_equal(plots['A'].curves['signal'].yData, np.arange(5) + 40)
    plots.activate_item(plots.namelist_model.findItems('A')[0].index())
    assert visible(liveplot) == {'A', 'B'}
    plots.source_disconnected(source)
    push(liveplot, QObject(), 'C')
    assert not plots.grid_button.isChecked()
    assert plots.selection_hint.isHidden()
    assert plots.namelist_view.selectionMode() == plots.namelist_view.SelectionMode.SingleSelection
    assert visible(liveplot) == {'C'}


@pytest.mark.parametrize('grid', [False, True])
def test_show_current_run_restores_closed_plots_after_browsing(liveplot, grid):
    plots = liveplot.namelist
    assert not plots.show_run_button.isEnabled()
    assert not plots.show_run_button.isChecked()
    first, second = QObject(), QObject()
    push(liveplot, first, 'Pinned')
    plots.toggle_pin()
    push(liveplot, first, 'Old')
    push(liveplot, second, 'A')
    push(liveplot, second, 'B')
    push(liveplot, second, 'Deleted')
    del plots['Deleted']
    plots.source_disconnected(first)
    assert not plots.show_run_button.isChecked()
    liveplot.tabwidget.setCurrentIndex(1)
    liveplot.show()
    QApplication.processEvents()
    plots['A'].close_button.click()
    assert not plots.show_run_button.isChecked()
    index = plots.namelist_model.findItems('Old')[0].index()
    QTest.mouseClick(plots.namelist_view.viewport(), Qt.MouseButton.LeftButton,
                     pos=plots.namelist_view.visualRect(index).center())
    assert visible(liveplot) == {'Pinned', 'Old'}
    assert not plots.show_run_button.isChecked()
    if grid:
        QTest.mouseClick(plots.grid_button, Qt.MouseButton.LeftButton)
    push(liveplot, second, 'A', offset=40)
    QTest.mouseClick(plots.show_run_button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()
    assert visible(liveplot) == {'A', 'B'}
    assert all(plots[name].isVisible() for name in ('A', 'B'))
    assert plots.show_run_button.isChecked()
    assert not plots.grid_button.isChecked()
    np.testing.assert_array_equal(plots['A'].curves['signal'].yData, np.arange(5) + 40)
    push(liveplot, second, 'C')
    assert visible(liveplot) == {'A', 'B', 'C'}
    plots['A'].close_button.click()
    push(liveplot, second, 'A', offset=50)
    assert visible(liveplot) == {'B', 'C'}
    plots.show_run_button.click()
    assert visible(liveplot) == {'A', 'B', 'C'}
    assert plots.show_run_button.isChecked()
    plots.show_run_button.click()
    assert visible(liveplot) == {'A', 'B', 'C'}
    assert plots.show_run_button.isChecked()


def test_show_current_run_restores_2d_and_tracks_run_boundaries(liveplot):
    plots = liveplot.namelist
    source = QObject()
    push(liveplot, source, 'Trace')
    data = np.arange(20).reshape(4, 5)
    liveplot.meta = dict(operation='plot_z', name='Image', rank=2, start_step=None,
                         Xname='X', X='', Yname='Y', Y='', Zname='Z', Z='', value='')
    liveplot.do_operation(data, source=source)
    plots['Image'].close_button.click()
    plots['Trace'].close_button.click()
    assert visible(liveplot) == set()
    plots.show_run_button.click()
    assert visible(liveplot) == {'Trace', 'Image'}
    np.testing.assert_array_equal(plots['Image'].get_data(), data)
    plots.source_disconnected(source)
    assert visible(liveplot) == {'Trace', 'Image'}
    assert not plots.show_run_button.isChecked()
    assert not plots.show_run_button.isEnabled()
    plots.show_run_button.click()
    assert visible(liveplot) == {'Trace', 'Image'}
    plots.begin_run()
    assert not plots.show_run_button.isEnabled()
    plots.show_run_button.click()
    assert visible(liveplot) == set()
    push(liveplot, QObject(), 'Next')
    plots['Next'].close_button.click()
    plots.show_run_button.click()
    assert visible(liveplot) == {'Next'}
    del plots['Next']
    assert not plots.show_run_button.isEnabled()


def test_activity_survives_hiding_and_clears_when_source_disconnects(liveplot):
    source = QObject()
    plots = liveplot.namelist
    push(liveplot, source, 'Dig')
    item = plots.namelist_model.findItems('Dig')[0]
    assert not item.icon().isNull()
    assert 'Live source connected' in item.toolTip()
    assert 'Last data:' in item.toolTip()
    plots['Dig'].close_button.click()
    plots.begin_run()
    plots.refresh_view()
    assert not item.icon().isNull()
    plots.source_disconnected(source)
    assert item.icon().isNull()
    assert 'Source disconnected' in item.toolTip()
    assert 'Last data:' in item.toolTip()


@pytest.mark.parametrize('grid', [False, True])
def test_disconnection_preserves_manual_browsing(liveplot, grid):
    plots = liveplot.namelist
    first, second = QObject(), QObject()
    push(liveplot, first, 'Old')
    plots.source_disconnected(first)
    push(liveplot, second, 'Live')
    plots.select_plot('Old')
    plots.activate_item(plots.namelist_model.findItems('Old')[0].index())
    plots.grid_button.setChecked(grid)
    assert visible(liveplot) == {'Old'}
    assert not plots.show_run_button.isChecked()
    plots.source_disconnected(second)
    assert visible(liveplot) == {'Old'}
    assert not plots.show_run_button.isEnabled()
    plots.show_run_button.click()
    assert visible(liveplot) == {'Old'}


def test_data_updates_do_not_rearrange_or_reopen_hidden_plots(liveplot, monkeypatch):
    plots = liveplot.namelist
    source = QObject()
    push(liveplot, source, 'A')
    push(liveplot, source, 'B')
    plots['A'].close_button.click()
    refreshes = []
    refresh_view = plots.refresh_view

    def record_refresh(*args):
        refreshes.append(True)
        refresh_view(*args)

    monkeypatch.setattr(plots, 'refresh_view', record_refresh)
    push(liveplot, source, 'A', offset=10)
    push(liveplot, source, 'B', offset=20)
    assert not refreshes
    assert visible(liveplot) == {'B'}
    np.testing.assert_array_equal(plots['A'].curves['signal'].yData, np.arange(5) + 10)
    np.testing.assert_array_equal(plots['B'].curves['signal'].yData, np.arange(5) + 20)


def test_shared_plot_stays_active_until_all_sources_disconnect(liveplot):
    first, second = QObject(), QObject()
    plots = liveplot.namelist
    push(liveplot, first, 'Dig')
    push(liveplot, second, 'Dig')
    item = plots.namelist_model.findItems('Dig')[0]
    plots.source_disconnected(first)
    assert not item.icon().isNull()
    assert plots.show_run_button.isEnabled()
    assert plots.show_run_button.isChecked()
    assert visible(liveplot) == {'Dig'}
    plots.source_disconnected(second)
    assert item.icon().isNull()
    assert not plots.show_run_button.isEnabled()
    assert not plots.show_run_button.isChecked()
    assert visible(liveplot) == {'Dig'}
    del plots['Dig']
    assert 'Dig' not in plots.plot_sources
    assert 'Dig' not in plots.last_plot_update


@pytest.mark.parametrize('rank', [1, 2])
def test_header_auto_range_button_restores_scale(liveplot, rank):
    plot = liveplot.add_new_plot(rank, 'Scale test')
    if rank == 1:
        plot.plot(np.arange(10), np.arange(10), name='signal', scatter='False')
        item = plot.plot_widget.getPlotItem()
    else:
        plot.setImage(np.arange(100).reshape(10, 10), axes={'y': 0, 'x': 1})
        item = plot.plot_item
    liveplot.tabwidget.setCurrentIndex(1)
    liveplot.show()
    QApplication.processEvents()
    item.setRange(xRange=(2, 3), yRange=(2, 3))
    assert not any(item.vb.autoRangeEnabled())
    plot.auto_range_button.click()
    QApplication.processEvents()
    assert all(item.vb.autoRangeEnabled())
    assert item.buttonsHidden
    assert not item.autoBtn.isVisible()
    assert plot.auto_range_button.isVisible()
    assert plot.auto_range_button.x() + plot.auto_range_button.width() < plot.close_button.x()
