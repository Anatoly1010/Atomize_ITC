"""Two field ranges in one TR scan, using the working instrument instances."""

import datetime
import math
from pathlib import Path

import numpy as np


def field_axis(start, end, step):
    if not all(math.isfinite(value) for value in (start, end, step)):
        raise ValueError('Field parameters must be finite.')
    if not 0 <= start <= end <= 15000 or step <= 0:
        raise ValueError('Use 0 ≤ Start ≤ End ≤ 15000 G and Step > 0.')
    count = math.floor((end - start) / step + 1e-8) + 1
    return np.round(start + np.arange(count) * step, 3)


def acquire(worker, conn, general, saver, magnet, scopes, temperature, counter,
            resolutions, lengths, time_steps, parameters, test_mode=False):
    """Acquire one common background, half field, then main field per scan."""
    off, name, end, start, step, off_averages, scans, averages, num_osc, trigger, save_each, two_side = parameters
    ranges = [tuple(worker.half_field), (start, end, step)]
    axes = [field_axis(*region) for region in ranges]
    if ranges[0][1] >= start:
        raise ValueError('Half-field range must be below the main-field range.')
    data = [[np.zeros((3 if num_osc == 3 and scope == 0 else 2, length, len(axis) + 1))
             for scope, length in enumerate(lengths)] for axis in axes]
    counts = [np.zeros(len(axis), dtype=int) for axis in axes]
    background = [np.zeros((2 if num_osc == 3 and scope == 0 else 1, length))
                  for scope, length in enumerate(lengths)]
    field = 100.0
    magnet.magnet_setup(field, min(region[2] for region in ranges))
    completed = 0
    measured = 0
    points_per_scan = (len(axes[0]) + len(axes[1])) * (2 if two_side else 1)
    if test_mode:
        scans = 1
    temp_start = str(temperature.tc_temperature('A'))
    plot_handles = {}
    written = set()
    filename = '' if test_mode else None

    class Cancelled(Exception):
        pass

    def poll():
        nonlocal scans
        if worker.command == 'exit':
            raise Cancelled()
        while conn.poll():
            command = conn.recv()
            if command == 'exit':
                worker.command = 'exit'
                raise Cancelled()
            if command.startswith('SC') and not test_mode:
                scans = max(int(command[2:]), completed + 1)

    def wait(milliseconds):
        while milliseconds > 0:
            poll()
            duration = min(50, milliseconds)
            general.wait(f'{duration} ms')
            milliseconds -= duration

    def ramp(target, returning=False):
        nonlocal field
        while abs(field - target) > 1e-6:
            if not returning:
                poll()
            field = round(field + np.clip(target - field, -10, 10), 3)
            magnet.magnet_field(field)
            general.wait('30 ms')
        magnet.magnet_field(target)

    def traces():
        for scope in scopes:
            scope.oscilloscope_start_acquisition()
        result = [[scope.oscilloscope_get_curve('CH1')] for scope in scopes]
        if num_osc == 3:
            result[0].append(scopes[0].oscilloscope_get_curve('CH2'))
        return result

    def header(region, scope, number):
        start_field, end_field, field_step = ranges[region]
        w = 30
        now = datetime.datetime.now().strftime('%d-%m-%Y %H-%M-%S')
        temp_end = str(temperature.tc_temperature('A'))
        return (
            f"{'Date:':<{w}} {now}\n"
            f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
            f"{'Start Field:':<{w}} {start_field} G\n"
            f"{'End Field:':<{w}} {end_field} G\n"
            f"{'Field Step:':<{w}} {field_step} G\n"
            f"{'Off-Resonance Field:':<{w}} {off} G\n"
            f"{'Off-Resonance Averages:':<{w}} {off_averages}\n"
            f"{'Number of Averages:':<{w}} {averages}\n"
            f"{'Number of Scans:':<{w}} {number}\n"
            f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
            f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
            f"{'Temperature Cernox:':<{w}} {temperature.tc_temperature('B')} K\n"
            f"{'Record Length:':<{w}} {lengths[scope]} Points\n"
            f"{'Time Resolution:':<{w}} {resolutions[scope]}\n"
            f"{'Frequency:':<{w}} {counter.freq_counter_frequency('CH3')}\n"
            f"{'-'*50}\n"
            f"2D Data"
        )

    def save(snapshot=None):
        if not filename:
            return
        path = Path(filename)
        hdf5 = path.suffix.lower() == '.h5'
        for region, blocks in enumerate(data):
            for scope, block in enumerate(blocks):
                channels = [(0, '_osc2' if scope else '')]
                if num_osc == 3 and scope == 0:
                    channels.append((2, '_pulse'))
                for channel, suffix in channels:
                    range_suffix = '_half' if region == 0 else ''
                    scan_suffix = f'_{snapshot}_scans' if snapshot and snapshot > 1 and not hdf5 else ''
                    output = path.with_name(f'{path.stem}{range_suffix}{suffix}{scan_suffix}{path.suffix}')
                    matrix = block[channel].T
                    text = header(region, scope, completed)
                    if hdf5 and output in written:
                        import h5py
                        with h5py.File(output, 'a') as stream:
                            stream['I'][...] = matrix
                            saver._write_h5_attrs(stream, text)
                    else:
                        saver.save_data(str(output), matrix, header=text,
                            axes=(np.arange(lengths[scope]) * time_steps[scope], np.r_[off, axes[region]]),
                            axes_units=('s', 'G'))
                        written.add(output)
                    if snapshot and hdf5:
                        worker._append_scan_h5(str(output), matrix, snapshot)

    def draw(region, scope, scan):
        block = data[region][scope]
        axis = axes[region]
        plot_name = name + ('_half' if region == 0 else '') + ('_2' if scope else '')
        plot_handles[plot_name] = general.plot_2d(
            plot_name, block[:, :, 1:],
            start_step=((0, time_steps[scope]), (axis[0], ranges[region][2])),
            xname='Time', xscale='s', yname='Field', yscale='G',
            zname='Intensity', zscale='V', pr=plot_handles.get(plot_name, 'None'),
            text=f'Scan: {scan} · Completed scans: {completed}')

    if not test_mode:
        conn.send(('Open', ''))
    try:
        while filename is None:
            while conn.poll():
                command = conn.recv()
                if command == 'exit':
                    raise Cancelled()
                if command.startswith('FL'):
                    filename = command[2:]
                    if filename == 'None':
                        filename = ''
                    break
            if filename is None:
                general.wait('50 ms')
        while completed < scans:
            ramp(off)
            wait(4000)
            for scope in scopes:
                scope.oscilloscope_number_of_averages(off_averages)
            for scope, values in enumerate(traces()):
                background[scope] += (np.asarray(values) - background[scope]) / (completed + 1)
            for region, axis in enumerate(axes):
                for scope, block in enumerate(data[region]):
                    block[0, :, 0] = background[scope][0]
                    if num_osc == 3 and scope == 0:
                        block[2, :, 0] = background[scope][1]
                ramp(axis[0])
                wait(4000)
                for scope in scopes:
                    scope.oscilloscope_number_of_averages(averages)
                passes = [range(len(axis))]
                if two_side:
                    passes.append(range(len(axis) - 1, -1, -1))
                for indices in passes:
                    for index in indices:
                        poll()
                        field = float(axis[index])
                        magnet.magnet_field(field)
                        wait(80)
                        for scope, values in enumerate(traces()):
                            block = data[region][scope]
                            count = counts[region][index] + 1
                            block[0, :, index + 1] += (values[0] - block[0, :, index + 1]) / count
                            block[1, :, index + 1] = block[0, :, index + 1] - background[scope][0]
                            block[1, :, index + 1] -= block[1, 0, index + 1]
                            if num_osc == 3 and scope == 0:
                                block[2, :, index + 1] += (values[1] - block[2, :, index + 1]) / count
                            draw(region, scope, completed + 1)
                        counts[region][index] += 1
                        measured += 1
                        if not test_mode:
                            conn.send(('Status', 100 * measured // (scans * points_per_scan)))
            completed += 1
            if not test_mode:
                conn.send(('ScanComplete', completed))
            for region in range(len(axes)):
                for scope in range(len(scopes)):
                    draw(region, scope, completed)
            if save_each:
                save(snapshot=completed)
    except Cancelled:
        pass
    save()
    ramp(off, returning=True)
    worker.command = 'exit'
    conn.send(('test' if test_mode else '', f'Script {name} finished; completed scans: {completed}'))
    conn.close()
