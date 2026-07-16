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

## Phase 1 — Engine (extract from awg_phasing_insys)
- [ ] **[F]** `engine/sequence.py`: `.phase_awg` preset → pulse program on a
      test-mode `Insys_FPGA` (phase cycling expansion, AWG amp-gate partner handling)
- [ ] **[F]** `engine/acquisition.py`: scan loop + digitizer readout + per-scan
      accumulation, LivePlot optional (deer_bench.py as the reference loop)
- [ ] Equivalence check: engine output for `hahn_echo_4s.phase_awg` matches
      what the phasing tool arms (compare test-mode pulse tables / DAC hashes,
      reuse the `~/pulser_optim/` golden-harness approach)

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
