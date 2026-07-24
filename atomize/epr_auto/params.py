"""Parameter specs and validators for protocol steps.

Self-contained on purpose: no atomize.general_modules / device imports, so
protocol validation runs headless before test/real mode is decided.
Time and field values follow the framework-wide '<float> <unit>' string form.
"""
import hashlib
import json
from pathlib import Path

import atomize

PRESET_DIR = Path(atomize.__file__).resolve().parent / 'control_center' / 'experiments'
# User preset space: presets a protocol author saves for themselves. Bare names
# in a protocol resolve here (after the protocol's own dir, before the shipped
# experiments set); step DEFAULTS always come from the shipped set only.
USER_PRESET_DIR = Path(__file__).resolve().parent / 'presets'
# sha256 fingerprints of the shipped default presets, so a GUI edit of one that
# automation relies on is flagged at load time. Regenerate with
#   python3 -m atomize.epr_auto.preset_hash --update
_HASH_MANIFEST = Path(__file__).resolve().parent / 'default_preset_hashes.json'
_MISSING = object()

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
        if isinstance(value, str):
            try:                            # foreach $var leaves arrive as strings
                value = int(value)
            except ValueError:
                raise ParamError(f'expected an integer, got {value!r}')
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
        if isinstance(value, str):
            try:                            # foreach $var leaves arrive as strings
                value = float(value)
            except ValueError:
                raise ParamError(f'expected a number, got {value!r}')
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
    length, by the calibration's mode). The literal 'none' opts out: run the
    preset's stored values even though a pi_calibration exists (omitting the
    parameter means infer the map from the preset's amplitude levels)."""

    typename = "mapping {P2..P9: pi | pi2} | 'none'"
    _SLOTS = tuple(f'P{i}' for i in range(2, 10))

    def validate(self, value, ctx):
        if value == 'none':
            return 'none'
        if not isinstance(value, dict) or not value:
            raise ParamError("expected 'none' or a non-empty mapping like "
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
    """A pulse-sequence preset. Returns the resolved absolute path.

    Resolution depends on whether the value is user-supplied or a step
    *default* (signalled by ctx['is_default'], set by protocol.py when it
    falls back to the parameter's default):

    - a user-supplied bare name resolves against the protocol's directory
      first, then the user preset space (atomize/epr_auto/presets/), then the
      shipped set (atomize/control_center/experiments/);
    - a step default resolves against the shipped set ONLY, so a user preset
      dropped into presets/ can never shadow the preset automation falls back
      to. When a shipped default's bytes differ from the recorded fingerprint
      (a GUI save overwrote it), a warning is queued on ctx['warnings'].

    An absolute path is taken as-is.
    """

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
        is_default = ctx.get('is_default')
        if p.is_absolute():
            candidates = [p]
        elif is_default:
            candidates = [PRESET_DIR / p]
        else:
            candidates = [ctx['protocol_dir'] / p, USER_PRESET_DIR / p, PRESET_DIR / p]
        for c in candidates:
            if c.is_file():
                resolved = c.resolve()
                if is_default:
                    _check_default_integrity(resolved, ctx)
                return str(resolved)
        looked = ' , '.join(str(c) for c in candidates)
        raise ParamError(f'preset file {value!r} not found (looked in: {looked})')


def _sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_hash_manifest():
    try:
        return json.loads(_HASH_MANIFEST.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None   # missing/corrupt manifest -> integrity check is a no-op


def _check_default_integrity(resolved, ctx):
    """Queue a warning if a shipped default preset differs from its recorded
    sha256. Warn once per protocol per preset name. A missing manifest, a
    missing entry, or an unreadable file is silently skipped — an integrity
    check must never break validation."""
    warnings = ctx.get('warnings')
    if warnings is None:
        return
    fname = Path(resolved).name
    warned = ctx.setdefault('_warned_presets', set())
    if fname in warned:
        return
    manifest = ctx.get('_preset_hashes', _MISSING)
    if manifest is _MISSING:
        manifest = _load_hash_manifest()
        ctx['_preset_hashes'] = manifest
    if not manifest:
        return
    expected = manifest.get(fname)
    if expected is None:
        return
    try:
        actual = _sha256_of(resolved)
    except OSError:
        return
    if actual != expected:
        warned.add(fname)
        warnings.append(
            f"default preset {fname!r} differs from the shipped version "
            "(edited in the GUI?) — the run will use the modified file; "
            "restore it with git, or save custom presets into "
            "atomize/epr_auto/presets/ under a new name")
