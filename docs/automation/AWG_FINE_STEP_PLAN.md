# 0.8 ns AWG timing step (Insys FM214x3GDA) — zero-padding sub-grid shifts

> Working plan for the multi-session implementation. Update the phase checklist + ROADMAP.md session log each session.

## Phase status

- [x] Phase 0 — baselines (golden pulser harness, gui_vs_engine) — both green 2026-07-16
- [x] Phase 1 — device transmit core (Insys_FPGA.py) — done 2026-07-16; golden harness BIT-EXACT with toggle off
- [x] Phase 1.9 — receive side (DETECTION fine tracking) — done 2026-07-16; integer ADC-point shift is the complete correction (no IQ rotation needed at dec 1–2: rows are raw FPGA I/Q, demod commutes with integer sample shifts)
- [x] Phase 2 — GUI (awg_phasing_insys.py) — done 2026-07-16; grid travels as `worker.awg_grid_cur` attribute (pickled with the Worker), not a positional arg
- [x] Phase 3 — log-time grid — done 2026-07-16 (`TimeLogSpinBox.set_fine_grid`, fine μs step = 0.02)
- [x] Phase 4 — mirror layer (snapshot.py + harness) — done 2026-07-16; gui_vs_engine ALL 17 PASS incl. 2 fine-grid synthetic presets + awg_grid_cur attribute check
- [x] Phase 5 — verification + docs — done 2026-07-16; functional suites in session scratchpad (`test_fine_grid.py`, `test_gui_fine.py`) — re-create from ROADMAP entry 2026-07-16 (6) if needed
- [x] Opus code-review — 15-agent workflow, 6 findings all fixed (2026-07-16); golden BIT-EXACT + all suites green after fixes
- [ ] Bench validation (lab) — see Verification table below

## Context

The Insys DAC runs at 1250 MHz → **0.8 ns per sample; 3.2 ns = exactly 4 samples**. The 3.2 ns grid is not a DAC hardware limit: it is (a) software rounding/asserts in `Insys_FPGA.py` and the GUIs, and (b) the pulser's 312.5 MHz TTL instruction clock, which **is** hardware — TTL trigger/gate edges can only move in 3.2 ns steps. The DAC buffer is already assembled at single-sample resolution and played from a fixed-clock trigger, so **a 0.8 ns effective AWG pulse start/length step is real and is achieved exactly as the user proposed: zero samples in the DAC buffer**, while the TRIGGER_AWG gate stays on the 3.2 ns grid.

User decisions (asked & answered):
- **Scope**: start + length + sigma + all increments for AWG pulses (P2–P9). DETECTION (P1) **start/st_inc become virtually fine too** (see "Receive side" below — needed so the detection window can track an echo that moves in 0.8/1.6 ns steps); P1 length, X0/XDelta, and all plain TTL channels stay on 3.2 ns (pulser hardware).
- **Carrier phase**: pulse-local, as today (waveform delayed by N×0.8 ns; carrier still starts at the programmed phase at the pulse start). No global-timebase compensation.
- **GUI exposure**: **Settings-tab toggle** (default 3.2 ns) so the feature can be validated independently. Mirrored by a device-level opt-in so exp scripts keep today's exact behavior unless they opt in.

Verified script-flow facts (deer_bench.py / exp scripts): timing motion goes **only** through `pulser_shift()` on TRIGGER_AWG pulses (the auto-spawned `name+'AWG'` amp-gate partner shares the same `delta_start`, `Insys_FPGA.py:669`); `awg_shift()` is phase-only (`:3565`); AWG-side `delta_start` is dead code (`pulse_delta_start_smp` computed at `:6163`, never used); AWG-side `start` never advances (used only for WURST/SECH correction midpoint). The buffer is already rebuilt every point (`awg_next_phase()` → `awg_update()` → `define_buffer_single_joined_awg()`), and `awg_shift()` sets `shift_count_awg = 1` unconditionally (`:3572`). **Scripts therefore need no API change** — they add one opt-in line and pass 0.8-multiples.

