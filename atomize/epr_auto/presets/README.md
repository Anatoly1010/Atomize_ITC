# User preset directory

This is the **user preset space** for the EPR automation layer. Pulse-sequence
presets you save here (`*.phase_awg`, `*.phase`) are found by **bare name** in
a protocol:

```yaml
steps:
  - exp.t2:
      preset: my_t2.phase_awg   # resolved from this directory
```

## Resolution order

For an **explicitly named** preset (a `preset:` you wrote in the protocol) the
runner searches, in order:

1. the protocol file's own directory,
2. **this directory** (`atomize/epr_auto/presets/`),
3. the shipped set (`atomize/control_center/experiments/`).

For a step **default** (the `preset:` you left out, so the step falls back to
its built-in default such as `hahn_echo_4s.phase_awg`) resolution is the
**shipped set only** — a file dropped here can never shadow a default that
automation relies on.

## Why save here

The AWG phasing GUI saves presets into `atomize/control_center/experiments/` —
the same folder that holds the shipped defaults. Saving a GUI edit of a shipped
preset there **overwrites the original** that automation falls back to. Instead:

- save GUI edits **under a new name in this directory**, and
- reference that new name from your protocol.

If a shipped default's bytes ever differ from the fingerprint recorded in
`atomize/epr_auto/default_preset_hashes.json`, the runner prints a warning at
load time (restore it with `git`, or move your custom preset here under a new
name). Regenerate that fingerprint file with
`python3 -m atomize.epr_auto.preset_hash --update` if you deliberately change a
shipped default.

Presets you save here are git-ignored (only this README is tracked), so your
sample-specific presets do not clutter the repository.
