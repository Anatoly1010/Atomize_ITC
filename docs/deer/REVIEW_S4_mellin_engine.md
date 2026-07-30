# S4 — Mellin engine + joint background

**Status: verification COMPLETE, 13/13 findings judged** — **10 CONFIRMED,
3 PLAUSIBLE, 0 REFUTED**. Stage 1 (5 dimension reviewers), stage 2 (triage) and
stage 3 (2 adversarial skeptics per finding, default stance REFUTED) are all done.

Two runs: `wf_79b3f216-ad5` (24 agents, ~1.1 M tokens; stages 1–2 plus 15 of the 24
skeptics) and `wf_f77b0b07-2aa` (the standalone continuation from a new session — 11
skeptics, 937 k tokens, 0 errors). The continuation banked the 15 verdicts already
collected and re-ran nothing.

**S4-13 was added to the queue after triage**, spun out of S4-8's refutation, and got
its own two skeptics like every other entry.

Scope per [REVIEW_PLAN.md](REVIEW_PLAN.md): `joint_background` (`deer.py:841-1009`)
and `deer_invert_mellin` (`deer.py:1229-1688`), plus their call sites. The Mellin
transform core (S3) and the shared foundation (S1) are cleared and were out of scope.

---

## Final verdict table

`bug` = wrong numbers/crash · `risk` = needs specific conditions · `note` = no action.
"severity after skeptics" is what the two skeptics returned; where they split, both
are given. A finding is CONFIRMED only if **neither** skeptic refuted it.

| id | file:line | claim | verdict | severity after skeptics | action |
|---|---|---|---|---|---|
| S4-1 | `deer.py:2661` | `deer_validate` pins α but nothing pins τmax for `engine='mellin'` → reported band far too wide | **CONFIRMED** 2/2 | **bug** / **bug** | **fix** |
| S4-2 | `deer.py:1424` | short-r taper width scales with the user's r grid, moving the reported mean distance | **CONFIRMED** 2/2 | **bug** / **bug** | **fix** (re-tune, not as written) |
| S4-3 | `deer.py:948` | a collapsed `kref` shrinks the k bracket to [1e-6, 1e-2]; k pinned at a bound "with no flag" | **PLAUSIBLE** 1/2 | risk / note — *"no flag" is false* | flag only |
| S4-4 | `deer.py:970` | collapse guard bifurcates on 10 ns of cursor or on pure noise (**H1**) | **CONFIRMED** 2/2 | risk / **bug** | **fix** (variant A) |
| S4-5 | `deer.py:1664` | Mellin MC band too narrow in default `joint` mode (**H2**) | **CONFIRMED** 2/2 | risk / risk | disclosure only |
| S4-6 | `deer_analysis.py:1274` | Bruker files with an empty `x_unit` are read in whatever unit the combo shows | **CONFIRMED** 2/2 | risk / risk | **fix** (first) |
| S4-7 | `deer_analysis.py:2409` | the σ_fit/σ_noise "overfit" verdict cannot mean over-fitting | **CONFIRMED** 2/2 | risk / risk | **fix** |
| S4-8 | `deer.py:2610` | `deer_validate`'s consensus median can land on the collapsed branch | **CONFIRMED** 2/2 | note / note — payload refuted, mechanism exact | part (b) only |
| S4-9 | `deer.py:1569` | reported forward model built outside `_fwd`; selector scores an untapered fit; the "Signed forward fit" box is bit-exactly dead | **CONFIRMED** 2/2 | **bug** / risk | GUI + docs half only |
| S4-10 | `deer.py:943` | `fit_dim=True` strongly biased, can sit on the d bound with no flag | **PLAUSIBLE** 1/2 | risk / note — 0/28 real traces at a bound | no code change |
| S4-11 | `deer.py:1664` | `sig_e == 0` silently deletes the Mellin CI band (**H4**) | **CONFIRMED** 2/2 | risk / note | **fix** (sentinel + flag) |
| S4-12 | `deer.py:819` | a manual δ is never clamped to the trace; δ ≥ Tmax discards the numeric integral (**H5**) | **PLAUSIBLE** 1/2 | note / note — R² −29…−288 announces it | no code change |
| S4-13 | `deer_analysis.py:2366` | with Validate on the reported row mixes the ensemble median (peak/mean) with the base trial (width/skew/λ/k/R²/DW) | **CONFIRMED** 2/2 | risk / note | **fix** (provenance) |

**Every suggested fix in the queue was criticized by at least one skeptic as wrong,
incomplete or optimistic — none was landed as written.** What was actually applied,
and why it differs, is in "Fixes applied" below.

### What the four new verifications established

**S4-9 — the "Signed forward fit" checkbox is bit-exactly dead, and silently
re-selects τmax at the next Run.** `taper_short` has **zero** occurrences outside
`deer.py` (both skeptics grepped it), so the shipped path is always
`f_disp = f_r*_fit_w; F_fit = K@masses` (`:1628-1631`) and `_fwd` — the only reader of
`signed_fit` — is reached **only** from the τmax selector at `:1569`. At fixed τmax,
toggling the box gives `max|ΔF_fit| = max|ΔP_density| = 0.000e+00` on **28/28** real
traces. With τmax on Auto (the default) the same toggle instead moves the cutoff on
**17/28** traces and the reported peak with it — up to **0.65 nm** (`sample4_labF`
4.244 → 3.590 nm), on traces that carry no background warning. The box is wired to
`_deer_rerender` (`:946`), which cannot refit, so it visibly does nothing when ticked
and changes the answer at the next Run. Four docstrings assert the opposite of the
code: `deer.py:1439-1444`, `deer.py:1332-1335`, `deer_analysis.py:2674-2677` and
`:2683-2686`. The selector-consistency half is a **tuning change** (it moves the pick
on 15/28 real traces for +0.0028 mean synthetic overlap) and both skeptics require it
to be re-gated on the full synthetic suite *plus* the 28 real traces first; skeptic 1
additionally showed the proposed one-line `_fwd` patch produces a **third** selector
(neither shipped nor taper-consistent — they disagree on 14/28) because `neg` at
`:1572` never goes through `_fwd`, and that `K@_phys_fit(f_disp)` would **double-taper**
(`_fit_w²`).

