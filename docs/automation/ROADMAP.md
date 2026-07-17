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

## Phase 3 — Runner UX & autonomy — code DONE 2026-07-17 (review next session)
- [x] Checkpoint gating completed: autonomous mode never pauses — checkpoints
      auto-approve with a notification, judges are the only brake; supervised /
      checkpointed keep the Phase 0 terminal prompt (GUI checkpoint = later)
- [x] Retry policy per step: `retries: n` (extra attempts) + `on_fail:
      abort | skip | ask` reserved step keys (parsed like `checkpoint`);
      'ask' prompts retry/skip/abort (autonomous or no-tty ⇒ abort + notify)
- [x] Rail-triggered fallback wired: StepFailure carries `rails` from the
      failing amplitude_rails judge; the runner re-runs the protocol's
      earlier tune.power_for_length (+ tune.auto_phase — the vane move
      invalidated the phase) once per step and retries — automatic in
      autonomous mode (with notification), y/n prompt otherwise; only
      available when the protocol declared the coarse step (its resolved
      params define the stage)
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

## Phase 4 — T1/T2 end-to-end
- [ ] `exp.t2` (hahn_echo preset, linear τ sweep) with fit + report
- [ ] `exp.t1` (inversion_recovery log-time preset) with characteristic-time
      initial guess fit
- [ ] `protocols/overnight_t2.yaml` full chain in `--test`
- [ ] **Hardware**: full chain on the spectrometer, supervised mode

## Phase 5 — Tune-up completeness (planned 2026-07-17; decisions in
## ARCHITECTURE.md "Tune-up completeness")
Gaps found reviewing the plan: classical length calibration had no consumer,
detection-pulse convention was implicit, and window / temperature / signal
search were missing entirely. `tune.echo_window` and the `apply_cal` hand-off
should land **before** the Phase 4 overnight hardware run — the full chain is
not autonomous without them.
- [ ] Calibration hand-off `apply_cal`: session pi_calibration results
      (amplitudes at fixed length, or grid-quantized lengths in the classical
      `mode: length` path) patch experiment presets via an explicit
      `{slot: role}` map; default inferred from the preset's own two
      amplitude levels among hard pulses; ambiguity ⇒ validation error
- [ ] Detection-pair handling in calibration: soft/selective pair (~3–4×
      target length) at proportionally lower amplitude; preset-stored values
      on the first pass, then the standard scaling rule
      `amp_det = amp_cal · L_target/L_det` (amp nearly linear) after every
      fine cal; `refine: true` = one self-consistency nutation re-run
- [ ] **[F]** `executor.acquire_trace`: engine-side echo-trace acquisition
      reusing the Worker's preview (dig_on-style) path — the engine only
      speaks the sweep-integral protocol today
- [ ] `tune.echo_window`: rotate trace by current zero-order, center = max of
      smoothed |V(t)|, width = FWHM × factor, snap to ADC grid; stored
      relative to the DETECTION pulse start; applied via _session_overrides;
      `window: auto | preset` on exp steps; MUST run before tune.auto_phase
- [ ] `temp.set` / `temp.wait` primitives (Lakeshore 335, temp_control
      setter-waiter semantics: per-channel band, hold count, wall-clock
      timeout ⇒ StepFailure; temp_param lock already in session);
      temperature-series protocols = explicit repeated steps in v1
- [ ] `field.edfs range: auto`: center from `mw_bridge_synthesizer` + `g:`
      (default 2.0023) ± `span:` (default 25 mT); one span-×2 escalation on
      a failed echo-SNR judge; failure report names the precondition to
      check ("flat everywhere" vs "weak line found")
- [ ] tune_up.yaml updated to the canonical chain: power_for_length →
      field.edfs → echo_window → auto_phase → pi_calibration (+ optional
      temp.set/wait prologue)

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
  sign: digitizer_iq rotates by exp(−i·z), so z_new = z_used − φ_residual —
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
  digitizer_iq applies exp(−i·zero_order) ⇒ z_new = z_used − φ; exp_field
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