## Core decomposition (integer DAC samples; done inside Insys_FPGA)

For a TRIGGER_AWG pulse with user start `S_ns`, length `L_ns` (0.8-multiples); stored trigger start `S_rel = S_ns − trigger_awg_shift(160)`:

```
S_smp = int(round(S_rel * 1.25))        # exact int64 for 0.8-multiples (verified)
L_smp = int(round(L_ns  * 1.25))
t0    = S_smp // 4                      # gate start tick  (FLOOR; Python // handles negatives)
t1    = -((-(S_smp + L_smp)) // 4)      # gate end tick    (CEIL)
k     = S_smp - 4*t0                    # front zero-pad, samples, in {0,1,2,3}
seg   = 4*(t1 - t0)                     # segment samples = k + L_smp + back-pad
dac_window contribution = t1 - t0
```

On-grid values ⇒ `k = 0`, `t0/t1` identical to today's math ⇒ **byte-identical TTL words and DAC buffer** (verified: ceil formula is an identity on-grid; the `:6136–6137` transform keeps sample alignment exact because 160 = 50×3.2 and `constant_shift_pulser` = 200 ticks). During an 0.8 ns sweep the TTL words move only every 4th point; intermediate points change **only the DAC buffer** — mechanically identical to what phase cycling already does today. Gate length may gain a tick when `k + L_smp` crosses a 3.2 boundary; buffer size changes mid-sweep are already legal (`awg_increment` precedent).

**Sub-grid data source**: `k` is derived from the **pulser-side TRIGGER_AWG ns strings** (they are what `pulser_shift` advances), never from the stale AWG-side `pulse_start_smp`.

## Receive side — DETECTION window vs a 0.8 ns-moving echo

Problem (user-raised, real): in a fine τ sweep the echo moves in 0.8/1.6 ns steps, but the DETECTION TTL window and today's integration limits sit on the 3.2 ns grid → the echo slides inside the window with a period-4 pattern, modulating both the echo position in saved traces and the integral (and rotating the demodulated IQ phase by 2π·f_iq·slide).

Solution — the exact mirror of the transmit trick, using the **ADC's 0.4 ns sample grid** (2500 MHz; integration already happens in the device module: slices `data_i_ph[:, win_left:win_right]` at `Insys_FPGA.py:2487–2494`, `:2575–2576`, `:2811`; `win_left/right` are in points of `0.4·dec` ns, set by GUI/scripts):

1. **Virtual fine DETECTION start**: in fine mode, P1 start/`delta_start` accept 0.8-multiples (e.g. `st_inc = 1.6 ns` to track a Hahn echo when the π pulse steps 0.8). The TTL window is placed at `floor(start/3.2)`; the residual `r ∈ {0, 0.8, 1.6, 2.4}` is recorded **per pack/nid** at instruction-generation time (`self.det_residual_by_nid[nid]`, filled where packs are built in `pulser_update`; residuals repeat cyclically over scans since on-board averaging is nid-keyed).
2. **Per-row readout correction** in the integration sites and `digitizer_get_curve`, grouped by residual value (only 4 groups → 4 vectorized slice-sums, cheap):
   - shift the integration slice by `r/(0.4·dec)` points — exact at dec = 1 (0.8 ns = 2 pts) and dec = 2 (1 pt); at dec = 4 the granularity is 1.6 ns → round + warn;
   - apply the deterministic IQ rotation `(I+iQ)·e^(−i·2π·f_iq·r)` per row so the demod phase behaves exactly as in a coarse sweep;
   - in full-trace mode, roll each row by the same points so the echo appears stationary in 2D plots/saves.
3. **Window-edge guard**: require `win_right + max_shift ≤ window points` (clamp + message) so the shifted slice never leaves the captured window. Practically: keep ≥ 2.4 ns (6 pts at dec 1) of right-side margin.

