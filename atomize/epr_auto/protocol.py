"""YAML protocol loading and validation.

Every validation error is a ProtocolError carrying '<file>:<line>: message',
using line numbers attached to mappings/sequences at parse time.
"""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from atomize.epr_auto.params import ParamError
from atomize.epr_auto.steps import STEPS

AUTONOMY_MODES = ('supervised', 'checkpointed', 'autonomous')
NOTIFY_MODES = ('none', 'telegram')
ON_FAIL_MODES = ('abort', 'skip', 'ask')
_TOP_KEYS = ('sample', 'autonomy', 'output', 'notify', 'steps')


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
class Protocol:
    path: Path
    sample: str
    autonomy: str
    output: str | None          # run-dir template; {date} and {sample} expand
    notify: str = 'none'        # none | telegram (general.bot_message)
    steps: list = field(default_factory=list)


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

    ctx = {'protocol_dir': path.parent}
    item_lines = getattr(raw_steps, 'item_lines', [top_line] * len(raw_steps))
    steps = [_parse_step(path, item, item_lines[i], ctx)
             for i, item in enumerate(raw_steps)]
    return Protocol(path=path, sample=sample, autonomy=autonomy, output=output,
                    notify=notify, steps=steps)


def _parse_step(path, item, fallback_line, ctx):
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
                params[key] = param.validate(raw_params[key], ctx)
            elif param.required:
                raise ParamError('required parameter is missing')
            elif param.default is not None:
                params[key] = param.validate(param.default, ctx)
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
