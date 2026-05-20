#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import threading

_KEY_SEP = ':  '
_DEFAULTS = {'Field': '0', 'Lock': 'Off', 'Source': ''}
_lock = threading.Lock()
_lock_count = 0
_lock_source = ''

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
    with _lock:
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


def acquire_lock(source):
    global _lock_count, _lock_source
    with _lock:
        _lock_count += 1
        if _lock_count == 1:
            _lock_source = source
            data = read()
            data['Lock'] = 'On'
            data['Source'] = source
            write(data)
        elif _lock_source != source:
            _lock_source = source
            data = read()
            data['Lock'] = 'On'
            data['Source'] = source
            write(data)


def release_lock():
    global _lock_count, _lock_source
    with _lock:
        if _lock_count <= 0:
            return
        _lock_count -= 1
        if _lock_count == 0:
            data = read()
            data['Lock'] = 'Off'
            data['Source'] = ''
            write(data)
            _lock_source = ''


def clear_lock():
    global _lock_count, _lock_source
    with _lock:
        _lock_count = 0
        _lock_source = ''
        data = read()
        data['Lock'] = 'Off'
        data['Source'] = ''
        write(data)
