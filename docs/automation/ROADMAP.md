# EPR Experiment Automation — Roadmap & Session Log

Working agreement for multi-session development: each session picks the next
unchecked item(s), updates this file before ending, and notes anything that
needs the lab machine / real hardware under **Pending hardware validation**.
Design decisions live in [ARCHITECTURE.md](ARCHITECTURE.md) — update it when a
decision changes, don't fork it here.

Model workflow: most items are Opus-suitable (the constraints are written down);
items tagged **[F]** involve subtle extraction/hardware semantics — prefer Fable
there, and run `/code-review` (Fable) after Opus implementation sessions.

## Phase 0 — Scaffold (no hardware) — DONE 2026-07-16
- [x] Architecture + roadmap docs (2026-07-16)
- [x] Package skeleton `atomize/epr_auto/` with `cli.py` entry point
      (`python -m atomize.epr_auto run <yaml> [--test]`; also `validate`,
      `steps`; `epr-auto` console script appears after next `pip install -e .`)
- [x] Protocol schema + loader + validation errors that name the YAML line
      (line-stamping SafeLoader; step specs declared in `steps.py`)
- [x] `--test` dry-run: whole protocol executes against test-mode devices
      (lazy Insys/Micran/BH_15 in session; canned results marked `canned: True`)

## Phase 1 — Engine (reuse awg_phasing_insys Worker) — DONE 2026-07-16
Design change vs the original plan: instead of extracting the sequence/scan
code, the engine REUSES `awg_phasing_insys.Worker` directly (the class the GUI
itself pickles into a Process — GUI-free, hardware-validated). The engine
reproduces only the GUI's snapshot pipeline.
- [x] **[F]** `engine/snapshot.py`: `.phase_awg` preset → exact Worker argument
      tuples (grid snap, ns/MHz strings, phase-cycle expansion via the GUI's
      own `expand_phase_cycling`, deg→rad, window ns→points, TimeLogSpinBox
      log-grid quantization)
- [x] **[F]** `engine/executor.py`: runs Worker.exp/exp_log/exp_amplitude/
      exp_field in a child process, speaks the pipe protocol (Status/Message/
      Error/Open→'FL<path>'/test/exit); scan loop + readout stay in Worker
- [x] Equivalence check: `~/epr_auto_dev/gui_vs_engine.py` drives the REAL GUI
      headless (offscreen), captures `dig_start_exp`'s Process args per preset,
      compares element-wise vs the engine — **ALL 13 presets PASS** across all
      four sweep types; executor pre-flight (`script_test=True`) runs clean
      end-to-end for all four. **Re-run this harness after ANY change to the
      GUI snapshot pipeline or engine/snapshot.py.**
- [x] 'ESEEM Avg' sweep (exp_eseem: eseem_inc2/cycles/save_each tail) and
      LASER presets (laser_flag/laser_num + Nd:YaG 9.9 Hz rep-rate forcing) —
      equivalence-tested via synthetic presets the harness derives at runtime
      (none exist on disk); executor pre-flight clean (2026-07-16)
