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
- Not covered yet: live 'SC' resize; per-cycle 'Save each' file naming in the
      executor (single save_path answers every 'Open'); resonator-correction
      overrides → moved to the backlog below.

## Phase 2 — Tuning primitives + judges
- [ ] `tune.auto_phase` (acquire echo → `fft.auto_phase_zero` → apply)
- [ ] `tune.pi_calibration`, two modes: amplitude sweep (default for AWG,
      `ampl_4s.phase_awg`) and length-increment nutation (`rabi_echo_4s.phase_awg`);
      fit → π, π/2 calibrated independently; amp(π)/amp(π/2)-ratio linearity judge
- [ ] `tune.power_for_length` (coarse stage): rotary vane scan at ~90–95 % AWG
      amplitude until π lands at target length; same-direction approach,
      optional Limit-mode re-home; invalidates auto-phase + fine calibration
      (see ARCHITECTURE.md "Flip-angle knobs")
- [ ] Rail-triggered fallback: fine sweep hits 100 % / <~30 % amplitude ⇒
      runner re-runs coarse stage per autonomy policy
- [ ] `field.edfs` (ed preset sweep → pick max/marker/value → set BH_15,
      respecting field.param lock)
- [ ] `judges.py`: echo SNR, fit RMSE/adj-R², convergence; every primitive
      returns (result, judge_report)

## Phase 3 — Runner UX & autonomy
- [ ] Checkpoint gating: terminal prompt at `checkpoint: true` steps;
      autonomy = supervised / checkpointed / autonomous
- [ ] Retry policy per step (n retries, on-fail: abort | skip | ask)
- [ ] Run directory: manifest (protocol snapshot + resolved parameters +
      calibration results + judge reports), CSVs with headers
- [ ] Telegram notifications on checkpoint/finish/abort (`general.bot_message`)

## Phase 4 — T1/T2 end-to-end
- [ ] `exp.t2` (hahn_echo preset, linear τ sweep) with fit + report
- [ ] `exp.t1` (inversion_recovery log-time preset) with characteristic-time
      initial guess fit
- [ ] `protocols/overnight_t2.yaml` full chain in `--test`
- [ ] **Hardware**: full chain on the spectrometer, supervised mode

## Later phases (unordered backlog)
- Resonator-correction overrides in the runner/protocol YAML (the ENGINE side
  is done 2026-07-17: WorkerArgs carries cor_model_cur/f0_cur/q_cur/
  phase_cor_cur/meas_freq_cur/meas_H_cur and the executor hands them to the
  worker like the GUI's `_hand_correction_to_worker`; set them on the built
  WorkerArgs. Remaining: plumb them from protocol steps + measured-H file
  loading outside the GUI)
- RECT channel support for calibration + runners
- ESEEM / DEER payload experiments (reuse ESEEM-avg + benchmark know-how)
- Autopilot GUI (control_center tool wrapping the runner)
- Assistant layer (Claude emits/edits protocols, reacts at checkpoints)
- Resonator tuning (needs actuation path assessment)
- Port to fork repos once stable

## Pending hardware validation
- (none yet)

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
  Next: Phase 2 tuning primitives.
