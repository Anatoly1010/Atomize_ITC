# Documentation handoff — session 2026-09-18

For a new session on the Windows machine (where `../atomize_docs` and the
doc generator live). Everything below changed in commit "Validate preliminary
tuning on hardware and redesign its maximize step"; read that repository's
`CLAUDE.md` before editing it.

## 1. Regenerate the step reference

```powershell
python -m atomize.epr_auto.docgen ..\atomize_docs\docs\projects\epr_auto\steps.md
```

Step schemas that changed: `tune.ringing_check` (+`field`), `tune.find_echo`
(`attenuation_db` 0–60, +`pulse_length`), `tune.maximize_echo` (rewritten:
`attenuation_db`, `amplitude_range`, `coarse_step`, `fine_step`, `pulse_map`,
`pulse_length`; `rv_range`, `coarse_step_db`, `length_range`, `length_points`
removed), `tune.save_presets` (+`field_span`, `field_points`,
`calibration_length`, `publish_dir`), new `tune.apply_calibration`
(`preset`, `pulse_map`, `destination`).

## 2. Prose pages to update (projects/epr_auto)

- Preliminary tuning: the maximize step is a fixed-RV amplitude scan (pi/2 at
  a, pi at 2a, both pulses at the operator's `pulse_length`); RV and pulse
  length are operator choices, edge maxima abort with "reduce/increase
  attenuation". Source: PRELIMINARY_TUNING_PLAN.md section 4.
- Handoff: four presets (`echo`, `calibration`, `field`, `echo_cal`), the
  Rabi pulse at `calibration_length` detected with the preliminary pair,
  `tune.apply_calibration` before the EDFS and at the end, publication to
  `tuned/` beside the protocols with an archive copy under `runs/`, EDFS over
  the `find_echo` span. The daily flow is three runs from one folder:
  `preliminary.yaml` → `tuned/fine_tuning.yaml` → an experiment protocol on
  `tuned/echo_cal.phase_awg` (`window: preset`, `apply_cal: none`). Source:
  PRELIMINARY_TUNING_PLAN.md section 5 and its implementation notes.
- Operating notes: open the bridge window before a run (it homes the vane);
  the ringing ladder runs at a nonresonant field (100 G default); worker
  stdout (FPGA library chatter) goes to `worker_stdout.log` in the run
  directory; resonator selection window 4 ns recommended.
- Do not add these to the endstation page; they belong to the epr_auto pages.

## 3. Main-window behaviour (only if the docs mention plot status)

A plot dock idle for 10 s with its source still connected shows a grey dot;
green while data flows; no dot after the source disconnects. Tooltip:
"Source connected, idle since HH:MM:SS".

## 4. Siblings

The grey-dot change is isolated in `atomize/main/main_window.py`; apply it to
the other Atomize variants with
`patches/2026-09-18_main_window_idle_plot_marks.patch` (see
`patches/README.md`).
