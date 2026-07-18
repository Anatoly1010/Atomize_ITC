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
      field.param + temp_param locks seized with source 'epr_auto', atexit
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

## Later phases (unordered backlog)
- Resonator-correction overrides in the runner/protocol YAML (the ENGINE side
  is done 2026-07-17: WorkerArgs carries cor_model_cur/f0_cur/q_cur/
  phase_cor_cur/meas_freq_cur/meas_H_cur and the executor hands them to the
  worker like the GUI's `_hand_correction_to_worker`; set them on the built
  WorkerArgs. Remaining: plumb them from protocol steps + measured-H file
  loading outside the GUI)
- RECT channel support for calibration + runners
- ESEEM / DEER payload experiments (reuse ESEEM-avg + benchmark know-how)
- `foreach:` protocol block (temperature/parameter series without repeating
  steps by hand — v1 keeps the schema flat on purpose)
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
  edfs pick=max lands on the line; field.param/temp_param locks vs an open
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

  ### >>> NEXT SESSION, FIRST THING: ONE code-review of `3be399d..b9cbc66` <<<

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

  ### >>> NEXT SESSION, FIRST THING: ONE /code-review of `3c492e4..ff90708` <<<

  Scope = Phase 4 (`cba862b`) PLUS the same-session relaxation_fit dAICc
  rework (`f7ebe93`, which rewrites the judge `cba862b` introduced — review
  the RANGE against the current tree, not the commits separately; the two
  docs commits in the range are hash records / checklist restructure).
  Files: primitives/exp.py new; steps.py exp wiring; executor.acquire_1d +
  tune._acquire scan_control threading; judges.relaxation_fit (dAICc form).
  Run it the usual way (Opus agents, workflow, high effort — patch
  model:"opus" into the persisted script if the Workflow tool still has no
  model param). Reviewer's brief — the judgement calls worth a second
  opinion:
  - `_retau`'s units rule (st_inc / min st_inc) assumes the preset's
    increment ratios encode the geometry ratio. True for the hahn family;
    check it does something sane (or fails loudly) for multi-pulse Linear
    Time presets whose increments are NOT multiples (4pdeer has pump st_inc
    negative — exp.t2 on such a preset is off-label but not rejected).
  - `_period_check` estimates the sequence extent (t2 exact per-slot, t1
    approx + documented overshoot ~t_start). It errs long: a borderline
    LEGAL config could be rejected that the driver would accept. Decide if
    the margin is acceptable or the check should soften to a warning.
  - The T1 fit is mono-exponential a − b·exp(−t/T1); stretched/bi-exp
    recovery data will fail the relaxation_fit gate rather than mis-fit —
    intended, but worth confirming that is the desired failure mode.
  - relaxation_fit was REWORKED same session (user suggestion, validated on
    the real oTP campaign — see the 2026-07-18 (3) entry): gate = dAICc vs
    the constant-mean null >= 150, not an adj-R² floor. The threshold and
    the null-tail numbers are data-derived but from ONE campaign; second
    opinion welcome on the 150 and on the N-dependence caveat.
  - `_duration_policy` trusts the worker's Status pct linearity; a strongly
    nonlinear progress rate (long per-point tails) could shrink too
    aggressively. Ratchet-down-only makes over-shrink permanent by design.
  - The e2e fit tests stub `exp_p._acquire` by module-attribute assignment —
    fine for the scratch suite, but the reviewer should confirm the real
    _acquire signature (scan_control kwarg) is exercised somewhere real
    (gui_vs_engine does not cover exp.py).
  Next (AFTER the review + fixes): the hardware run per
  HARDWARE_CHECKLIST.md ('Newly hardware-runnable' section first), then
  Phase 6 planning (2D/DEER experiments or GUI launcher).