Notes: in practice only ~3/4 of the echo sits inside the integration window (user), so **both corrections are load-bearing**: the slice shift keeps the same portion of the echo integrated (otherwise a 0.8–2.4 ns slide directly modulates the integral), and the IQ rotation keeps the demod phase constant. Both read the same residual array. Scripts get all of this for free because integration lives in the device module.

## Toggle design

- **Device**: new method `awg_time_resolution(resolution)` on `Insys_FPGA` (`'3.2 ns'` default | `'0.8 ns'`), both real and test branches; sets `self.awg_grid_ns`. All AWG-related snaps/asserts (TRIGGER_AWG + `'AWG'` partner + `awg_pulse` fields) use `self.awg_grid_ns`; everything else stays hard 3.2. The floor/ceil decomposition in `convertion_to_numpy_pulser` is **unconditional** (values reaching it are already snapped to the active grid, so 3.2-mode yields k=0 always). Default-off ⇒ trivially bit-exact for every existing script including `~/q/2026_07_06_insys_efficiency_auto/deer_bench.py`.
- **GUI**: Settings-tab checkbox "0.8 ns AWG grid" (default off). Switches P2–P9 timing spinbox `singleStep` + snap grid; travels to the Worker in the packed args; the Worker calls `pb.awg_time_resolution(...)` during setup and records it in `pulser_setup_calls` so the LiveReject test-mode replay inherits it.
- **Preset**: append one trailing line `AWG grid: 0.8` on save; `open_file` parses it if present, defaults to 3.2 (same backward-compat pattern as `st_inc2`). Old presets unchanged/valid. Mirrored in `epr_auto/engine/snapshot.py:load_preset`.

## Execution model (multi-session)

This is multi-session work (device module → GUI → mirror → harnesses → bench). Workflow agreed with the user:
- **First implementation step**: copy this plan into the repo as `docs/automation/AWG_FINE_STEP_PLAN.md` (design docs live in `docs/automation/` per project convention), and add a memory-index pointer. Each session updates the plan's per-phase status checkboxes and the `docs/automation/ROADMAP.md` session log (project convention).
- **Model split**: **Fable implements** (this session and continuations, auto-mode after start); **Opus reviews** afterwards (`/model opus` + `/code-review`, or an Opus review agent) before anything is committed. Commit only when explicitly asked (standing preference).
- Suggested slicing (may compress into fewer sessions — the change is contained): (1) Phase 0 baselines + Phase 1 device transmit core; (2) Phase 1.9 receive side; (3) Phase 2 GUI + Phase 3 log grid; (4) Phase 4 mirror + harness updates; (5) verification sweep + docs. Bench items batch into a lab-day list under "Pending hardware validation" in ROADMAP.md.

## Implementation phases

### Phase 0 — Baselines (no code changes)
- Run golden pulser harness `~/pulser_optim/run_insys_scenarios.py` (test + prod) → must match `golden_insys.json`.
- Run `~/epr_auto_dev/gui_vs_engine.py` → ALL PASS.