**S4-10 — PLAUSIBLE, and it is S1's refuted `background_fit` finding relocated one
function down.** The synthetic mechanism is real (d pins at 6.000 in 4/10 seeds,
λ +12.6 %, mean distance +0.22 nm, no warning, because `kref` at `:911` is computed
with the same `fit_dim=True` and co-moves so `k_ratio` = 0.884). But on the 28 real
traces **0/28** sit on either bound (d spans 1.205–3.612), **25/28** already fire
`k_disagrees` + the orange banner, and `deer_analysis.py:2453` already prints
`dim = …`. Both skeptics also refuted the *fix*: the `d ≤ 1.001 or d ≥ 5.999`
predicate catches only 11 of 17 materially-wrong synthetic runs and 0/28 real ones,
and the proposed tighter `[2, 4]` range is worse — DeerLab 0.14.2's own
`bg_homfractal` bounds are `[0.01, 5.99]` (**wider** at the bottom), 12/28 real traces
land below d = 2, and re-fitting with `[2, 4]` just relocates the pile-up (d = 4.000 in
10/10 seeds, λ still 8 % high). Opt-in, default-off, mostly announced → **no code
change**; the identifiability test that *would* work (Δvss between fitted d and d = 3,
or a profile-likelihood width) is recorded for S6.

**S4-11 — CONFIRMED, boundary arithmetic corrected, and S3's "n ≤ 16" was wrong.**
`_tail_noise` returns a literal `0.0` as a "cannot measure" sentinel
(`deer.py:1070`, `:1078`), and `deer.py:1664`'s gate `sig_e > 0` then drops the band
with **no else, no warning, no status change** — confirmed with
`warnings.catch_warnings(record=True)` (empty) and through the real offscreen GUI
(`ci_box=True`, `_band_fill.isVisible()=False`, status string structurally incapable
of differing because `:2501-2503` has no band token, unlike the Tikhonov/Gaussian arms
at `:2509-2512`). The threshold is **n_pos = 18**, not 16. Reachability splits the two
skeptics: route A (short trace / ~95 % trim) needs n_pos ≤ 17 where all 28 real traces
run 158–1213, *and* fires three other flags; route B (constant tail) needs ~124
consecutive bit-identical samples, and the measured longest identical run in every
real file is exactly **1**. Skeptic 1 nevertheless found two live consequences the
finding missed: **zero-padding** a 200-pt trace to 320 (38 % pad) silently kills the
band, at 33 % pad it reports `noise_level` **9× too high**, and `deer_analysis.py:2616`
`res.get('noise_level') or res.get('sigma_noise')` **silently swaps in a different
quantity** when `noise_level` is 0.0 and legends it "±σ noise".

**S4-12 — PLAUSIBLE, and the proposed clamp is counterproductive.** The mechanism is
exact (no clamp on the manual path; `delta ≥ Tmax` hits the `Tmax <= delta` early
return at `:820` and the reported P(r) comes from the analytic term alone; at
`delta = 1e9` the output is *data-independent* — mean 3.659 nm and
P ∈ [−171.6, +178.9] identical for all 7 traces tested). But "silently" is false: R²
goes 0.981 → **−28.7** at δ ≥ Tmax and **−288** at 1e9, printed in the status bar, the
summary table and the info panel. And the suggested `min(delta, t.max())` clamp
**does not fix it** — the guard is non-strict, so the clamped value still discards the
numeric integral — while making the result *look* more plausible (P ∈ [−5.1, +3.8],
R² −28 instead of ±179 / −288). The one genuinely quiet window found is a different
thing: δ at 3–6× the auto value (still far below Tmax) keeps R² ≥ 0.91 while moving the
reported mean up to **0.50 nm**. Recorded for S6 as a `delta_excessive` flag candidate;
no clamp shipped.

