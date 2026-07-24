"""YAML protocol loading and validation.

Every validation error is a ProtocolError carrying '<file>:<line>: message',
using line numbers attached to mappings/sequences at parse time.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from atomize.epr_auto.params import ParamError
from atomize.epr_auto.steps import STEPS

AUTONOMY_MODES = ('supervised', 'checkpointed', 'autonomous')
NOTIFY_MODES = ('none', 'telegram')
ON_FAIL_MODES = ('abort', 'skip', 'ask')
FOREACH_FAIL_MODES = ('continue', 'abort')   # per-iteration policy of a foreach
_TOP_KEYS = ('sample', 'autonomy', 'output', 'notify', 'steps')
_FOREACH_KEYS = ('var', 'values', 'steps', 'on_fail')
_VAR_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_VAR_REF_RE = re.compile(r'\$([A-Za-z_][A-Za-z0-9_]*)')


class ProtocolError(Exception):
    def __init__(self, path, line, msg):
        loc = f'{path}:{line}' if line else str(path)
        super().__init__(f'{loc}: {msg}')


class _LineDict(dict):
    line = None


class _LineList(list):
    line = None


class _LineLoader(yaml.SafeLoader):
    """SafeLoader that stamps 1-based source lines onto maps and sequences,
    and rejects duplicate mapping keys (stock YAML silently keeps the last)."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in seen
            except TypeError:  # unhashable key; SafeLoader rejects it itself
                continue
            if duplicate:
                raise yaml.constructor.ConstructorError(
                    None, None, f'duplicate key {key!r}', key_node.start_mark)
            seen.add(key)
        return super().construct_mapping(node, deep=deep)

    def _construct_marked(self, cls, construct, node):
        data = cls()
        data.line = node.start_mark.line + 1
        yield data
        if cls is _LineDict:
            data.update(construct(node))
        else:
            data.extend(construct(node))
            # Per-item lines: a scalar item ("- tune.auto_phase") carries no
            # mark of its own, so errors for it need the sequence's records.
            data.item_lines = [child.start_mark.line + 1 for child in node.value]


_LineLoader.add_constructor(
    'tag:yaml.org,2002:map',
    lambda self, node: self._construct_marked(_LineDict, self.construct_mapping, node))
_LineLoader.add_constructor(
    'tag:yaml.org,2002:seq',
    lambda self, node: self._construct_marked(_LineList, self.construct_sequence, node))


@dataclass
class Step:
    name: str
    params: dict
    checkpoint: bool
    line: int
    retries: int = 0            # extra attempts after the first failure
    on_fail: str = 'abort'      # after all attempts: abort | skip | ask


@dataclass
class Foreach:
    """A series block: run `steps` once per value of `var`, with `$var`
    substituted into the sub-steps' string parameters. Sub-steps are fully
    parsed and validated per value at load time (one inner list per value), so
    a typo in a substituted parameter is caught before the run. on_fail:
    'continue' (default) records a failed iteration and moves to the next value
    — a dead field/temperature position must not kill the series; 'abort'
    propagates like the global policy."""
    var: str
    values: list                # loop values, as strings (stamped into names)
    iterations: list            # list[list[Step]] — one validated group per value
    line: int
    on_fail: str = 'continue'


@dataclass
class Protocol:
    path: Path
    sample: str
    autonomy: str
    output: str | None          # run-dir template; {date} and {sample} expand
    notify: str = 'none'        # none | telegram (general.bot_message)
    steps: list = field(default_factory=list)   # Step | Foreach entries
    warnings: list = field(default_factory=list)  # non-fatal load-time advisories


