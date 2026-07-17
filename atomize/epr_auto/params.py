"""Parameter specs and validators for protocol steps.

Self-contained on purpose: no atomize.general_modules / device imports, so
protocol validation runs headless before test/real mode is decided.
Time and field values follow the framework-wide '<float> <unit>' string form.
"""
from pathlib import Path

import atomize

PRESET_DIR = Path(atomize.__file__).resolve().parent / 'control_center' / 'experiments'

_TIME_NS = {'ps': 1e-3, 'ns': 1.0, 'us': 1e3, 'ms': 1e6, 's': 1e9, 'ks': 1e12}
_FIELD_G = {'G': 1.0, 'mT': 10.0, 'T': 1e4}


class ParamError(ValueError):
    pass


def parse_time_ns(value):
    return _parse_quantity(value, _TIME_NS, 'time')


def parse_field_g(value):
    return _parse_quantity(value, _FIELD_G, 'field')


def _parse_quantity(value, units, kind):
    if not isinstance(value, str):
        raise ParamError(f'expected a "<value> <unit>" string, got {value!r}')
    parts = value.split()
    if len(parts) != 2:
        raise ParamError(f'{kind} must be "<value> <unit>", got {value!r}')
    num, unit = parts
    if unit not in units:
        raise ParamError(f"unknown {kind} unit {unit!r} (use one of: {', '.join(units)})")
    try:
        magnitude = float(num)
    except ValueError:
        raise ParamError(f'bad numeric value {num!r} in {value!r}') from None
    return magnitude * units[unit]


class Param:
    typename = 'value'

    def __init__(self, help='', required=False, default=None):
        self.help = help
        self.required = required
        self.default = default

    def validate(self, value, ctx):
        raise NotImplementedError

    def describe(self):
        if self.required:
            return f'{self.typename}, required'
        if self.default is not None:
            return f'{self.typename} [{self.default}]'
        return f'{self.typename}, optional'


class TimeStr(Param):
    typename = 'time ("300 ns")'

    def validate(self, value, ctx):
        ns = parse_time_ns(value)
        if ns <= 0:
            raise ParamError(f'time must be positive, got {value!r}')
        return ' '.join(value.split())


class FieldStr(Param):
    typename = 'field ("3478 G")'

    def __init__(self, signed=False, **kw):
        super().__init__(**kw)
        self.signed = signed
        if signed:
            self.typename = 'field offset ("-15 G")'

    def validate(self, value, ctx):
        if parse_field_g(value) < 0 and not self.signed:
            raise ParamError(f'field must be non-negative, got {value!r}')
        return ' '.join(value.split())


class Int(Param):
    typename = 'integer'

    def __init__(self, min=None, max=None, **kw):
        super().__init__(**kw)
        self.min, self.max = min, max

    def validate(self, value, ctx):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ParamError(f'expected an integer, got {value!r}')
        if self.min is not None and value < self.min:
            raise ParamError(f'must be >= {self.min}, got {value}')
        if self.max is not None and value > self.max:
            raise ParamError(f'must be <= {self.max}, got {value}')
        return value


class Float(Param):
    typename = 'number'

    def __init__(self, min=None, max=None, **kw):
        super().__init__(**kw)
        self.min, self.max = min, max

    def validate(self, value, ctx):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ParamError(f'expected a number, got {value!r}')
        value = float(value)
        if self.min is not None and value < self.min:
            raise ParamError(f'must be >= {self.min}, got {value}')
        if self.max is not None and value > self.max:
            raise ParamError(f'must be <= {self.max}, got {value}')
        return value


class Bool(Param):
    typename = 'boolean'

    def validate(self, value, ctx):
        if not isinstance(value, bool):
            raise ParamError(f'expected true/false, got {value!r}')
        return value


class Str(Param):
    typename = 'string'

    def validate(self, value, ctx):
        if not isinstance(value, str):
            raise ParamError(f'expected a string, got {value!r}')
        return value


class Choice(Param):
    def __init__(self, *options, **kw):
        super().__init__(**kw)
        self.options = options
        self.typename = ' | '.join(options)

    def validate(self, value, ctx):
        if value not in self.options:
            raise ParamError(f"must be one of: {', '.join(self.options)}; got {value!r}")
        return value


class AutoOr(Param):
    """The literal string 'auto', or a value validated by `inner`."""

    def __init__(self, inner, **kw):
        super().__init__(**kw)
        self.inner = inner
        self.typename = f"'auto' | {inner.typename}"

    def validate(self, value, ctx):
        if value == 'auto':
            return 'auto'
        return self.inner.validate(value, ctx)


class PairOf(Param):
    """A two-element list, each element validated by `inner` (e.g. a field range)."""

    def __init__(self, inner, **kw):
        super().__init__(**kw)
        self.inner = inner
        self.typename = f'[{inner.typename}, {inner.typename}]'

    def validate(self, value, ctx):
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ParamError(f'expected a two-element list, got {value!r}')
        return [self.inner.validate(v, ctx) for v in value]


class CalMap(Param):
    """apply_cal slot -> role mapping, e.g. {P2: pi2, P3: pi}: which pulse
    slots receive the calibrated pi / pi2 value (amplitude or grid-quantized
    length, by the calibration's mode)."""

    typename = 'mapping {P2..P9: pi | pi2}'
    _SLOTS = tuple(f'P{i}' for i in range(2, 10))

    def validate(self, value, ctx):
        if not isinstance(value, dict) or not value:
            raise ParamError('expected a non-empty mapping like '
                             f'{{P2: pi2, P3: pi}}, got {value!r}')
        out = {}
        for k, v in value.items():
            key = str(k).upper()
            if key not in self._SLOTS:
                raise ParamError(f'slot must be one of P2..P9, got {k!r}')
            if v not in ('pi', 'pi2'):
                raise ParamError(f"role must be 'pi' or 'pi2', got {v!r} for {key}")
            out[key] = v
        return out


class PresetFile(Param):
    """A pulse-sequence preset. Bare names resolve against the protocol's
    directory first, then atomize/control_center/experiments/. Returns the
    resolved absolute path."""

    typename = 'preset file'

    def __init__(self, extensions=('.phase_awg',), **kw):
        super().__init__(**kw)
        self.extensions = extensions

    def validate(self, value, ctx):
        if not isinstance(value, str):
            raise ParamError(f'expected a preset filename, got {value!r}')
        p = Path(value)
        if p.suffix not in self.extensions:
            raise ParamError(f"preset {value!r} must have extension {' or '.join(self.extensions)}")
        candidates = [p] if p.is_absolute() else [ctx['protocol_dir'] / p, PRESET_DIR / p]
        for c in candidates:
            if c.is_file():
                return str(c.resolve())
        looked = ' , '.join(str(c) for c in candidates)
        raise ParamError(f'preset file {value!r} not found (looked in: {looked})')
