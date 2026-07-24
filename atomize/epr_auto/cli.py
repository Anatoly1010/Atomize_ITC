"""Command-line entry point.

    python -m atomize.epr_auto run <protocol.yaml> --test   # dry-run, no hardware
    python -m atomize.epr_auto run <protocol.yaml>           # live (GUI open first)
    python -m atomize.epr_auto validate <protocol.yaml>
    python -m atomize.epr_auto steps                         # list available steps

Ordering inside run() is load-bearing:
  1. sys.argv is rewritten to ['...', 'test'|'None'] BEFORE anything imports
     atomize.general_modules or a device module (both read argv[1] to pick
     test mode) — cli/protocol/steps deliberately never import them.
  2. The protocol is loaded (resolving preset paths) BEFORE chdir.
  3. cwd is switched to Atomize_ITC/libs — the Insys driver reads brd.ini /
     exam_adc.ini relative to cwd at instantiation time.
"""
import argparse
import os
import sys
from pathlib import Path

import atomize

from atomize.epr_auto.protocol import ProtocolError, load_protocol
from atomize.epr_auto.steps import STEPS

EXIT_OK, EXIT_INVALID, EXIT_ABORTED, EXIT_UNSUPPORTED = 0, 1, 2, 3


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='epr-auto', description='Automated pulsed-EPR protocol runner (Atomize/ITC)')
    sub = parser.add_subparsers(dest='command', required=True)

    p_run = sub.add_parser('run', help='execute a protocol')
    p_run.add_argument('protocol', help='path to a protocol .yaml file')
    p_run.add_argument('--test', action='store_true',
                       help='dry-run against test-mode devices (no hardware, no GUI needed)')

    p_val = sub.add_parser('validate', help='validate a protocol without running it')
    p_val.add_argument('protocol')

    sub.add_parser('steps', help='list available protocol steps and their parameters')

    args = parser.parse_args(argv)

    if args.command == 'steps':
        return _list_steps()
    if args.command == 'validate':
        return _validate(args.protocol)
    return _run(args.protocol, args.test)


def _list_steps():
    for name in sorted(STEPS):
        spec = STEPS[name]
        print(f'{name}\n    {spec.summary}')
        if not spec.params:
            print('    (no parameters)')
        for key, param in spec.params.items():
            help_text = f' — {param.help}' if param.help else ''
            print(f'    {key}: {param.describe()}{help_text}')
        print()
    return EXIT_OK


def _validate(protocol_path):
    try:
        protocol = load_protocol(protocol_path)
    except ProtocolError as e:
        print(f'INVALID: {e}', file=sys.stderr)
        return EXIT_INVALID
    names = [f'foreach[{it.var}]' if hasattr(it, 'var') else it.name
             for it in protocol.steps]
    print(f'OK: {protocol.path.name} — sample {protocol.sample!r}, '
          f'autonomy {protocol.autonomy}, {len(protocol.steps)} entries '
          f'({", ".join(names)})')
    for w in protocol.warnings:
        print(f'warning: {w}')
    return EXIT_OK


def _run(protocol_path, test):
    # argv[1] is the framework-wide mode flag: general_functions and every
    # device module read it at import/instantiation time. 'test' selects the
    # canned-device branch; 'None' mirrors their own no-argument fallback and
    # selects live hardware. Must be set before those imports happen below.
    sys.argv = [sys.argv[0], 'test' if test else 'None']

    try:
        protocol = load_protocol(protocol_path)
    except ProtocolError as e:
        print(f'INVALID: {e}', file=sys.stderr)
        return EXIT_INVALID

    # Device modules read their configs from the user config store, which is
    # normally provisioned by the main window on GUI startup; re-establish
    # that invariant here (no-op when the store already exists).
    import atomize.main.local_config as lconf
    pkg = Path(atomize.__file__).resolve().parent
    lconf.copy_config(str(pkg / 'config.ini'), str(pkg / 'device_modules' / 'config'))

    libs = pkg.parent / 'libs'
    if not libs.is_dir():
        print(f'Cannot find the libs/ directory (looked at {libs}); '
              'the Insys driver needs cwd=libs.', file=sys.stderr)
        return EXIT_ABORTED
    invoke_dir = Path.cwd()   # relative output templates resolve against this
    os.chdir(libs)

    from atomize.epr_auto.runner import RunnerAbort, run_protocol
    from atomize.epr_auto.session import EPRSession

    session = EPRSession(sample=protocol.sample, autonomy=protocol.autonomy,
                         test=test, output=protocol.output, notify=protocol.notify,
                         base_dir=invoke_dir)
    try:
        run_protocol(protocol, session)
    except RunnerAbort as e:
        print(f'ABORTED: {e}', file=sys.stderr)
        return EXIT_ABORTED
    except KeyboardInterrupt:
        print('\nABORTED: interrupted by operator', file=sys.stderr)
        return EXIT_ABORTED
    finally:
        # belt to the session's atexit braces: free the field/temp locks the
        # moment the run ends, not at interpreter shutdown
        session.release_hardware_locks()
    return EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
