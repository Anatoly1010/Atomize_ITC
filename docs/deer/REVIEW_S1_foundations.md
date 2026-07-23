# DEER review S1 — Foundations: kernel, background, zero-time

Session 1 of [REVIEW_PLAN.md](REVIEW_PLAN.md). Run `wf_c5eab96a-a1b` — 19 agents,
1.01 M tokens, ~78 min. Every bug/risk verified by **2 independent adversarial
skeptics** (default stance REFUTED).

**Verdicts: 4 confirmed, 1 plausible, 2 refuted, 6 notes.**

> **ALL FIXED 2026-07-23**, including the plausible one — the skeptics' split on it
> was settled against both their positions on real Bruker data (see
> [ROADMAP.md](ROADMAP.md) § *The skeptics split on the asymmetric window*).
> Regression after fixes: kernel vs DeerLab unchanged, background vs `bg_hom3d`
> 4e-11, synthetic recovery 3.0/4.0/5.0 nm → 3.00/4.02/4.96 nm, all four engines
> end-to-end.

## Headline

**The physics core is correct. The pipeline around it is not.**

The blind-derivation panel cleared exactly what S1 existed to check — so the
nightmare case (a wrong kernel silently biasing all three engines identically) is
ruled out. But four defects sit in the *handling* around that correct kernel:
negative-time samples, zero-time fitting, and a background λ that can go negative.
Three of them are invisible to the existing benchmark suite because **the harness
crops `t >= 0` before calling the engine** and the GUI does not.

---

## The blind-derivation panel

Three agents derived the foundations from first principles with **no sight of the
code, the repo, or DeerLab's source** — verified after the fact: zero repo-touching
tool calls from any of the three. They were pushed specifically on the angular-vs-
ordinary frequency distinction, since a stray 2π is the error this design exists to catch.

| Quantity | Deriver 1 | Deriver 2 | Deriver 3 | Code | Verdict |
|---|---|---|---|---|---|
| ν_dd (MHz·nm³) | 52.041016 | 52.04101582 | 52.041016 | 52.04 | **agree** |
| powder average uniform in | cos θ | cos θ | cos θ | cos θ | **agree** |

**Unanimous to 8 significant figures, and unanimous on the powder measure.** The
code's `NU_DD = 52.04` is the ordinary-frequency (cyclic) prefactor, correctly used:
the panel confirmed 52.04 MHz·nm³ is the perpendicular dipolar frequency at 1 nm
(19.2 ns period), and that the code applies the 2π before multiplying `t`. The
`(1−3cos²θ)` integral is done uniformly in cos θ, not θ — the classic silent error
is **not** present.

Panel agreement this tight is itself the result: it means the reference is solid, so
the small residual differences below are genuinely notes rather than open questions.

### Confirmed correct — do not re-derive in later sessions

- `NU_DD` value, units and 2π convention; consumed consistently downstream.
- Powder average measure (uniform in cos θ) and the `(1−3cos²θ)` angular factor.
- The 3D background form `B(t) = exp(−k·t)` and the fractal exponent entering as
  `d/3` (not `d`); `d=3` reduces correctly.
- `dipolar_kernel` vs DeerLab's `dipolarkernel`, and `background_general` vs
  `bg_hom3d`, compared element-wise.

---

## CONFIRMED (4)

### S1-1. Pre-zero-time samples are fed to the kernel as |t| dipolar evolution

`atomize/math_modules/deer.py:507` — **CONFIRMED** · bug · found by code-review

**Defect.** Neither `deer_invert` nor `background_fit`/`background_general`/`_no_background` restricts the trace to t >= 0 after the zero-time shift. `dipolar_kernel` (deer.py:89) uses `a = |w*t|`, so every sample recorded BEFORE the zero time is modelled as ordinary dipolar evolution at +|t|. But the data there is the echo rising edge (V falls to ~0.6 of the echo top 130 ns before t0 on the real Bruker YopO traces in ~/deer_benchmark), which the model B(t)[(1-lam)+lam*K.P] cannot reproduce except by piling NNLS mass at short r to manufacture a fast decay.

The GUI hits this by default: `deer_analysis.py:1832` does `t_us = (x - t0_disp) * tf` and passes the FULL trace; the Source tab's Trim start/end spinboxes default to 0 and are explicitly reset to 0 on every new trace (deer_analysis.py:1365). Meanwhile 'Fit' zero-time is ON by default (deer_analysis.py:605), so t0 is moved into the trace and the leading samples become negative-time.

This was never caught because the validation harness crops: ~/deer_benchmark/benchmark.py:46 does `m = t >= 0.0; t, V = t[m], V[m]` before calling deer_invert. The 0.978 DeerLab overlap therefore validates a path the GUI does not take. DeerAnalysis and DeerLab workflows both cut everything before zero time.

Measured, using an echo rise matched to the real labA data (V = 0.59 of the top at -128 ns), sigma = 0, 8 ns step, 4 us trace, true sigma_r = 0.3 nm, lam = 0.35:
  true r0 = 3.0 nm: 0 pre-t0 pts -> <r> 3.00 | 17 pts -> 2.65 | 38 pts -> 2.74
  true r0 = 4.0 nm: 0 -> 4.00 | 17 -> 3.45 | 38 -> 2.85
  true r0 = 5.0 nm: 0 -> 4.90 | 17 -> 4.20 | 38 -> 2.76 (P peak collapses 5.00 -> 2.74 nm)
17 and 38 are the actual pre-t0 sample counts of sample1_labA.DTA and sample1_labD.DTA. With a steeper rise (35 ns Gaussian) 10 pre-t0 samples (80 ns) already move the P(r) peak from 4.49 nm to 1.76 nm.

Short-distance traces are nearly immune (real labA, true ~2.35 nm, is unchanged) because short-r mass is present anyway — which is why the effect went unnoticed on the ring-test data. It is the long-distance regime, where DEER is actually hard, that breaks.

**Scenario.** Load a standard Bruker 4-pulse DEER trace of a ~5 nm distance into the DEER tool, leave Trim at its default 0 and 'Fit' zero-time checked, run the Tikhonov engine -> the reported P(r) peak is ~2.7 nm instead of ~5.0 nm (17-38 leading samples are pre-t0). No warning is issued.

**Suggested fix.** In `deer_invert` (and `deer_invert_joint`/`_mellin`/`_gauss`, i.e. once at the entry point), mask `t >= 0` after the zero-time shift before building the kernel and fitting the background — matching what ~/deer_benchmark/benchmark.py:46 already does. Alternatively have the GUI auto-set `trim_start` to the number of pre-t0 samples once t0 is fitted. Either way, warn when non-empty pre-t0 data is discarded so the user sees it.

<details><summary>Skeptic 1</summary>

CONFIRMED — I reproduced the whole chain independently.

1) Code path, verified by reading: `deer_invert` (deer.py:495-530) does `t = np.asarray(t, float)` and goes straight to `dipolar_kernel(t, r)` (deer.py:507) with no `t >= 0` mask; `background_fit`/`background_general`/`_no_background`/`joint_background` only mask `t >= bg_start` (deer.py:143, 181, 243, 781) — nothing drops pre-t0 samples. `dipolar_kernel` uses `a = np.abs(w*t)` (deer.py:90), so a sample at t = -0.128 us is modelled identically to +0.128 us. Only the Mellin transform is incidentally protected (`pos = t > 0`, deer.py:698 and 889) — the finding's suggested fix list is slightly over-broad there.

2) Reachability through the GUI, verified by running the real code on real Bruker data (/home/anatoly/deer_benchmark/1_YopO_S585R1_Q603R1/sample1_labA.DSC, raw XMIN=0, XWID=2832 ns): `deer.fit_zero_time` returns t0 = 0.13008 us -> **17 samples land at negative t** and are passed to `deer_invert`. deer_analysis.py:1828 passes the full `t_us = (x - t0_disp)*tf`; trim_start is reset to 0 per trace (deer_analysis.py:1365, `_trim_slice` 1418-1424) and `deer_fit_t0` is checked by default (deer_analysis.py:605). No warning anywhere. The reference harness does crop (~/deer_benchmark/benchmark.py:46 `m = t >= 0.0`), so the 0.978 DeerLab agreement indeed validates a different path. Real pre-t0 counts across the ring test: A 16, B 15, C 18, D 37, E 26, F 15, G 21, with V(t_first)/V(0) = 0.58-0.77 — the echo rising edge is genuinely there.

3) Harm, reproduced on synthetic data using the MEASURED labA rising-edge envelope (8 ns step, 4 us, lam 0.35, k 0.05, sigma_r 0.3, noise 0), Tikhonov/GCV `engine='sequential'`, r grid 1.5-8 nm, mean distance <r>:
   r0 = 3.0: 0 pre -> 3.01 | 17 -> 2.62 | 38 -> 2.61
   r0 = 4.0: 0 pre -> 3.99 | 17 -> 3.28 | 38 -> 3.04
   r0 = 5.0: 0 pre -> 5.34 | 17 -> 4.63 | 38 -> 4.28
   With a Gaussian rise instead: r0 = 4.0, 17 pre pts -> <r> 3.53 (vs 3.99). So a 0.7-1.0 nm long-distance bias from 17 real pre-t0 samples.

4) Mechanism isolated (this is the part that rules out "wrong-convention" false alarm): feeding 38 pre-t0 samples whose values are the MODEL extended to negative t (no echo rise) gives peak/mean (3.98, 3.98) — bit-for-bit the same as the cropped fit (3.98, 3.99). The |t| symmetry of the kernel is therefore self-consistent and not itself wrong; the damage comes specifically from the rising-edge data, which the model cannot fit except by piling NNLS mass at short r — exactly as claimed.

One overstatement: I do NOT reproduce the headline "P peak collapses 5.00 -> 2.74 nm". In my runs the argmax stays near truth (5.0 -> 5.03/5.06; 4.0 -> 4.05/4.02) and it is the mean / short-r mass that moves. Also confirmed by direct run: real labA (short distance) is unaffected (full 2.35/2.54 vs cropped 2.35/2.54), as the finding itself concedes. Severity stays "bug": a silent 0.5-1 nm mean-distance bias on the default GUI path for a routine Bruker trace is a real correctness defect, but the reported peak number should be corrected before it is quoted.

</details>

<details><summary>Skeptic 2</summary>

MECHANISM CONFIRMED, HEADLINE SEVERITY REFUTED.

Code facts verified: `deer.py:89 dipolar_kernel` uses `a = np.abs(w*t)`; neither `deer_invert` (deer.py:485-530), `deer_invert_joint`, `background_fit` nor `_no_background` masks `t >= 0`. GUI `deer_analysis.py:1828` (and 1907, 1992) does `t_us = (x - t0_disp)*tf` and passes the full trace; `deer_fit_t0` is checked by default (line 605); trim spinboxes are reset to 0 on every new trace (line 1365). `~/deer_benchmark/benchmark.py:46` does crop (`m = t >= 0.0`). All as stated.

