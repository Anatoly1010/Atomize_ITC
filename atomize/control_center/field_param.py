#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import threading

_KEY_SEP = ':  '
_DEFAULTS = {'Field': '0', 'Lock': 'Off', 'Source': ''}
_io_lock = threading.Lock()


def path():
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'field.param')


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
    payload = {
        'Field': str(data.get('Field', _DEFAULTS['Field'])),
        'Lock': str(data.get('Lock', _DEFAULTS['Lock'])),
        'Source': str(data.get('Source', _DEFAULTS['Source'])),
    }
    content = '\n'.join(
        f'{key}{_KEY_SEP}{payload[key]}' for key in ('Field', 'Lock', 'Source')
    ) + '\n'
    temp_path = path() + '.tmp'
    with open(temp_path, 'w', encoding='utf-8') as status_file:
        status_file.write(content)
    os.replace(temp_path, path())


def write_field(field):
    with _io_lock:
        data = read()
        data['Field'] = str(field)
        write(data)


def is_locked():
    return read().get('Lock', 'Off').strip().lower() == 'on'


def current_field(default=0.0):
    try:
        return float(read().get('Field', default))
    except (TypeError, ValueError):
        return default


def lock_source():
    return read().get('Source', '')


def set_lock(source):
    """Lock field control for other apps (stored in field.param)."""
    with _io_lock:
        data = read()
        data['Lock'] = 'On'
        data['Source'] = source
        write(data)


def clear_lock():
    """Allow field control again."""
    with _io_lock:
        data = read()
        data['Lock'] = 'Off'
        data['Source'] = ''
        write(data)


def acquire_lock(source):
    set_lock(source)


def release_lock():
    clear_lock()
