"""Fingerprint the shipped default presets so a GUI edit of one that
automation relies on is flagged at protocol-load time.

    python3 -m atomize.epr_auto.preset_hash            # verify + report
    python3 -m atomize.epr_auto.preset_hash --update   # regenerate the manifest

The list of default presets is derived from the STEPS registry (every
PresetFile parameter that carries a `default`) plus the two mode-dependent
literals in tune.pi_calibration's check function, which are not introspectable
from a Param spec. Keeping it derived means it cannot silently go stale when a
step's default changes.
"""
import sys

from atomize.epr_auto.params import (
    PRESET_DIR, PresetFile, _HASH_MANIFEST, _load_hash_manifest, _sha256_of,
)
from atomize.epr_auto.steps import STEPS

# The two mode-dependent defaults chosen inside _check_pi_calibration; they are
# plain string literals there, so they cannot be scanned off a Param spec.
_PI_CAL_DEFAULTS = ('ampl_4s.phase_awg', 'rabi_echo_4s.phase_awg')


def default_preset_names():
    """Every shipped preset a step can fall back to, derived from the registry."""
    names = set(_PI_CAL_DEFAULTS)
    for spec in STEPS.values():
        for param in spec.params.values():
            if isinstance(param, PresetFile) and param.default:
                names.add(param.default)
    return sorted(names)


def compute_hashes():
    return {name: _sha256_of(PRESET_DIR / name) for name in default_preset_names()}


def _update():
    import json
    hashes = compute_hashes()
    _HASH_MANIFEST.write_text(json.dumps(hashes, indent=2, sort_keys=True) + '\n',
                              encoding='utf-8')
    print(f'wrote {_HASH_MANIFEST} ({len(hashes)} presets)')
    for name in sorted(hashes):
        print(f'  {name}  {hashes[name][:12]}…')
    return 0


def _verify():
    manifest = _load_hash_manifest()
    if manifest is None:
        print(f'no manifest at {_HASH_MANIFEST} — run with --update to create it',
              file=sys.stderr)
        return 1
    ok = True
    for name in default_preset_names():
        recorded = manifest.get(name)
        path = PRESET_DIR / name
        if recorded is None:
            print(f'MISSING  {name}  (no manifest entry — run --update)')
            ok = False
            continue
        if not path.is_file():
            print(f'ABSENT   {name}  (file not found in {PRESET_DIR})')
            ok = False
            continue
        if _sha256_of(path) == recorded:
            print(f'OK       {name}')
        else:
            print(f'MISMATCH {name}  (differs from the shipped fingerprint)')
            ok = False
    return 0 if ok else 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == '--update':
        return _update()
    if argv:
        print(f'usage: python3 -m atomize.epr_auto.preset_hash [--update]',
              file=sys.stderr)
        return 2
    return _verify()


if __name__ == '__main__':
    sys.exit(main())