def load_protocol(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ProtocolError(path, None, 'file not found')
    try:
        doc = yaml.load(path.read_text(encoding='utf-8'), Loader=_LineLoader)
    except yaml.YAMLError as e:
        mark = getattr(e, 'problem_mark', None)
        raise ProtocolError(path, mark.line + 1 if mark else None,
                            f'YAML parse error: {e}') from None

    if not isinstance(doc, dict):
        raise ProtocolError(path, 1, 'protocol must be a YAML mapping')
    top_line = getattr(doc, 'line', 1)

    for key in doc:
        if key not in _TOP_KEYS:
            raise ProtocolError(path, top_line,
                                f"unknown top-level key {key!r} (allowed: {', '.join(_TOP_KEYS)})")

    sample = doc.get('sample')
    if not isinstance(sample, str) or not sample:
        raise ProtocolError(path, top_line, "'sample' (non-empty string) is required")

    autonomy = doc.get('autonomy', 'supervised')
    if autonomy not in AUTONOMY_MODES:
        raise ProtocolError(path, top_line,
                            f"autonomy must be one of: {', '.join(AUTONOMY_MODES)}; got {autonomy!r}")

    output = doc.get('output')
    if output is not None:
        if not isinstance(output, str):
            raise ProtocolError(path, top_line, f"'output' must be a string, got {output!r}")
        try:  # session.run_dir only expands these two — catch typos at load,
            # not at run start (a dry-run never evaluates the template)
            output.format(date='', sample='')
        except (KeyError, IndexError, ValueError) as e:
            raise ProtocolError(
                path, top_line,
                "'output' template: only {date} and {sample} placeholders "
                f'are supported ({e})') from None

    notify = doc.get('notify', 'none')
    if notify not in NOTIFY_MODES:
        raise ProtocolError(path, top_line,
                            f"notify must be one of: {', '.join(NOTIFY_MODES)}; got {notify!r}")

    raw_steps = doc.get('steps')
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ProtocolError(path, top_line, "'steps' (non-empty list) is required")

    # ctx threads through every step's validation. 'warnings' collects
    # non-fatal advisories (default-preset integrity, step-order lint);
    # '_warned_presets' dedupes the integrity warning to once per name.
    ctx = {'protocol_dir': path.parent, 'warnings': [], '_warned_presets': set()}
    item_lines = getattr(raw_steps, 'item_lines', [top_line] * len(raw_steps))
    steps = [_parse_item(path, item, item_lines[i], ctx)
             for i, item in enumerate(raw_steps)]
    _lint_step_order(steps, ctx['warnings'])
    return Protocol(path=path, sample=sample, autonomy=autonomy, output=output,
                    notify=notify, steps=steps, warnings=ctx['warnings'])


def _lint_step_order(steps, warnings):
    """Warn on statically dead step orders. (1) a phase/amplitude tuning step
    before any field.* step: on a cold start there is no echo to tune on
    unless the magnet was already parked on the line. (2) rep_rate: auto with
    no earlier tune.rep_rate: exp.* resolves it at run time and aborts. Walks
    execution order; a foreach block's body is walked in place (once — every
    iteration has the same step order)."""
    field_seen = [False]
    rep_rate_seen = [False]

    def walk(items):
        for it in items:
            if isinstance(it, Foreach):
                walk(it.iterations[0] if it.iterations else [])
                continue
            if it.name == 'tune.rep_rate':
                rep_rate_seen[0] = True
            if it.name.startswith('field.'):
                field_seen[0] = True
            elif it.name in ('tune.auto_phase', 'tune.pi_calibration',
                             'tune.power_for_length') \
                    and not field_seen[0]:
                warnings.append(
                    f'{it.name} (line {it.line}) runs before any field.* step '
                    '— on a cold start there may be no echo to tune on; make '
                    'sure the magnet is already parked on the line')
            if it.params.get('rep_rate') == 'auto' and not rep_rate_seen[0]:
                warnings.append(
                    f'{it.name} (line {it.line}) uses rep_rate: auto with no '
                    'earlier tune.rep_rate step — the run will abort resolving '
                    'it; add a tune.rep_rate first or set an explicit rate')

    walk(steps)


def _parse_item(path, item, fallback_line, ctx):
    """A steps-list entry: either a foreach block or an ordinary step."""
    line = getattr(item, 'line', fallback_line)
    if isinstance(item, dict) and len(item) == 1 and next(iter(item)) == 'foreach':
        return _parse_foreach(path, item['foreach'], line, ctx)
    return _parse_step(path, item, fallback_line, ctx)


def _apply_subst(raw, subst):
    """Replace every `$var` reference in string leaves (recursing into
    lists/mappings, so `range: [$LO, $HI]` and nested params substitute too);
    non-strings pass through untouched. References are matched as whole names
    (`$B` never fires inside `$Bank`), and an unmatched `$name` raises — a
    typo'd variable must fail at load, not flow into validation as a literal
    `$X` string."""
    if isinstance(raw, str):
        def repl(m):
            name = m.group(1)
            if name not in subst:
                raise ParamError(
                    f'unresolved ${name} (foreach defines: '
                    f'{", ".join("$" + v for v in subst)})')
            return subst[name]
        return _VAR_REF_RE.sub(repl, raw)
    if isinstance(raw, list):
        return [_apply_subst(x, subst) for x in raw]
    if isinstance(raw, dict):
        return {k: _apply_subst(v, subst) for k, v in raw.items()}
    return raw


def _parse_foreach(path, spec, line, ctx):
    if not isinstance(spec, dict):
        raise ProtocolError(path, line, "foreach must be a mapping "
                            "(var / values / steps [/ on_fail])")
    for key in spec:
        if key not in _FOREACH_KEYS:
            raise ProtocolError(path, line, f"foreach: unknown key {key!r} "
                                f"(allowed: {', '.join(_FOREACH_KEYS)})")
    var = spec.get('var')
    if not isinstance(var, str) or not _VAR_RE.match(var):
        raise ProtocolError(path, line, "foreach 'var' must be a name "
                            "(letters/digits/underscore, not starting with a digit)")
    values = spec.get('values')
    if not isinstance(values, list) or not values:
        raise ProtocolError(path, line, "foreach 'values' (non-empty list) is required")
    values = [v if isinstance(v, str) else _scalar_str(path, line, var, v)
              for v in values]
    on_fail = spec.get('on_fail', 'continue')
    if on_fail not in FOREACH_FAIL_MODES:
        raise ProtocolError(path, line, "foreach on_fail must be one of: "
                            f"{', '.join(FOREACH_FAIL_MODES)}; got {on_fail!r}")
    raw_sub = spec.get('steps')
    if not isinstance(raw_sub, list) or not raw_sub:
        raise ProtocolError(path, line, "foreach 'steps' (non-empty list) is required")
    sub_lines = getattr(raw_sub, 'item_lines', [line] * len(raw_sub))
    iterations = []
    for val in values:
        group = [_parse_step(path, it, sub_lines[i], ctx, subst={var: val})
                 for i, it in enumerate(raw_sub)]
        iterations.append(group)
    return Foreach(var=var, values=values, iterations=iterations, line=line,
                   on_fail=on_fail)


def _scalar_str(path, line, var, v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ProtocolError(path, line, f"foreach 'values' must be scalars "
                            f"(string/number); {var} got {v!r}")
    return str(v)


def _parse_step(path, item, fallback_line, ctx, subst=None):
    line = getattr(item, 'line', fallback_line)
    if isinstance(item, str):  # shorthand: "- tune.auto_phase"
        name, raw_params = item, {}
    elif isinstance(item, dict) and len(item) == 1:
        name, raw_params = next(iter(item.items()))
        if raw_params is None:
            raw_params = {}
        if not isinstance(raw_params, dict):
            raise ProtocolError(path, line, f'parameters of {name!r} must be a mapping')
    else:
        raise ProtocolError(path, line,
                            'each step must be a single "name: {params}" mapping '
                            '(check the indentation of the parameters)')

    if name == 'foreach':
        raise ProtocolError(path, line, 'foreach cannot be nested')

    spec = STEPS.get(name)
    if spec is None:
        raise ProtocolError(path, line,
                            f"unknown step {name!r} (available: {', '.join(sorted(STEPS))})")

    raw_params = dict(raw_params)
    checkpoint = raw_params.pop('checkpoint', False)
    if not isinstance(checkpoint, bool):
        raise ProtocolError(path, line, f'checkpoint must be true/false, got {checkpoint!r}')
    retries = raw_params.pop('retries', 0)
    if not isinstance(retries, int) or isinstance(retries, bool) or retries < 0:
        raise ProtocolError(path, line, f'retries must be an integer >= 0, got {retries!r}')
    on_fail = raw_params.pop('on_fail', 'abort')
    if on_fail not in ON_FAIL_MODES:
        raise ProtocolError(path, line,
                            f"on_fail must be one of: {', '.join(ON_FAIL_MODES)}; got {on_fail!r}")

    for key in raw_params:
        if key not in spec.params:
            valid = ', '.join(sorted(spec.params)) or '(none)'
            raise ProtocolError(path, line,
                                f'[{name}] unknown parameter {key!r} (valid: {valid})')

    params = {}
    for key, param in spec.params.items():
        try:
            if key in raw_params:
                raw = raw_params[key]
                if subst:              # foreach: $var -> this iteration's value
                    raw = _apply_subst(raw, subst)
                params[key] = param.validate(raw, ctx)
            elif param.required:
                raise ParamError('required parameter is missing')
            elif param.default is not None:
                # a step default preset resolves from the shipped set only
                # (is_default), never the user preset dir
                params[key] = param.validate(param.default, {**ctx, 'is_default': True})
            else:
                params[key] = None
        except ParamError as e:
            raise ProtocolError(path, line, f'[{name}] {key}: {e}') from None

    if spec.check is not None:
        try:
            spec.check(params, ctx)
        except ParamError as e:
            raise ProtocolError(path, line, f'[{name}] {e}') from None

    return Step(name=name, params=params, checkpoint=checkpoint, line=line,
                retries=retries, on_fail=on_fail)
