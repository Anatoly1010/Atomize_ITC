#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import threading

_KEY_SEP = ':  '
_KEYS = ('Frequency', 'Rotary Vane', 'Lock', 'Source')
_DEFAULTS = {'Frequency': '9700', 'Rotary Vane': '60.0', 'Lock': 'Off', 'Source': ''}
_io_lock = threading.Lock()


def path():
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'bridge.param')


def _parse_line(line):
    line = line.strip()
    if not line:
        return None, None
    if _KEY_SEP in line:
        key, value = line.split(_KEY_SEP, 1)
    elif ':' in line:
        key, value = line.split(':', 1)
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
    content = '\n'.join(
        f'{key}{_KEY_SEP}{data.get(key, _DEFAULTS[key])}' for key in _KEYS
    ) + '\n'
    temp_path = path() + '.tmp'
    with open(temp_path, 'w', encoding='utf-8') as status_file:
        status_file.write(content)
    os.replace(temp_path, path())


def is_locked():
    return read().get('Lock', 'Off').strip().lower() == 'on'


def lock_source():
    return read().get('Source', '')


def current_frequency(default=0):
    try:
        return int(float(read().get('Frequency', default)))
    except (TypeError, ValueError):
        return default


def current_vane_db(default=60.0):
    try:
        return float(read().get('Rotary Vane', default))
    except (TypeError, ValueError):
        return default


def set_lock(source):
    """Lock bridge control for other apps (stored in bridge.param)."""
    with _io_lock:
        data = read()
        data['Lock'] = 'On'
        data['Source'] = source
        write(data)


def clear_lock():
    """Allow bridge control again."""
    with _io_lock:
        data = read()
        data['Lock'] = 'Off'
        data['Source'] = ''
        write(data)