### Phase 1 — Device module (`atomize/device_modules/Insys_FPGA.py`)
Add `self.awg_grid_ns = 3.2` + `awg_time_resolution()` + helpers `_awg_ns_to_smp()` / `_trigger_gate_ticks(S_rel_ns, L_ns) -> (t0, t1, k)` near `:102`. Then:
1. **`pulser_pulse`** (real `:640`, test `:723`): for `channel == 'TRIGGER_AWG'` snap length/start/delta_start/length_increment to `awg_grid_ns` (`:657/:754`, `:687/:793`, `:696/:811`, `:707/:827`) and asserts (`:760/:801/:817/:833`) check divisibility by `awg_grid_ns`. Replace `dac_window += ceil(p_length/3.2)` (`:668/:767`) with `t1 − t0` from the helper (hoist start parsing before it). Other channels untouched.
2. **`awg_pulse`** (real `:2892`+, test `:2972`+): grid `awg_grid_ns` for length/sigma/length_increment/start/delta_start snaps (`:2903/:3036`, `:2915/:3054`, `:2929/:3078`, `:2940/:3095`, `:2951/:3111`) and matching asserts (`:3041/:3063/:3083/:3102/:3118`).
3. **`pulser_shift`** (`:1476/:1507/:1534/:1566`): snap grid `awg_grid_ns` when `channel in ('TRIGGER_AWG','AWG')`, else 3.2. Same per-channel grid in `pulser_redefine_start` (`:879/:908`, assert `:913`), `pulser_redefine_delta_start` (`:946/:975`, assert `:980`), `pulser_redefine_length_increment` (`:992`+). The redefine functions already mirror to the paired `i-1` `'AWG'` entry — both move together.
4. **`awg_redefine_delta_start`** (`:3277/:3303`, assert `:3309`) and `awg_redefine_length_increment` (`:3503`+): grid `awg_grid_ns`.
5. **`convertion_to_numpy_pulser`** (real `:4477`+, test `:4524`+): TRIGGER_AWG rows only → `(t0, t1)` from the helper (`row = (2**ch, cs+t0, cs+t1)`). All other channels (incl. the `'AWG'` RECT-gate entries via `change_pulse_settings_pulser:5773` — leave its `int()` truncation alone, gate slack is protective) keep today's path.
6. **`define_buffer_single_joined_awg`** (`:6122`): per TRIGGER_AWG entry compute `k_i`, `L_smp_i` from current ns strings; pair with `tr_awg_array` rows (stable-sort both by gate start; definition-order ties verified stable). `total_samples = Σ seg_i` (replaces `np.sum(pulse_length_smp)` at `:6174`); paste waveforms at `channel[current_pos + k_i : current_pos + k_i + length]` (cached `:6200–6201`, fresh `:6320–6321`); `current_pos += seg_i`. **Waveform cache key unchanged** (`:6191–6197`) — zeros live in the buffer, never in cached arrays. Add per-pulse consistency check: `0 ≤ k_i < 4` and `k_i + L_smp_i ≤ seg_i` (the meaningful invariant; the `:6468` assert is near-tautological since `dac_window` is overwritten at `:6335/:6342`). Overlap path (`has_overlap:6111`, `post_process_overlap:6349`) unchanged — chunk length per row is `end−start == seg_i` and pads are zeros. **Do not** touch resonator-correction midpoints (`:6261/:6291`) — stale-under-sweep is pre-existing; log as follow-up.
7. **Stale-k rebuild guard**: in `pulser_shift`/`pulser_redefine_start`, when a TRIGGER_AWG start's residue (`S_smp mod 4`) changes, set `self.shift_count_awg = 1` so the next `awg_update` (guard `:2837/:2855`) rebuilds the buffer. Never fires on-grid ⇒ rebuild cadence today is preserved. (Canonical script loops call `awg_shift()` which sets the flag anyway, but scripts that only `pulser_shift()` must not get stale padding.)
8. Check `pulser_visualize` (`:1785`) / `awg_visualize` (`:4000`) display sub-grid starts without truncation (display-only).
9. **Receive side (DETECTION fine tracking)**: in fine mode, `pulser_pulse`/`pulser_shift`/`pulser_redefine_start`/`pulser_redefine_delta_start` accept 0.8-grid values for `channel == 'DETECTION'` (start/delta_start only; length stays 3.2 — `adc_window` is in ticks). TTL placement = floor to 3.2; record residual per pack (`det_residual_by_nid`) where instruction packs are generated in `pulser_update`. Apply the per-row corrections (slice shift, IQ rotation by `2π·f_iq·r`, full-trace roll) at the three integration/readout sites (`:2487–2494`, `:2575–2576`, `:2811`) grouped by residual; add the window-edge guard. `iq_freq` is already plumbed per-scan (DETECTION-freq → `digitizer_iq`). Fires only when fine mode is on AND a DETECTION residual ≠ 0 exists — otherwise the readout path is byte-identical to today.