**S4-13 — CONFIRMED, and the two skeptics disagree about which half of the row to
trust.** Both reproduced the chimera to 3–4 s.f. (printed row peak 3.470 / mean 4.412 /
width 0.202 / skew −0.85; the base density's own mean is 3.499, the median curve's real
width/skew are 1.545 / +1.01), and skeptic 1 showed it survives at the GUI's **own**
defaults (auto α, auto r grid): printed mean sits **7.2 printed-δr** from the printed
peak. On the 28 real traces the mixing is sub-display (|Δmean| ≤ 0.046 nm,
|Δwidth| ≤ 0.052 nm median 0.004) — so visible severity is coupled to S4-4, as triage
suspected. The decisive new measurement is skeptic 2's, and it **inverts the proposed
fix**: over 28 traces × 9 trials, the *base* width is an unbiased representative of the
ensemble (bias +0.0000 nm, range −0.008…+0.011) while the *pointwise-median curve's*
width is biased narrow (−0.018 nm mean, −0.222 worst) and lies **outside the entire
per-trial range on 8/28** traces; the median curve's mean lies outside on **11/28**.
A pointwise median of nine densities is not a density. So moving width/skew onto the
median (the raiser's option (a)) would degrade the reported width on real data to fix a
corner case.

### The three that are unambiguous bugs

**S4-1 — `deer_validate` leaves the Mellin regularization free.** `deer.py:2659`
pins `alpha_fixed = float(base['alpha'])` deliberately, so validation measures
background-start sensitivity and *not* the regularization choice. For
`engine='mellin'` both halves of that are inert: `base['alpha']` is literally
`float('nan')` (`:1681`), the mellin dispatch (`:568-576`) forwards neither `alpha`
nor `scan_lcurve`, and `**kwargs` still carries `tau_max=None` — so every one of the
9 background-start trials re-scans the whole 10-candidate grid. τmax **is** the
Mellin regularization knob by the engine's own docstring.

Reachable with stock GUI defaults (`deer_analysis.py:903` `setChecked(True)` →
`:1904` → `:1923` → `:1927`); only the Validate checkbox has to be ticked. Measured
through the real GUI offscreen on `sample4_labG`: per-trial auto picks
18,18,18,18,18,8,10,10,10 → band area **0.4982** vs **0.0483** pinned, i.e. the
reported band is **10.3× too wide** (w_max 11.2×), and 2.2× slower. Both skeptics
independently confirmed the `n_tau` half of the fix is *necessary*, not cosmetic:
`n_tau = _ntau_for(tau_max)` is applied only inside the auto branch, so pinning
τmax alone reverts the trials to the caller's `n_tau`.

**S4-2 — the short-r taper is grid-dependent, and it moves the reported mean.**
`deer.py:1424` sets the taper width to `fit_rmin_frac*(r[-1]-r[0])` — 18 % of the r
*range*, not an absolute distance — and `:1628` multiplies it into the **displayed**
density before `_masses` renormalizes. `taper_short` is not in the GUI's kwarg dict,
so the default `True` is what every user gets and no widget can turn it off, while
`r` comes straight from the "Distance max" spinbox (range 0.5–50 nm).

Both skeptics reproduced, on real data. `sample1_labA` reported mean:
**2.554 / 2.652 / 2.834 / 3.170 nm** on grids 1.5–6 / 1.5–8 / 1.5–12 / 1.5–20, with
τmax identical (30.0) in every pair, against **2.493 / 2.502 / 2.501 / 2.501** with
the taper off. Over all 28 real traces the tapered spread across {8, 12, 20} is
mean 0.441 / max 0.873 nm versus 0.060 / 0.211 untapered. The docstring's claim that
the taper "leaves the mid/long-r density bit-identical" holds only for the default
grid. An equal-area 2.0 + 4.0 nm bimodal has its short peak's population read as
0.436 / 0.326 / 0.196 / 0.093 on those four grids (truth 0.500).

*Both skeptics warn the proposed 0.5 nm absolute cap is right in shape but its cost
in the tuned 3.0–4.3 nm band is understated — do not land it as written.*

**S4-6 — a Bruker file with no `XUNI` is read in whatever unit the combo happens to
show.** Found by the call-sites reviewer, outside the session's nominal scope, and
the most user-visible defect in the set. `deer_analysis.py:1274-1277` overrides the
time-unit combo only on a *recognised* unit, with no `else`; `DEER_TUNITS` makes
`'µs'` the session default, and there is no settings restore, so every fresh window
starts on µs. Exactly **7 of the 27** ring-test DSC files carry no `XUNI` line
(`sample{1,2,3,4}_labE`, `sample{1,2,4}_labF` — all `DSRC MAN`), i.e. third-party or
hand-saved files; all 14 of the user's own lab files carry `XUNI 'ns'`.

Reproduced through the real GUI offscreen: `sample1_labE.DSC` as opened silently
sets rmin 11.90, rmax 50.00, bg start 1608 "µs", and Mellin returns λ = 0.0200
(clamped, `lambda_raw = -4.55e+170`), peak **16.11 nm**, mean 48.84 nm, R² = nan —
and the info panel prints a **171-character integer** inside the ⚠ span (`%.2f` on
`lambda_raw` at `:2460`). Forcing the combo to ns and re-running Auto range gives
λ = 0.3072, peak **2.438 nm**, R² = 0.956. All 7 files reproduce (16.10–21.60 nm as
opened vs 2.33–4.81 nm correct).

*Both skeptics found the proposed fix incomplete in the same way: a `set_status`
advisory at `:1274` is immediately clobbered by `open_bruker`'s own final
`set_status` at `:1281-1283`, and flipping the combo alone is not enough because
`_unit_changed` does not recompute the auto distance range or the bg window
(measured: combo-flip alone still gives peak 18.027 nm, R² = −95.7).*

### H1 and H2 — the two big hand-overs, both answered

**H1 (S4-4) — CONFIRMED, and the mechanism is now fully characterized.** The
headline reproduced to 4 s.f. by both skeptics independently: a Gaussian 3.5/0.20 at
k = 0.20, one **10 ns** step of `bg_start` (1.42 → 1.43 µs) moves
k 0.19922 → 0.03747, λ 0.3487 → 0.5462 and the reported mean **3.517 → 4.527 nm**.
The discontinuity lives entirely in the *wide* fit: `k_t` is stable
(0.19922 → 0.19939) while `k_w` jumps 0.00197 → 0.03747 and `decay_w`
0.0049 → 0.0894, flipping `collapsed`. Mapping `vss(log k)` on the wide grid shows
**3–4 local minima** (0.0113 / 0.0331 / 0.4858), and the two adopted branches differ
in `vss` by **0.032 %** while `k_w` differs **19×** — so the bounded golden-section
`minimize_scalar` at `:948` is picking a *basin*, not a minimum. That is why S2's
"compare the residuals" idea cannot separate the cases.

Two things sharpen S2's hand-over:

- **The bad branch is already caught and announced.** At the failing `bg_start`,
  `k_disagrees` is True, `joint_background` raises the RuntimeWarning, and
  `deer_analysis.py:2463-2466` renders it as an orange flag. Coverage was perfect
  where it matters: 5/34 bifurcations in a `bg_start` sweep flagged 5/34; in a
  100-realization noise ensemble 14 mis-branched and **14/14** were flagged. So this
  is a robustness/knife-edge defect, not a silent one — hence one skeptic's downgrade
  to `risk`.
- **The joint-bg reviewer's proposal (A: drop the wide fit) survived both skeptics'
  gates; the alternatives did not.** Gated on 104 synthetic cells, tight-cap-only
  improves mean |ln k/k_true| **0.176 → 0.095** and mean |λ−λ_true|
  **0.0078 → 0.0021**, cuts the max adjacent |Δln k| over a `bg_start` sweep from
  **2.24 → 0.012**, and changes the 28 real traces by a median **0.42 %** in k and at
  most **0.027 nm** in mean distance. A skeptic rebuilt the long-r family that the
  wide cap supposedly exists for and found ship == tight == ratio-only **bit-for-bit**
  (because `k_w` collapses to 0 there, the shipped guard already rejects the wide cap),
  so the "10.7× in k" cost attributed to (A) is *shipped* behaviour, not a cost of the
  change. The mc-band reviewer's weaker variant (B: drop only `decay_w < 0.05`) was
  **refuted as a standalone remedy** — at k_true 0.12 it leaves a 0.261 jump and a
  24 %-low k that the ratio test cannot catch.

**H2 (S4-5) — the Mellin MC band DOES inherit the deficit, and the contradiction
between two reviewers resolved to a single knob.** The fwd-delta reviewer measured
the band honest (~1.0×) and the mc-band reviewer measured it 2–11× too narrow. Both
skeptics settled it on one shared setup: the deficit is a monotone function of the
cutoff, and fwd-delta had pinned `tau_max = 30` — above even the manual spinbox
default of 25.

| `tau_max` | band/scatter @ peak | coverage of own ensemble mean @ peak |
|---|---|---|
| **Auto (GUI default, picks 10–15)** | **0.457** | **0.625** |
| 12 (= what Auto picks) | 0.476 | 0.625 |
| 30 (fwd-delta's pin) | 0.746 | 0.833 |
| 40 | 0.860 | 0.906 |

All four arms print bit-identical background fits, so the cutoff is the only
difference — and **the narrow configuration is the default**. Conditioning on the
modal cutoff still gives 0.511, so this is not τmax jitter. *Method note for
whoever implements the fix: never validate this band with `tau_max` pinned high — that
configuration inflates it 3.0–3.7× and hides the defect.* Both skeptics recommend
the cheap half now: give the Mellin result a distinct `ci_kind` (`'mc_fixed_bg'`; it
currently has **none** while `deer_invert_joint` sets `'noise_fixed_bg'`) and fix the
`deer_ci_chk` tooltip's Mellin arm (`deer_analysis.py:380`), which today carries none
of the caveats S2 added to the Tikhonov arm and misdescribes the noise source.

### S4-3 — the one downgrade

The bracket mechanism reproduced exactly (`kref = max(k0, 1e-4)` with the sequential
`k0` collapsing, giving the bracket [1e-6, 1e-2]; ceiling signature k = 0.009825 and
floor 1.011e-06 both reproduced to 5–6 s.f., `kref` floors somewhere on 15/28 real
traces, worst adjacent jump 367×). But the finding's headline — "with no flag" — is
**false**: a bound hit forces `|log(k/kref)| ≈ log(100)`, so `k_ratio` is ~98 or
~0.0101, which always trips `k_disagrees` and the existing RuntimeWarning. Measured
17/17 bound hits warned, and the GUI already renders it. All that is genuinely
missing is a `k_at_bound` label to separate "pinned at a bound" (no information) from
"interior but far from kref" (informative). One skeptic also refuted the
bracket-widening half of the proposed fix outright.

*This also reconciles with my own check: I found **0/28** at a bracket edge at the
GUI's single `bg_start`, while the reviewer reached the floored-`kref` regime by
sweeping `bg_start`. Both are right; they measure different things.*

### S4-8 — the arithmetic is exact, the payload is refuted, and it spawned a better finding

Worth recording as method. Skeptic 1 reproduced the mechanism **bit-for-bit**: on the
demo case 5 of the 9 `_bg_start_grid` trials land on the collapsed branch (trial
`r_mean` 3.500, 3.500, 3.515, **4.518**, 3.499, **4.597**, **4.548**, **4.486**,
**4.585**), `deer_validate` returns `r_mean` 4.4123 against a true 3.500, and the base
trial is flag-clean. It also confirmed the flag-plumbing code fact — `deer_validate`
(`deer.py:2685-2691`) exposes only the P-density ensemble plus `base`, no per-trial
k/λ/flag at all, and `main.py:253/269` connects only `readyReadStandardOutput` for
`process_deer`, so the 5 RuntimeWarnings really are invisible in the GUI log.

But the finding's *payload* — "signal-free, it looks converged" — is **refuted with
numbers**, and severity drops to `note`:

- The validation band, which is drawn unconditionally when Validate is on, is
  **73× wider** than a healthy ensemble's at the failing case (band/peak 0.73 vs 0.01
  at k = 0.02/0.05/0.10 on the identical P(r) and noise). The feature's own product
  screams.
- The plotted median carries a spurious local max at 7.02 nm at 25 % of peak height,
  30 % of its mass above 4 nm.
- The finding's second data point is simply wrong: at centre 1.55 µs the base trial
  **does** fire `k_disagrees` (as do 1.45 and 1.60). Only the single centre 1.50 is
  flag-clean.
- Reachability is one cell of a map, not a regime: seeds 0/1/2/3 give `r_mean`
  3.480–3.499 with band/peak 0.01 — **only the finding's own seed 9 bifurcates**. Over
  Tmax {1.5, 2.5, 4} × k {0.02…0.30} × seed {0, 9}, seed 0 never bifurcates anywhere,
  and the demo needs k·Tmax = 0.50. On real data k·Tmax is 0.030–0.142, and the one
  trace with a wide within-grid k spread has **9/9 trials flagged**, so the user *is*
  warned. **No signal-free real instance exists.**

**The better-aimed defect it found instead** (new, for the next session's queue): the
GUI *mixes two different curves in one reported row*. `deer_analysis.py:2366` takes
peak/mean from the ensemble **median** while `:2382-2384` takes width/skew (and λ, k,
R², DW) from `val['base']`. In the failing case the row prints **mean 4.412 beside
width 0.202 and skew −0.85** — the base's own mean is 3.499 and the median's real width
is 1.545 / skew +1.01. A mean-minus-peak of 0.94 nm next to a 0.20 nm width is
arithmetically impossible, and it is a cheaper, more general fix than the proposed
per-trial spread warning (which would only duplicate an already-firing flag).

*Method note: this is the second time in S4 that a skeptic's refutation was more
valuable than a confirmation would have been. Both times the finding's mechanism was
real and its consequence claim was over-reached, and the corrected aim came out of the
adversarial pass — not the review pass.*

---

## Fixes applied

Order followed the report's own constraint: **S4-6 first** (most user-visible), then
S4-1 and S4-4, re-baseline, then S4-2 — the taper and the band move the numbers
S4-1's and S4-4's gates measure. Every fix departs from the queue's suggestion
somewhere, because every suggestion was criticized; the departures are listed.

**S4-6 — Bruker/CSV files with no time unit** (`deer_analysis.py`). The unit is now
*guessed from the trace length* before `_add_traces` (`_preset_unit_from_span`,
gated on `DEER_TSPAN_US = (0.05, 50) µs`), and the guess is **appended to
`open_bruker`'s final status string** rather than emitted at the check, where it was
clobbered. `_unit_changed` now calls `_retune_auto_rrange`, which re-derives the
distance window **only while it still holds the auto values** (tracked in
`_rrange_auto`), so flipping the combo no longer leaves the stale range that gave
peak 18.03 nm / R² −95.7. The same path serves the CSV and plot-buffer loaders
(`_preset_deer_unit` now takes `x` and returns the advisory). `%.2f` → `%.3g` on
`lambda_raw` in the GUI flag *and* in `joint_background`'s own RuntimeWarning
(a 171-character integer in both).
*Verified through the real offscreen GUI on all 27 ring-test DSC files: the 7
unit-less ones now open in ns with peaks 2.17–5.24 nm; **0 traces above 9 nm**
(before: 7 at 16.10–21.60 nm). The 20 files with `XUNI` are untouched.*

**S4-1 — `deer_validate` pins the Mellin regularizer** (`deer.py`). After the base
inversion, `engine == 'mellin'` now pins `tau_max`, `n_tau = len(base['tau'])` and
`delta` into `kwargs`. `n_tau` is not cosmetic (both skeptics): the auto branch
replaces it with `_ntau_for(tau_max)`, so pinning τmax alone moves the trials onto
the caller's grid. `delta` was measured stable and is pinned for the same reason at
zero cost. Skeptic 1's condition — *do not ship it as "the band is now honest"* — is
met by the next item: `deer_validate` now also returns per-trial `trials` and a
`trial_spread` summary, and the panel raises a flag when they disagree.

**S4-8(b) + S4-13 — the reported row now describes one density** (both files).
`deer_validate` returns `trials` (per-trial bg_start / r_mean / λ / k / flagged) and
`trial_spread` with `disagree` set when a **majority** of trials flag (any-one fires
on 4/28 real traces where the answer is right to 0.035 nm) or the trial mean
distances span more than max(0.15 nm, 5 %). In the panel, peak/mean/width/skew and
λ/k/R²/DW now all come from the central trial; the ensemble's median peak/mean and
the trial spread are printed in the validation block, and the header says
"central trial; curve and band from the sweep". This follows skeptic 2's measurement
(base width bias +0.0000 nm vs the trials; the median curve's width lies outside the
*entire* per-trial range on 8/28) and **rejects the raiser's option (a)**, which
would have moved width/skew onto the biased median curve. The plotted curve and the
CSV export are unchanged.

**S4-4 — the collapse guard is gone (variant A, tight cap only)** (`deer.py`).
`joint_background` no longer fits a second, wider cap. Both skeptics gated the
alternatives out: (B) leaves a 0.261 `|Δln k|` jump and a 24 %-low k that the ratio
test cannot catch; (C) is worst on every metric; and the long-r family the wide cap
supposedly protected is **bit-identical** under ship/tight because `k_w` collapses to
0 there and the shipped guard already rejected it. Skeptic 2's condition that A land
*with* S4-3 is met by the next item.

**S4-3 — the missing label** (`deer.py`, `deer_analysis.py`). `_fit_rate` now
reports whether k landed on an edge of its `[kref/100, kref*100]` bracket;
`k_at_bound` joins the reliability keys, the RuntimeWarning and the orange flag
line. The finding's *bracket-widening* half was refuted and is not implemented —
"with no flag" was false, so only the "pinned at a bound vs interior" distinction
was actually missing.

**S4-2 — the short-r taper is now an absolute window** (`deer.py`).
`fit_rmin_frac=0.18` (18 % of the r *range*) is replaced by
`fit_rmin_abs=2.0` / `fit_rmin_width=0.5`: the raised cosine ramps from the grid
bottom to at most 2.0 nm, over at most 0.5 nm, and **vanishes entirely on a grid
starting above 2.0 nm**. This is the shape both skeptics demanded (anchor to a
physical short-r limit, not to `r[0]`), not the queue's 0.5 nm cap, which they showed
still slides with `r_min`.

*Re-tuned, not assumed.* Sweeping ceiling ∈ {2.0, 2.5, 3.0} × width ∈ {0.5, 1.0, 1.5}
over four arms at once (`~/deer_benchmark/s4_fix/s42_tune.py`):

| window | grid spread | r_min bias | bimodal error | mid-r overlap | mid-r ⟨\|Δmean\|⟩ |
|---|---|---|---|---|---|
| old (0.18 × range) | 0.617 nm | 0.319 nm | 0.240 | 0.8049 | 0.135 nm |
| **abs 2.0 / w 0.5 (shipped)** | **0.009** | **0.000** | **0.010** | 0.7619 | 0.217 |
| abs 2.5 / w 1.0 | 0.011 | 0.055 | 0.124 | 0.7815 | 0.165 |
| abs 3.0 / w 1.5 | 0.015 | 0.220 | 0.245 | 0.8017 | 0.130 |
| no taper | 0.010 | 0.000 | 0.047 | 0.7153 | 0.334 |

The sweep answers the skeptics' warning directly: **the old taper's mid-r advantage
is bought by deleting real short-r mass.** Every window wide enough to recover it
(2.5/1.0, 3.0/1.5) re-creates the defect — the equal-area 2.0 + 4.0 nm bimodal's
short peak is mis-read again (error 0.124, 0.245 against 0.010). So the mid-r cost is
**accepted deliberately**: overlap 0.805 → 0.762 and ⟨|Δmean|⟩ 0.135 → 0.217 nm on
the tuned synthetic set, in exchange for a reported mean that no longer depends on the
"Distance max" box (spread 0.617 → 0.009 nm on a real trace) or on `r_min`
(bias 0.319 → 0.000 nm; the old taper cut straight through the peak on a 2.5–8 grid,
biasing the mean +0.76 nm), and a bimodal population read as 0.509–0.512 against a
truth of 0.500 (old: 0.434 / 0.329 / 0.188 / 0.091 over grids 6/8/12/20).

**S4-7 — the fit-quality verdict** (both files). The panel now reports
**σ_fit/σ_e** against `noise_level` (the model-free tail noise of V) with a
"matched" / "residual above the noise floor" verdict. The **"overfit" arm is gone**,
per both skeptics: no residual statistic here can see Mellin over-fitting (τmax
10→150 drives roughness ×325 while the ratio moves 0.93 → 0.90). The old
σ_fit/σ_noise ratio survives only as what it actually measures — a separate
"tail residual N× the noise floor — check the background" line when the tail is
elevated. The over-fit gauge that *does* respond to τmax is the new `neg_area`
(negative area of the signed density), returned by the engine and printed in the
panel.

**S4-9 — the checkbox** (both files). "Signed forward fit (negative-aware)" is
relabelled **"Signed density in the τmax selection"**, its tooltip says it does not
change the displayed fit and needs a re-run, and it is rewired from
`_deer_rerender` (which cannot refit) to `_mellin_live`. Its Qt read is hoisted out
of the worker closure into the snapshot block. All four false docstrings
(`deer.py` `_fwd` and the returns block, `deer_analysis.py` `_fit_curve` and
`_whiteness_of`) now say what runs. **The selector-consistency change was NOT
made** — it moves the cutoff on 15/28 real traces for +0.0028 synthetic overlap,
the queue's one-line patch produces a *third* selector (it never touches `neg` at
`:1572`) and double-tapers the unsigned branch. Left for S5/S6 with its own gate.

**S4-11 — the vanishing CI band** (both files). `_tail_noise` now returns **NaN**
for "cannot measure" and keeps `0.0` for a genuinely constant tail — skeptic 1's
root-cause fix, which repairs every caller at once. `deer_invert_mellin` carries
`ci_kind = 'mc_fixed_bg'` (it had none, while `deer_invert_joint` sets
`'noise_fixed_bg'` — this is also S4-5's cheap half) and a `ci_unavailable` reason
string that names *which* case fired; the panel shows it in the orange style when
the CI box is ticked. The Residual view no longer silently substitutes
`sigma_noise` for `noise_level` under a truthiness test — it falls back only when
the first is genuinely absent and **relabels the curve** ("±σ tail residual").
"Process all" now reports how many traces got no band instead of dropping them
silently.

**S4-5 — disclosure only.** Beyond the `ci_kind`, the CI tooltip's Mellin arm now
states the noise source correctly (the decayed-tail noise of V, not "the
fit-residual noise"), that the band conditions on the fitted background/λ/τmax/δ,
the measured 78–91 % coverage against a nominal 95 %, and that it is centred on a
possibly biased density — the caveat no widening would fix. Per skeptic 2, the
"2–11×" figure is **not** quoted anywhere: that cell needs k = 0.30 µs⁻¹, 6.7× the
maximum k on any real trace. The parametric bootstrap was **not** implemented (418
ms/realization = ~21 s at the GUI's n_mc = 50, on a path wired to live update).

### Found while gating: the echo-top parabola collapses on noisy shallow traces

Not a queued finding — it surfaced when the synthetic suite was re-run for the S4-2
gate, on `hard/gauss_broad` and `hard/gauss_narrow_broad` at the highest noise
(lambda 0.20, sigma 0.04), where the Mellin forward fit sits **above** the data for
the whole echo top (residual reaching −0.09 in V units, several times the noise band)
while the Tikhonov fit on the same trace is clean. Pre-existing: the pre-S4 worktree
reproduces it identically.

**Mechanism** (confirmed independently by a Fable agent, `~/deer_benchmark/s4_fable/`).
F carries the 1/λ-amplified noise, so at λ = 0.20 / σ = 0.04 the noise on F (~0.2)
exceeds the 0.15 level drop `mellin_delta` tests for. The *first* sample below the
level is then a noise dip, not the decay — measured crossing 27 ± 15 ns against a
noiseless 110 ns — and `floor_ratio` caps δ at twice that dip, so the noise-adaptive
widening runs **backwards** exactly where it is needed (δ 141 → 37 ns going from
σ 0.02 to 0.04). The curvature window collapses with it to its 3-sample minimum,
giving |b| ≈ 560 where the noise-only scatter of b is ≈ 230 — pure noise.

**Two fixes applied**, both narrow:
- The level crossing is read off an F smoothed over `w` samples, `w` sized from the
  measured relative noise so that **w = 1 — the identical code path — below
  rel ≈ 0.09**, which covers the entire tuned regime (verified: every `easy` point
  and every `hard` σ ≤ 0.01 point bit-identical).
- The curvature-window floor goes from 3 samples to 9 **under the same
  noise gate**. It must not be raised unconditionally: the first attempt was, and
  the real-trace check vetoed it — early-time residual up to **6.6x worse** on the
  28 ring-test traces, R2 down 0.015, and one reported peak moved **1.40 nm**
  (`sample4_labE` 3.721 -> 2.317). On clean data the parabola is only valid very
  near the echo top, so forcing nine samples fits the curvature past its own range
  of validity. Gated, the 28 real traces come back **bit-identical**.

**The honest result: the fits are repaired, the distributions are not.** Repairing
the analytic term *either* way — through δ or through b — costs the same ~0.10
overlap on `gauss_broad` at σ 0.04:

| arm | δ | early residual | overlap |
|---|---|---|---|
| before | 36.9 ns, \|b\| 559 | 0.0708 | 0.720 |
| median echo-top reference (**rejected**) | 148.5 ns | 0.0492 | 0.612 |
| **9-sample curvature window (shipped, noise-gated)** | 36.9 ns | **0.0380** | 0.619 |

So the good P(r) on that case was being produced **by** the broken parabola: |b| = 560
was an accidental regularizer suppressing spurious long-r mass. A wrong forward fit is
still a defect — it is displayed, exported, and feeds σ_fit and the whiteness verdict —
but nobody should expect the recovered distances to improve. Aggregate cost of the
shipped pair over 12 condition × shape pairs × 4 noise levels × 3 seeds: **zero on
every `easy` point and on `hard` σ ≤ 0.005**, −0.0013 / −0.0029 / −0.0053 overlap at
`hard` σ 0.01 / 0.02 / 0.04.

**Rejected on measurement:** taking the echo-top reference as the median of the first
few samples (better crossing accuracy — mean error 15.3 vs 28.1 ns against the
noiseless crossing — but it fires in the tuned regime and costs 0.108 overlap on the
very case it fixes); a curvature clamp keyed to δ (binds on 75 % of clean seeds); a
free intercept in the parabola (mixed, and it drops the F(0) = 1 guarantee); a
Savitzky–Golay smoother (noisier than the boxcar at equal width); a robust decay-scale
fit replacing the threshold (shifts the clean regime by 4–10 ns).

**The real lever is the zero-time fit, not δ.** Handing the engine the true t₀ is worth
**+0.085 overlap** on that case — 3–6× anything δ does — and it removes most of the
collapse as a side effect, because a mis-set t₀ starts the trace already down the
slope. `fit_zero_time` lands +3.9 ns biased with a 21 ns scatter (worst 77 ns) at the
highest noise; fitting it on a 5-point smoothed trace gives +0.4 ns bias, 16 ns scatter,
worst 52 ns. That is a self-contained improvement to S1 territory with its own gate —
**queued, not applied**, because it changes an estimator every engine depends on.

**Not implemented, by verdict:** S4-10 (PLAUSIBLE; 0/28 real traces at a bound,
25/28 already flagged, and both skeptics refuted the proposed detector *and* the
tighter `[2, 4]` range — DeerLab's own bounds are wider), S4-12 (PLAUSIBLE; R² −29
to −288 already announces it, and the proposed clamp is inert *and* makes the
result look more plausible).

---

## Confirmed correct — do not re-derive in S5/S6

- **`n_tau` is converged at the shipped default.** At fixed `tau_max = 30`, sweeping
  `n_tau` 601 → 4001 leaves mean 3.5537 nm and width 0.4439 nm *identical*; max |ΔP|
  between 601 and 2001 is 4.4e-5 against a 1.974 peak. The 601-vs-`_ntau_for(30)=2001`
  asymmetry between the explicit and auto paths is cosmetic. *(session lead,
  `s4_me/chk.py`)*
- **`rmax_tight = 5*(Tmax/2)^(1/3)`** is the correct DeerAnalysis/Jeschke rule: the
  exponent follows from ν ∝ r⁻³, the constant reproduces the textbook 5 nm at
  Tmax = 2 µs, and it matches the GUI's own `R_MAX_FACTOR = 5.0`
  (`deer_analysis.py:1674`). The clip at 8 nm is what makes it inert on long traces.
- **The `fit_dim` and fixed-dim branches minimise the same objective** (verified
  numerically: `vss(k=0.05, d=3) = 0.002170314908096325` from the same closure).
  `max_nfev = 120` is not binding (measured nfev 8–26).
- **`fit_zero_time` does not go through `joint_background`** — it forces
  `engine='sequential'` internally (`deer.py:2537`), so a fitted t₀ is immune to the
  collapse bifurcation. `deer_validate` *is* exposed (that is S4-8).
- **`n_r = 60` / `rate_alpha = 1.0`** leave the final k stable to ~1 % over
  `n_r` 30/60/120 and `rate_alpha` 0.1–3 on real traces; the instability is in the
  collapse *decision*, not the coarse grid.
- **The λ pin is accurate wherever the tail has decayed**: over the 104-cell
  synthetic suite |λ − λ_true| ≤ 0.0063 (mean 0.0021) with a single-cap fit. Its
  failures are the ones the code already flags (`tail_abs_F` = 0.536 on the 1 µs /
  4.5 nm undecayed case where λ comes out 7.6× low, against a 0.05 threshold).
- **The k bracket spans the answer on all 28 real traces at the GUI's `bg_start`** —
  0/28 at either edge, `k_seq` 0.0149–0.0482. *(session lead, `s4_me/chk3.py`)*
- **The reliability keys S2 added do reach the user on the joint path** and fire on
  the cases that matter (`deer_analysis.py:2459-2466`). The hole is the Validate
  path, which is S4-8.
- **`data_treatment.py` has no DEER call site at all** (grep clean) — the only
  consumer of these two functions in the tree is `deer_analysis.py`. That retires
  part of S6's duplication question.

## Independent session-lead findings

`~/deer_benchmark/s4_me/my_findings.md`. The one that matters:

**σ_fit/σ_noise cannot mean over-fitting — 17/28 real traces mislabelled.** Both
quantities come from the *same* residual (`σ_noise` is its last 30 %), so the ratio
is self-referential; `ratio < 0.9` means the tail is fit worse than average — the
droop — which is the opposite conclusion. Against the independent noise level
already in the result dict (`noise_level`, `_tail_noise` on `Vn`), all 17 traces
called "overfit" have σ_fit **above** the noise (1.04–6.09×, median 1.44). The set
contains **zero** genuine over-fits. This became S4-7, **CONFIRMED 2/2**, and both
skeptics went past my check:

- Skeptic 1 showed a *genuine* over-fit is invisible to the statistic: τmax 10→150
  drives roughness ×325 and the recovered mean 3.495 → 3.263 nm while the ratio moves
  only 0.93 → 0.90 and the label stays "matched".
- Skeptic 2 reproduced the label split exactly (11 overfit / 10 matched / 7 underfit
  at Auto τmax; 11/9/8 at the 30.0 default), measured σ_fit/σ_e = 1.02–5.86 on all 11
  "overfit" traces — at or above the independent noise floor in every case, with the
  *tail* window elevated instead (σ_noise/σ_e up to 10.3) — and showed the verdict is
  **invariant across the entire GUI-reachable τmax range 2–200** while P(r) roughness
  grows ×170. A statistic that cannot move in the only regularizer is not measuring
  fit quality at all.

Both converged on `res['noise_level']` as the honest denominator (already returned at
`deer.py:1681`, and safe to substitute — its only other reader,
`deer_analysis.py:2616`, already prefers `noise_level` for the Mellin path). Two
caveats for the fix: **the 0.9/1.6 thresholds cannot be carried over**, and the `<<`
arm would become *dead* rather than correct, since no available statistic here
detects a genuine over-fit — the honest move is to drop that arm and report a
roughness/negative-area diagnostic instead.

---

## Persisted state (the review is complete; kept for S5/S6)

`Workflow`'s `resumeFromRunId` is **same-session only**, so run `wf_79b3f216-ad5`
could not be resumed after the pause. Everything both runs produced lives outside the
session directory instead, and the same machinery is reusable for S5/S6:

```
~/deer_benchmark/s4_persist/s4_raw_results.json      all agent results
~/deer_benchmark/s4_persist/s4_queue.json            the 13-finding queue
~/deer_benchmark/s4_persist/s4_extra_findings.json   findings raised AFTER triage
~/deer_benchmark/s4_persist/s4_reviewers.json        5 reviewers: findings + coverage + numbers
~/deer_benchmark/s4_persist/s4_triage_notes.json     merged notes + what was dropped
~/deer_benchmark/s4_persist/s4_verdicts_so_far.json  the banked skeptic verdicts
~/deer_benchmark/s4_persist/s4_verified_final.json   the finished 13-finding verdict set
~/deer_benchmark/s4_persist/build_resume.py          rebuilds the continuation script
~/deer_benchmark/s4_verify_resume.js                 standalone stage-3 continuation
```

`build_resume.py` re-harvests the journal, recovers each verdict's finding id from the
skeptic's own prompt in `agent-*.jsonl` (the journal stores no labels), merges any
`s4_extra_findings.json` entries into the queue by id, and rewrites the continuation
script's DATA block. **Two bugs in it were found and fixed when the continuation
session first ran it**, both worth knowing before reusing it: the DATA-block
substitution was line-anchored, so it left the previous multi-line array in place and
produced unparseable JavaScript; and a finding added after triage had no way to
survive a rebuild until `s4_extra_findings.json` was added.

The in-session gates are in `~/deer_benchmark/s4_fix/`: `s42_tune.py` (the taper
window sweep), `s44_gate.py` (the collapse-guard gate), `s41_map.py` + `s41_gate.py`
(finding a background-start window where the cutoff changes, then measuring the band
there), `s46_gui.py` and `s4_gui_smoke.py` (both real-GUI, offscreen), and
`pre_tree/` — a `git worktree` at the pre-S4 commit, which is what every "before"
number was measured against.

### Gate to re-run after any fix (per the S1/S2/S3 lesson)

- `~/deer_benchmark/s2_fix/{unit.py,check.py,gui_smoke.py}` — the last is the
  **GUI-path** smoke run; a harness-only check has now missed a real bug three
  sessions running.
- `~/deer_benchmark/batch.py` — DeerLab cross-check, must hold at overlap 0.978 /
  |Δpeak| 0.024 nm / |Δλ| 0.0259 over 28 traces.
- `~/deer_benchmark/synth/` + `~/deer_benchmark/s4_jointbg/variant.py` — the latter
  has a `cap_mode` switch already monkeypatched over `deer.joint_background`, which
  is what any H1 proposal must be gated through.
- **Fix-order note:** S4-2 (the taper) and S4-5 (the band) both move numbers that
  S4-1's and S4-4's gates measure. Land S4-1 and S4-4 first, re-baseline, then S4-2.

### Environment

python3 only (no `python`); numpy 2.2.6, scipy 1.15.3, sympy 1.14.0, mpmath 1.3.0.
DeerLab 0.14.2 needs `~/deer_benchmark/deerlab_shim.py` imported *before* `deerlab`.
Qt needs `QT_QPA_PLATFORM=offscreen`; matplotlib needs Agg.

**Trap that cost a run:** the real Bruker `*_bckg.dat` time column is already in
**microseconds** — do not divide by 1000. `benchmark.py:46` also crops `t >= 0`
itself where the GUI does not.

## Carried forward

- **The port is now four sessions deep.** `deer.py` is byte-identical across plain /
  NIOCH / NIOCH_Q / Cryomech while ITC carries S1 + S2 + S3; `deer_analysis.py`
  exists only in ITC / NIOCH / NIOCH_Q. Port together, and run
  `~/atomize_sync/sync_check.py` first.
- **To S6:** S4-6 shows the Bruker loader's unit handling needs a look beyond the
  `else` branch (`_unit_changed` does not recompute the auto range or bg window).
  Also still open from S3: the ME₁-ε placement, with the queued CI work.
- The 17 S2 notes and 11 S3 notes remain unverified; the full text of S4's own
  note-severity findings is in `s4_triage_notes.json`.

## Notes worth acting on later (unverified — no skeptic ran on these)

Ranked. The first three are the ones I would queue for S5/S6; the rest are recorded
so they are not re-found. Everything here comes from the reviewers' own measurements
and has **not** been through the adversarial pass, so treat the numbers as claims.

1. **The τmax candidate grid clamps silently at both ends** (`deer.py:1505`). The
   fixed grid is [6 … 40] with no boundary flag, where `l_curve` warns in the
   equivalent situation. It picks the **ceiling on 10 of 28 real traces**, and on an
   extended grid the penalty argmin lies above 40 on 7/28 and below 6 on 1/28. Real
   mean distances barely move (max 0.081 nm) because the plateau is flat, but the
   synthetic cost is large where the tuning suite has no shapes: a sharp
   3.0 nm / σ = 0.05 case scores overlap 0.929 at the ceiling against 0.988 at
   τ = 60. Widening to [3 … 60] over 72 conditions: mean overlap 0.675 → 0.692
   (oracle 0.720), 20 better / 14 worse, gain rising with noise, ~35 % more cost.
   *This was the closest finding to the verification cut.*
2. **`_masses` normalizes by the signed area**, with a fallback only at
   |area| < 1e-12 — nine orders below the smallest area actually reachable (0.0021).
   At low λ the reported density is amplified by 1/|area| and, for a negative area,
   is the exact **negative** of the honest output (measured: 1 seed in 12 at σ = 0.04
   on a 1 µs trace with λ at its clamp; 3/12 at σ = 0.08). Healthy on all 28 real
   traces. Any fix must be a *relative* guard (area < η·positive area), gated on the
   synthetic suite.
3. **`_fit_rate`'s two `except Exception: return kref, d0` arms make a failure
   indistinguishable from success** (`deer.py:952`): the joint fit silently degrades
   to the sequential one, `k_ratio` comes out exactly 1.0, `k_disagrees` is False and
   nothing warns. A single non-finite sample *before* `bg_start` is enough to trigger
   it, and the NaN then travels into the inversion.
4. **The λ clamp is inconsistent across the module** — `joint_background` clamps to
   [0.02, 0.95], `background_fit` and `_no_background` to 1.0, `background_general` to
   0.98. A true λ = 0.99 is reported as 0.950 by the joint path (flagged) and 0.991 by
   the sequential one.
5. **H3 is answered and the aliasing story is refuted.** Against a converged
   `du = 0.0002`, the `du = 0.02` quadrature error on Ṽ(τ) is 1.3e-4 … 8.6e-4, and
   S3's 0.689-vs-0.735 overlap gap was a forward-model r-quadrature artifact. What
   `du` actually costs is **noise decimation** (one tail point in 14 on a long
   trace): P scatter 0.0293 → 0.0192 and mean-distance bias +0.037 → +0.009 nm going
   from 0.02 to 0.00125. The two reviewers split on whether to change the default
   (+0.016 mean overlap at 1.46× cost vs "no action"), and both rejected a
   data-driven `du = dt/Tmax` rule (no better, up to 6× cost).
6. **Both non-default τmax methods are broken, and neither is reachable from the
   GUI.** `'discrepancy'`'s noise floor treats the still-modulated V as white noise,
   so on 17/28 real traces its threshold collapses and the branch silently becomes
   argmin(σ_fit) — the over-fit chase its docstring says it prevents; `'lcurve'`
   cannot return its end candidates at all and takes a plain argmax of a signed
   curvature with no no-corner fallback.
7. **Every forward model is a rectangle sum over the user's r grid** and needs
   dr ≪ r⁴/(6·ν_dd·T). The GUI default (200 points over 1.5–8 nm) violates that by 6×
   at r = 2 nm on a 10 µs trace, where the error (1.6e-2) exceeds a typical noise
   level — exactly where the Mellin engine puts its short-r noise. Not reachable on
   the real traces (n_r 200 → 800 leaves τmax and the mean identical to 3 dp), and it
   affects the Tikhonov engines' kernel too.
8. **`joint_background` defaults `bg_start` to 0.6 × span while every other engine
   uses 0.5 × span.** Unreachable from the GUI (which always passes a value), but a
   script that omits `bg_start` analyses a different window depending on the engine.
9. Fixed in passing while landing S4-1: the **validation panel printed the
   background-start sweep on the zero-time-relative axis** while the spin box, the
   cursor and the plot use the acquisition axis, so the swept window read as offset
   by t₀ (~130 ns on a real trace) and the user's own cursor position appeared near
   the top of the printed range.

### Method notes from the verification pass

- **A refuted payload was worth more than a confirmation, twice.** S4-8 and S4-10
  both had exact mechanisms and over-reached consequence claims; in both cases the
  corrected aim came out of the adversarial pass (S4-8 spawned S4-13; S4-10's
  refutation showed the *proposed detector* would miss 6 of 17 failures it targets).
- **Ask the skeptics to gate the fix, not just the finding.** Every one of the 13
  suggested fixes was wrong, incomplete or optimistic, and in three cases
  (S4-2, S4-12, S4-13) the proposed change would have made things worse. The
  `fix_comment` field earned its place.
- **Reproduce the *configuration*, not just the trace.** Two attempts to re-measure
  S4-1's band inflation landed on cases where the cutoff happened to be constant,
  because the engine's own default `tau_max = 30.0` is not the GUI's "Auto".