Pre-t0 samples are real and reachable: I loaded all 27 YopO ring-test Bruker files through `bruker_opener` + `deer.fit_zero_time`. Every trace has pre-t0 points — sample1_labA npre=17 (t0=130.1 ns, V[0]/Vtop=0.591), sample1_labD npre=38 (t0=149.0 ns, 0.670) — exactly the counts and droop the finding quotes.

BUT the claimed harm does not reproduce on real data. Running `deer_invert(engine='sequential', method='gcv', r=1.5..8 nm)` FULL vs `t>=0`-CROP on the real traces:
  sample1_labA npre=17: mean 2.59 vs 2.58, peak 2.35 vs 2.35
  sample1_labD npre=38: mean 2.75 vs 2.75, peak 2.35 vs 2.35
  sample2_labA npre=11: 3.80/3.33 vs 3.80/3.30
  sample2_labD npre=19: 3.85/3.79 vs 3.84/3.79
  sample3_labA npre= 4: 5.23/5.03 vs 5.23/5.03   <- the ~5 nm case
  sample3_labC npre=14: 5.29/8.00 vs 5.27/8.00
  sample3_labD npre=11: 5.20/8.00 vs 5.19/8.00
Max difference over all of them: 0.02 nm in <r>, 0.03 nm in peak. The scenario "load a standard Bruker ~5 nm trace, get 2.7 nm instead of 5.0" is contradicted by the ~5 nm ring-test traces themselves.

The finding's dramatic synthetic numbers only reproduce with an inflated pre-t0 SPAN. I reproduced them exactly with the finding's own setup (8 ns step, 0.59 droop at -128 ns): r0=3 -> 3.00/2.65/2.74; r0=4 -> 3.99/3.44/2.85; r0=5 -> 5.21/4.61/3.55 (peak 4.90/4.99/2.77). But "38 pre-t0 points" was taken from sample1_labD, whose step is 4 ns (XPTS 1008 / XWID 4028), i.e. a 152 ns pre-span, not the 304 ns the finding simulated. Re-running with each real file's OWN (span, droop, dt): r0=5.0, 130 ns @0.59, dt 8 -> FULL <r> 4.68 peak 4.99 vs CROP 5.21/4.90; 150 ns @0.67, dt 4 -> 4.75/4.96 vs 5.21/5.22; 290 ns @0.86, dt 12 -> 5.02/4.99 vs 5.21/5.22. Same at r0=3/4: peak never moves, <r> shifts 0.05-0.5 nm from a little spurious short-r mass. No peak collapse anywhere.

Convention check against the independent reference: DeerLab 0.14.2 `dl.dipolarkernel([-0.1,-0.05,0.05,0.1], r)` returns rows even in t (K[-t]==K[+t] to machine precision), i.e. the |t| kernel is the same convention, and DeerLab likewise does not auto-crop pre-t0 data. So the kernel itself is not wrong; only the instrumental echo-rise droop is unmodelled, which is a data-hygiene matter shared with the reference implementation.

Net: a genuine, unwarned modelling looseness that adds a small amount of spurious short-r mass and can bias <r> by up to ~0.5 nm in a worst-case synthetic, but on every real Bruker trace available it changes the answer by <=0.02 nm and never moves the P(r) peak. Not the bug as written.

</details>

### S1-2. Boxcar mode='same' zero-padding pins argmax at index w//2 when t0 is at the trace start

`atomize/math_modules/deer.py:2267` — **CONFIRMED** · risk · found by code-review

**Defect.** `Vs = np.convolve(V, np.ones(w)/w, mode='same')` (deer.py:2267) zero-pads, so the first and last w//2 smoothed samples are strongly depressed. On a trace that already begins at the zero time (monotonically decreasing V), the true argmax is index 0, but the smoothed array reads [0.5991, 0.7977, 0.9954, 0.9919, ...] against a raw [1.0000, 0.9989, 0.9966, ...] — the argmax is forced to index w//2 = 2 and a concave parabola IS found, so the routine does not return None. The vertex is then extrapolated outside the data and never clipped (deer.py:2286, in contrast to `_echo_top` at deer.py:122 which does clip).

Measured on a noiseless synthetic trace already at t0 = 0 (8 ns step): smooth_w=1 -> -8.3 ns; smooth_w=3 -> -14.1 ns; smooth_w=5 (default) -> -14.1 ns; smooth_w=9 -> -20.5 ns. `fit_zero_time` returns the same -14.1 ns.

This directly contradicts deer.py:2297-2298, which promises the routine 'falls back to method=residual when no concave echo peak is found (e.g. the trace already starts at the zero-time)'. That fallback never fires for this case.

**Scenario.** Load a pre-cropped / simulated trace that already starts at the dipolar zero time, leave 'Fit' t0 checked -> t0 = -14 ns (outside the trace), silently shifting the whole kernel; magnitude scales with smooth_w (-20 ns at w=9).

**Suggested fix.** Compute the smoothed trace with edge-preserving padding (`np.convolve(np.pad(V, w//2, mode='edge'), ...)` then slice) so the first/last samples are not artificially depressed, and clip the returned vertex to [t[lo], t[hi]] — returning None when it lands outside, so the documented residual fallback actually engages.

<details><summary>Skeptic 1</summary>

CONFIRMED — I reproduced the whole chain independently with DeerLab-generated ground-truth traces (kernel `dl.dipolarkernel`, background `dl.bg_hom3d`, lam=0.35, k=0.15, Gaussian P(r)), truncated to start exactly at t0=0.

1. Mechanism (deer.py:2266-2267). `Vs = np.convolve(V, np.ones(w)/w, mode='same')` zero-pads. On a trace starting at t0, raw V[:6] = [1.0000, 0.9985, 0.9939, 0.9865, 0.9763, 0.9636]; smoothed w=5 = [0.5985, 0.7958, 0.9910, 0.9837, 0.9738, 0.9614]. `i0 = argmax(Vs[:ns])` is therefore 2 (= w//2) instead of 0; w=3 -> i0=1, w=9 -> i0=4. Exactly as claimed.

2. No fallback. `a < 0` (concave) always holds on the resulting one-sided window, so `_parabolic_zero_time` returns a value, and `fit_zero_time` (deer.py:2344-2347, method='parabola' default, xcheck default False) returns it verbatim without ever reaching the residual path. This directly contradicts the docstring at deer.py:2297-2298 ("falls back to method=residual ... e.g. the trace already starts at the zero-time"). Confirmed: `fit_zero_time(t, V, bg_start=1.5, r=r, dim=3.0)` returned -6.16 ns on a trace whose true t0 is 0.

3. Vertex outside the data, unclipped (deer.py:2286). Instrumented run shows fit window [t_lo, t_hi] = [0, 72] ns and vertex -6.2 ns — i.e. extrapolated before t[lo]=0. `_echo_top` at deer.py:122 does `np.clip(..., tt[0], tt[-1])`; this routine does not.

4. Magnitudes (default smooth_w=5), true t0 = 0:
   - 8 ns step: -6.2 ns (w=1 -3.5..-2.7, w=9 -12.8)
   - 16 ns step: -8.5 ns (w=9 -54.9)
   - 32 ns step: -135.4 ns (w=3 -45.8)
   - 4 ns step / short trace: -3.5 ns
   My exact numbers differ from the finding's (-8.3/-14.1/-20.5) because the synthetic trace differs, but sign, order of magnitude and the monotone growth with smooth_w and with dt all reproduce.

5. Downstream impact is real but modest at fine sampling: re-running `deer_invert` at the bogus t0 vs t0=0 (8 ns step) moved the P(r) peak 2.947 -> 3.015 nm and gave 0.936 overlap with the correct-t0 result; at 32 ns step / -30.6 ns the peak was unchanged (3.519 both) but overlap fell to 0.832. lambda essentially unaffected. So it is a shape/accuracy degradation, not a catastrophic failure — consistent with the filed [risk] severity, not [bug].

6. Reachability confirmed: `self.deer_fit_t0.setChecked(True)` (deer_analysis.py:605) — Fit is ON by default, and compute() calls fit_zero_time with method left at the 'parabola' default (deer_analysis.py:1822/1902/1987). Requires a pre-cropped/simulated trace that begins at the dipolar zero time; ordinary acquisitions include pre-t0 points, so this is an edge case rather than the common path.

One correction to the suggested fix: edge-padding ALONE does not restore correctness. With `np.pad(V, w//2, mode='edge')` the argmax returns to 0 as claimed, but the vertex is still extrapolated negative (-2.7 ns at 8 ns step, -4.0 ns at 16 ns) because the fit window is inherently one-sided; only at 32 ns did the padded version return None. The load-bearing part of the fix is the clip / return-None-when-vertex-outside-[t[lo], t[hi]], which is what actually makes the documented residual fallback engage.

</details>

<details><summary>Skeptic 2</summary>

CONFIRMED — I reproduced the full evidence chain independently and the failure is worse than the finding states.

Mechanism (deer.py:2267): `Vs = np.convolve(V, np.ones(w)/w, mode='same')` zero-pads. On a DeerLab-generated noiseless trace (8 ns step, lam=0.3, r=3.0/0.3 nm, hom3d bg) already starting at t0=0, raw V head = [1.0000, 0.9986, 0.9944, 0.9876, ...] but smoothed w=5 head = [0.5986, 0.7961, 0.9918, 0.9851, ...] — argmax is pinned at index w//2 = 2 exactly as claimed (w=3 -> idx 1, w=5 -> idx 2, w=9 -> idx 4). A concave parabola IS found (a<0), so `_parabolic_zero_time` does NOT return None, and the vertex is returned unclipped at deer.py:2286.

My reproduced numbers (synthetic details differ slightly from the finding's, same structure/sign/magnitude):
- 8 ns step:  w=1 -> -3.4 ns, w=3 -> -7.7, w=5 (default) -> -7.7, w=9 -> -21.9
- 16 ns step: w=1 -> -5.0, w=3 -> -10.5, w=5 -> -19.8, w=9 -> -71.6
- 32 ns step: w=5 -> -177.2 ns
`fit_zero_time(t,V)` returns -7.68 ns (the parabola early-return path at deer.py:2346-2348, xcheck default False), so the documented residual fallback (deer.py:2297-2298: "falls back to method=residual ... e.g. the trace already starts at the zero-time") never fires. Confirmed.

Real-data check is decisive: 20 YopO .DTA traces (~/deer_benchmark), each cropped at its own argmax so the trace begins at t0. `_parabolic_zero_time` returned a vertex BELOW t[0] on 19/20, including -0.266, -0.905, -1.207 us (sample3_labG, 32 ns step). These are catastrophic, not few-ns.

Downstream consumption is unguarded: deer_analysis.py:1822 -> `t0_disp = t0u/tf`; :1830 `t_us = (x - t0_disp)*tf` and the bg window shift at :1831-1832. No clip anywhere, in contrast to `_echo_top` (deer.py:122) which does `np.clip(..., tt[0], tt[-1])`. So the whole kernel is silently misaligned by the bogus t0 — the same docstring (deer.py:2323-2325) states "an error of even a few tens of ns misaligns the kernel, broadens P(r) and biases the mean distance long".

I verified the suggested fix isolates the cause: replacing the smoothing with `np.convolve(np.pad(V, w//2, mode='edge'), ones(w)/w, mode='valid')` plus clipping the vertex to [t[lo], t[hi]] (returning None outside) gives out-of-range 0/20 on the same real traces and None on every synthetic case — i.e. the documented residual fallback then actually engages.

Not a convention artifact: the sign/consumption were traced and there is no compensating clip. Not already handled: the fallback is documented for exactly this case and provably does not run. Reachable via the ordinary GUI path (pre-cropped or simulated trace + 'Fit' t0 checked, default method='parabola', default smooth_w=5).

Severity raised from risk to bug: it is not a corner case (19/20 real traces once cropped at t0) and the error reaches -1.2 us, far beyond the "few tens of ns" the code itself calls damaging.

</details>

### S1-3. Echo max beyond the 30% search cap returns a silently wrong t0

`atomize/math_modules/deer.py:2268` — **CONFIRMED** · note · found by code-review

**Defect.** `ns = max(5, int(search_frac*n))` with `search_frac` forced to >= 0.30 by `fit_zero_time` (deer.py:2345) restricts the initial peak search to the first 30 % of the trace. If the echo maximum lies beyond that point, `i0` lands on the last sample of the search window while the trace is still rising; the threshold walk then produces a window on the rising flank and the parabola vertex is extrapolated far past it. Nothing detects that `i0` is at the search boundary, so no None is returned and no fallback fires.

Measured: synthetic trace t in [-0.20, +0.59] us (short 0.8 us trace with 200 ns of pre-zero data), true t0 = +0.100 us, which sits at 38 % of the span; the 30 % cap ends at t = +0.038. `_parabolic_zero_time` returns +0.2844 us — a +184 ns error, ~2.5x larger than any noise-driven error the docstring discusses.

**Scenario.** A short trace (< ~1 us total) with a normal 100-300 ns pre-zero segment, or any trace where the operator recorded a long pre-t0 baseline: t0 is returned ~180 ns late with no indication of failure, and the subsequent P(r) is meaningless.

**Suggested fix.** Return None (falling through to the residual search) when `i0 >= ns-1`, i.e. when the search window boundary is the maximum; and/or scale `search_frac` from the trace length rather than fixing it at 0.30.

<details><summary>Skeptic 1</summary>

MECHANISM CONFIRMED, MAGNITUDE PARTLY CONFIRMED, REACHABILITY WEAK -> downgrade to note.

1) Code path (deer.py:2268-2276): `ns = max(5,int(search_frac*n))`, `i0 = argmax(Vs[:ns])`, but the threshold walk `hi` is NOT capped by ns. So the window can self-widen past the true peak. There is indeed no `i0 >= ns-1` boundary check, and fit_zero_time:2344-2347 returns the parabola result directly when xcheck is off (default), so nothing detects it.

2) The finding's own model does NOT fail. Using deer.simulate (which is even about t0 — exactly the "V near the echo is even" assumption the docstring states), t in [-0.20,+0.59], true t0=+0.100 (38% of span), n=80..400, sigma 0..0.005: i0 lands exactly on the boundary (i0=47, ns=48, true argmax=60) yet `_parabolic_zero_time` returns 0.0999-0.1002 — error -0.5..+0.2 ns, not +184 ns. The self-widening `hi` walk brackets the true peak, which is the compensating mechanism the finding missed. Pre-zero fractions up to 45% still give <1 ns error on an even trace.