- Status of the original "not covered" list (updated 2026-07-17):
      resonator-correction overrides → engine side DONE (review fix: WorkerArgs
      correction fields + executor hand-off; YAML plumbing still backlog);
      per-cycle 'Save each' naming → NOT a gap (review-refuted: the Worker
      derives `_cycle{n}.csv` names internally from the single path and sends
      exactly one 'Open' — the executor's single save_path answer is correct);
      live 'SC' resize → still uncovered, not needed for protocol runs (scan
      count is fixed up front) — future hook for judge-driven adaptive scan
      control in autonomous mode (backlog).

## Phase 2 — Tuning primitives + judges — code DONE 2026-07-17 (needs hardware)
- [x] `tune.auto_phase` (short echo run via the engine → principal-axis
      `auto_phase_zero` → `zero_order_new = (used − φ) mod 360`; the corrected
      zero-order flows into every later build via session state)
- [x] `tune.pi_calibration`, two modes: amplitude sweep (default,
      `ampl_4s.phase_awg` — the swept pulse is the one with nonzero Start
      Increment, the worker's own name_list criterion) and length nutation
      (`rabi_echo_4s.phase_awg`, nonzero Length Increment). The sequences are
      inversion-detection ⇒ echo ∝ cos θ(x); θ = b·x + s·x² fitted (s absorbs
      compression), then de-biased: π from the model-free parabola vertex at
      the observed minimum, π/2 from a re-fit with θ anchored at that π.
      Synthetic benchmark (20 noise seeds, 10 % compression): π −0.3 ± 0.34 %,
      π/2 −0.3 ± 0.4 % of full scale; length mode 179.8/89.9 ns vs 180/90 true
- [x] `tune.power_for_length` (coarse): length nutation at held amplitude →
      dB += 20·log10(target/measured) per iteration; same-direction (from-
      above +1 dB overshoot) vane moves, exact mechanical wait from the
      device's own calibration curve (36 ms/step), optional Limit-mode
      re-home; every vane move invalidates auto-phase + fine cal
- [x] Rail detection: π ≥ 99 % ('cannot reach π') or ≤ 30 % (wasted dynamic
      range) fails the `amplitude_rails` judge; π beyond the sweep end is
      reported as `rails: high` with x[-1] as a lower bound. Automatic
      re-run of the coarse stage = Phase 3 runner policy (retry framework)
- [x] `field.edfs` (exp_field run → pick max/value → BH_15 via the session,
      field.param + temp.param locks seized with source 'epr_auto', atexit
      release; pick=marker rejected at validation until Phase 3) + `field.set`
- [x] `judges.py`: echo SNR (MAD-of-diff sigma, extreme-value ceiling —
      pure noise scores ~1), fit RMSE/adj-R², convergence, π-ratio linearity
      (advisory: warns, never aborts), amplitude rails; every primitive
      returns (result, judge_reports), steps gate on them in live runs only
- [x] Engine data-return: `executor.load_1d`/`acquire_1d` (iq_cor==1 CSV:
      axis, I, Q; axis s / % / G by sweep); dry-run = real per-preset
      engine pre-flight (Worker child forces test devices) + canned result

## Phase 3 — Runner UX & autonomy — DONE 2026-07-17 (Opus-reviewed, fixes applied)
- [x] Checkpoint gating completed: autonomous mode never pauses — checkpoints
      auto-approve with a notification, judges are the only brake; supervised /
      checkpointed keep the Phase 0 terminal prompt (GUI checkpoint = later)
- [x] Retry policy per step: `retries: n` (extra attempts) + `on_fail:
      abort | skip | ask` reserved step keys (parsed like `checkpoint`);
      'ask' prompts retry/skip/abort (autonomous or no-tty ⇒ abort + notify)
- [x] Rail-triggered fallback wired: StepFailure carries `rails` from the
      failing amplitude_rails judge; the runner re-runs the most recent
      earlier tune.power_for_length (+ the tune.auto_phase steps after it —
      the vane move invalidated the phase) once per step and retries, the
      fallback retry granted on top of the retry budget — automatic in
      autonomous mode (with notification), y/n prompt otherwise; only
      available when the protocol declared the coarse step (its resolved
      params define the stage); re-runs recorded in the manifest, a chain
      failure is recorded + surfaced in the abort message
- [x] Adaptive scan channel: `run_worker(scan_control=(pct, elapsed_s) ->
      int|None)` sends 'SC<n>' on change (harness stub-tests the round
      trip). The judge/budget-driven POLICY consumer lands with the Phase 4
      exp steps — nothing calls it yet
- [x] Run directory + manifest: protocol-level `output` template
      ({date}/{sample}) now honored; manifest.json (protocol snapshot copy,
      per-step resolved params / result / judge dicts / attempts / errors,
      status + timestamps) rewritten atomically after every step; dry-runs
      write nothing. Worker CSVs already carry headers
- [x] Notifications: protocol-level `notify: telegram` -> session.notify()
      via general.bot_message (never raises, logged always, silent in
      dry-run) on autonomous checkpoints, on_fail skips/aborts, finish, abort

## Phase 4 — T1/T2 end-to-end — code DONE 2026-07-18 (primitives/exp.py)
- [x] `exp.t2` (hahn_echo preset, linear τ sweep) with fit + report:
      `_retau` re-anchors every moving pulse in the preset's own increment
      ratio (hahn: π 1 unit, DETECTION 2 — axis = total evolution time,
      starts at the new π start = the worker's f_delay rule);
      stretched-exp fit on the principal-axis-rotated trace; HARD
      `relaxation_fit` judge (fit_quality stats under a non-advisory name)
      + `echo_snr`; `rep_rate` param + friendly period pre-check
- [x] `exp.t1` (inversion_recovery log-time preset) with characteristic-time
      initial-guess fit (1/e crossing anchor — a generic p0 degenerates on
      log-spaced sweeps): t_start/t_end → Log Start/End = log10(ns); the
      worker's grid-rounded log axis deduplicates ⇒ result `npoints` ≤
      `points`; sign-blind rotation handled (bipolar + flipped validated)
- [x] `max_duration` → scan_control policy (`_duration_policy`): projected
      wall-clock over budget ⇒ shrink scans ('SC<n>', ratchet-down only,
      5 % grace, ≥2 % progress + ≥10 s before trusting the projection);
      `window: auto|preset` consumer (`preset` pins the preset's stored
      window over the session echo_window override)
- [x] `protocols/overnight_t2.yaml` full chain in `--test` (exp.t2 now runs
      the real path: retau + apply_cal + pre-flight)
- [ ] **Hardware**: full chain on the spectrometer, supervised mode (see
      HARDWARE_CHECKLIST 'Newly hardware-runnable')

## Phase 5 — Tune-up completeness — code DONE 2026-07-17 (review folded into
## the single `3be399d..b9cbc66` review — see the end of the session log;
## decisions in ARCHITECTURE.md "Tune-up completeness")
Gaps found reviewing the plan: classical length calibration had no consumer,
detection-pulse convention was implicit, and window / temperature / signal
search were missing entirely. `tune.echo_window` and the `apply_cal` hand-off
landed **before** the Phase 4 overnight hardware run — the full chain is
not autonomous without them.
- [x] Calibration hand-off `apply_cal` (`tune.apply_calibration` +
      `params.CalMap`, wired into the exp.* stubs so dry-runs validate):
      amplitude-mode results patch slot coefficients with the standard
      inverse-length scaling `amp = amp_cal · L_cal/L_slot` (pi_calibration
      now stores `length_ns`; equal lengths ⇒ verbatim, >100 % ⇒ clean
      error); length-mode results patch lengths quantized to the preset's
      AWG grid. Default map inferred from the hard MW pulses: two amplitude
      levels (lower = π/2), OR one amplitude level with two lengths
      (hahn_echo-style length encoding, π = 2× π/2 — found in dry-run:
      the amplitude-levels-only rule from the plan can't see these);
      soft cutoff at ≥2.5× shortest; ambiguity ⇒ validation error
- [x] Detection-pair re-scaling after every fine amplitude cal
      (`_scale_detection_pair`: pair = active MW ≥2× swept length, roles by
      relative amplitude, rule `amp_det = amp_cal · L_cal/L_det`; skipped on
      a rail or an unrecognizable pair with a log note; result key
      `detection_pair`); `refine: true` = one nutation re-run with the
      re-scaled pair patched in (recursion; dry-run pre-flights it too)
- [x] **[F]** `executor.acquire_trace`: runs Worker.dig_on UNMODIFIED in the
      accumulating readout (l_mode=1 → live_mode=0, the phase-cycled
      average the exp methods integrate), captures the trace by patching
      general.plot_1d in the child (dig_on never pipes data — it only
      plots), per-cycle Status from the capture, 'exit' at 100 % = the GUI
      Stop path, trace = last completed cycle. `WorkerArgs.dig_args()`
      mirrors dig_start/run_main_experiment packing (43 args; + p_to_drop
      field); harness extended: per-preset dig_on packing comparison (17
      presets) + real-dig_on pre-flight + stub capture round-trip
- [x] `tune.echo_window`: center = max of smoothed |V(t)| (phase-free, so
      it can run before auto_phase), width = FWHM × factor (≥1, default 2),
      edges rounded outward onto the ADC grid (0.4 ns × decimation) and
      clamped; trace saved to the run dir; judge `echo_in_trace` (hard:
      FWHM edge on the trace boundary = echo cut) + echo_snr; stored
      relative to DETECTION start, applied via _session_overrides
      (win_left_ns/win_right_ns); `window: auto | preset` param on exp steps
      (consumer lands with Phase 4)
- [x] `temp.set` / `temp.wait` (`primitives/temp.py`, session lazy
      Lakeshore_335): setter validates heater range + setpoint through the
      device test branch; waiter = hold consecutive in-band polls at 1 s
      cadence inside a wall-clock timeout ('1800 s' TimeStr — no 'min'
      unit), `temperature_band` hard judge ⇒ StepFailure on timeout so
      retries/on_fail apply; readings mirrored into temp.param for an open
      temp_control window
- [x] `field.edfs range: auto` (params.AutoOr): center =
      0.71447704·ν[MHz]/g from `mw_bridge_synthesizer()` readout, `g:`
      (default 2.0023) ± `span:` (default 250 G), + `offset:` (signed
      FieldStr, default '0 G' — the magnet is not absolutely calibrated;
      the result's `shift_g` = measured line − predicted center, ready to
      feed back as the standing offset); one span-×2 escalation on
      a failed echo-SNR judge; a second failure returns WITHOUT moving the
      magnet (no noise-argmax field.set) and the judge carries a
      `diagnosis`: score ≥1.5 = "weak line near X G — more scans / narrow
      range", else "flat everywhere — check tuning/temperature/g/sample"
- [x] tune_up.yaml = canonical chain: power_for_length → field.edfs (auto) →
      echo_window → auto_phase → pi_calibration (+ commented temp prologue)

## Phase 6 — Field series (`foreach:`) + SNR-driven scans — code DONE 2026-07-19, committed `94481c7` (planned 2026-07-18)
Motivating workflow (user): several relaxation times at fixed T, different
magnetic fields — expressible today only by repeating field.set/exp.* blocks
by hand. Design validated against the real 2026-07 oTP campaign (see the
"Real-data validation" block below; harness `~/epr_auto_dev/field_phase_snr_check.py`).

- [x] `foreach:` protocol block (promoted from backlog; covers field AND
      temperature series) — DONE 2026-07-19:
      ```yaml
      foreach:
        var: B
        values: ['3000 G', '3318 G', '3376 G', '3450 G']
        steps:
          - field.set: {value: $B}
          - exp.t2: {...}
          - exp.t1: {...}
      ```
      Decisions: (a) output naming — manifest entries and CSV filenames
      stamp the loop variable/value; (b) per-iteration failure policy —
      a StepFailure inside an iteration records it and CONTINUES to the
      next value by default (unlike the global on_fail), overridable;
      (c) **no auto_phase invalidation on field moves** — measured, not
      assumed (validation below); temperature keeps `rephase_delta`.
- [x] `target_snr:` param on exp.t1/t2 (DONE 2026-07-19) — SNR-driven scan count. `scans`
      becomes the ceiling; a second scan_control consumer (composed with
      `_duration_policy`, min wins) projects the needed scan count from
      sqrt(N) scaling — after scan k, N ≈ k·(target/SNR_k)² — and sends
      'SC<n>' (ratchet-down only, same guards as the duration policy).
      Stop metric = `judges.echo_snr` on the principal-axis-rotated
      accumulated curve — the SAME metric as the final judge, so the
      stopping rule and pass/fail agree. Noise sigma stays MAD-of-diff
      (noise-only), NOT fit-residual sigma — misfit does not average down
      (validation below).
- [x] Worker pipe extension the SNR policy needs (DONE 2026-07-19): an
      opt-in scan-boundary message carrying the accumulated data
      (`scan_data_flag` worker ATTRIBUTE — like awg_grid_cur, not a method
      arg — default absent ⇒ GUI-launched runs unchanged). Touches
      awg_phasing_insys.py's Worker (`exp` + `exp_log` boundaries) ⇒
      mirror rule applied: executor `_hand_attrs`/`run_worker` mirrored,
      gui_vs_engine ALL PASS.

**Real-data validation (2026-07-18,** `~/Documents/OTP/2026_07_02_ap210_oTerPhenyl`
t1/+t2/ (24+24 traces, 80–280 K × 3000/3318/3376/3450 G) **+**
`2026_07_03_ap210_oTP_new` **ED sweeps):**
- Phase vs FIELD: ED sweeps show ±1–3.5° (amp-weighted std) across the whole
  significant line region; local phase at 3318/3376/3450 G agrees within ~3°.
  Raw T2 curves: max |Δφ| vs the 3318 G reference 0.9–4.8° per temperature
  (worst Q-leak 8 %); T1 4.7–8.4° (bipolar, low-SNR — includes estimator
  noise). And exp.* re-rotates every curve onto its principal axis before
  fitting (`_to_real`), so a few degrees of demod drift costs nothing.
  ⇒ auto_phase transfers across field moves; do NOT rephase per field.
- Phase vs TEMPERATURE/retune: session-to-session weighted phase moved up to
  ~40° (160 K ED: −38.8° vs +2.9° on the repeat) — temperature/retune
  rephasing (`rephase_delta`) stays necessary; field rephasing does not.
- echo_snr vs operator ground truth: the ONLY failing T2 trace (score 2.8
  < 3.0) is 280 K/3000 G — exactly the trace the human analysis excluded
  for SNR. And the operator already adapted scans per field by hand
  (T2: 6 scans at the 3318 G line max vs 32–46 at the 3000 G shoulder) —
  precisely the adaptation `target_snr` automates.
- Noise sigma: MAD-of-diff vs fit-residual sigma on the 240 K extracted
  curves — ratio 0.14–0.85; residual sigma is inflated by systematic model
  misfit (ESEEM modulation etc.), which more scans cannot reduce. A
  residual-based stop metric would over-scan forever; MAD-of-diff is the
  right choice (and log-spacing does NOT inflate it: ratio 0.85 on the
  log-T1 trace where slope-per-point is largest).

## Phase 7 — Documentation (atomize_docs Projects section) — re-planned
## 2026-07-20 (was: local in-repo MkDocs site; user direction)
User manual for epr_auto published DIRECTLY on the public site
(`/home/anatoly/atomize_docs` -> anatoly1010.github.io/atomize_docs) as a
new subsection of the existing **Projects** nav tab, next to the
spectrometer pages (`projects/endstation.md` IS Atomize_ITC's page).
Audience split stays: `docs/automation/*.md` = internal design/session
docs (this file); the site = the user manual.

- [ ] Pages live at `docs/projects/epr_auto/` in the atomize_docs repo;
      nav gains, under `Projects:`, an `EPR automation (epr_auto):`
      subsection listing them (same pattern as the Spectrometers block).
      Existing authoring conventions apply (nav in mkdocs.yml, admonitions,
      title from first H1, relative links).
- [ ] The section must state up front that epr_auto ships with the
      **Atomize_ITC endstation variant** (not plain Atomize): link the
      landing page both ways — `projects/epr_auto/index.md` ->
      `projects/endstation.md` + the Atomize_ITC repo, and a short
      pointer paragraph on endstation.md -> the epr_auto section.
- [x] Generator placement: `atomize/epr_auto/docgen.py` (imports the STEPS
      registry; refuses to emit if a step family is missing from its
      FAMILIES map). Emits `docs/projects/epr_auto/steps.md` into
      atomize_docs; the page carries the do-not-edit banner + the
      regeneration command:
      `python3 -m atomize.epr_auto.docgen <atomize_docs>/docs/projects/epr_auto/steps.md`.
      Regeneration is manual — still to record in atomize_docs/CLAUDE.md.
- [x] **First five pages LIVE in the atomize_docs tree (2026-07-20,
      Opus-authored, uncommitted there):** index (overview), quickstart,
      protocols (Writing protocols), steps (generated), tuning (The
      tune-up chain) + nav subsection + endstation.md cross-section.
      `mkdocs build --strict` passes. Empty `help=''` gaps in steps.py
      all filled (26 params) as planned.
- [ ] Remaining pages: presets (what steps expect of a `.phase_awg`),
      examples (annotated overnight_t2 + field-series), troubleshooting
      (StepFailures verbatim + locks + LivePlot behaviour); judges got a
      compact treatment inside protocols.md/tuning.md — decide if a
      dedicated page is still wanted.
- [x] **Auto-generated step reference** from the STEPS registry — verified
      2026-07-18; DONE 2026-07-20 (4) via `docgen.py` (see the checked
      "Generator placement" item above — implemented as a single
      generated `steps.md`, not one page per family): `steps.py`
      introspects headless (summary, param class, default, required,
      min/max, Choice options, help) ⇒ the reference CANNOT drift from
      code. Side effect handled: the empty `help=''` strings (26 params)
      were filled in steps.py as part of this pass.
- [ ] Hand-written pages:
      - Home — what epr_auto is (YAML protocol runner reusing the phasing
        Worker), architecture sketch, relation to the GUI tools
      - Quickstart — install (`pip install -e .`, epr-auto entry point),
        `--test` dry-run first, real run with the GUI open (cwd=libs),
        run directory / manifest.json / file naming (`NNN_tag.csv`)
      - Writing protocols — top-level schema (sample/autonomy/output/
        notify/steps), per-step retries/`on_fail: abort|skip|ask`, output
        template `{date}/{sample}`, autonomy levels + checkpoint behaviour,
        telegram notify
      - Judges & gating — hard vs advisory, echo_snr (MAD-of-diff),
        phase_coherence, relaxation_fit dAICc rationale, temperature_band,
        amplitude_rails + rail fallback, edfs flat-vs-weak diagnoses
      - Tune-up chain — annotated tune_up.yaml walkthrough
        (power_for_length → field.edfs auto → echo_window → auto_phase →
        pi_calibration), apply_cal + detection-pair rescaling rules
      - Presets — what steps expect (`IQ Correction: 2`, phase_awg format
        pointer), window/rep_rate/apply_cal overrides, session overrides
      - Examples — overnight_t2.yaml annotated; field-series T1/T2 (update
        when Phase 6 lands)
      - Troubleshooting — common StepFailures verbatim + what they mean,
        param locks vs open control-center GUIs, LivePlot behaviour of
        engine runs
- [ ] Maintenance rule (goes into CLAUDE.md when the site lands): step/param
      changes regenerate the reference automatically at build; protocol
      SCHEMA changes must touch the Writing-protocols page in the same
      session.

## Phase 8 — Progress cap + auto rep-rate + auto EDFS — code DONE 2026-07-20
## (same session as planned; committed `e339240` — hardware still pending)

Three items (user request, post-Phase-6-review session):

- [x] **Status never exceeds 100%** — including the SC-shrink trailing scan
      (the Phase 6 review's confirmed minor: a stop-now `SC k` is consumed
      during scan k+1, whose Status ticks read >100% because SCANS already
      holds the lower ceiling). Worker-side clamp `min(100, ...)` on the
      Status sends of every SC-honouring sweep loop (exp / exp_log /
      exp_field / exp_amplitude — identical expression in all four;
      exp_eseem holds SCANS fixed and provably cannot overshoot). GUI-shared
      file ⇒ mirror rule: re-run gui_vs_engine. Side effect on the engine:
      `_duration_policy`'s projection reads a capped pct during the trailing
      scan only — the run is finishing either way.
- [x] **Auto rep-rate: `tune.rep_rate` step** (design sketched 2026-07-20
      session log). Log grid of repetition rates rate_min..rate_max (steps
      points, geomspace, slowest first — each new rate settles into steady
      state within a few shots), one quick echo acquisition per rate
      (auto_phase style: points~4, |mean(sig)| — complex mean, phase-
      robust), fit A(T=1/rate) = A0·(1 − exp(−T/T1_eff)) — the steady-
      state saturation curve. Store `session.state['rep_rate']` =
      {t1_eff_s, rep_rate_hz, mode}; recommended rate = 1/(factor·T1_eff)
      (factor default 5, 'quantitative'; <1% residual saturation) or
      1/(1.26·T1_eff) ('sensitivity', max S/√time — tuning/EDFS only),
      never extrapolated above rate_max. Judges: **phase_coherence on ALL
      acquisitions concatenated** (no echo at all must fail the step, not
      recommend rate_max; NOT echo_snr — these curves are deliberately
      FLAT, no peak-above-baseline, and a single points~4 trace is too few
      samples for a reliable noise resultant, found by the unit suite) +
      hard `rep_rate_fit` (fit converged AND the grid brackets the knee:
      residual saturation exp(−T_max/T1_eff) < 0.15, else T1_eff is
      extrapolated → fail with "extend rate_min", nothing stored) +
      advisory fit_quality. Flat curve (spread < 5%) = no saturation
      anywhere → T1_eff « fastest period, recommend rate_max, pass with
      note. `rep_rate: auto` on exp.t1/t2 (AutoOr param) resolves from the
      session result; StepFailure if tune.rep_rate has not run. Per-rate
      curves + a rate/period/amplitude summary CSV land in the run dir.
- [x] **Auto EDFS: `target_snr` on field.edfs** — the exp_field ScanData
      path landed post-review (`1c1432c`); wire the consumer: param on the
      step, `wa.scan_data_flag = 1` + `on_scan_data=_snr_policy(...)` in
      the edfs primitive (threaded through the escalation re-run too).
      Same metric as edfs's own hard echo_snr gate, so stop and verdict
      agree; `scans` becomes the ceiling exactly as on exp.t1/t2.

Bench items (fold into HARDWARE_CHECKLIST when implemented): rep-rate
saturation curve on a real sample vs a hand-measured T1; EDFS target_snr
early-stop on a strong line.

Verified (2026-07-20, all offscreen): 22-check unit suite (fit recovery
within 10% + 200 Hz recommendation on synthetic saturation, sensitivity
794 Hz, flat→rate_max, saturated-grid fail + nothing stored, pure-noise
phase_coherence fail, rate_max clamp, bad grid, auto-resolution paths,
edfs flag/policy/pick-max/stop-on-strong-line, no-target passthrough) +
new phase8 protocol dry-run 6/6 (canned T1_eff 1.2 ms → auto 166.7 Hz
flows into exp.t2/t1) + regression dry-runs tune_up 6/6, overnight_t2
4/4, field_series 16/16 + validate + **gui_vs_engine ALL PASS** (Status
clamp touched the Worker → mirror rule exercised).

## Phase 9 — Post-bench follow-ups + experiment breadth — planned 2026-07-20

- [ ] **Review follow-ups** (decisions in the 2026-07-20 session log):
      pairing assert in `_acquire`; foreach substitution context in
      ParamError; try/except around executor scan_control/on_scan_data
      callbacks; OVER_TICKS-style 2-scan persistence for SNR projections
      **if** the bench shows the min-ratchet undershoot matters.
- [ ] **exp.t1 with varied tau**: optional `tau` param — `_retau`-style
      re-anchor of the pi/2–pi detection pair (+ DETECTION) at fixed sweep;
      changing tau invalidates tune.echo_window's stored window ⇒ must
      force window='preset' or re-run echo_window; use case: sitting the
      detection tau on an ESEEM-blind point.
- [ ] **Full-2D acquisitions**: keep the stop metric on the integrated 1-D
      curve; for 2-D protocols add a worker-side per-column window integral
      sent as ScanData (never the matrix over the pipe) + save2d for the
      offline transients.
- [ ] **Auto 3p-ESEEM with varied T and tau**: exp.eseem step on the
      ESEEM-avg worker path (ScanData already in, monitor-only — SCANS is
      locked there, so target_snr can only observe, not shrink); vary the
      3-pulse T sweep preset's tau per iteration (foreach-able) with the
      tau-averaging Cycles machinery for blind-spot suppression.

## Later phases (unordered backlog)
- Resonator-correction overrides in the runner/protocol YAML (the ENGINE side
  is done 2026-07-17: WorkerArgs carries cor_model_cur/f0_cur/q_cur/
  phase_cor_cur/meas_freq_cur/meas_H_cur and the executor hands them to the
  worker like the GUI's `_hand_correction_to_worker`; set them on the built
  WorkerArgs. Remaining: plumb them from protocol steps + measured-H file
  loading outside the GUI)
- RECT channel support for calibration + runners
- ESEEM / DEER payload experiments (reuse ESEEM-avg + benchmark know-how)
- ~~`foreach:` protocol block~~ — promoted to Phase 6 (field/temperature
  series)
- Autopilot GUI (control_center tool wrapping the runner)
- Assistant layer (Claude emits/edits protocols, reacts at checkpoints)
- Resonator tuning (needs actuation path assessment)
- Port to fork repos once stable

## Pending hardware validation
- **Phase 2 primitives on the spectrometer** (all code-complete, dry-run
  clean; nothing has touched hardware): auto-phase round-trip (zero-order
  sign: digitizer_demodulate rotates by exp(−i·z), so z_new = z_used − φ_residual —
  verify the corrected run comes out real-positive); pi_calibration amplitude
  sweep on `ampl_4s` (fit + rails on real compression); power_for_length vane
  loop (dB step direction, mechanical wait long enough, backlash approach);
  edfs pick=max lands on the line; field.param/temp.param locks vs an open
  field_control/temp_control GUI.
- LivePlot behaviour of engine-run Workers (plots go to the open GUI exactly
  like GUI-launched runs — expected but unverified).

## Session log
- **2026-07-16** — Variants discussed, decisions fixed (see ARCHITECTURE.md
  table), docs created. Next: Phase 0 package skeleton + protocol loader.
- **2026-07-16 (2)** — Phase 0 complete. `atomize/epr_auto/` (params → steps →
  protocol → session/runner → cli layering; nothing imports general_modules or
  device modules at module scope — cli sets argv[1]='test' and chdirs to libs/
  before lazy device creation). 7 steps registered as stubs with real param
  specs; `protocols/overnight_t2.yaml` example; pyproject: +pyyaml dep,
  +epr-auto script. Verified: dry-run end-to-end (test-mode Insys instantiates
  headless), 9 broken-protocol cases all give file:line errors, live run
  refuses with exit 3. Next: Phase 1 engine extraction ([F] — prefer Fable).
- **2026-07-16 (3)** — Phase 0 reviewed (5 findings fixed: UTF-8 protocol read,
  duplicate-key rejection, per-item step lines, EOF at checkpoint prompt,
  user-config bootstrap in cli) and committed: ITC `f994f6f`. Phase 1 started.
- **2026-07-16 (4)** — Phase 1 complete (uncommitted). Key decision: reuse
  `Worker` instead of extracting it — engine = snapshot builder + executor.
  Equivalence harness `~/epr_auto_dev/gui_vs_engine.py`: ALL 13 presets PASS
  (byte-identical worker args vs real offscreen GUI; harness must reset
  `window.is_experiment = False` between presets — dig_start_exp latches it).
  Gotchas encoded in snapshot.py: `_snap` is ceil-to-grid (3.2 ns default,
  0.8 ns for fine-grid presets since 2026-07-16 (6)); log sweep
  bounds go through TimeLogSpinBox unit-grid quantization (`_log_snap`);
  P1 'phase' field is receiver coefficients, expanded together with active
  pulses only (length ≠ 0); combo_cor/combo_synt/save2d are NOT in presets
  (GUI defaults 0/1/0). Next: Phase 2 tuning primitives wired through the
  engine (field.edfs→exp_field, pi_calibration→exp_amplitude/exp).
- **2026-07-16 (5)** — ESEEM Avg + LASER added to the engine (ALL 15 PASS incl.
  2 synthetic presets); resonator-correction deferred to backlog; CLAUDE.md
  gained the phasing-GUI ↔ engine mirror rule. Phase 1 committed+pushed: ITC
  `f28bb47`. **Next session: /code-review of f28bb47 first, then Phase 2.**
- **2026-07-16 (6)** — **0.8 ns AWG timing step implemented** (uncommitted;
  plan of record: `AWG_FINE_STEP_PLAN.md`, all software phases done). DAC =
  1250 MHz ⇒ 0.8 ns/sample; TTL stays on the 3.2 ns tick; sub-tick start =
  floor(gate) + k∈{0..3} leading zero samples in the DAC segment
  (`Insys_FPGA._trigger_gate_ticks`), waveform cache untouched
  (paste-at-offset). Receive side: virtual fine DETECTION start (floored TTL
  window + per-nid residual, `det_residual_by_nid`), corrected at readout by
  integer ADC-point slice shifts / row alignment (`_window_sum` /
  `_align_det_rows`; exact at decimation 1–2). Opt-in everywhere:
  `pb.awg_time_resolution('0.8 ns')`, GUI Settings checkbox, preset trailing
  `AWG grid:  0.8` line; engine mirrors via `Preset.awg_grid` →
  `WorkerArgs.awg_grid` → `worker.awg_grid_cur` (attribute, not an arg).
  Verification: golden pulser harness BIT-EXACT (toggle off), fine-grid
  functional suite ALL PASS (scratch `test_fine_grid.py` — decomposition,
  k-cycling sweep, gate-overlap merge, readout corrections), offscreen GUI
  suite ALL PASS (`test_gui_fine.py` — toggle, re-snap, preset round-trip,
  worker transport), gui_vs_engine ALL 17 PASS (now incl. 2 fine-grid
  synthetic presets + awg_grid_cur attribute check), end-to-end test-mode
  Worker runs pass for fine + coarse presets.
  **Opus /code-review done (15-agent workflow) — 6 findings, all fixed:**
  (1) grid toggle mid-preview left the running worker on the stale launch-time
  grid → now blocked during an experiment and stops a live preview (mirrors
  open_file); (2) NameError on an invalid TRIGGER_AWG length unit (moved
  dac_window accounting referenced p_length) → gated on a valid length, so the
  historical silent skip is restored; (3) trig_info paired with the AWG
  waveforms positionally but sorted by the FLOORED gate tick → now sorted by
  gate start in samples (matches the waveform start-sort, no floor-tie
  mispairing); (4) test-mode `_acc_dec` stayed 1 while the scale used dec_coef
  → locked to dec_coef in the test readout; (5)+(6) coarse mode still ran the
  per-row residual dict-loop / built+sorted trig_info every rebuild → residuals
  now recorded only when nonzero (empty dict ⇒ readout fast-returns None) and
  trig_info is built only on the fine grid, restoring the free-when-off path.
  Golden BIT-EXACT + all suites still green after the fixes. **Next: lab bench
  items (AWG_FINE_STEP_PLAN.md verification table: scope TTL vs DAC at k=0..3,
  0.8 ns τ sweep, residual 4-point flatness, GIM re-arm under mid-sweep gate
  ±1 tick).**
- **2026-07-17** — /code-review of f28bb47 (workflow, high effort, harness
  included in scope) — 9 findings, all fixed (uncommitted): (1) executor now
  mirrors `_hand_correction_to_worker` (WorkerArgs gained the six correction
  fields, defaults = Worker/GUI defaults; harness compares them as worker
  attributes next to awg_grid_cur — mutation-tested: a diverging f0_cur fails
  every preset); (2) harness SKIP-on-missing-runner now counts as FAIL *and*
  executor raises at import if SWEEP_METHOD ≠ snapshot.SWEEP_TYPES; (3)
  harness now exercises `executor.run_worker` itself — real test-mode
  pre-flight per sweep type + real-run save handshake (Open→'FL<path>'→
  finished, Status/Message callbacks) via a protocol-speaking StubWorker;
  (4) KeyboardInterrupt stop no longer hard-kills a still-saving worker after
  60 s — waits indefinitely, second Ctrl-C force-terminates (dead `stopping`
  flag removed); (5) harness `normalize` derives slot inactivity per-side
  (each payload's own awg length) instead of blanking both sides from the
  engine's view; (6) expander-tautology coverage limit documented in
  `_expand_phases` + harness docstring (shared expander is by design); (7)
  the five preset-independent args (exp/curve name, combo_cor/synt/save2d)
  are fed to the engine as literals with the GUI defaults asserted, no longer
  compared against themselves; (8) = (2) import-time sync check; (9) coverage
  gates: ≥ MIN_COMPARED (17) presets compared + every sweep type covered or
  the run fails. Harness re-run: ALL PASS (17 presets + 5 pre-flights +
  handshake). Refuted by review: awg_grid getattr default (unreachable),
  per-cycle Save-each naming (worker-internal, single Open is correct).
  Committed+pushed: ITC `c855ca1`.
- **2026-07-17 (2)** — **Phase 2 code-complete** (uncommitted).
  `primitives/{judges,tune,field}.py` + engine `load_1d`/`acquire_1d` +
  session run_dir/save_path/hardware-locks(atexit)/invalidate_fine_calibrations;
  steps.py rewired (stubs → primitives, judge gating: failed judge ⇒
  StepFailure live-only, pi_ratio_linearity advisory). Key discoveries
  encoded in code comments: Amplitude-sweep swept-pulse = nonzero st_inc
  (worker name_list criterion; acquire-then-step, so axis[j] = amplitude at
  point j); ampl_4s/rabi are inversion-detection ⇒ cos θ nutation;
  digitizer_demodulate applies exp(−i·zero_order) ⇒ z_new = z_used − φ; exp_field
  axis in G, POINTS = (end−start)/step + 1; Worker pre-flight forces
  sys.argv=['','test'] in-child (safe against live hardware); vane wait
  must be slept out locally (worker child owns a fresh Micran instance).
  π/π2 extraction: global fit judges, model-free vertex for π, θ-anchored
  re-fit for π/2 (benchmarked; free fit root was 6× noisier from the
  c0/envelope degeneracy). New `protocols/tune_up.yaml`; overnight_t2 +
  tune_up dry-run clean; validate/steps/marker-rejection OK;
  gui_vs_engine ALL PASS. Next: hardware validation of Phase 2 (see
  Pending), then Phase 3 (runner retry/fallback policy + manifest) or
  Phase 4 (exp.t1/t2 on the same acquire_1d path).
- **2026-07-17 (3)** — Opus /code-review of Phase 2 (23-agent workflow,
  harness in scope) — 10 findings, all fixed (uncommitted): (1) sign-blind
  principal-axis rotation could hand the fit a −cos trace → orientation from
  the leading points (θ(x₀) < π/2 in the presets) + flip-rescue; chasing the
  fix exposed a second fit basin (small-b/positive-s accelerating chirp,
  plausible SSR, garbage π/2) → physical chirp bound r = s·x_max/b ∈
  [−0.35, 0.15] in BOTH the free fit and the anchored re-fit (benchmark:
  inverted-trace π/2 went from +4.8 ± 7.7 to −0.5 ± 0.6); (2)
  power_for_length no longer moves the vane after the last measurement —
  the returned (attenuation_db, pi_length) pair always describes the state
  the vane is in; (3) auto_phase judged by new `phase_coherence`
  (resultant length R) — echo_snr's MAD-of-diff sigma is meaningless on a
  4-point trace; (4)+(5) judge gating: fit_quality + convergence moved to
  advisory (π/π2 come from de-biased local estimates; pi_length_target is
  power_for_length's hard gate; convergence emitted only on failure as a
  diagnostic — a single large-but-correct vane jump is not a defect; NOTE
  Phase 4 relaxation fits need a differently-named HARD fit judge); (6)
  _run_primitive now routes RuntimeError (incl. EngineError, vane parse,
  lock conflicts) to StepFailure, not a traceback; (7) iq_cor==1 checked in
  _acquire before the pre-flight so --test rejects non-'IQ Correction: 2'
  presets; (8) edfs validates pick=value against the range before the
  sweep (dry-run parity); (9) _vane_set reads the vane once; (10)
  pi_calibration reuses its probe parse (_build accepts a Preset).
  Re-verified: nutation battery incl. inverted + length-inverted cases,
  exception-routing unit test, both protocol dry-runs, gui_vs_engine ALL
  PASS. Refuted by review: rail score literal 100 (intended), points=None
  defaults (intended), canned-branch duplication (accepted). Committed+
  pushed: ITC `5d73529`.
- **2026-07-17 (4)** — **Phase 3 code-complete** (uncommitted, NOT yet
  code-reviewed — **next session: /code-review of Phase 3 first**). Protocol
  schema: step keys `retries`/`on_fail`, top-level `notify`, `output`
  template now honored by session.run_dir. Runner rewritten: retry loop
  (attempts = 1 + retries), on_fail abort/skip/ask, rail fallback (once per
  step, extra attempt outside the retry budget, re-runs coarse + auto_phase
  from the protocol's own resolved params), autonomous checkpoint
  auto-approval, crash-safe manifest.json (atomic rewrite per step;
  disabled in dry-run), notifications on checkpoint/skip/finish/abort.
  Executor: scan_control command channel ('SC<n>' on change only).
  cli releases hardware locks in finally. Verified: 8-case runner unit
  suite (scratch test_runner_phase3.py — retry/skip/abort/manifest/rail
  fallback incl. no-coarse-step case/autonomous checkpoint/no-manifest-in-
  dry-run/schema validation), both protocol dry-runs, harness ALL PASS
  incl. new StubWorkerSC scan-control round-trip. tune_up.yaml demonstrates
  retries. Committed+pushed: ITC `f45433c` (session-log line added post-
  commit). Next: /code-review (Phase 3), then Phase 4 exp.t1/t2 (wire
  max_duration -> scan_control policy there).
- **2026-07-17 (5)** — Plan review with the user; five gaps closed as **Phase
  5** (decisions in ARCHITECTURE.md "Tune-up completeness"): (1) classical
  length nutation exists (`mode: length`) but had no downstream consumer →
  `apply_cal` hand-off; (2) detection pulses in π/π₂ calibration are
  **soft/selective at ~3–4× the target length** (lab convention: 22 ns target
  ⇒ 60–90 ns detection; ampl_4s already encodes it, 28.8 ns GAUSS vs 86.4 ns
  SINE pair) at proportionally lower amplitude — standard rule
  `amp_det = amp_cal · L_target/L_det`, reliable because the amp is nearly
  linear (user, 2026-07-17); optional `refine` re-run; (3) temperature was
  missing → temp.set/temp.wait on the temp_control setter-waiter pattern;
  (4) initial signal search was user-only → `range: auto` from synthesizer
  frequency + g, one widen-×2 escalation, then human with a diagnostic
  report; (5) integration window was taken verbatim from the preset →
  tune.echo_window (needs new engine acquire_trace **[F]**), stored relative
  to DETECTION start, must precede auto_phase. echo_window + apply_cal are
  prerequisites for the Phase 4 overnight hardware run. Also fixed the
  ARCHITECTURE decision table (three rows were stranded below the flip-angle
  section). Next: /code-review of Phase 3 (still pending), then Phase 5
  items or Phase 4 code.
- **2026-07-17 (6)** — **Opus /code-review of Phase 3 `f45433c`** (workflow,
  high effort, 19 agents): 8 findings confirmed, 3 refuted, **all 8 fixed**
  (uncommitted). Correctness: (1) rail-fallback attempt consumed a configured
  retry → `fallback_bonus` grants the fallback retry on top of the budget
  (initial + fallback + retries); (2) non-StepFailure from the fallback
  chain escaped run_protocol leaving manifest.json stuck at 'running' →
  chain now catches Exception (logged traceback, recorded, clean abort);
  (3) unknown `{field}` in the `output` template passed load + dry-run then
  KeyError'd the live run at startup → load_protocol probes
  `output.format(date=,sample=)` and rejects with a ProtocolError; (4) a
  fallback coarse-stage failure was swallowed into a log line → recorded in
  the manifest as 'failed (rail fallback)' and appended to the abort message
  ('rail fallback blocked: …', e.g. vane end-stop now visible); (5) fallback
  re-runs (vane moves!) were absent from the manifest → recorded as
  'ok (rail fallback)' entries, failing step's own judges preserved via
  save/restore of last_judges. Cleanups: (6) fallback picked the FIRST
  power_for_length but re-ran EVERY auto_phase → most recent coarse before
  the failing step + only the auto_phase steps after it; (7) retry log
  off-by-one → 'retry N of M'; (8) prompt loop deduped into `_ask()`
  (on_fail/rail/checkpoint; tty+autonomy guards stay per-site). Refuted:
  skip stale-state, cli finally lock-release masking, hardcoded fallback
  step names (intended). Verified: runner suite extended 8 → 13 cases
  (budget-on-top, fallback-crash manifest, blocker surfacing, most-recent
  coarse selection, template validation) ALL PASS; both protocol dry-runs;
  gui_vs_engine ALL PASS (executor/snapshot untouched). Next: commit, then
  Phase 5 items or Phase 4 exp.t1/t2.
- **2026-07-17 (7)** — Phase 3 review fixes committed+pushed ITC `3be399d`.
  **Phase 5 code-complete, committed+pushed ITC `4aa1c27`** (all 7
  checklist items, details in the Phase 5 section above — NOT yet
  code-reviewed; superseded in part by `b9cbc66`, so its review is folded
  into the single `3be399d..b9cbc66` review at the end of this log). Highlights/gotchas: dig_on never sends
  trace data over the pipe (the GUI reads it off the LivePlot), so
  acquire_trace captures via a general.plot_1d patch in the child and stops
  through the normal 'exit' path at a cycle boundary; dig_on's l_mode is
  INVERTED (l_mode=1 → live_mode=0 = accumulating, phase-cycled — what the
  trace needs); GUI dig_start pre-flights with script_test=True,
  run_main_experiment is the real preview launcher. apply_cal inference
  needed a second rule the plan lacked: hahn_echo-style presets encode
  π/π₂ by LENGTH (2×) at equal amplitude — direct amp patching there would
  be wrong, hence the inverse-length scaling (amp ≈ linear, the same rule
  as the detection pair); pi_calibration results now carry
  length_ns / held_amplitude context. edfs auto: the failed-SNR path must
  NOT set the magnet (noise argmax). Verified: 13-case runner suite,
  tune_up (6/6) + overnight_t2 (4/4) dry-runs, gui_vs_engine ALL PASS
  incl. the new per-preset dig_on packing comparison (MIN_COMPARED gate
  ×2) + real-dig_on trace pre-flight + stub capture round-trip. Follow-up
  same session (user review): edfs auto gains `offset:` (signed FieldStr —
  magnet calibration shift) + `shift_g` in the result to measure it;
  l_mode question answered (n_averages = on-board per-phase-step shots;
  the phase-cycle sign-fold reads the persistent accumulator, which
  live_mode=1 RESETS on every call — no averages setting substitutes for
  the accumulating mode). Corollary pinned as an executor invariant (user
  point): the accumulating buffer is allocated once and NEVER cleared on a
  parameter change (flag_adc_buffer latch, Insys_FPGA.py:2438/2468), so a
  mid-preview live edit would corrupt the average — acquire_trace sends
  ONLY 'start'/'exit', never live-edit commands; a parameter change = a
  new acquire_trace call (fresh child, fresh accumulator). Driver audit of
  the (never-hardware-used) dig_on accumulating path (user request):
  PHASES>=2 is the everyday multi-scan exp accumulate mechanism
  (pulser_pulse_reset per cycle restarts nIP_No_brd/N_IP, so the blocking
  is_drain gate is fresh each cycle; intermediate readouts may return
  (None, None) → dig_on writes NaN frames — cosmetic, and the capture now
  refuses non-finite frames); PHASES==1 is NOT safe (no reset → is_drain
  never fires again, header nids may all fall out of the parser's
  in_range filter) → acquire_trace rejects single-phase presets with a
  clear error. HARDWARE_CHECKLIST item 2 doubles as this path's first
  bench validation (watch: cycle-boundary stall / missing trace / SNR not
  growing with sweeps). **docs/automation/HARDWARE_CHECKLIST.md** added:
  ordered list of everything runnable on the spectrometer today, with
  YAML snippets + expected outcomes (incl. the shift_g measurement run).
  Next: /code-review Phase 5, commit, then Phase 4 exp.t1/t2 (acquire_1d +
  max_duration → scan_control + the window/apply_cal consumers) and the
  hardware run.
- **2026-07-17** — Temperature re-phase rule (investigation-driven; the
  `2026_07_03_ap210_oTP_new` t1/t2 presets are the evidence). Two findings
  from that data: (a) zero-order is a detection-chain property, identical for
  T1 vs T2 at matched (T, field) in 25/26 pairs despite DETECTION starts of
  678.4 vs 409.6 ns, and flat across 3000–3460 G ⇒ one auto_phase per state
  serves every experiment; (b) it swings 215°→25° monotonically over 80–280 K
  at constant B1 ⇒ "once per run" was wrong. Only the vane invalidated
  anything before this, so a T-series silently carried a stale phase.
  Implemented: `session.invalidate_phase` (auto_phase only, vs
  `invalidate_fine_calibrations`' both — temperature does not move B1, and per
  the operator the vane is re-set only after a large ΔT to hold bandwidth);
  `tune.auto_phase` stamps `temperature_k`; `_rephase_check` in BOTH temp.set
  and temp.wait (temp.set-without-wait, and external-setpoint, both closed),
  fires in dry-runs too; `rephase_delta` param, default 5 K. ARCHITECTURE.md
  'Temperature rules' + HARDWARE_CHECKLIST §1 scope note added.
  **Window ns -> points truncation FIXED** (found while reviewing
  tune.echo_window's `factor` bound; the bound STAYS at min=1 -- that is the
  matched-filter optimum, SNR peaks at factor ~1.19 for a Gaussian echo and
  the 2.0 default trades 10% SNR for capturing 98% of it). The bug:
  `int(win_ns / tpp)` truncates on binary float error -- tpp is 0.4*dec,
  which has no exact binary form, so `int(259.2/1.6)` gives 161 not 162, and
  a requested 12.0 ns boundary lands at 11.6. Present in the GUI
  (awg_phasing_insys) as much as in the engine. At realistic echo widths
  (FWHM 20-500 ns) about a THIRD of windows have an edge one ADC point off.
  Magnitude is small: one point at a window EDGE sits in the echo tail (~6%
  of peak at factor 2), so the integral error is ~0.03% at dec=1, ~1% at
  dec=8. Worth fixing as correctness, not a data-integrity issue -- no
  published result is affected.
  Fix: `points_from_ns()` at module scope in awg_phasing_insys.py (a
  float-error-tolerant floor, +1e-9 point -- far above the ~1e-13 division
  error, far below any real off-grid entry, so floor() semantics are
  untouched), used at all 5 GUI sites (win_left x2, win_right x2, the
  Win_left/Win_right widget-init in the spin-box loop) and called DIRECTLY
  by engine/snapshot.py's win_points, as the engine already does with
  expand_phase_cycling -- sharing beats mirroring for a one-line arithmetic
  helper, at the known cost that gui_vs_engine.py cannot catch a bug inside
  it. Verified: 0/64000 on-grid truncations (was 10462), off-grid floor()
  unchanged (12.7 ns @ 0.4 -> 31), harness ALL PASS, both example protocols
  dry-run clean.
  **CORRECTION to an earlier claim in this session:** a degenerate
  win_left == win_right (which both integration paths would consume as a
  bare empty `[wl:wr]` slice => silent all-zero scan) is NOT reachable from
  echo_window. It needs FWHM*factor < tpp, i.e. an echo narrower than 3.2 ns
  even at dec=8 -- a single ADC sample, not an echo. The randomized sweep
  that "found" it was drawing FWHM from 1 ns. Real echoes give windows of
  7-52 points at worst (dec 8..1). The GUI's equality guard
  (`cur_win_right += 1`, in dig_stop's param-file writer, not on the exp
  path) is therefore left exactly as it is; no real preset of the 85 checked
  (repo + oTP campaign) has an empty window.
  **Fork port: NOT NEEDED — the forks are IMMUNE, verified not assumed.**
  NIOCH / NIOCH_Q `awg_phasing.py` + `phasing.py` set
  `time_per_point = 2` (both assignments in all four files are that literal;
  never dynamic). 2 is a power of two, so `ns / 2` is exact in IEEE 754 and
  `int()` can never truncate short: 0 of 16001 on-grid spin-box values, vs
  5580 for ITC at dec=1. The bug needs ITC's `tpp = 0.4 * decimation`, and
  0.4 has no exact binary form. Porting would be pure churn plus a docstring
  that is false there. Re-check IF a fork ever moves to a dynamic /
  non-power-of-two time_per_point.
  The real gap that scan found was in ITC itself: **`phasing_insys.py` (the
  RECT tool) had all 5 sites** and is now fixed too — it imports
  points_from_ns from awg_phasing_insys (sibling import, same package, the
  module is __main__-guarded and side-effect-free; the engine already reaches
  into it the same way for expand_phase_cycling). epr_auto has no RECT path
  yet, so this is a GUI-only fix, but it lands before RECT support does.
  `sync_check.py` green before and after; no fork repo touched.
  Also added: HARDWARE_CHECKLIST 'Presets' section — where the pulse sequence
  actually comes from (the YAML names a preset, it never describes a
  sequence), bare-string vs mapping step form, the per-step default table,
  name resolution order, the IQ Correction: 2 requirement, and what the
  session overrides on top of the preset. Written because the bare
  `- tune.auto_phase` snippets read as if no preset were involved at all.
  **COMMITTED: ITC `b9cbc66`** (+ hash record `6cdeaa0`).

  ### Review brief (DONE 2026-07-18, see that entry): ONE code-review of `3be399d..b9cbc66`

  **Scope = the whole unreviewed backlog, as ONE review, not three.** Three
  commits are unreviewed and they OVERLAP, so reviewing them separately would
  review superseded code:
  - `4aa1c27` Phase 5 (tune-up completeness) — was flagged "review first" and
    never got it;
  - `5136a3c` phasing tools: Accumulation Mode checkbox — **NOT under review:
    user judged it trivial (2026-07-17), accepted as-is. It is inside the range
    only because it touches the same two files as `b9cbc66`
    (awg_phasing_insys.py, phasing_insys.py) and so cannot be split out by
    path. Spend no effort on it;**
  - `b9cbc66` this session (temperature re-phase + points_from_ns).
  `b9cbc66` rewrites FIVE files Phase 5 introduced or changed (temp.py,
  tune.py, steps.py, session.py, snapshot.py) — e.g. Phase 5's temp.py has no
  rephase_delta and its echo_window has an unargued `factor` bound. Review the
  RANGE against the current tree; do NOT review `4aa1c27` in isolation.
  (`20b70c0` / `b061c67` in the range are docs-only.)

  Reviewer's brief for the `b9cbc66` part — the judgement calls worth a
  second opinion, and the two claims this session already had to retract
  (the Phase 5 part's own gotchas are in the Phase 5 section above):
  - `rephase_delta` default 5 K is a guess, not a measurement. The oTP
    series only sampled 40 K steps (8 deg from 80->120 K, 55 deg from
    240->280 K), so the phase-vs-T slope is unknown below 40 K and is
    strongly non-linear across the range. 5 K may be far too loose near
    280 K and pointlessly tight near 80 K.
  - `_rephase_check` fires in temp.set AND temp.wait (deliberate: covers
    set-without-wait and external setpoints, and both are idempotent) --
    but that means two invalidation points for one physical event. Check
    the log noise and that no path double-reports.
  - `was is None` (phased before any temp step) invalidates. Conservative;
    could be judged wrong for a protocol that phases at ambient and then
    sets that same temperature.
  - Invalidation is a log line + a dropped key, so a protocol that changes
    temperature and does NOT re-run tune.auto_phase silently falls back to
    the PRESET's stored zero_order. That is better than a stale session
    value but is still silent. A hard gate was considered and not built.
  - `points_from_ns` is imported by phasing_insys.py FROM awg_phasing_insys.py
    (RECT tool -> AWG tool). Import-safe and drift-free, but the dependency
    direction is odd; a small shared control_center module (cf.
    time_log_spinbox.py) may be the better home.
  - The +1e-9 epsilon is justified in the docstring but is a magic number.
  - Retraction #1: "run auto_phase once per protocol" was wrong (temperature).
    Retraction #2: the degenerate-window / silent-all-zero hazard was NOT
    reachable -- the sweep that "found" it drew FWHM from 1 ns. Both are
    corrected in this file and in the code comments; if the reviewer finds
    either claim still asserted anywhere, that is a real defect.
  Next (AFTER that single review + its fixes): Phase 4 exp.t1/t2, then the
  hardware run per HARDWARE_CHECKLIST.md.

- **2026-07-18** — **The single `3be399d..b9cbc66` code-review DONE** (Opus
  18-agent workflow, high effort, range vs current tree; Accumulation-Mode
  commit excluded per the brief). 15 candidates -> 11 verified -> 8 distinct
  findings, ALL FIXED (uncommitted):
  (1) field.py edfs: failed-SNR early return had no `pick=='value'` guard —
  an explicitly-requested field was never set on a weak sweep (magnet left
  stale, downstream steps at the wrong field). Now: pick='value' skips the
  auto-escalation entirely (the requested field never depends on the echo)
  and ALWAYS parks the magnet; the failed judge + diagnosis still surface.
  pick='max' keeps the do-NOT-move-to-a-noise-argmax invariant (tested).
  (2) steps.py exp.t1/t2 forced `_apply_cal` inference — a session
  pi_calibration + a non-2-level preset (e.g. 4pdeer's 3 amp levels) meant
  hard StepFailure with no opt-out, incl. --test dry-runs. **User decision:
  `apply_cal: none`** (CalMap literal; YAML-safe — `none` is a string, only
  `null`/`~` are YAML null) = run preset-stored values, logged; inference
  failure without the opt-out stays hard.
  (3) _check_edfs skipped lo>=hi for range='auto' -> `span: '0 G'` passed
  config-check into a 200-point zero-width sweep; now `range: auto` requires
  a positive span. (Related PLAUSIBLE) auto lo could go negative (low nu /
  wide span; 'auto' literal short-circuits FieldStr validation) -> runtime
  clamp to 0 G with a log line.
  (4) temp.py `was is None` dropped an ambient auto_phase unconditionally on
  the FIRST temp step. **User decision: stamp the real cryostat temperature**
  — `tune._phase_temperature` now reads Lakeshore channel B when no temp
  step has run (canned in test mode), so the delta rule applies uniformly;
  None (=> conservative drop) only when the Lakeshore is unreachable. Read
  at MEASUREMENT time, not check time — temp.wait's external-setpoint case
  may already be ramping by check time.
  **User decision: `rephase_delta` default 5 K -> 1 K** (swing ~1 deg/K
  average, steeper warm; 1 K keeps carried error at phase-noise level).
  (5) apply_calibration >100% inverse-length raise reachable from dry-runs
  via the CANNED pi values -> canned cal now logs + leaves the slot
  unpatched (real cal still raises — genuine physics).
  (6) `_SOFT_LEN_RATIO = 2.5` shared constant unifies the hard/soft cut that
  was 2.5x in _infer_cal_map vs 2x in _scale_detection_pair (the [2.0, 2.5)
  band got opposite roles across the two primitives). Verified against every
  repo preset: detection pairs sit at 3x+, hahn's length-encoded pi at
  exactly 2x stays hard — no real preset changes classification.
  (7) points_from_ns duplicated docstring paragraph removed (ITC-only file).
  REFUTED by the review (design stands): double `_rephase_check` set+wait
  (first pop empties the key — no double-report); points_from_ns import
  direction (engine already hard-depends on awg_phasing_insys);
  acquire_trace plot-per-step assumption (dig_args forces fft_flag=0);
  script_test=False branch (run_main_experiment exercises it). Neither
  retracted claim found re-asserted. ARCHITECTURE.md (rephase 1 K + stamp
  semantics, 2.5x shared cut) + HARDWARE_CHECKLIST (1 K) updated.
  Verified: 30-check fix suite (scratch test_review_fixes.py) ALL PASS,
  13-case runner suite ALL PASS, tune_up (6/6) + overnight_t2 (4/4)
  dry-runs clean, gui_vs_engine ALL PASS. Next: commit, then Phase 4
  exp.t1/t2 (acquire_1d + max_duration -> scan_control + window/apply_cal
  consumers), then the hardware run per HARDWARE_CHECKLIST.md.
  **Review fixes committed+pushed ITC `3c492e4`.**

- **2026-07-18 (2)** — **Phase 4 code-complete** (`primitives/exp.py`, new;
  checklist details in the Phase 4 section above). Key discoveries encoded in
  code comments:
  - **Linear Time axis rule** (Worker.exp, xd==0 path): step = the DETECTION
    start increment, f_delay = the first moving P2..P9 pulse's start ⇒ for
    hahn the axis is tau_start + i·2·tau_step = total evolution time, the
    correct T2 axis. `_retau` therefore re-anchors ALL moving pulses in the
    preset's own st_inc ratio (units = st_inc / min st_inc): start +=
    units·(tau_start − anchor), st_inc = units·tau_step; anchor = first
    moving P2..P9 pulse (the axis start). Rejects a below-zero start.
  - **Log Time**: the worker builds delays itself from Log Start/End
    (10^linspace → grid-round → np.unique ⇒ POINTS CAN SHRINK), axis offset =
    first moving pulse's start; the swept ADDED delay spans ~(t_end −
    t_start) with t_start setting the log-density floor. exp.t1 only
    overrides log_start/log_end = log10(ns) — no pulse mutation.
  - Both fits run on t = x − x[0]: the constant axis offset (preset initial
    geometry) folds into the amplitude, leaving T1/T2 exact.
  - **Repetition-period gotcha found by the dry-run pre-flight** (the driver
    assert fired on t_end 5 ms at the preset's 480 Hz): both steps gain a
    `rep_rate` param (preset override) + `_period_check`, a friendly
    pre-check that names the knob; the driver assert stays the authority.
  - `max_duration` policy: don't trust projections before 2 % / 10 s; 5 %
    grace band; ratchet-down only (never raise a sent limit).
  Verified: scratch test_phase4.py, 39 checks ALL PASS — _retau geometry vs
  the hahn preset numbers (601.6/25.6 DET), synthetic-truth fits (T2 1.8 µs
  β 1.15 within 5 %, T1 1.2 ms log-spaced, both ALSO with flipped sign and
  signal parked in Q), characteristic-time guess order-of-magnitude,
  relaxation_fit pass/fail, duration-policy shrink/ratchet/grace, window
  plumbing, end-to-end t2/t1 primitives over a stubbed _acquire incl.
  garbage-data fit-failure path. Regression: 30-check review-fix suite,
  13-case runner suite, tune_up 6/6 + overnight_t2 4/4 (exp.t2 real path)
  + scratch t1 protocol (exp.t1 + window: preset + apply_cal: none +
  max_duration + rep_rate 100) dry-runs clean, gui_vs_engine ALL PASS.

  **COMMITTED+PUSHED: ITC `cba862b`** (review fixes earlier this session:
  `3c492e4`).

- **2026-07-18 (3)** — **relaxation_fit reworked: adj-R² floor -> dAICc gate**
  (user suggestion "probably AIC is better", validated on the REAL
  2026-07-03 oTP campaign, `~/Documents/OTP/2026_07_03_ap210_oTP_new`
  t1/ + t2/, 56 traces, 80–280 K x 4 fields). Findings (harness: scratch
  aic_investigation.py):
  - adj-R² >= 0.85 punishes NOISE, not fit validity: it FAILED 3 real 280 K
    traces (SNR 12–27) whose fitted T2s were physically sound (0.1–0.4 us —
    an overnight run would have aborted on usable data), and 18/56 at 10x
    noise where the time constant was still recovered on most.
  - dAICc = AICc(constant-mean null) − AICc(model): every real trace >= 321
    at any noise level that still held signal; no-signal null (shuffled
    controls, n=1120) max 80, p99 13 — the tail comes from a tiny-beta
    stretched exp latching onto extreme points. Threshold 150 = geometric
    midpoint, ~2x margin both ways. Validation on the new judge: 56/56 real
    PASS, 0/280 shuffled PASS.
  - Wrong-model control: BOTH metrics score a T1 model on T2 data highly
    (adj 0.94 / dAICc 1392) — and residual-structure tests cannot be the
    gate either, because even CORRECT fits here have structured residuals
    (ESEEM modulation on T2; the mono-exp T1 approximation, DW down to
    0.01 with adj-R² 0.99). The gate's question is 'is there a described
    relaxation signal', not 'is the model exact' — documented in the judge.
  - Caveat pinned in the docstring: dAICc scales with N (calibrated at
    N ~ 300–500); details now carry adj_r2 + rmse for the manifest.
  Verified: 39-check Phase 4 suite + 30-check review suite + 13-case runner
  suite + both dry-runs + gui_vs_engine ALL PASS after the rework.
  **COMMITTED+PUSHED: ITC `f7ebe93`**; HARDWARE_CHECKLIST restructured to
  checklist-form Phase 4 items 8–10 + full session-state override list in
  the Presets section, `ff90708`. Session total: `3c492e4` (review fixes),
  `cba862b` (Phase 4), `6fdfe87`/`ff90708` (docs), `f7ebe93` (judge).

- **2026-07-18 (4)** — **Phase 6 planned** (user request: T1/T2 at fixed T
  across several fields + SNR-controlled scan count). Field series is
  possible today via repeated `field.set` blocks; `foreach:` promoted from
  backlog to make it ergonomic. Both design questions answered from REAL
  data (`~/epr_auto_dev/field_phase_snr_check.py` over the oTerPhenyl
  t1/+t2/ 48-trace grid + oTP_new ED sweeps): (1) phase is
  field-independent (≤5° across the line; up to ~40° across
  temperature/retune) ⇒ foreach does NOT rephase on field moves;
  (2) echo_snr reproduces the human SNR judgement (unique failing trace =
  the one excluded from the published fits) and the operator already
  hand-adapted scans per field 6→46 — the exact behaviour `target_snr`
  automates; MAD-of-diff (not fit-residual sigma) confirmed as the stop
  metric. Full numbers in the Phase 6 section; design decisions in
  ARCHITECTURE.md "Series & SNR-driven scans". Next: implement foreach
  (no Worker/pipe changes) first, then the target_snr policy + Worker
  scan-boundary message (mirror rule + gui_vs_engine).
  **COMMITTED+PUSHED with the Phase 7 plan: ITC `b2c22c0`** (docs only —
  does NOT extend the pending `3c492e4..ff90708` review range).

- **2026-07-18 (5)** — **Phase 7 planned** (user request): epr_auto user
  manual as a LOCAL MkDocs Material site (`docs/epr_auto_site/`), same
  theme/version/conventions as `/home/anatoly/atomize_docs` so pages lift
  into the public site verbatim later. Key decision: the step reference is
  GENERATED from the STEPS registry (introspection verified headless this
  session — summary/params/defaults/help all available), so it cannot
  drift from code; empty param help strings get filled in steps.py as part
  of the phase. Page outline in the Phase 7 section. Committed with the
  Phase 6 plan: `b2c22c0` (docs only).

- **2026-07-19** — **The `3c492e4..ff90708` Phase 4 code-review DONE** (Opus
  workflow, 24 agents all pinned `model:"opus"` high-effort — 4 finder
  dimensions → 10 candidates → 2-skeptic adversarial verify each → 8 survived
  (3 were the same dAICc-N finding from 3 dims), **6 distinct, ALL FIXED**;
  user chose every fix, all uncommitted):
  (1) **HIGH — `_fit_stretched` dropped the axis origin.** The worker's saved
  Linear-Time axis IS the total evolution time `2·tau`: f_delay = the
  DETECTION start (`2·tau_start`; the P2..P9 loop tests `len_inc`, which is 0
  for hahn, so it falls through to `rect1[1]` = DET start — NOT the pi
  position, corrected after the user flagged it), step = the DETECTION
  increment (`2·tau_step`); the manual-x0 branch (xd≠0) uses the preset's
  x0/xdelta instead. So the old docstring's "total evolution time" was right;
  the bug was purely that the fit rebased `t = x − x[0]`, dropping the nonzero
  `x[0] = 2·tau_start` origin — which for a stretched exp does not fold into
  the amplitude, so t2/beta came out 8–32% LOW for β≠1 (verified: β=1.5 Tm
  2 µs → 1633 ns, matching the old code). **Fix:** fit the ABSOLUTE saved axis
  (no rebase), identical to what Data Treatment already does; verified 0.00 %
  recovery for β∈{1,1.5,1.8,2}. `_fit_recovery` (T1, single-exp) rebases
  safely — the origin folds into b. **Data Treatment is fully correct** (it
  fits the same absolute evolution-time axis, no residual bias) — §8 updated.
  (2) **MEDIUM — dAICc fixed-150 gate is N-dependent** (found by 3 dims).
  dAICc ~ n·ln(null_rss/rss) scales with n, so a valid fit at points=100 or a
  dedup-shrunk T1 grid false-FAILED and aborted the run. **Fix:** gate on the
  PER-POINT density dAICc/n ≥ 0.375 (N-invariant; = old 150 at n=400).
  Re-validated N-invariant on synthetic (n=30..400 pass, flat noise rejected).
  (3) **MEDIUM — echo_snr hard-gated the relaxation steps**, undoing the
  f7ebe93 noise-tolerance design (a noisy-but-valid trace relaxation_fit
  accepts still aborted on SNR<3). **Fix:** `_run_primitive` gained an
  `advisory_extra` param; exp.t2/exp.t1 pass `('echo_snr',)` so echo_snr is
  advisory THERE only — it stays a hard gate for tune.*/field.*.
  (4) **MEDIUM — `_duration_policy` transient-stall ratchet.** One Status tick
  during the per-scan temp-settle wait (~8 s, no pct advance) spiked the
  projection and permanently cut scans. **Fix:** require the over-budget
  condition to persist K=3 consecutive ticks (a sub-budget tick resets the
  streak); still ratchet-down-only once committed.
  (5) **LOW — exp.t2 accepted a fixed-echo preset.** `_retau` only required
  some moving P2..P9, so a DEER-style preset (4pdeer: DET frozen, only pump
  moves) produced a pump-position axis mislabeled T2. **Fix:** require the
  DETECTION slot (index 0) to move, else raise. hahn still accepted.
  (6) **LOW — `_apply_cal` load error escaped as RunnerAbort.** load_preset
  ran outside `_run_primitive`'s try, so a corrupt `.phase_awg` aborted the
  whole protocol ignoring retries/on_fail. **Fix:** wrap the load →
  StepFailure. REFUTED (design stands): T1 mono-exp accepting stretched data
  (intended failure mode); fit-failure dict "omits keys" (refuted 2×).
  Verified: 13-check fix harness ALL PASS (scratch verify_fixes.py),
  overnight_t2 4/4 + tune_up 6/6 dry-runs clean, gui_vs_engine ALL PASS
  (incl. the SC scan-control channel). ARCHITECTURE unaffected;
  HARDWARE_CHECKLIST §8/§9 updated (saved-axis-vs-fit-axis, per-point gate,
  echo_snr advisory). **UNCOMMITTED — awaiting the go-ahead to commit.**
  Next: commit, then the hardware run per HARDWARE_CHECKLIST.md ('Newly
  hardware-runnable' first), then Phase 6 planning. **Bench follow-up flagged
  by the review: the per-point 0.375 threshold is derived from ONE campaign —
  re-validate dAICc/n on the next real T1/T2 series before trusting it as the
  overnight abort gate.**
  **Review fixes committed+pushed ITC `eeea8ac`** (after a user correction:
  the worker's Linear-Time f_delay is the DETECTION start = 2·tau_start, not
  the pi position — the fix became fit-the-absolute-axis, matching
  data_treatment, which is fully correct with no residual bias).

- **2026-07-19 (2)** — **Phase 6 code-complete** (all three items, see the
  Phase 6 section above). Implementation notes:
  - **foreach** (protocol.py `Foreach` dataclass + `_parse_foreach`): keys
    var/values/steps/on_fail; `$VAR` substitution recurses into list/mapping
    params (`_apply_subst`), applied BEFORE `param.validate` so a bad
    substituted value is a load-time ProtocolError per iteration; sub-steps
    fully parsed per value at load (`iterations` = list of Step groups);
    numeric scalar values allowed (stringified), nested foreach rejected.
    Runner: `_run_foreach` sets `session.loop_tag` ('B_3318G' — stamped into
    save_path CSV names) + `session.loop_context` (var/value/index — stamped
    into each manifest entry as `loop`); per-iteration on_fail:
    **continue (default)** catches the sub-step RunnerAbort, records, moves
    to the next value; abort re-raises. `[i/n]` counters count EXPANDED
    steps (`_count_steps`). Rail fallback scans `protocol.steps` with
    getattr-guarded `.name` (Foreach has none); sub-steps pass index 0 so
    the fallback never fires inside a series (tune before the loop).
    cli.py validate prints `foreach[B]`.
  - **target_snr** (steps.py param on exp.t2/t1 → exp.`_snr_policy`):
    on_scan_data consumer; stop metric = judges.echo_snr on the accumulated
    complex curve — the SAME metric as the final judge; SNR_k >= target →
    'SC k' immediately (direct measurement, any k); else projection
    needed = ceil(k·(target/SNR_k)²), acted on only from k >= 2 (one noisy
    early estimate must not cut), never below k, None when >= the scans
    ceiling.
  - **Worker scan-boundary message** (mirror rule): `('ScanData',
    (k, data_x.copy(), data_y.copy()))` sent after each completed scan in
    `exp` AND `exp_log`, gated on `getattr(self, 'scan_data_flag', 0)` (a
    worker ATTRIBUTE set via `_hand_attrs`, like awg_grid_cur — the GUI
    never sets it, so GUI runs are behaviour-identical) `and iq_cor == 1
    and not script_test and self.command != 'exit'`. Executor: run_worker
    gains `on_scan_data(k, i, q)`; **both channels share one `_maybe_resize`
    ratchet — a resize is only ever sent DOWNWARD from the lowest value
    already sent**, which is how target_snr composes with max_duration
    (min wins) and how a later larger projection can never re-raise a sent
    limit. acquire_1d/tune._acquire thread it through.
  - protocols/field_series_t1t2.yaml NEW: the motivating tune-once →
    foreach-over-4-fields T2+T1 protocol with target_snr 10 / scans 48
    (the oTP operator's hand-adapted 6→46 range).
  Verified: 12-check foreach suite (parse/substitution/save_path/error
  cases) + 13-check Phase-6 suite (_snr_policy stop/guard/shrink branches
  incl. a real shrink projection 8→14-of-64; executor ScanData routing +
  min-ratchet ['SC8','SC6','SC4'] and no-re-raise ['SC5' only] via stub
  workers over the real pipe; _hand_attrs flag opt-in/default-off) +
  on_fail continue-vs-abort dry-runs (2/3 ran vs ABORT) + field-series
  16/16, overnight_t2 4/4, tune_up 6/6 dry-runs + Phase-4 13-check
  regression harness + **gui_vs_engine ALL PASS** (Worker changed → mirror
  rule exercised).

  **Same-session self-check of the foreach paths (user request) found and
  fixed TWO defects before commit:**
  - **Operator aborts were swallowed by `on_fail: continue`** — the
    iteration-level `except RunnerAbort` caught EVERYTHING, including an
    operator abort at a checkpoint inside the iteration and
    unexpected-error aborts (a code bug would recur every iteration → N
    tracebacks, then status 'finished'). Fix: `RunnerAbort(hard=True)` for
    operator decisions (checkpoint abort/EOF/no-tty, interactive
    ask→'abort-op') and unexpected non-StepFailure errors; `_run_foreach`
    re-raises hard aborts regardless of on_fail. StepFailure-driven aborts
    (the designed case) still continue the series. Verified: TypeError bug
    → re-raised hard=True; StepFailure → both iterations tried.
  - **`$VAR` substitution was plain str.replace** — `$B` corrupted a
    literal `$Bank`, and a typo'd `$C` flowed into validation as a literal
    string. Fix: whole-name regex substitution + **unresolved `$name` is a
    load-time ProtocolError** naming the defined vars.
  Re-verified after the fixes: all suites + dry-runs + gui_vs_engine green.
  **COMMITTED+PUSHED: ITC `94481c7`** (review fixes earlier this session:
  `eeea8ac`).

  ### Review brief (DONE 2026-07-20, see that entry): ONE Opus /code-review of Phase 6 `94481c7`

  Scope = the Phase 6 commit `94481c7` against the current tree. Files:
  protocol.py (Foreach/_parse_foreach/_apply_subst), runner.py
  (_run_foreach/_do_step/_count_steps/loop stamping, rail-fallback getattr
  guards), session.py (loop_tag/loop_context/save_path), cli.py (validate),
  steps.py + primitives/exp.py (target_snr/_snr_policy), engine/executor.py
  (on_scan_data/_maybe_resize shared ratchet/_hand_attrs flag),
  **awg_phasing_insys.py (Worker exp/exp_log ScanData sends — GUI-shared
  file, review extra carefully)**, protocols/field_series_t1t2.yaml.
  Run it the usual way (Opus agents pinned via model:'opus', workflow, high
  effort). Reviewer's brief — judgement calls worth a second opinion:
  - `_apply_subst` is now whole-name regex substitution with a load-time
    error on unresolved `$name` (fixed same session — verify the fix and
    whether a legitimate literal `$` in a param value can ever be needed;
    there is currently NO escape syntax).
  - `RunnerAbort.hard` semantics (added same session): operator decisions
    + unexpected errors re-raise through `on_fail: continue`. Check every
    RunnerAbort site is classified correctly — notably the unattended
    ask→abort (no tty / autonomous) stays SOFT, so an unattended series
    continues past it; is that right?
  - foreach values are stringified scalars; a numeric 3318 becomes '3318'
    (no unit) — FieldStr then rejects it. Intended (units belong in the
    YAML), but the error message may confuse.
  - `_run_foreach` gives sub-steps index 0 ⇒ rail fallback disabled inside
    a series even when the protocol HAS an earlier coarse stage. Decision
    was deliberate (vane move mid-series invalidates the series' premise);
    second opinion welcome.
  - The manifest's `loop` stamp relies on session.loop_context being reset
    in a finally: — check crash paths (KeyboardInterrupt mid-iteration).
  - `_snr_policy` k>=2 guard: scan 1 with SNR >= target STOPS at 1 (direct
    measurement, no guard) — is one scan's MAD estimate trustworthy enough
    to stop on, or should stop also require k >= 2?
  - The sqrt(N) projection assumes noise-dominated accumulation; a drifty
    system (phase drift across scans) breaks SNR ∝ sqrt(k) — the policy
    would over- or under-project. Ratchet-down-only makes under-projection
    permanent (same accepted trade as max_duration).
  - Worker sends ScanData BETWEEN scans only when the command is not
    'exit'; the arrays are .copy()'d — check pipe-volume (POINTS floats x
    2 per scan) is negligible vs the Status traffic and that an engine
    OLDER than this change (no on_scan_data) ignores the message (it does:
    unknown kinds fall through) — but confirm no fork/GUI parent parses
    the same pipe.
  - Executor `_maybe_resize` shared DOWNWARD-only ratchet replaced the old
    send-on-change semantics for scan_control too — confirm no existing
    consumer relied on re-raising a limit (grep says only exp.* use it).
  Next (AFTER the review + fixes): the hardware run per
  HARDWARE_CHECKLIST.md (now including a field-series + target_snr bench
  item), then Phase 7 (MkDocs manual) or the GUI launcher.

- **2026-07-20** — **Phase 6 Opus code-review of `94481c7` DONE** (workflow,
  3 Opus reviewers @ high effort over the briefed dimensions + adversarial
  Opus verification of every non-note finding; 6 agents, ~417k tokens).
  **1 confirmed minor, 2 findings refuted on verification, 3 notes, all 7
  brief questions answered.**
  - **CONFIRMED (minor, benign): target_snr stops one scan late.**
    ScanData(k) is sent at the scan boundary (awg_phasing_insys.py ~5406 /
    ~7106) but the worker only recv()s commands inside the per-point loop,
    and `_scan_iter` re-checks `k <= SCANS` between scans WITHOUT polling —
    so a stop-now `SC k` (or degenerate needed==k) is consumed at scan
    k+1's first point and that scan runs to completion: exactly one extra
    scan past the target. Verifier confirmed data correctness is unaffected
    (digitizer_at_exit recomputes exact state; extra scan = strictly better
    SNR); side effects are cosmetic (Status >100% on the trailing scan;
    current_scan>total_scan skips the per-scan is_drain on that scan).
    Genuine UPWARD projections (needed>k) are NOT affected — SC{needed} is
    consumed during scan k+1 < needed and the run stops exactly at needed.
    Same class as the pre-existing duration-SC boundary behaviour. Decision:
    accept as-is (a fix means polling between scans in the GUI-shared
    worker loop — not worth the risk for one bonus scan); documented here.
  - **Refuted:** (1) "rail-fallback log misleads inside a series" —
    unreachable: no foreach-body step (field.set/exp.*) can raise a
    StepFailure carrying `rails`, so _rail_fallback never runs in-series;
    (2) "unguarded on_scan_data/scan_control callback exception loses the
    run" — mechanically true consequence but no reachable input makes the
    callbacks raise (echo_snr degenerate cases all land in the
    isfinite-score guard); optional hardening only.
  - **Notes (no defects):** [pos/n] header drifts low after a soft-aborted
    iteration (cosmetic; final ran/n summary stays honest); ScanData curve
    is the lagging live-view accumulation, not the at_exit-exact curve
    (bias is conservative — inflated MAD sigma → later stop, never a false
    early-stop); scan_data_flag↔on_scan_data pairing is a hand-maintained
    invariant outside gui_vs_engine coverage (degrades gracefully on
    mismatch; consider an assert in _acquire).
  - **Brief verdicts (all endorse the shipped design):** $-escape not
    needed (regex only fires on $identifier; add '$$' later if ever
    needed); unattended ask→abort staying SOFT is right for overnight
    resilience (a per-iteration condition that must kill the series is
    modelled as foreach on_fail:abort or a non-StepFailure raise —
    document); stringified-scalar FieldStr error is adequate (optional:
    append "(from foreach B = 3318)" context in _parse_step's except);
    index-0 rail-fallback suppression in-series is correct physics;
    k=1 direct-measurement stop is defensible (same metric as the final
    judge; mild lean to add k>=2 for symmetry — and the one-scan-late
    behaviour means the SAVED data has >=2 scans anyway whenever scans>1);
    projection is scale-invariant under sqrt(N) noise (no oscillation, no
    ceiling overshoot) but min-of-noisy-estimates biases the ratchet LOW →
    systematic slight undershoot of target; if it matters on the bench,
    require a sub-ceiling projection to persist 2 consecutive scans
    (OVER_TICKS-style) before committing; attribute (_hand_attrs) transport
    for scan_data_flag is the right channel (precedent: awg_grid_cur),
    needs no harness change.
  - **Candidate follow-ups (NOT applied, operator's call):** (a) assert
    flag↔callback pairing in _acquire; (b) OVER_TICKS-style 2-scan
    persistence for SNR projections; (c) k>=2 on the stop branch; (d)
    substitution context in ParamError; (e) try/except around executor
    callbacks. None are defects; (b) is the only one with a measurable
    physics effect (target undershoot) — decide after the bench run.
  Next: unchanged — hardware run per HARDWARE_CHECKLIST.md, then Phase 7
  (MkDocs manual) or the GUI launcher.

- **2026-07-20 (2)** — post-review Q&A + ScanData widened to the other
  worker modes (user direction):
  - **"Can a smaller SC value avoid the one-extra-scan?" — No.** The value
    is irrelevant: by the time any SC is consumed (first poll inside scan
    k+1's point loop), `_scan_iter` has already committed scan k+1; every
    value <= k+1 means "finish after scan k+1". The only parent-side cure
    is a PREDICTIVE stop (fire when SNR_k >= target*sqrt(k/(k+1)), letting
    the unavoidable scan k+1 carry it to ~target) — rejected for now: it
    trades the direct-measurement guarantee for a projection that can land
    under target with no re-raise. Decision stands: accept the bonus scan.
  - **ScanData added to exp_eseem + exp_field** (same gate:
    `getattr(self,'scan_data_flag',0) and iq_cor==1 and not script_test
    and command != 'exit'`; GUI untouched — flag default off).
    exp_field: full parity with exp — SC honoured, so a future EDFS step
    gets target_snr for free (sent before the settle wait/ramp-down).
    exp_eseem: **monitor-only** — ESEEM Avg locks SCANS (SC acked but
    ignored), and k = cycle*SCANS + k counts ALL accumulated scans across
    tau-averaging cycles so a consumer sees a monotone count. Engine-side
    consumers (an EDFS target_snr step) are future work; the worker side
    is ready. **gui_vs_engine re-run: ALL PASS** (13/13). UNCOMMITTED.
  - **exp.t1 detection tau is preset-only (confirmed):** the step exposes
    only t_start/t_end (Log Start/End), rep_rate, window, apply_cal; the
    pi/2–pi tau and all pulse geometry come from the preset (amplitudes
    aside via apply_cal). If a `tau` param is ever wanted (ESEEM-blind
    tau choice), it is a `_retau`-style re-anchor of the detection pair +
    DETECTION — but changing tau invalidates tune.echo_window's stored
    window, so it must force window='preset' or re-run echo_window.
    Phase 7 candidate, not planned.
  - **Auto rep-rate (Phase 7 candidate, sketched):** new `tune.rep_rate`
    step — log-grid rep-rate sweep on the echo preset, fit amplitude vs
    period to 1−exp(−t/T1_eff); store a session calibration like the pi
    calibration; exp.* rep_rate gains 'auto' = 1/(5·T1_eff) (quantitative,
    <1% saturation error) with a possible 'sensitivity' variant
    (period ≈ 1.26·T1, max S/√time) for EDFS/tuning-only steps. Cheap
    alternative: after a completed exp.t1, stamp T1 into the session and
    let rep_rate: auto reuse it for subsequent steps at the same
    field/temperature.
  - **Full-2D scan control (deferred):** the automation stop metric stays
    on the window-integrated 1D curve (iq_cor==1). For a future full-2D
    protocol, do NOT ship the matrix over the pipe — add a worker-side
    per-column window integral and send THAT as ScanData (reuses echo_snr
    unchanged); save2d already captures the transients for offline use.
    No concrete protocol needs it yet.
  - **Follow-up decisions (implement after the hardware check):**
    ADOPT (a) scan_data_flag↔on_scan_data pairing assert in _acquire;
    ADOPT (d) foreach substitution context appended to ParamError;
    ADOPT (e) try/except around executor scan_control/on_scan_data
    callbacks (log + treat as no-resize) — insurance for the future
    EDFS/2D policies; CONDITIONAL (b) OVER_TICKS-style 2-scan persistence
    for SNR projections — decide from bench achieved-vs-target SNR;
    DROP (c) k>=2 stop guard — redundant (boundary consumption already
    gives >=2 accumulated scans whenever scans>1, and the stop metric
    equals the final judge).

- **2026-07-20 (3)** — **ScanData commit + Phase 8/9 planned + Phase 8
  code-complete** (user direction). Review fixes committed: ITC `1c1432c`
  (exp_eseem/exp_field ScanData + the review record). Phase 8/9 sections
  added above; Phase 8 implemented same session:
  - **Status clamp** (awg_phasing_insys.py, GUI-shared): `min(100, ...)`
    on the identical Status expression in exp/exp_log/exp_field/
    exp_amplitude (one replace-all — the four SC-honouring loops;
    exp_eseem holds SCANS fixed and cannot overshoot). Also caps the
    same overshoot for a GUI-side live scans shrink.
  - **tune.rep_rate** (primitives/tune.py `rep_rate` + steps.py):
    details in the Phase 8 section. Judge lesson from the unit suite:
    echo_snr mis-fails a flat 4-point echo curve (no peak above
    baseline) and a SINGLE 4-point phase_coherence can pass pure noise
    (resultant variance at N=4; one rng draw hit R=0.77 > 0.7) —
    judged on all steps x points samples concatenated instead.
    exp.py `_resolve_rep_rate` ('auto' → session, logs the resolution,
    StepFailure when absent); steps.py exp.t1/t2 rep_rate → AutoOr.
  - **field.edfs target_snr**: `wa.scan_data_flag = 1` +
    `on_scan_data=_snr_policy(...)` in primitives/field.py (threaded
    through the auto-span escalation re-run too), param in steps.py.
    Same echo_snr metric as the step's own hard judge.
  All checks green (see the Phase 8 "Verified" block).
  **Phase 8 COMMITTED: ITC `e339240`** (same session, user request).
  **Phase 7 re-planned** (user direction): the epr_auto manual goes
  straight onto the public atomize_docs site as a Projects-tab
  subsection (`docs/projects/epr_auto/` + nav), cross-linked with
  `projects/endstation.md` (= Atomize_ITC's page) — see the rewritten
  Phase 7 section.

- **2026-07-20 (4)** — **Phase 7 first tranche: five manual pages live in
  atomize_docs** (user request; 4 parallel Opus authors + my scaffolding,
  NO code review this round). In atomize_docs (separate repo,
  UNCOMMITTED there): `docs/projects/epr_auto/{index,quickstart,
  protocols,steps,tuning}.md`, the `EPR automation (epr_auto)` nav
  subsection under Projects, and an "Automated tune-up and measurement"
  section on `projects/endstation.md`; `mkdocs build --strict` passes.
  In Atomize_ITC (committed `a3147f4` — see the 2026-07-20 (5) review
  brief below): `atomize/epr_auto/docgen.py` (step-reference generator,
  FAMILIES-coverage guard) + steps.py help strings filled for all 26
  blank params.
  **Two real findings surfaced by the docs pass:**
  - **rephase_delta default bug (FIXED in steps.py): the 2026-07-18 user
    decision "5 K -> 1 K" was implemented only as temp.py's
    REPHASE_DELTA_K constant, but steps.py still carried default=5.0 on
    temp.set/temp.wait — and the step layer ALWAYS passes its default, so
    the decided 1 K never took effect through protocols.** Both step
    defaults now 1.0 (help cites the ~1 deg/K oTP evidence); steps.md
    regenerated; tune_up dry-run green. Fold into the next review's scope.
  - **cli.py live-run gate is stale**: `epr-auto run` without --test still
    exits 3 with "Live execution is not implemented yet (Phase 1+)" — a
    Phase 0 leftover, while HARDWARE_CHECKLIST documents the live command.
    NOT changed (execution-gating; needs a deliberate decision) — lift it
    as the first act of the hardware session. The published pages carry a
    "Commissioning status" warning admonition stating live CLI execution
    is disabled pending hardware validation, so the docs are honest today.
  Fact-fixes applied to the Opus drafts during my review: Telegram-
  credentials link retargeted endstation.md -> usage.md config section +
  bot_message reference; "quoted unit strings" wording (YAML plain
  scalars); tuning.md's rephase paragraph corrected — invalidation DROPS
  the stored phase (fallback = preset zero-order), it does not auto-rerun
  auto_phase; the protocol must declare the fresh tune.auto_phase.
  All other checked claims (protocol_ copy name, DRY-RUN banner,
  checkpoint auto-continue line, failed-skipped manifest status, output-
  template error text, brd.ini/exam_adc.ini cwd rationale, rail-fallback
  chain incl. auto-phase re-runs) verified against code.

- **2026-07-20 (5)** — **Live CLI execution ENABLED (user decision) +
  both repos committed & pushed.** cli.py `_run`: the Phase 0 refuse
  branch removed; argv is now `[argv[0], 'test' if test else 'None']` —
  'None' mirrors the no-argument fallback both general_functions and the
  device modules use, so live device instantiation takes its normal
  branch. Verified: a live invocation now reaches the protocol loader
  (INVALID/exit 1 on a bad path, previously the exit-3 gate message);
  tune_up dry-run 6/6 green; EXIT_UNSUPPORTED kept as a documented
  constant. The five site pages' "Commissioning status" admonitions
  updated to match: enabled but NOT hardware-validated — dry-run first,
  first live sessions in supervised autonomy. `mkdocs build --strict`
  passes. **The next bench session is the first true live exercise of
  the runner — start with HARDWARE_CHECKLIST items 1-3 in supervised
  mode.**

  ### Review brief (DONE 2026-07-21, see that entry): ONE Opus /code-review of `367b9bc..e339240`

  Scope = BOTH unreviewed commits of 2026-07-20 against the current tree:
  `1c1432c` (exp_eseem/exp_field ScanData) + `e339240` (Phase 8). Files:
  awg_phasing_insys.py (ScanData sends in exp_eseem/exp_field + the
  4x Status min(100,...) clamp — GUI-shared file, review extra
  carefully), primitives/tune.py (rep_rate + _recommend_rate + module
  constants), primitives/exp.py (_resolve_rep_rate), primitives/field.py
  (edfs target_snr threading), steps.py (tune.rep_rate registration,
  AutoOr rep_rate, edfs target_snr). ALSO include the docs session's code
  (committed after this marker was first written): steps.py rephase_delta
  defaults 5.0 -> 1.0 + 26 filled help strings, docgen.py, and the cli.py
  live-gate lift (`sys.argv = [argv[0], 'test' if test else 'None']` — the
  'None' live flag mirrors the device modules' own no-argument fallback;
  check nothing downstream keys on argv length or a specific live value).
  Run it the usual way (Opus agents pinned via model:'opus', workflow,
  high effort). Reviewer's brief —
  judgement calls worth a second opinion:
  - Saturation model A(T) = A0*(1-exp(-T/T1_eff)) assumes the sequence
    fully tips the magnetization every shot (echo preset). How wrong is
    T1_eff if the operator points tune.rep_rate at a different preset
    family, and should the step warn/enforce a preset type?
  - Steady-state transient at each rate change: the first few shots of an
    acquisition still carry the previous rate's saturation level (slowest-
    first ordering + phase-cycle x points x scans averaging is the
    mitigation). Is the residual bias negligible at points=4, scans=1?
  - |mean(sig)| amplitude metric: |mean| of pure noise is positive
    (Rayleigh floor) — does that bias the flat-curve detection or the fit
    plateau at low SNR?
  - _FLAT_SPREAD = 0.05 vs noise: a truly flat but NOISY curve (spread
    just over 5%) falls through to the fit — trace what the fit + coverage
    check recommend in that regime (clamp to rate_max is the belief).
  - phase_coherence on the concatenation is amplitude-weighted: heavily
    saturated (near-zero) points contribute little — confirm a real echo
    that only appears at slow rates still passes, and pure noise still
    fails, at steps=3 x points=2 minimum sizes.
  - _resolve_rep_rate reuses the stored recommendation across later field/
    temperature steps — T1 changes with both; should the session invalidate
    'rep_rate' on field/temp moves like it does auto_phase?
  - edfs target_snr with the default scans=1: policy no-ops (nothing to
    shrink) — fine, or worth a load-time warning?
  - The Status clamp also caps a mid-run GUI scans INCREASE case? (SC
    upward: ratio drops below 100 anyway — confirm no path reads 100 as
    'done'.)

- **2026-07-20 (6)** — **Doc-review fixes (user Q&A) + edfs IF-aware
  auto-centering — committed & pushed both repos (ITC `1d1dc5b`, docs
  `4b30fa2`; Opus agent did the edits).** From the user's read-through of
  the new docs: (1) clarified why tune.rep_rate uses hahn_echo_4s — it
  MEASURES T1_eff by the saturation method (echo amplitude vs log-spaced
  rate), it does not consume exp.t1's T1; any echo preset serves (doc
  answer only, no code change). (2) **field.edfs `range: auto` now
  centers on the true observation frequency ν_eff = ν_LO − ν_IF**: new
  `_detection_if_mhz` reads the preset DETECTION pulse's freq via
  snapshot.load_preset (pure parse, --test-safe); lower-sideband LO−RF
  sign confirmed from Insys_FPGA.awg_correction comments +
  awg_phasing_insys `iq_freq = -freq`. `offset` now means
  magnet-calibration shift ONLY — any bench-calibrated offset values
  must have the IF contribution (~0.357·ν_IF/g·2 G) removed at the next
  hardware session. Log line shows the arithmetic (`LO 9750 MHz - IF 50
  MHz = ...`). tune_up.yaml dry-run 6/6 green. (3) Lock naming
  normalized: files `field.param`/`temp.param`, modules
  `field_param`/`temp_param`. (4) steps.py formula in typographic form
  h·ν/(g·μ_B). (5) docgen: long filename defaults emitted as
  `<code>stem<wbr>.ext</code>` so the step-reference table wraps only
  when cramped; steps.md regenerated. **NOTE for the pending
  `367b9bc..e339240` review: `1d1dc5b` touched primitives/field.py
  (edfs centering) and steps.py after that range — review against the
  current tree as planned.**

- **2026-07-21** — **The `367b9bc..HEAD` Phase 8 code-review DONE** (the
  usual harness: workflow, 3 Opus reviewers @ high effort over the briefed
  dimensions + adversarial Opus verification of every non-note finding;
  7 agents, ~428k tokens). **1 confirmed minor (FIXED), 2 downgraded to
  notes on verification, 1 refuted, 4 reviewer notes, all brief questions
  answered clean.**
  - **CONFIRMED (minor) + FIXED: edfs target_snr below the judge floor
    abandons a real line.** steps.py declared `target_snr: Float(min=1)`
    while the final hard judge uses echo_snr's pass floor 3.0 — same
    metric, different thresholds. A target in [1,3) stops the sweep early
    at SNR ~2, the judge then rejects the same curve, edfs widens the span
    x2 and ultimately returns field:None — abandoning a line that reaches
    SNR>=3 at the full scan budget. The field.py comment's invariant
    ("an early stop can never deliver a sweep the judge then rejects")
    held only for target>=3. **Fix:** named constant `judges.SNR_FLOOR =
    3.0` (echo_snr's default now references it), edfs registration
    `Float(min=SNR_FLOOR)` + help states why, field.py comment notes the
    enforced floor. exp.t1/t2 deliberately KEEP min=1 — their echo_snr
    judge is advisory (`advisory_extra`), so a sub-3 target there is a
    knowing "stop early, accept the warn", not a wrong outcome. Verified:
    validate(2) raises / validate(3) passes, tune_up.yaml --test 6/6
    green, docgen steps.md regenerated in atomize_docs (target_snr row:
    `>= 3` + new help).
  - **Downgraded to notes on verification (real observations, not
    defects):** (1) 'rep_rate' is never invalidated on temp/field moves
    (nothing ever drops it; T1_eff is strongly T-dependent) — but this is
    the documented scope ("subsequent steps at the same field/
    temperature") and the destructive case is exp.t1, not t2 (for a
    fixed-rate tau sweep, saturation is a near-uniform amplitude
    prefactor: SNR loss, not a Tm bias), and echo_snr/fit judges
    partially catch it; (2) rep_rate has no preset-family check (unlike
    pi_calibration) — a bipolar inversion-recovery preset cancels the
    |mean| metric, BUT the phase_coherence hard judge (carried into
    every return path incl. the flat-spread branch) catches exactly that
    case; only an effectively-unipolar trace fits, and that is a
    legitimate measurement.
  - **Refuted:** "iq_cor==0 preset makes target_snr a silent no-op" —
    unreachable: tune._acquire raises ValueError('preset must be saved
    with IQ Correction: 2') up front in both --test and live before any
    sweep; the worker's iq_cor==1 gate on ScanData is defensive
    redundancy.
  - **Notes (no action taken):** phase_coherence does no baseline
    subtraction (echo_snr does) — a constant DC/LO-leakage offset gives
    R=1.0 and can walk rep_rate's flat branch to rate_max with no real
    echo; the flat-but-noisy (>5% spread) path clamps to rate_max via the
    fit->over-rail route in the typical case but is fit-dependent, a
    chance-monotone arrangement hard-fails coverage instead (fail-safe);
    target_snr with the default scans=1 is silently inert (ceiling-only
    policy, k<2 guard) — candidate load-time warning in _check_edfs/
    _check_t1; docgen's "cannot drift from the code" header overstates —
    only a NEW step family is caught (SystemExit), param/help drift needs
    the manual re-run (banner mitigates).
  - **Brief verdicts (all endorse shipped code):** ScanData sends
    byte-consistent across all 4 sites, exp_eseem's `cycle*SCANS+k` index
    correct, GUI-launched runs bit-identical (flag short-circuits before
    the copies); Status min(100,...) clamp — nothing reads 100 as done
    (GUI only setValue's; engine waits for the '' 'finished' message;
    executor.py:273 `>=100 -> exit` is the separate dig_on preview path;
    exp_eseem correctly left unclamped); mirror rule satisfied (executor
    already unpacks ScanData generically in all modes; no worker-arg/
    dig_start_exp change, gui_vs_engine re-run not load-bearing for this
    range); cli.py live-gate 'None' flag is byte-equal to what the GUI
    produces (main.py launches with no argv[1] -> same 'None' fallback;
    nothing keys on len(sys.argv) or the literal; workers inherit via
    fork); edfs nu_eff = nu_LO - nu_IF sign confirmed against
    awg_correction's lower-sideband comments + iq_freq=-freq;
    _detection_if_mhz --test-safe (pure parse), fallback harmless; all 26
    help strings truthful; temp.py/session.py one-liners are the
    'temp_param' -> 'temp.param' lock-file naming prose fix; saturation
    transient at points=4/scans=1 negligible (slight fast bias — one more
    reason the step is documented as not-for-quantitative-relaxation);
    |mean| Rayleigh floor benign (the real hazard is the DC-offset note
    above).
  - **Candidate follow-ups (operator's call, none applied):** (a) drop
    'rep_rate' in session invalidation on temperature (and maybe field)
    moves; (b) median-subtract in phase_coherence before computing R;
    (c) load-time warning when target_snr is set with scans<=1; (d) a
    preset-family warn in tune.rep_rate mirroring pi_calibration's check.
  - **UNCOMMITTED: the fix (judges.py/steps.py/field.py) + this log in
    ITC; regenerated steps.md in atomize_docs.** Next: unchanged —
    hardware run per HARDWARE_CHECKLIST.md.

- **2026-07-21 (2)** — follow-ups (a) and (b) APPLIED per user direction,
  plus an Opus ROADMAP cleanup pass (stale status markers).
  - **(a) 'rep_rate' invalidated on TEMPERATURE moves — NOT field**
    (user physics call: T1 is surely different at different T; the field
    effect is minor and exists only in systems with two different spins —
    rationale recorded in session.invalidate_rep_rate's docstring). All
    THREE `session.state['rep_rate']` sites in tune.py now stamp
    `temperature_k` via _phase_temperature (the flat branch had no stamp
    at all); temp._rephase_check loops auto_phase AND rep_rate, each
    against its OWN measurement temperature under the same rephase_delta
    — this closes the gap a naive invalidate_phase piggyback would have
    left (the old check early-returned when auto_phase was already gone,
    so a stale rep_rate could outlive it; and in a series the two can be
    measured at different temperatures). Vane moves still keep rep_rate
    (T1 does not depend on B1). Verified: unit checks (within-delta keeps
    both / big move drops both / rep_rate-alone dropped / independent
    anchors), canned stamp temperature_k=200.0.
  - **(b) phase_coherence corrected — NOT via the reviewer's naive
    median-subtract**, which would have been a regression: auto_phase and
    rep_rate traces are deliberately FLAT coherent traces, so subtracting
    the median leaves pure noise and every genuine echo would fail the
    judge. Correct discriminator = the auto_phase_zero sign-blind
    principal-axis trick on the median-subtracted deviations:
    R2 = |sum d^2|/sum|d|^2 (a real echo's amplitude moves along ONE
    phase axis so squaring folds the +/- flips together, R2 -> 1; a
    constant LO-leakage phasor leaves isotropic noise deviations,
    R2 ~ 1/sqrt(N)). Always reported as `structure_r` in the details;
    hard-gated only via new `require_structure=True`, which rep_rate sets
    when spread >= _STRUCTURED_SPREAD = 0.15 (deviations then
    signal-dominated — between 0.05 and 0.15 the gate would false-fail a
    real low-SNR echo, so it stays off). Judge computation moved after
    the spread is known. Flat curves keep the plain gate: leak vs a
    genuinely rate-insensitive echo is INDISTINGUISHABLE in-band (both
    are one constant phasor + noise) — documented in the code, exp
    steps' echo_snr judge named as the backstop. Numeric checks: flat
    echo passes plain, structured echo passes gated, DC leak fails gated
    with a naming note, pure noise fails; all 3 protocol dry-runs green
    (6/6, 4/4, 16/16) + direct rep_rate canned run.
  - Docs synced: rephase_delta help strings (both temp registrations),
    ARCHITECTURE.md "Temperature rules" (rep_rate row + independent
    anchors + field-exemption rationale), tuning.md invalidation table
    (three-column Kept incl. vane keeps rep_rate) + a leak-guard
    paragraph in its tune.rep_rate section, steps.md regenerated.
  - **ROADMAP cleanup (Opus agent, git-verified):** stale "UNCOMMITTED"
    /"NEXT SESSION" markers corrected in place — Phase 8 header now
    "committed `e339240` — hardware still pending" (the user's example),
    three old ">>> NEXT SESSION <<<" review banners de-fanged to "Review
    brief (DONE <date>, see that entry)" keeping the briefed content,
    Phase 6 header now "code DONE 2026-07-19, committed `94481c7`",
    docgen/help-strings clause now "committed `a3147f4`", Phase 7
    step-reference checklist item ticked (single generated steps.md, not
    per-family pages). Chronological per-entry "(uncommitted)" markers
    that self-resolve later in the log were deliberately left as history.
  - Remaining candidates from the review: (c) warn on target_snr with
    scans<=1; (d) preset-family warn in tune.rep_rate. **UNCOMMITTED:
    everything from both 2026-07-21 entries (ITC: judges/tune/temp/
    session/steps/field + ARCHITECTURE + this file; atomize_docs:
    steps.md + tuning.md).** Next: hardware run per
    HARDWARE_CHECKLIST.md.
