# Documentation handoff — evening session 2026-09-18

For a new session on the Windows machine (where `../atomize_docs` and the
doc generator live). Everything below changed in the commit that adds this
file; read that repository's `CLAUDE.md` before editing it. Delete this file
once the published pages are updated.

## 1. Regenerate the step reference

```powershell
python -m atomize.epr_auto.docgen ..\atomize_docs\docs\projects\epr_auto\steps.md
```

Only `tune.ringing_check` changed: `max_length` is renamed `pulse_length`
(the ladder's SINE pulse, default 102.4 ns) and `done` (bool, default false)
is new. No other schema changed; help texts that mentioned a length limit
are gone.

## 2. Prose pages to update (projects/epr_auto)

- Ringing check: the ladder no longer limits the pulse length of later
  steps. Only the IF and the DAC amplitudes are carried forward as limits.
  Ringing after a pulse is set by the resonator ring-down, and the protection
  timing is derived from each run's own pulse geometry. Any sentence saying
  `max_length` must cover the preliminary or calibration pulses is wrong now.
  Source: PRELIMINARY_TUNING_PLAN.md section 1.
- Ringing check: `done: true` declares that the ladder already passed at the
  same IF on the same setup. The hardware-free preflight still runs and the
  limits are recorded, but the RV, field and receiver are not touched and no
  trace is taken. Intended for a same-day rerun of the preliminary protocol.
- Resonator selection: the ringing peak is searched only after the nominal
  pulse end when `region` is omitted, because the reflected-pulse plateau at
  off-resonance frequencies can exceed the trailing-edge ringing. An explicit
  `region` is still searched in full. Source: PRELIMINARY_TUNING_PLAN.md
  section 2, step 1.
- Preset export: `calibration_length` is free (grid-snapped); the sentence
  "cannot exceed the ringing-tested maximum" goes away. It sets the length
  of the Rabi pulse and of both echo pulses in `field` and `echo_cal`, so it
  is the length a later experiment uses. Changing it requires rerunning the
  preliminary protocol; editing `tuned/calibration.phase_awg` by hand only
  changes the Rabi pulse, and the calibration is then transferred to the
  exported length by the length ratio.
- Echo search: `tune.find_echo` takes no absolute frequency, only
  `frequency_shift_mhz`. An absolute value is a `bridge.set` step with
  `frequency_mhz` before it. If the page shows the shipped
  `protocols/preliminary_tuning.yaml`, it now carries that step as a
  commented example between the resonator scan and the echo search.
- Do not add these to the endstation page; they belong to the epr_auto pages.

## 3. Example protocol

If the docs reproduce `protocols/preliminary_tuning.yaml`, replace it with
the current file: the ringing step reads `pulse_length: 102.4 ns` and the
commented `bridge.set` example is new.