### Phase 2 — GUI (`atomize/control_center/awg_phasing_insys.py`)
Module constants `PULSER_GRID_NS = 3.2`, `AWG_GRID_NS = 0.8`; MainWindow helper `grid_for(i, field)` → 0.8 when the fine toggle is on and (i ≥ 2, any timing field) or (i == 1, start/st_inc/st_inc2 fields); 3.2 otherwise (P1 length, X0/XDelta, toggle off).
- **Settings tab**: checkbox "0.8 ns AWG grid" (default off). On change: update `singleStep` of P2–P9 `_st/_len/_sig/_st_inc/_st_inc2/_len_inc` boxes (`:548–553`, loop `:563–617`) **and P1 `_st`/`_st_inc`/`_st_inc2`** (fine detection tracking; P1 `_len` stays 3.2); switching fine→coarse re-snaps values (ceil) with a log message. Decimals stay 1. X0/XDelta (`:1015–1016`) stay 3.2.
- `round_and_change` (`:3314`) gains a grid parameter; `update_pulse_value` (`:1975`) passes `grid_for(index)`; `round_and_change_no_ns` (`:3323`) stays 3.2.
- Link-mode SHIFT snap (`:1759`): `grid = grid_for(j)`.
- **Worker**: pass the grid in the packed args (one element appended alongside the existing arg lists in `dig_start_exp` packing `:3513–3543` and each `exp*/dig_on` signature). Worker setup calls `pb.awg_time_resolution(...)` and appends it to `pulser_setup_calls` (LiveReject replay `:4552–4589` then inherits the 0.8 asserts automatically). Grid-aware snap call sites: `_shift_start` (`:4534–4536`; per-name grid, P1 start included in fine mode; update stale comment `:4514–4520`), LASER q-switch re-snap pairs (`:4341/:4343`, `:5011/:5013`, `:5596/:5598`, `:6184/:6186`, `:6730/:6732`, `:7209/:7211` — AWG starts → grid), f_delay axis snaps (`:4878–4891`, `:5442–5455`: AWG starts → grid; `rect1`/detection and `x0` → 3.2), Worker's `round_to_closest` copy (`:4818`) stays, call sites choose grid.
- `_live_snapshot`/`_structure_sig` (`:2026`, `:2059`): unchanged — start stays live-appliable (sub-grid start moves rebuild the DAC via `shift_count_awg`), length stays restart.
- **Preset**: `save_file` (`:3206–3273`) appends `AWG grid: 0.8|3.2` line; `open_file` (`:3010–3117`) parses if present (guarded), sets the toggle before `setter()` calls so values snap on the right grid.

### Phase 3 — Log-time grid (`atomize/control_center/time_log_spinbox.py` + log sweep)
- Make `_UNIT_STEP`/`_SNAP_NS` instance-switchable: `set_fine_grid(bool)` → fine: `{'ns': 0.8, 'μs': 0.02, 'ms': 0.01, 's': 0.01}` (0.02 μs = 25×0.8 is the smallest 2-decimal μs value on the 0.8 grid; ms/s values already 0.8-multiples). Wire to the Settings toggle for `Log_start`/`Log_end`.
- Worker log sweep: `general.numpy_round(nonlinear_time_raw, 3.2)` (`:6537`) → grid; per-pulse `pulser_redefine_delta_start` snaps: P1 (`:6643`) and LASER (`:6703`) stay 3.2, AWG pulses (`:6691/:6761/:6870`) → grid.

### Phase 4 — Mirror layer (`atomize/epr_auto/engine/snapshot.py`) — CLAUDE.md mirror rule
- `GRID_NS` (`:19`) → `DET_GRID_NS = 3.2` + per-preset AWG grid (from the new preset line in `load_preset` `:124–137`, default 3.2); `_snap(value, grid)` (`:32–35`).
- Packing (`:328–380`): p1 length + x0/xdelta + window clamp vs `_snap(p1.length)` keep 3.2; p1 start/st_inc(2) and slots 1–8 start/length/sigma/st_inc/len_inc/st_inc2 use the preset's AWG grid.
- `_log_snap` (`:38–52`): per-unit grids mirror Phase 3 exactly.
- `WorkerArgs` builders (`:257–296`): append the new grid element to match the changed `exp*` signatures.
- Update `~/epr_auto_dev/gui_vs_engine.py`: add synthetic fine-grid preset variants (0.8-grid values + `AWG grid: 0.8` line) so equivalence is proven in both modes.