3) The failure IS real for a NON-even trace (real echo rise before t0, dipolar decay after: V = env(t-t0) for t<t0, dipolar for t>t0, sigma 0.005). There the walk runs to the trace end and the vertex is dragged late:
   t=[-0.20,0.59] (38%, echo width 40 ns): +114.9 ns  (finding claims +184)
   t=[-0.25,0.59] (42%): +147.4 ns
   t=[-0.30,0.59] (45%, ew 60 ns): +185.0 ns -> t0 = 0.28498, essentially the finding's quoted 0.2844
   Symmetric model with t0 at 51-69% of span: -561 ns and -9248 ns (worse, different sub-case).
   So the quoted number is reproducible, but at ~45% pre-zero, not the 38% stated.

4) The cap is causal: re-running the same failing traces with search_frac=1.0 drops the error from +92..+208 ns to +12..+26 ns (residual is the non-even-model bias, not the cap). So the suggested fix direction is sound.

5) Reachability is poor. All 27 real DEER traces in ~/deer_benchmark (YopO ring test, loaded via DeerLab deerload) have the echo maximum at 0.3%-11.7% of the span (worst: sample1_labG, 11.7% of a 1.43 us trace). `_parabolic_zero_time` with cap 0.30 and with cap 1.00 returns bit-identical t0 on every one of them. Triggering needs >30% of the record before t0 — ~3x more pre-zero than the worst real trace, i.e. an operator deliberately recording a long pre-t0 baseline on a sub-1 us trace. The GUI also displays the fitted t0 with a manual override ('Fit' checkbox + 'Max' button), so it is visible/correctable.

Net: genuine unguarded boundary condition with a silent 100-200 ns error, but only on traces far outside anything this lab's own data produces, and the finding's headline configuration (38%, even echo) does not reproduce the error at all.

</details>

<details><summary>Skeptic 2</summary>

CONFIRMED, severity stays "risk". Mechanism at atomize/math_modules/deer.py:2265-2268 (`ns = max(5, int(search_frac*n))`; `i0 = argmax(Vs[:ns])`) with search_frac forced >= 0.30 at deer.py:2345. When the echo max lies past 30% of the samples, i0 pins to ns-1 on the rising flank, vpk/thr are taken there, the threshold walk yields a one-sided window, and the parabola vertex extrapolates. `a < 0` still holds so no None is returned; xcheck defaults False so fit_zero_time returns the bad value directly to deer_analysis.py:1822 (Fit checkbox default-on, full loaded axis passed).

Reproduced numerically (synthetic via deer.simulate, span 0.79 us, n=200, gaussian echo rise width ew before t0):
- ew=0.03, pre-t0 frac 0.38: true t0 = 0.3002, _parabolic_zero_time = 0.4854 -> +185.2 ns error, matching the finding's +184 ns. Same trace with search_frac 0.5/0.75/1.0 -> 0.3267 (+26.5 ns); method='residual' or xcheck=True -> 0.1185. So the 30% cap is unambiguously causal.
- Clean cliff at 30%: frac 0.18-0.28 gives +23/+16/+2 ns (ew=0.03/0.06/0.12); frac >= 0.32 gives +126, +171, -207 and one -1269 ns wild extrapolation. i0>=ns-1 flags exactly the failing region.
- Failure also needs a sharp echo rise: at ew=0.12 us the window still straddles the true peak and error stays <30 ns even at 48% pre-t0.

