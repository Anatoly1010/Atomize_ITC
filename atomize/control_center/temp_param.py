#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Cross-process status + lock file for the Lakeshore temperature controller.
# Mirrors field_param.py: a single small text file that lets the temp_control
# GUI and an experiment runner (e.g. awg_phasing_insys) coordinate access to the
# same GPIB/RS-232 Lakeshore session. Whoever is about to talk to the device
# takes the lock; the other side reads THIS file instead of the bus, so the two
# processes are never on the instrument at the same time.

import os
import threading

_KEY_SEP = ':  '
_DEFAULTS = {'Setpoint': '0', 'TempA': '0', 'TempB': '0', 'Lock': 'Off', 'Source': ''}
_ORDER = ('Setpoint', 'TempA', 'TempB', 'Lock', 'Source')
_io_lock = threading.Lock()


def path():
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'temp.param')


def _parse_line(line):
    line = line.strip()
    if not line:
        return None, None
    if _KEY_SEP in line:
        key, value = line.split(_KEY_SEP, 1)
    elif ':' in line:
        key, value = line.split(':', 1)
        value = value.strip()
    else:
        return None, None
    return key.strip(), value.strip()


def read():
    data = dict(_DEFAULTS)
    try:
        with open(path(), encoding='utf-8') as status_file:
            for line in status_file:
                key, value = _parse_line(line)
                if key in data:
                    data[key] = value
    except FileNotFoundError:
        pass
    return data


def write(data):
    directory = os.path.dirname(os.path.abspath(path()))
    os.makedirs(directory, exist_ok=True)
    payload = {key: str(data.get(key, _DEFAULTS[key])) for key in _ORDER}
    content = '\n'.join(f'{key}{_KEY_SEP}{payload[key]}' for key in _ORDER) + '\n'
    temp_path = path() + '.tmp'
    with open(temp_path, 'w', encoding='utf-8') as status_file:
        status_file.write(content)
    os.replace(temp_path, path())


def write_status(setpoint=None, temp_a=None, temp_b=None):
    """Update the published status without touching the lock (partial update)."""
    with _io_lock:
        data = read()
        if setpoint is not None:
            data['Setpoint'] = str(setpoint)
        if temp_a is not None:
            data['TempA'] = str(temp_a)
        if temp_b is not None:
            data['TempB'] = str(temp_b)
        write(data)


def _float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def current_setpoint(default=0.0):
    return _float(read().get('Setpoint', default), default)


def current_temperature(channel, default=0.0):
    key = 'TempA' if str(channel).upper() == 'A' else 'TempB'
    return _float(read().get(key, default), default)


def is_locked():
    return read().get('Lock', 'Off').strip().lower() == 'on'


def lock_source():
    return read().get('Source', '')


def set_lock(source):
    """Claim the temperature controller for other apps (stored in temp.param)."""
    with _io_lock:
        data = read()
        data['Lock'] = 'On'
        data['Source'] = source
        write(data)


def clear_lock():
    """Release the temperature controller."""
    with _io_lock:
        data = read()
        data['Lock'] = 'Off'
        data['Source'] = ''
        write(data)


def acquire_lock(source):
    set_lock(source)


def release_lock():
    clear_lock()
