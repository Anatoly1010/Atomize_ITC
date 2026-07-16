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
- Resonator-correction overrides in the engine (equivalent of the GUI's
  `_hand_correction_to_worker` + Combo_cor/Combo_model settings; Worker
  defaults are used until then) — deliberately deferred 2026-07-16
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
  Gotchas encoded in snapshot.py: `_snap` is ceil-to-3.2-grid; log sweep
  bounds go through TimeLogSpinBox unit-grid quantization (`_log_snap`);
  P1 'phase' field is receiver coefficients, expanded together with active
  pulses only (length ≠ 0); combo_cor/combo_synt/save2d are NOT in presets
  (GUI defaults 0/1/0). Next: Phase 2 tuning primitives wired through the
  engine (field.edfs→exp_field, pi_calibration→exp_amplitude/exp).
- **2026-07-16 (5)** — ESEEM Avg + LASER added to the engine (ALL 15 PASS incl.
  2 synthetic presets); resonator-correction deferred to backlog; CLAUDE.md
  gained the phasing-GUI ↔ engine mirror rule.