Reachability is the weak link (why risk, not bug): all 27 real Bruker DEER traces in ~/deer_benchmark/*/ (7 labs, YopO ring test) have smoothed-argmax at 0.3%-11.7% of the trace (max sample1_labG, 1.43 us span), and _parabolic_zero_time at search_frac 0.30 vs 1.0 is bit-identical on every one. The repo's own synthetic benchmark (synth_validation.py, t0 0.10-0.12 us on 2.5-3.5 us traces) is also far from the cap. Latent robustness hole, silent when hit, one-line guard (i0 >= ns-1 -> return None) fixes it; but no real or benchmark trace comes within 3x of the trigger.

</details>

### S1-4. background_fit can return negative lambda, flipping the form factor sign

`atomize/math_modules/deer.py:199` — **CONFIRMED** · bug · found by blind-reconcile

**Defect.** This is NOT a physics-vs-panel disagreement (the panel's three quantities all check out, see coverage) but it surfaced while stress-testing the background model. `background_fit` bounds the baseline amplitude A to [0.0, 1.5] in the fit_dim=True curve_fit call (line ~190) and then sets lam = 1.0 - A (line 199), so lam can run down to -0.5. The only guard is `if abs(lam) < 1e-6: lam = 1e-6` (line 201), which catches lam==0 but NOT lam<0. F = (V/B - (1 - lam))/lam at line 203 then divides by a negative number, inverting the form factor; the subsequent Tikhonov/NNLS inversion (non-negativity constrained) fits the sign-flipped F and returns garbage. The other two background routines in the same file both clip lam to a positive range (_no_background: np.clip(..., 0.02, 1.0), line ~148; background_general: np.clip(..., 0.02, 0.98), line ~285) — background_fit is the odd one out. The extra free parameter in fit_dim=True is what makes the (A, k, d) tail fit degenerate on a short trace whose form factor has not yet reached its asymptote, letting A run to the upper bound.

**Scenario.** Realistic long-distance/short-trace input: r grid 2-8 nm, P(r) = Gaussian at 5.0 nm sigma 0.3, t = linspace(0, 1.5 us, 300), simulate(lam=0.4, k=0.05, dim=3, noise=0.003), then deer_invert(..., bg_start=0.8, fit_dim=True). Result: A = 1.31 (upper-bound-driven), lam = -0.31, recovered P(r) peaks at r = 2.0 nm (the grid edge) with r_mean = 0.88 nm. The identical call with fit_dim=False gives lam = 0.299 and peak 4.89 nm (correct). A second case (r0 = 5.5 nm, tmax = 1.2 us, bg_start = 0.6, fit_dim=True) hits A = 1.5 exactly, lam = -0.5.

**Suggested fix.** Clip lam positive the same way the sibling routines do, e.g. lam = float(np.clip(1.0 - A, 0.02, 1.0)) (or lower the A upper bound from 1.5 to ~1.0), and optionally emit a warning when the raw 1-A was <= 0 so the caller knows the tail fit was degenerate rather than silently receiving an inverted P(r).

<details><summary>Skeptic 1</summary>

CONFIRMED — I reproduced the full evidence chain independently.

Exact scenario reproduction (/tmp/sk1/repro.py, r = default_r_axis(2.0, 8.0, 200), P = Gaussian r0=5.0 sigma=0.3, t = linspace(0, 1.5, 300), simulate(lam=0.4, k=0.05, dim=3, noise=0.003)):
- fit_dim=True, bg_start=0.8: A = 1.315/1.310/1.309/1.304/1.291/1.311 across seeds 0-5, lam = -0.315 ... -0.291, k runs away to 0.72, d pinned to its lower bound 1.00; recovered P(r) peaks at r = 2.00 nm (the grid edge), r_mean 2.27.
- Identical call with fit_dim=False: A = 0.700, lam = 0.297-0.301, peak 4.86-4.89 nm (correct). The finding's quoted "lam = 0.299 and peak 4.89" is my seed-1 result exactly.
- Second case (r0 = 5.5, tmax = 1.2, bg_start = 0.6, fit_dim=True): A = 1.4999999999 (upper bound hit exactly), lam = -0.49999999996. Reproduced.

Mechanism verified at /home/anatoly/Atomize_ITC/atomize/math_modules/deer.py:190 — bounds upper A = 1.5 — and :199 lam = 1.0 - A, with the only guard at :201 being `if abs(lam) < 1e-6`, which does not catch lam < 0. The resulting F at :203 is sign-inverted: F[0] = +1.003 (F(0)=1 is sign-independent) but F[-1] = -0.162 and F.min() = -1.024, i.e. the modulation is flipped. The NNLS/Tikhonov inversion then returns R^2 = -0.66 on F.

Siblings confirmed to clamp, so background_fit is genuinely the odd one out: `_no_background` :148 `np.clip(..., 0.02, 1.0)`; `background_general` :281 `np.clip(..., 0.02, 0.98)`; and `joint_background`'s `lam_of` at :804 `min(max(1.0 - ..., 0.02), 0.95)`.

Independent reference: DeerLab 0.14.2 `dl.dipolarmodel(...)` parameter table bounds `mod` (modulation depth) to [0, 1] by construction. A negative modulation depth is non-physical in the peer-reviewed reference implementation of the same model.

Reachability is BROADER than the finding claims, not narrower. `fit_dim` is a user checkbox (`self.deer_fitdim`, atomize/control_center/deer_analysis.py:659, read at :1811/:1884/:1965), so the path is one click away. And fit_dim=False is not immune: over 30 randomized long-distance/short-trace traces (r0 in 4.5-7.0 nm, tmax 1.0-2.0 us, bg_start 0.4-0.8*tmax, lam=0.4, k=0.05, noise=0.003), `background_fit(..., fit_dim=False)` returned lam < 0 in 16/30 cases — the [0.0, 1.5] A bound at :196 has the same hole. The negative lam is also propagated verbatim into the GUI status line, the V-overlay reconstruction (deer_analysis.py:2559/2570) and the CSV export (:2893, :2930) with no warning.

Two caveats that qualify but do not refute:
1. The finding's "r_mean = 0.88 nm" is impossible on a 2-8 nm grid and I could not reproduce it (I get 2.27). The substantive claim — peak pinned to the grid edge vs. 4.89 nm correct — reproduces exactly.
2. The suggested fix is insufficient: applying `lam = np.clip(1.0 - A, 0.02, 1.0)` to the same data gives lam = 0.02 and a P(r) peaked at 8.0 nm, i.e. the other grid edge — still garbage, because the real disease is the runaway background (k = 0.73, d -> 1). Lowering the A bound to ~1.0 plus an explicit degeneracy warning is the meaningful part of the fix; the clip alone only converts an inverted result into a differently-wrong one.

The defect as stated — background_fit is the only background routine that can return a negative modulation depth, and it silently emits a sign-inverted form factor when it does — is real, unguarded, and reachable.

</details>

<details><summary>Skeptic 2</summary>

CONFIRMED — reproduced independently, deterministically across 10 seeds.

Code (verified by reading /home/anatoly/Atomize_ITC/atomize/math_modules/deer.py):
- L189-191 fit_dim=True: `curve_fit(_bg_model, ..., bounds=([0.0,0.0,1.0],[1.5,np.inf,6.0]))` — A upper bound 1.5.
- L199 `lam = 1.0 - A`; L201-202 `if abs(lam) < 1e-6: lam = 1e-6` — magnitude guard only, no sign guard.
- L203 `F = (V/B - (1 - lam))/lam` — divides by a negative lam.
- Siblings do clip: `_no_background` L148 `np.clip(1.0-mean, 0.02, 1.0)`; `background_general` L281 `np.clip(1.0-g0, 0.02, 0.98)`. background_fit is indeed the odd one out.

Reproduction (scratch scripts in /tmp/skep2, repo untouched), r grid 2-8 nm, Gaussian P, deer.simulate(lam=0.4,k=0.05,dim=3,noise=0.003):
- Case 1 (r0=5.0, t=0..1.5 us, 300 pts, bg_start=0.8), background_fit(fit_dim=True): A=1.2907..1.3179, lam=-0.2907..-0.3179 for ALL seeds 0-9 (seed 0: A=1.3154, lam=-0.3154, k=0.732, d=1.000 — d pinned at its lower bound 1.0, the degeneracy the finding describes). Same data with fit_dim=False: A=0.700, lam=0.297-0.301, d=3 for all seeds.
- Case 2 (r0=5.5, t=0..1.2 us, bg_start=0.6), fit_dim=True: A=1.5000 exactly (upper bound), lam=-0.5000 for all 10 seeds. Both numbers in the finding match exactly.

Downstream damage confirmed via the full public entry point deer_invert (150-pt r grid, seed 0, bg_start=0.8):
  fit_dim=True  -> lam=-0.315, F spans -1.02..1.00, alpha driven to the grid ceiling 1e3, P(r) peak = 2.00 nm (grid edge), r_mean 2.32 nm
  fit_dim=False -> lam=+0.297, F spans -0.09..1.05, alpha=2.51, P(r) peak = 4.86 nm, r_mean 5.41 nm (correct)
So the NNLS/Tikhonov inversion silently returns a garbage, edge-pinned distribution.

Reachability: `fit_dim` is a user checkbox, not an internal flag — atomize/control_center/deer_analysis.py:1811 `fit_dim = self.deer_fitdim.isChecked()`, passed into deer_invert at :1825/:1834/:1840 and into the mellin/gauss engines at :1917/:1922/:2004/:2009. Grep of deer_analysis.py finds no clip/sign/warning check on the returned lambda anywhere, so nothing downstream catches it — the user just sees a plausible-looking P(r) at the wrong distance. Long-distance/short-trace data is exactly the regime DEER users work in, so this is not a contrived input.

Not a convention artifact: the sign of lam is consumed as a divisor in the same formula the two sibling routines use, and those two clip it positive — the inconsistency is internal to this file, not against an external textbook.

Severity stays `bug`: silent wrong scientific result, no exception, no warning, reachable from a GUI checkbox.

</details>

---

## PLAUSIBLE (1)

One skeptic upheld, one refuted — read both before acting.

### S1-5. _parabolic_zero_time fit window is asymmetric -> systematic late t0 bias

`atomize/math_modules/deer.py:2272` — **PLAUSIBLE** · bug · found by code-review

**Defect.** The docstring (deer.py:2255-2259) states the fit window 'WIDENS symmetrically out to where the smoothed signal has fallen `drop` of its peak-to-min amplitude'. The implementation does not: lines 2272-2277 walk left and right INDEPENDENTLY to the same threshold, and lines 2278-2279 only enforce a minimum half-width of 3, never symmetry. Because `amp = vpk - min(Vs)` is the peak-to-far-tail range of the whole trace (line 2270), the threshold `thr = vpk - 0.15*amp` sits only ~10-15 % below the echo top, and the two sides of a DEER trace fall at very different rates: the pre-t0 side is the steep echo rising edge, the post-t0 side is the slow dipolar+background decay. The window therefore extends far further to the right, and the least-squares parabola vertex is dragged LATE.

Instrumented on a synthetic trace (r0=3.5 nm, lam=0.35, k=0.08/us, 8 ns step, NOISELESS): window = [+0.080, +0.240] us around a peak at +0.112 — left half-width 32 ns, right half-width 128 ns (4x). Returned t0 = +0.1380 vs true +0.1000, i.e. +38.0 ns at ZERO noise. The docstring claims '~1 ns at low noise' (deer.py:2305).

Bias vs distance and modulation depth (all noiseless):
  r0=2.5: lam 0.50/0.35/0.20 -> +9.9 / +13.8 / +20.8 ns
  r0=3.5:                     -> +32.2 / +38.0 / +43.7 ns
  r0=4.5:                     -> +57.1 / +60.8 / +48.1 ns
  r0=5.5:                     -> +67.1 / +56.7 / -1.0 ns
Control: with a genuinely symmetric echo envelope the same routine returns 0.0 ns at sigma=0 and -0.6 ns at sigma=0.03 — confirming the bias is the window asymmetry, not the parabola. Forcing the window symmetric (half-width = min(left, right)) halves it: +38.0 -> +19.8 ns at r0=3.5.

Downstream (sigma=0.003, 4 us trace, cropped to t>=t0 to isolate this effect): true r0=4.5 nm gives <r> 4.469, sd 0.265 with the true t0, but <r> 4.242, sd 0.496 with the fitted t0 (+59 ns) — a -0.23 nm (-5 %) distance bias and a 1.9x broadening, exactly the failure the docstring at deer.py:2323-2324 warns about.

Real Bruker traces are largely spared (labA/B/D show +2.1/+0.7/+1.0 ns, left and right half-widths within one sample) because their post-echo drop is steep. The failure is specific to long-distance / shallow-modulation traces, i.e. the ones where t0 accuracy matters most.

**Scenario.** Fit t0 on a 4-5 nm, lam<=0.35 DEER trace (the regime the tool exists for): t0 comes back 40-70 ns late even with zero noise, which biases the recovered mean distance ~5 % short and broadens P(r) ~2x.

**Suggested fix.** Make the window actually symmetric, as documented: after the two threshold walks, take `half = max(3, min(i0-lo, hi-i0))` and set `lo, hi = i0-half, i0+half`. Optionally also base `amp` on a local peak-to-local-min rather than the global minimum so the threshold tracks the echo top rather than the full trace decay.

<details><summary>Skeptic 1</summary>

CONFIRMED. I reproduced the whole chain independently with DeerLab-generated ground truth (dl.dipolarkernel + dl.bg_hom3d), never reusing the reviewer's script.

1) Code/doc mismatch is real. deer.py:2270-2279: `amp = vpk - min(Vs)` is the global peak-to-tail range; `thr = vpk - 0.15*amp`; then two INDEPENDENT while-walks (2271-2277) and only a min-half-width clamp (2278-2279). Nothing enforces the "WIDENS symmetrically" of the docstring (2255-2259).

2) Asymmetric window + late bias at ZERO noise, my own synthetic (Gaussian P(r) sd=0.3, k=0.08/us, 8 ns step, Gaussian echo rise before t0, true t0=+0.100 us):
   r0=3.5, lam=0.35, rise=60 ns -> peak at +0.112, window [+0.064,+0.192], left half-width 48 ns vs right 80 ns; returned t0 = +0.1204 = +20.4 ns error at sigma=0.
   Bias vs distance (rise 60 ns, noiseless): r0=2.5/3.5/4.5/5.5 -> +3.1 / +20.4 / +49.6 / +104.6 ns. Same ordering at rise=30 and 100 ns (+6.9/+26.7/+55.0/+84.5 and +1.4/+14.0/+46.0/+99.3). This directly refutes the docstring's "~1 ns at low noise" (deer.py:2305).

3) The suggested fix is causally the right one. Applying `half = max(3, min(i0-lo, hi-i0))` to the SAME data: +26.7->+17.9, +55.0->+29.4, +84.5->+31.2 ns (rise 30); +49.6->+24.8, +104.6->+38.7 (rise 60). Roughly halves it, matching the reviewer's "+38 -> +19.8" claim. Note the raw smoothed argmax alone (4-20 ns) beats the parabola vertex, so the asymmetric window actively degrades the estimate.

4) Downstream reproduced (sigma=0.003, 4 us trace, cropped to t>=t0, engine='joint', deer_invert + distribution_moments):
   r0=4.5: true t0 -> <r>=4.529, width 0.189 ; fitted t0 (+58.2 ns) -> <r>=4.404, width 0.351. That is -0.125 nm (-2.8%) and a 1.86x broadening — the 1.9x broadening claim matches exactly; the distance bias is about half the claimed -5%.
   r0=3.5: 3.550/0.210 -> 3.475/0.256 (+20.3 ns t0).

5) Reachable on the default path. fit_zero_time defaults method='parabola', xcheck=False, and deer.py:2346-2348 returns t0_para unconditionally with no bound. deer_analysis.py:1822/1902/1987 call it without xcheck (grep for "xcheck" in deer_analysis.py: no hits), so the residual cross-check never fires in the GUI.

6) Real data confirms the mechanism is reachable, and is worse than described in one respect. On the YopO ring-test Brukers (phase-corrected, dl.deerload): sample1 (deep modulation) is spared, L/R within one sample, errors +0.0..-5.8 ns — matching the reviewer. But the sample3 family (shallow modulation) has grossly asymmetric windows: labA L=80/R=280, labE L=120/R=360, labG L=96/R=352, labB L=16/R=352, with errors vs the smoothed peak of -21.3, -12.5, -2.6 and -917.7 ns (labB returns t0 = -885.7 ns, a concave fit over a monotonic decay that silently passes the a<0 check and is never bounded).

Two corrections to the finding's framing, neither of which rescues the code: (a) the bias direction is not universally LATE — on real shallow-modulation traces the same asymmetry drives it EARLY, so the defect is "large uncontrolled t0 error from an asymmetric window", not specifically a late bias; (b) my magnitudes are smaller than the reviewer's (+20 vs +38 ns at r0=3.5; -2.8% vs -5% distance) and depend on the assumed echo-rise width. The docstring's existing caveat about a late bias and a compensating Mellin bias is about NOISE-driven bias and explicitly promises ~1 ns at low noise, so it does not cover this; not already handled.

</details>

<details><summary>Skeptic 2</summary>

REFUTED as stated: the evidence chain does not reproduce on either real data or this codebase's own forward model; I could only reproduce it by multiplying the trace with a fabricated one-sided echo rising edge that neither exists in the code nor in any real trace.

1) Code fact confirmed. deer.py:2271-2279 does walk left/right independently and only enforces a minimum half-width of 3, contrary to the "WIDENS symmetrically" docstring (deer.py:2255-2259). That much is true.

2) The claimed bias table is NOT reproducible with this codebase's forward model. `deer.simulate` (deer.py:2512-2528) is even in t (`np.abs(t)` in the background, and `dipolar_kernel` is even), so a DEER trace generated the way every existing benchmark generates it (`deer.simulate(T-t0, ...)`, see ~/deer_benchmark/synth/diag_grid.py:68, diag_taumax_select.py:47) is symmetric about t0. Rerunning the finding's exact grid (t0=0.100 us, 8 ns step, k=0.08/us, sigma=0, r axis 1.5-8 nm) gives t0 errors (ns), lam 0.50/0.35/0.20:
   r0=2.5: +0.0/-0.0/-0.0   r0=3.5: +0.2/+0.6/+1.1   r0=4.5: -0.7/-2.4/-9.1   r0=5.5: -18.3/-30.9/-64.2
The headline claim "r0=3.5, lam=0.35 -> +38.0 ns" comes back as +0.6 ns, and every nonzero error I do find is EARLY (negative), i.e. the opposite sign of the finding. The window at r0=3.5/lam=0.35 is L=11, R=15 samples, not 4 vs 16.

3) I located exactly how the finding's number was manufactured. Multiplying the same trace by an artificial one-sided rising edge 0.5*(1+erf((t-0.05)/w)) reproduces their reported peak (+0.112 us) and t0 for w≈30 ns: w=10 ns -> +1.6 ns, w=20 ns -> +33.3 ns, w=30 ns -> +39.2 ns (their +38.0), w=50 ns -> +56.6 ns. That construction is not the codebase's model, and it genuinely moves the trace maximum to +112 ns, so ANY peak-based estimator (including DeerLab's reftime, which is also fitted to a signal even in t-t0) would report "late" there — the trace is pathological, not the fit window.

4) Not reachable on real data (21 traces checked, far more than the 3 the finding cites). Raw Bruker .DTA with plenty of pre-t0 data: 7 YopO ring-test traces plus 14 lab traces in ~/deer_benchmark/deer_data/myr_*. Peak/window half-widths: labA 4/5, labB 5/5, labC 4/3, labD 9/9; myr traces 14/12, 13/15, 8/8, 7/8, 12/12, 20/20, 9/8, 19/20, 9/8, 9/8, 8/8, 12/12, 8/7, 9/8 — i.e. symmetric within 1-2 samples in every case, and the returned t0 is within a few ns of the sampled peak. Direct inspection of the echo top (labA, labD) shows the real trace is symmetric about the maximum, if anything slightly steeper on the RIGHT. Even artificially truncating a real trace to start only 2-10 samples before the peak changes t0 by at most -0.9 ns.

5) What IS real (hence a note, not a bug): the asymmetric window does bite, but with the opposite sign and a different trigger — the trace must both start <~15 samples before t0 AND have a very flat top (r0>=5 nm with shallow lam), so the left walk truncates at the array start while the right runs 58 samples. Contributing artifact: `np.convolve(..., mode='same')` zero-pads, depressing Vs[0:2] (raw V[:4]=[0.989,0.990,0.991,0.992] vs Vs[:4]=[0.594,0.792,0.991,0.992]), which terminates the left walk one or two samples early. Giving the same trace more pre-t0 data removes it entirely: t0=0.10 -> -64.2 ns, t0=0.30 -> +5.1 ns, t0=0.50 -> +0.0 ns. The finding's suggested symmetric-window fix does fix this variant (r0=5.5: -18.3/-30.9/-64.2 -> -0.4/-0.5/-0.6 ns; all other cases stay under 0.5 ns), so the fix is worth taking — but as a docstring/robustness cleanup for long-r flat-top traces that begin at t0, not as the "+40-70 ns late, -5% distance bias" defect described. The downstream distance-bias number rests entirely on the fabricated erf-rise trace and does not survive.

</details>

---

## REFUTED (2)

Recorded so a later session does not re-derive them.

### fit_dim drives the fractal dimension to its 6.0 bound and biases lambda +15%

`atomize/math_modules/deer.py:190`

`background_fit(..., fit_dim=True)` floats d over bounds [1.0, 6.0] (deer.py:190). Values d > 3 have no physical meaning for an intermolecular background (d is the fractal dimension of the spin distribution; homogeneous 3D is d = 3), and the extra flexibility lets the stretched exponential absorb residual dipolar decay still present in the tail window, inflating the modulation depth.

Measured on a synthetic trace with a TRUE d = 3 background (k = 0.06/us, lam = 0.35, r0 = 4.0 nm, bg_start = 2.5 us of a 4 us trace):
  sigma = 0.000: fixed d=3 -> lam 0.349, k 0.0602 | fit_dim -> lam 0.397, k 0.0849, d 4.96
  sigma = 0.005: fixed d=3 -> lam 0.348, k 0.0630 | fit_dim -> lam 0.398, k 0.0874, d 4…

<details><summary>Skeptic 1</summary>

Reproduced the headline number exactly, but the controls refute the diagnosis and the suggested fix.

1) Noise-free case reproduces (deer.py:188-192, synthetic lam=0.35, k=0.06/us, Gaussian P at r0=4.0 nm sigma=0.3, t=0..4 us/256 pts, bg_start=2.5): fixed d=3 -> lam 0.3491, k 0.0603; fit_dim -> lam 0.3960, k 0.0842, d 4.905. Matches the finding's 0.397/0.0849/4.96 to rounding.

2) The noisy numbers do NOT reproduce and the claimed bias is not systematic. Over 20 noise seeds at sigma=0.005: fit_dim lam median 0.386, range [0.275, 0.411], d median 4.28, range [2.00, 6.00] (7/20 at the upper bound). At sigma=0.020: lam median 0.267, range [-0.072, 0.425], d median 2.75, 9/20 pinned at ub=6 AND 10/20 pinned at lb=1. With seed 0 at sigma=0.02 I got d=1.000 and lam=0.0166 — i.e. the failure is a variance blow-up in BOTH directions, not the stated "+14 to +18 % lambda" upward bias. Sweeping bg_start on the same noise-free trace: 1.5 us -> d 1.000/lam 0.089; 2.0 -> d 5.65/lam 0.406; 2.5 -> d 4.91/lam 0.396; 3.0 -> d 2.16/lam 0.284; 3.5 -> d 1.39/lam 0.147. The sign of the lambda error flips with the window, so "on any ordinary 3D trace d comes back ~5-6 and lambda is ~15 % high" is false.

3) The estimator itself is correct. Control with a genuinely flat form factor in the window (pure (1-lam)*exp(-k t)): fit_dim returns d = 3.000, k = 0.0600, lam identical to the fixed-d fit. So there is no formula, bound or convention error at deer.py:188-192 — the entire effect is residual dipolar structure inside the user-chosen fit window (S(2.5 us) = -0.007 with a +0.006 rise across the window) being absorbed by the extra freedom. That is the textbook ill-conditioning of floating d on a short tail, not a code defect.

4) The suggested fix contradicts the independent reference. DeerLab 0.14.2's dl.bg_homfractal parameter table bounds fdim to [0.01, 5.99] — essentially the same upper bound as this code's 6.0, and it too floats it without pinning warnings. Narrowing to [1.0, 3.5] would make this code stricter than the peer-reviewed implementation of the same model.

Combined with the mitigations already acknowledged (opt-in, default-off checkbox at deer_analysis.py:659; fixed-d path unaffected; the fitted d and k are reported back in the result dict and shown in the GUI, so a pinned d is visible in the readout, not silent), this is a usability note about an inherently ill-conditioned opt-in option, not a bug or risk in the math.

</details>

<details><summary>Skeptic 2</summary>

REFUTED — the claimed bias is a knife-edge artifact of a bad background window, not a property of `fit_dim`.

1) Reproduced the reviewer's exact numbers, and found they are non-generic. Their trace (r0=4.0 nm, tmax=4 us, bg_start=2.5 us) only yields their figures at one specific P width. Sweeping the Gaussian width sigma at that geometry (true lam=0.35, k=0.06, d=3):
   sig=0.05 fixed lam .316 | fit_dim lam **-0.128**, d **1.00** (LOWER bound)
   sig=0.10 fixed lam .310 | fit_dim lam -0.149, d 1.00
   sig=0.20 fixed lam .328 | fit_dim lam -0.053, d 1.00
   sig=0.30 fixed lam .349 k .0602 | fit_dim lam .397 k .0847 d 4.96  <-- exactly the finding's sigma=0 row
   sig=0.50 fixed lam .352 | fit_dim lam .333, d 2.61
   sig=1.00 fixed lam .352 | fit_dim lam .373, d 3.63
   So d runs to the LOW bound as often as the high one, and the reported "+15% lam" is one point of a non-monotonic scatter. The finding's framing ("d > 3 lets the stretched exponential absorb residual dipolar decay, inflating lambda") does not survive: at neighbouring widths the same residual decay pushes d to 1.0 and lambda NEGATIVE.

2) On a correctly chosen tail window the estimator is unbiased. With tmax=8 us / bg_start=4.0 us (window past the dipolar decay — the standard DEER requirement), 20 noise seeds, r0=4 nm:
   sigma=0.000: fit_dim lam 0.353, d 3.03 | fixed lam 0.350
   sigma=0.005: fit_dim lam 0.350+-0.018, d 3.03+-0.22 | fixed 0.350+-0.004
   sigma=0.020: fit_dim lam 0.322+-0.102, d 3.01+-0.87 | fixed 0.352+-0.013
   d recovers 3.00 with no drive toward 6.0 and no lambda inflation. A broader sweep (r0 2.5/3.0/4.0/5.0 x sig 0.2/0.5 x 3 windows, /tmp/sk2/r2.py) shows fit_dim returning d=2.99-3.01 and lam=0.350-0.357 for every case whose bg window clears the dipolar decay; it only misbehaves for the r0=4-5 nm traces truncated at 4 us — where the FIXED-d fit is also badly wrong (lam 0.089 and 0.405 vs true 0.35, i.e. -75% / +16%, worse than the fit_dim error the finding complains about).

3) The independent reference contradicts the physical premise. DeerLab 0.14.2 `bg_homfractal` declares fdim with lb=0.01, ub=**5.99**, par0=2.2 — essentially the identical upper bound to deer.py:190's 6.0. So "d > 6 range is unphysical, bound to [1.0, 3.5]" is a deviation from the peer-reviewed reference, not a fix.

4) The suggested fix does not fix the reproduced case. Re-running the sig=0.3 trace with the upper bound clamped: ub=6 -> lam 0.397 d 4.96; ub=3.5 -> lam **0.367** d 3.50 (still pinned, still +5%); only ub=3.0 (i.e. disabling the feature) recovers 0.349. And it does nothing for the d->1.0/negative-lambda cases, which are the more common failure at that window.

Root cause is bg_start chosen inside the dipolar decay (deer.py:190 fits on `t >= bg_start`), which corrupts fixed-d and floating-d alike. The only residual merit is ergonomic: nothing surfaces a d that has pinned at either bound (deer.py:186-192 returns `dim` silently; deer_analysis.py:659 checkbox). That is a usability note, not a numerical bug, and it should cover the lower bound too.

Scripts: /tmp/sk2/r2.py, /tmp/sk2/r4.py, /tmp/sk2/r5.py

</details>

### _echo_top anchors V(0)=1 at the sample nearest t=0, not at the echo maximum

`atomize/math_modules/deer.py:113`

`_echo_top` takes `i0 = int(np.argmin(np.abs(t)))` (deer.py:113) — the sample nearest t = 0 — and fits its +-w parabola there. That is correct only when the zero time has already been applied. If the caller passes an un-shifted trace (GUI 'Fit' zero-time unchecked, or a fit that failed), the normalization anchor lands on the echo rising edge instead of the echo top and every downstream quantity is scaled by that wrong reference.

Measured on the real sample1_labA.DTA (t starts at 0, echo max at +130 ns, bg_start 1.9 us):
  t0 left at 0 : A = 0.9652, lambda = 0.0348, V_norm max = 1.6995, F max = 21.25, P peak 3.75 nm, <r> 4.40 nm
  t0 = 0.130 us, pre-t0 cropped: lambda = 0.433, P peak 2.35 nm…

<details><summary>Skeptic 1</summary>

Numbers reproduce but the attribution is wrong and the fix is wrong. On sample1_labA.DTA (t starts at 0, echo max +0.128 us, bg_start 1.9 us) I measured t0=0 -> lam=0.0338, V_norm max 1.7005, F max 21.87, P peak 3.72 nm, <r> 4.29; t0=0.128 cropped -> lam=0.4344, F max 1.00, P peak 2.35, <r> 2.53; GUI-default fit_zero_time -> 0.1301, lam=0.4312, P peak 2.35. So the raw figures match the finding. DECISIVE TEST: monkey-patching _echo_top to the finding's own suggested anchor (echo maximum) while leaving t0=0 gives lam=0.4318, F max 1.007, but P peak STILL 3.721 nm and <r> 4.100 nm — the 1.4-1.6 nm distance error comes from the 130 ns offset entering dipolar_kernel, not from _echo_top. The proposed fix repairs only lambda and actively removes the F=21 red flag, producing a plausible-looking F(t)~1 from a 130-ns-wrong kernel. _echo_top (deer.py:101-124) does exactly what its docstring and background_fit's contract state (deer.py:167 "V is normalized so V(t=0)=1"); zero-time determination is a separate, existing routine (_parabolic_zero_time deer.py:2248, fit_zero_time deer.py:2289). Reachability is user-forced and signposted, not silent: deer_fit_t0 is default-checked (deer_analysis.py:605) with a tooltip stating "A wrong t0 broadens P(r) and biases it long"; a "Max" button sets t0=argmax|V| in one click (_deer_t0_max, line 1741); the spinbox is auto-populated with the fitted t0 after any Fit-on run (line 2313); and both bg['V_norm'] (with the B overlay, lines 2561/2628) and res['form_factor'] (line 2553) are plotted, so V_norm=1.70 and F=21 are visible on screen. The w=5 sub-claim FAILS to reproduce: on a realistic DeerLab-generated V(t) (dipolarkernel + bg_hom3d, lam=0.3, 4 nm Gaussian, t0 applied) the echo_top deviation is -0.0000% at 4/8 ns, +0.0004% at 16 ns, -0.0034% at 32 ns and -0.0327% at 64 ns — 17x smaller than the claimed "+0.57% overshoot" and the opposite sign. The only way I got a large number (-26.8% at 64 ns) was decimating the un-t0-shifted raw trace so the window straddles the echo rise, i.e. the t0 issue again. Residual legitimate value is only a "warn if form factor exceeds ~1.2" UX guard against a wrong t0 — a note, not the reported _echo_top defect.

</details>

<details><summary>Skeptic 2</summary>

REFUTED as a risk; downgrade to note. I reproduced the numbers but the causal attribution is wrong and the scenario is user-explicit.

WHAT REPRODUCES (real sample1_labA.DTA, dt=8 ns, echo max at t=0.128 us, bg_start 1.9 us, joint engine, r=1.5-8 nm):
- t0 left at 0: lambda=0.0203, A=0.9797, V_norm max=1.6995 (exact match to the finding's 1.6995), F max=35.8, P peak 3.722 nm, <r>=4.272
- t0=0.128 applied (no crop, as the GUI actually does): lambda=0.4149, F max=1.010, P peak 2.158 nm, <r>=2.505
So the magnitudes are real.

WHY IT IS NOT AN _echo_top BUG — the decisive test. I monkey-patched _echo_top to the finding's own suggested fix (argmax of a lightly-smoothed V over the leading third) and re-ran with t0 still 0:
  FIXED-anchor, t0=0: lambda=0.4015, F max=1.051, P peak 3.722 nm, <r>=4.103
The suggested fix repairs lambda and F(0), but the distance is UNCHANGED (3.722 nm peak, <r> 4.10 vs the correct 2.16/2.50). The "1.4 nm distance shift" is caused entirely by the un-applied zero time misaligning the dipolar kernel, not by the normalization anchor. The finding attributes to _echo_top an error its own fix demonstrably does not remove.

CONVENTION: in this module t=0 IS the dipolar reference time by construction (deer.py:2289 fit_zero_time, and every caller passes t - t0). Given that contract, argmin|t| at deer.py:113 is the correct anchor — it lands exactly on the echo max on the shifted axis (index 16 in the real trace).

REACHABILITY IS WEAK. deer_analysis.py is the only caller in the repo (grep: no other file imports deer_invert/background_fit). There, deer_fit_t0 defaults Checked (line 605); the fitted t0 is written back into the spinbox after every run (lines 2312-2314), so unchecking 'Fit' after a run retains the good value; there is an explicit 'Max' button (line 600, _deer_t0_max at 1741); and the tooltip literally says "Uncheck to set t0 manually". fit_zero_time does not silently fail — the parabola falls back to the residual grid search (deer.py:2344 ff). I confirmed the default path: fit_zero_time returns 0.12981, giving lambda 0.4144, F max 1.010, <r> 2.501. The failure requires the user to deliberately turn off automatic t0 and then leave it at 0 on a trace that starts at 0 — the symptom of a wrong t0, not of the anchor.

THE w=5 SUB-CLAIM: qualitatively right, numerically wrong in the finding. On a clean synthetic V with V(0)=1 exactly (DeerLab-cross-checked kernel, lam=0.4, 3D bg), _echo_top error vs dt: 4 ns -0.061%, 8 ns -0.144%, 16 ns -0.592%, 32 ns -4.17%, 64 ns -16.4%. It is an UNDERSHOOT, not the claimed "+0.57% overshoot at dt=64 ns" — wrong sign and ~30x off. At realistic DEER steps (8-16 ns) it is <=0.6%, i.e. sub-noise; it only bites at 32-64 ns steps. Real but minor: worth making w a time window, hence "note".

Net: the only defensible actionable content is (a) make w a time window, and (b) add an F(0)/F-max sanity warning — which is a guard against a bad user-supplied t0, not a fix to _echo_top.

</details>

---

## Notes (6)

### NU_DD uses g=2.0023 (52.0400); DeerLab uses g_e=2.0023193 (52.0410)

`atomize/math_modules/deer.py:49`

Independent derivation: nu_perp = mu0 g^2 muB^2 / (4 pi h r^3). With CODATA muB = 9.2740100657e-24 J/T, h = 6.62607015e-34 J s and g = 2.0023, mu0 g^2 muB^2/(4 pi h) = 5.204001237e-20 Hz m^3 = 52.04001 MHz nm^3. The code's 52.04 is therefore CORRECT to all four digits given, for the stated g = 2.0023.

DeerLab uses the free-electron g_e = 2.00231930436 -> 52.041016 MHz nm^3. Fitting the constant that minimizes the element-wise difference between `dipolar_kernel` and `dl.dipolarkernel(t, r, integralop=False)` over t in [0,5] us, r in [1.5,8] nm returns nu = 52.041016 with a residual of 3.6e-9 (vs 2.2e-4 at 52.04) — i.e. the kernel functional form is identical and the only difference is this constant. The distance error is (52.0410/52.0400)^(1/3) - 1 = 6.5e-6 relative, ~3e-5 nm at 5 nm. Immaterial; recorded so no later session re-derives it.

_Fix:_ None needed. If exact DeerLab parity is ever wanted, set NU_DD = 52.0410 and note g = g_e.

### deer_invert_joint reports F_fit = K@P_norm while deer_invert reports K@P

`atomize/math_modules/deer.py:598`

`deer_invert` returns `F_fit = K@P` with the raw NNLS masses (deer.py:519) but `deer_invert_joint` returns `F_fit = K@P_norm` with the sum-normalized masses (deer.py:598), while `residuals = F - F_fit` and `tikhonov_ci` are still computed from the raw masses. The two engines' reported residuals are therefore not on the same footing.

Measured magnitude (r0=3.5 nm, lam=0.35): sum(P) = 1.0017 / 0.9994 / 1.0075 at sigma = 0.002 / 0.01 / 0.03, and the joint engine's reported rms residual differs from the true K@P residual by < 1e-5 in all three cases. So the discrepancy is under 1 % today and only matters if regularization ever shrinks sum(P) appreciably.

This also confirms the S1 hunt item about the kernel discretisation: K carries no dr, P are masses, K(0,r) = 1 and F(0) = 1 force sum(P) -> 1 automatically, and P_density = P_norm/dr with dr from a uniform linspace grid (deer.py:521; the GUI builds r with np.linspace at deer_analysis.py:1806). The Riemann sum is self-consistent and lambda is not rescaled.

_Fix:_ Use `K@P_masses` in the joint engine for F_fit/residuals, matching deer_invert, and keep P_norm for the density output only.

### fit_zero_time does not receive bg_params and always fits t0 with the stretched-exponential background

`atomize/control_center/deer_analysis.py:1822`

The GUI passes `engine=engine` to `fit_zero_time` (deer_analysis.py:1826, and the same at 1902/1987) but not `bg_params`. `fit_zero_time` then overrides the engine to 'sequential' anyway (deer.py:2356), so the t0 search always uses `background_fit`'s exp(-(k|t|)^(d/3)) model even when the final inversion runs with engine='general' (the free a/b/c/d background) or engine='none' (B = 1). The t0 estimate and the inversion therefore disagree about the background model.

In practice `method='parabola'` is the default and returns before any inversion runs (deer.py:2347-2348), so the residual path — and hence this mismatch — only executes when the parabola finds no concave peak. Recorded rather than raised because of that.

Also in the same neighbourhood: `_auto_rmax_value` (deer_analysis.py:1673) uses `t_us = |x[-1] - x[0]|`, the full acquisition span including the pre-t0 segment, in the Jeschke r_max = 5*(t/2)^(1/3) rule, so r_max is slightly over-estimated (e.g. +2 % for 130 ns of pre-t0 data on a 3 us trace).

_Fix:_ Forward `bg_params` and honour the requested background engine inside `fit_zero_time`'s residual search (it already forces engine='sequential' only for speed), or document that the residual t0 search is always stretched-exponential.

### Background is exp(-(k t)^(d/3)), not the physical exp(-k t^(d/3)) — convention, not bug

`atomize/math_modules/deer.py:157`

PANEL: unanimous, all three agents derived B(t) = exp(-k_d |t|^(d/3)) with the stretch exponent equal to d/3 (not d, not (d-1)/3), and ALL THREE explicitly flagged the exp(-k t^(d/3)) vs exp(-(k t)^(d/3)) parameterisation as the classic trap, warning they differ by k -> k^(d/3) and coincide only at d = 3. CODE: `_bg_model` (line 157) is A*exp(-(k*|t|)**(d/3)) — the second, 'stretched-exponential' form. DeerLab (third opinion) uses the first form: bg_homfractal computes exp(-kappa_d*lam*conc*|D*t*1e-6|**(d/3)), i.e. rate times t^(d/3). SURVIVES CONVENTION: the exponent d/3 itself is correct, and the code consumes k consistently everywhere — `simulate` (line ~2520) generates with exactly the same expression it fits with, and grep shows NO concentration conversion anywhere in deer.py or deer_analysis.py, so k is never given a physical (uM) interpretation. The two families span the identical set of curves under k_code = k_phys^(3/d) (verified to 1.1e-16), and free-d fits recover the true dimension: injecting exp(-k t^(d/3)) backgrounds with d = 1.5/2.0/2.5/3.0 and fitting with fit_dim=True returns d = 1.606/2.088/2.576/3.066 and k_code^(d/3) = 0.453/0.371/0.299/0.240 vs true k_phys = 0.500/0.397/0.315/0.250. So this is a reparameterisation, not an error. The only live hazard is external: the reported `k` has units us^-1 in this parameterisation but us^(-d/3) in the literature one, so applying the standard calibration k[us^-1] = 9.974e-4 * lambda * C[uM] to a fitted k is only valid at d = 3 exactly (where the two forms coincide). Default dim = 3.0, so the default path is safe.

_Fix:_ No code change required. Optionally state the parameterisation in the background_fit docstring ('k is the stretched-exponential rate, B = exp(-(k t)^(d/3)); it equals the literature homogeneous rate only at d = 3') so downstream code never converts a d != 3 k into a concentration.

### NU_DD = 52.04 vs derived 52.041016; docstring credits the wrong g

`atomize/math_modules/deer.py:49`

PANEL: unanimous on 52.041016 MHz*nm^3 (52.041016 / 52.04101581614 / 52.041016 — agreement to 8 significant figures), all three deriving it as mu_0*g_e^2*mu_B^2/(4*pi*h) with g = g_e = 2.0023193, and all three warning that this is the ORDINARY (cyclic) prefactor requiring a 2*pi before it multiplies t inside a cosine. CODE: NU_DD = 52.04 (line 49); the comment says '(g = 2.0023)'. DeerLab's constants.D / (2*pi) = 5.204101599e-20 Hz*m^3 = 52.041016 MHz*nm^3 — exactly the panel value, confirming both magnitude and the 2*pi convention. Relative error of the code constant is -1.95e-5. Since r enters the frequency as 1/r^3, the distance bias is one third of that: 6.5e-6, i.e. 0.00065% — 0.00002 nm at r = 3.5 nm, five orders of magnitude below the achievable resolution. The 2*pi IS present (line 88, w = 2*np.pi*nu_dd/r**3), so the 1.845x distance error the panel warned about does not occur. Minor doc nit: g = 2.0023 actually gives 52.0400, not 52.04 as rounded from g_e = 52.041016; the constant is the rounded free-electron value, so the parenthetical attribution is inaccurate (harmless).

_Fix:_ Optional cosmetic: NU_DD = 52.041016 and change the comment to '(g = g_e = 2.0023193; = DeerLab constants.D/2pi)'. No numerical consequence.

### Pake band in _gauss_mc truncates at 1.3x nu_perp and hardcodes 52.04

`atomize/math_modules/deer.py:1575`

Two small issues on one line, neither a physics error. (1) The frequency grid for the Monte-Carlo Pake-domain fit is capped at nu_hi = 1.3*52.04/rmin^3, but the Pake pattern of a pair at rmin extends to the PARALLEL horn at 2*nu_dd/rmin^3 (the panel's derivations all give nu(theta) = nu_dd(1-3cos^2 theta)/r^3, so |nu| runs to 2x at theta = 0). With the default r axis starting at 1.5-2.0 nm the cap sits at 15.4-8.5 MHz while the parallel edge is at 30.8-13.0 MHz, so roughly the outer third of the spectrum of the shortest distances is outside the fit window. This does not bias the result — Phi is applied identically to data (Fnu) and model (Kfreq) and the `band` mask further restricts to |Fnu| > 2% of max — it only discards information that would constrain the short-r components. (2) The literal 52.04 is used even though `nu_dd` is a parameter of _gauss_mc, so a caller passing a custom nu_dd (a non-nitroxide g) gets a band computed from the default constant. _pake_transform itself (line 1543) is correct: Phi = 2*cos(2*pi*nu*t)*dt with trapezoid end-halving, and the arbitrary factor 2 cancels because both F and K pass through the same Phi.

_Fix:_ Use nu_hi = min(2.2*nu_dd/max(rmin,0.5)**3, nyquist) — the parallel edge at 2x plus a small margin — and take nu_dd from the argument instead of the literal 52.04.

---

## Coverage

**Code review.** READ IN FULL: deer.py lines 1-330 (module docstring/conventions, NU_DD, dipolar_frequency, dipolar_kernel, _echo_top, _no_background, _bg_model, background_fit, background_general, regularization_matrix, tikhonov_nnls), 330-610 (l_curve, default_r_axis, _normalize_masses, tikhonov_ci, deer_invert, deer_invert_joint — read for how the foundations are consumed), 1543-1602 (_pake_transform + its only caller _gauss_mc), 2240-2420 (_parabolic_zero_time, fit_zero_time, _bg_start_grid). GUI: deer_analysis.py Source/Phase/Background tab construction (lines 327-670), the auto-window/auto-r helpers (1600-1760), and all three engine drivers' compute() closures (1795-2020). data_treatment.py: grepped for DEER paths — there are none left (only one comment at line 237 referencing deer_analysis); the DEER code lives solely in the standalone tool, so the S6 'duplicated DEER code' hunt is already resolved as 'not duplicated'.

DeerLab 0.14.2 works via ~/deer_benchmark/deerlab_shim.py as-is; no further fixing was needed.

=== VERIFIED CORRECT — do not re-derive ===

1. NU_DD = 52.04 MHz nm^3 (deer.py:49). Derived independently: mu0*g^2*muB^2/(4*pi*h) with CODATA muB=9.2740100657e-24 J/T, h=6.62607015e-34 J s, g=2.0023 -> 5.204001237e-20 Hz m^3 -> 52.04001 MHz nm^3. Correct to all four digits given. (g=2.0 -> 51.9205; g_e=2.0023193 -> 52.0410, which is DeerLab's value — see the note finding.)

2. dipolar_kernel closed form (deer.py:74-95). K = sqrt(pi/(6a))*[cos(a)C(z)+sin(a)S(z)], a=w|t|, z=sqrt(6a/pi), w=2*pi*nu_dd/r^3, K(a=0)=1. Checked element-wise against scipy.integrate.quad of int_0^1 cos((1-3x^2) w t) dx at r = 2.0/3.5/6.0 nm and t = 0.1/0.5/1.5/3.0 us: agreement to 1e-16 (machine precision) in every cell.

3. Powder average is uniform in cos(theta), NOT in theta — correct. There is no orientation grid at all (the average is analytic via Fresnel integrals), so grid-density/convergence is a non-issue. For the record, the WRONG uniform-in-theta average would give e.g. -0.0843 instead of -0.2108 at r=2 nm, t=0.1 us — a large, easily visible error that is not present.

4. dipolar_kernel vs DeerLab dl.dipolarkernel(t, r, integralop=False): max |diff| = 2.2e-4 over t in [0,5] us x r in [1.5,8] nm, and 3.6e-9 when NU_DD is set to DeerLab's 52.041016. The entire difference is the g-factor constant; the functional form is identical.

5. Kernel discretisation / lambda scaling is self-consistent (the hunt's main worry — cleared). K carries no dr; P are discrete masses; K(0,r)=1 and F(0)=1 force sum(P) -> 1 automatically. Measured sum(P) = 1.0014 / 0.9991 / 1.0059 at sigma = 0.002 / 0.01 / 0.03 (sequential) and 1.0017 / 0.9994 / 1.0075 (joint). P_density = P_norm/dr with dr = r[1]-r[0]; the r grid is always uniform (default_r_axis np.linspace, deer.py:402; GUI np.linspace at deer_analysis.py:1806), so K.P is a valid Riemann sum and lambda is not silently rescaled.

6. Background exponent convention exp(-(k|t|)^(d/3)) (deer.py:158). The d/3 exponent matches DeerLab's bg_homfractal (verified: log-log slope of -ln B vs t = 1.0000 at d = 3). deer.py parameterizes (k|t|)^(d/3) where DeerLab uses k*|t|^(d/3) — a pure reparameterization of k at fixed d, identical model family.

7. background_general / background_fit at d = 3 vs dl.bg_hom3d: exp(-k|t|) with k = 9.974e-4 * conc * lam reproduces DeerLab to 5 significant figures (conc = 100 uM, lam = 0.3, t = 4 us: 0.8871987 vs 0.8871972; implied k ratio 9.9739e-4). The documented conc->k mapping is right.

8. bg_start placement sensitivity on a clean synthetic (true lam 0.35, k 0.06): bg_start = 0.3/0.6/1.0/1.5/2.0/2.5 us of a 4 us trace gives lam = 0.341/0.390/0.378/0.319/0.315/0.370. Bounded ~+-10 % even when bg_start lands well before the dipolar evolution has decayed — no runaway, no sign flip. The hunt's 'bg_start before decay' concern is not a defect at fixed dim (it IS one with fit_dim on — see that finding).

9. _echo_top vertex is correctly clipped to the fit window (deer.py:122) and correctly falls back to V[i0] on a non-concave fit or a non-positive estimate. Accuracy vs an exact V(0)=1 trace: +0.000 % at 4/8 ns steps, +0.004 % at 16 ns, +0.057 % at 32 ns, +0.575 % at 64 ns.

10. _parabolic_zero_time IS unbiased when the echo is symmetric: with a symmetric Gaussian echo envelope it returns 0.0 ns error at sigma = 0, -0.2 ns at sigma = 0.01, -0.6 ns (worst 2.5 ns) at sigma = 0.03. The bias found is entirely a window-asymmetry artifact, not a flaw in the parabola/vertex math.

11. On the four real Bruker YopO traces the zero-time fit is accurate (t0 - peak = +2.1 / +0.7 / -5.8 / +1.0 ns) and the fit window is near-symmetric (L/R half-widths 32/40, 40/40, 48/36, 36/36 ns) — the asymmetry bug does not fire on short-distance, fast-decaying real data.

12. GUI r-window heuristics (deer_analysis.py:1668-1690) are both correct: r_max = 5*(t_us/2)^(1/3) is the standard Jeschke/DeerAnalysis rule; r_min = (4*NU_DD*dt)^(1/3) is the correct Nyquist condition for the fastest (parallel) component 2*nu_perp = 2*NU_DD/r^3 sampled at 1/dt >= 2*nu_max.

13. _pake_transform (deer.py:1543): trapezoidal cosine transform with correct half-weight end points and the factor 2 for the one-sided integral. It is used only as a relative comparison inside _gauss_mc (Phi is applied identically to F and to K), so the finite-t truncation cancels and it is not an absolute Pake spectrum — correct for its use.

14. NOT re-checked here (out of S1 scope): l_curve/GCV, tikhonov_ci coverage, the Mellin core, joint_background, and the multi-Gaussian block — all deferred to S2-S5.

**Reconciliation.** READ FULLY: atomize/math_modules/deer.py lines 1-300 (module docstring, NU_DD, dipolar_frequency, dipolar_kernel, _echo_top, _no_background, _bg_model, background_fit, background_general), 605-640 (Mellin convention block), 1210-1240 (Mellin D = 2*pi*nu_dd), 1520-1600 (_pake_transform, _gauss_mc band setup), 2505-2545 (simulate + self-test). SKIMMED via grep: every nu_dd/NU_DD consumption site (lines 68-88, 444-584, 738-811, 1060-1224, 1710-1884, 2076, 2429-2512) and every "F = (V/B - (1-lam))/lam" site (203, 817, 826, 862) to confirm the kernel constant and the background parameterisation are consumed consistently. Grepped for any concentration conversion (9.97e-4, N_A, uM, mM) — there is NONE in deer.py or control_center/deer_analysis.py, so fitted k is never given a physical concentration meaning.

NUMERICAL CHECKS (all run from ~/deer_benchmark, scratch scripts in /tmp/deercheck, nothing under Atomize_ITC touched):
1. NU_DD: recomputed mu_0*g_e^2*mu_B^2/(4*pi*h)*1e21 = 52.0410159928 (CODATA 2018) vs code 52.04 -> rel -1.95e-5 -> r bias +6.5e-6 (0.00065%). g = 2.0023 gives 52.040013. DeerLab constants.D/(2*pi) = 5.204101599e-20 = 52.041016 MHz*nm^3, confirming both the magnitude and that 52.04 is the CYCLIC (divide-by-h) prefactor.
2. Powder average / kernel: verified dipolar_kernel(t,r) equals the direct quadrature int_0^1 cos[(1-3x^2)*2*pi*nu_dd*t/r^3] dx (uniform in cos theta, the panel's unanimous answer) to < 1e-8 absolute at r = 2.0/3.5/5.0 nm, t = 0..2 us. The 2*pi IS inside the cosine (line 88), so the (2*pi)^(1/3) = 1.845x distance error the panel warned about is absent. vs DeerLab dl.dipolarkernel(t,r,integralop=False): max abs diff 1.1e-4 (DeerLab's grid orientation average vs the exact Fresnel closed form).
3. Forward model: D.simulate vs dl.dipolarkernel(t,r,mod=0.35)@P — max abs diff 6.0e-6.
4. END-TO-END ROUND TRIP: simulate Gaussians at 2.5 / 3.5 / 4.5 nm (sigma 0.2, lam 0.35, k 0.10, dim 3, noise 0.002) then deer_invert(bg_start=1.2). Recovered peaks 2.508 / 3.512 / 4.515 nm, r_mean 2.484 / 3.555 / 4.497, lambda 0.351 / 0.363 / 0.357 (true 0.35), k 0.1004 / 0.0921 / 0.0943 (true 0.10). Distances correct to <0.5%; no 2*pi (would be 84% error) and no factor-2 (26% error) present.
5. Background parameterisation: exp(-k*t^(d/3)) vs exp(-(k*t)^(d/3)) shown to be an exact reparameterisation k_code = k_phys^(3/d) (max diff 1.1e-16). Injected DeerLab-form fractal backgrounds with d = 1.5/2.0/2.5/3.0 and fit with fit_dim=True: recovered d = 1.606/2.088/2.576/3.066, k_code^(d/3) = 0.453/0.371/0.299/0.240 vs true 0.500/0.397/0.315/0.250. Exponent d/3 confirmed correct; DeerLab bg_hom3d / bg_homfractal source read directly as the third opinion.
6. Stress test that produced the one real bug: short trace + long distance + fit_dim=True drives A to its 1.5 bound, lam negative, P(r) collapses to the grid edge (details in the finding).

CONCLUSION on the panel's three quantities: NU_DD, the cos-theta powder average / kernel form, and the d/3 background exponent ALL match the derived reference; the two apparent differences (52.04 vs 52.041016, and the (kt)^(d/3) vs k*t^(d/3) parameterisation) both survive convention and are reported as notes, not bugs. The only actionable defect is the unguarded negative lambda.

---

## What this means for S2–S6

- The kernel and background physics are **cleared**. Later sessions may rely on the
  confirmed-correct list above rather than re-deriving.
- **S1-1 (negative-time) must be fixed before S2/S4/S5 benchmarking**, or every
  engine comparison inherits it. It is an entry-point fix — one mask in each
  `deer_invert*`.
- The existing benchmark suite crops `t >= 0`; the GUI does not. Any future
  validation must exercise the **GUI's** path, or it will keep missing this class
  of defect.
