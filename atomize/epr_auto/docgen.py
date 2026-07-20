"""Generate the epr_auto step reference as a Markdown page for atomize_docs.

The atomize_docs site builds on GitHub Pages without Atomize installed, so
this generator runs HERE (it imports the STEPS registry) and emits a page
that is committed into the docs repo:

    python3 -m atomize.epr_auto.docgen \
        /home/anatoly/atomize_docs/docs/projects/epr_auto/steps.md

Re-run it whenever steps.py changes a step, a parameter, a default or a
help string — the page carries a do-not-edit banner for this reason.
Headless-safe: steps.py imports only the param specs at module scope.
"""
import sys

from atomize.epr_auto.steps import STEPS

FAMILIES = (
    ('tune', 'Tuning steps'),
    ('field', 'Field steps'),
    ('temp', 'Temperature steps'),
    ('exp', 'Experiment steps'),
)

HEADER = """\
# Step reference

<!-- AUTO-GENERATED — do not edit by hand.
     Regenerate from the Atomize_ITC repo:
     python3 -m atomize.epr_auto.docgen docs/projects/epr_auto/steps.md
     (run from atomize_docs' parent layout; pass the real output path) -->

Every step a protocol can name, with its parameters, defaults and
constraints — generated from the runner's own step registry, so this page
cannot drift from the code. The same listing is available offline from
`epr-auto steps`. How the steps compose into a protocol is described in
[Writing protocols](protocols.md).

A parameter marked *required* has no default and must appear in the
protocol; every other parameter may be omitted. Time and field values are
the framework-wide `"<value> <unit>"` strings (`ns/us/ms/s`, `G/mT/T`).
"""


def _type_of(param):
    t = param.typename
    lo = getattr(param, 'min', None)
    hi = getattr(param, 'max', None)
    if lo is not None or hi is not None:
        lo_s = f'{lo:g}' if lo is not None else ''
        hi_s = f'{hi:g}' if hi is not None else ''
        t += f' ({lo_s}..{hi_s})' if hi_s else f' (>= {lo_s})'
    return t


def _default_of(param):
    if param.required:
        return '*required*'
    if param.default is None:
        return '—'
    d = param.default
    if isinstance(d, str) and len(d) > 25 and '.' in d:
        stem, _, ext = d.rpartition('.')
        if stem and ext:
            # A long filename default (e.g. inversion_recovery_echo_4s_log
            # .phase_awg) makes the table cell too wide. Emit raw HTML with a
            # <wbr> break OPPORTUNITY at the extension: the name wraps only
            # when the cell is cramped and still copies as one intact string.
            # _cell touches only '|' and newlines, so this HTML survives it.
            return f'<code>{stem}<wbr>.{ext}</code>'
    return f'`{d}`'


def _cell(text):
    return str(text).replace('|', '\\|').replace('\n', ' ')


def generate():
    out = [HEADER]
    for prefix, title in FAMILIES:
        steps = {n: s for n, s in sorted(STEPS.items())
                 if n.startswith(prefix + '.')}
        if not steps:
            continue
        out.append(f'## {title}\n')
        for name, spec in steps.items():
            out.append(f'### {name}\n')
            out.append(f'{spec.summary}.\n')
            if not spec.params:
                out.append('*(no parameters)*\n')
                continue
            out.append('| Parameter | Type | Default | Description |')
            out.append('| --------- | ---- | ------- | ----------- |')
            for key, param in spec.params.items():
                out.append(f'| `{key}` | {_cell(_type_of(param))} '
                           f'| {_cell(_default_of(param))} '
                           f'| {_cell(param.help)} |')
            out.append('')
    # families must cover the whole registry — a new family added to
    # steps.py without a FAMILIES entry must fail loudly, not vanish
    covered = {n for prefix, _ in FAMILIES for n in STEPS
               if n.startswith(prefix + '.')}
    missing = sorted(set(STEPS) - covered)
    if missing:
        raise SystemExit(f'docgen: steps not covered by FAMILIES: {missing}')
    return '\n'.join(out) + '\n'


def main():
    text = generate()
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'w', encoding='utf-8') as f:
            f.write(text)
        print(f'wrote {sys.argv[1]} ({len(STEPS)} steps)')
    else:
        sys.stdout.write(text)


if __name__ == '__main__':
    main()