### Phase 5 — Docs & bookkeeping
- `docs/automation/ARCHITECTURE.md` (`:15`, `:24–25` grid statements + decisions table), `docs/automation/ROADMAP.md` new dated session-log entry (+ fix `:113` "_snap is ceil-to-3.2" note), `CLAUDE.md` (3.2 ns grid mentions in epr_auto section), `atomize/documentation/` pulse-programmer/AWG pages (new `awg_time_resolution` API + grid rules). Docs-site repo `/home/anatoly/atomize_docs` follow-up.
- This is Insys-specific ⇒ **ITC repo only**, no fork ports (forks are Spectrum/PB hardware).

## Verification

| Check | Tool | Pass criterion |
|---|---|---|
| Bit-exact back-compat (TTL rows, GIM words, DAC sha256), toggle off | `~/pulser_optim/run_insys_scenarios.py` test+prod vs `golden_insys.json` | zero diffs |
| Sub-grid correctness | extend golden harness: 0.8/1.6/2.4 starts & lengths, gate-overlap-after-expansion case, 8-point 0.8-step sweep (k cycles 0→3, tick bump every 4th) | `k∈{0..3}`, `seg ≡ 0 mod 4`, `Σseg == len(buffer)`, waveform samples = unshifted reference shifted by k; TTL words constant at intermediate points |
| GUI ↔ engine equivalence, both modes | `~/epr_auto_dev/gui_vs_engine.py` (+ new fine-grid presets) | ALL PASS |
| Preset replay bit-exactness | replay each `.phase_awg` into test-mode `Insys_FPGA`, hash buffer + GIM words pre/post-change | byte-identical (toggle off) |
| Test-mode dry runs | `python <script> test`; GUI "Test Scripts" incl. live-edit LiveReject | valid 0.8 values pass; `0.4 ns` rejected |
| Echo tracking (receive side) | synthetic + bench: fine Hahn τ sweep with P1 `st_inc = 1.6 ns`; check integral amplitude and IQ phase flatness across the 4-point residual cycle (dec 1 and 2); 2D full-trace mode shows a stationary echo | no period-4 modulation of amplitude/phase beyond noise |
| Hardware (lab bench) | scope DAC vs TRIGGER_AWG TTL at offsets 0/0.8/1.6/2.4 ns; 0.8-step τ sweep echo behavior; mid-sweep buffer-size change (k wrap / gate ±1 tick) doesn't glitch GIM re-arm; amp-gate margins still cover sub-grid pulses; `deer_bench.py` with `awg_time_resolution('0.8 ns')` + `step: 0.8` | physical 0.8 ns steps, no re-arm glitches |

## Risks / open questions
- **Stale-k rebuild guard** (Phase 1.7) is the top correctness risk — must fire on every residue change and never on-grid.
- Gate/waveform pairing relies on stable-sort tie-breaking on both sides (pre-existing; the new per-pulse k/length check turns silent corruption into a loud error).
- Receive-side residual bookkeeping (`det_residual_by_nid`) must stay consistent with pack regeneration order across scans/resets — second-highest correctness risk; covered by the residual-cycle flatness test.
- Decimation 4: receive-side tracking granularity is 1.6 ns (1 ADC point) — 0.8-residuals get rounded; warn in the log. Recommend dec ≤ 2 for fine sweeps.
- Echo phase vs τ at 0.8 ns steps: pulse-local convention means the same phase-vs-delay behavior as today, just 4× finer sampling of it; the deterministic window-residual IQ rotation is corrected (see Receive side); anything left is physics to evaluate on the bench, not a code bug.
- Follow-ups logged, out of scope: resonator-correction midpoint stale under sweeps; optional global-timebase carrier phase; X0/XDelta fine grid.
