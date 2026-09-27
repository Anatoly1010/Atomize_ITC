# CPMG detection and HYSCORE scripts: bench tests

Created 2026-09-27. Everything below passed offline (test mode, offscreen GUI, `~/epr_auto_dev/gui_vs_engine.py` ALL PASS for 21 presets) but has **not** run on the Insys spectrometer. After these tests pass, port the CPMG tab to `Atomize_NIOCH` and `Atomize_NIOCH_Q` (`awg_phasing.py`; their time-per-point map differs from ITC, see the sync notes).

Record for each test: date, sample, preset or script, field, rep rate, result, and the saved file names.

## 1. CPMG tab, preview

| # | Step | Pass when |
| --- | --- | --- |
| 1.1 | Load `CPMG; 2S` (T₂ menu). Start the preview. | The detection window spans the whole echo train (length + 2·N·τ); 17 echoes are visible. |
| 1.2 | Press **A** next to Echo Center on a Hahn echo. | Echo Center = detection start + echo peak; compare with the calculated 608 ns and note the difference (receiver delay). |
| 1.3 | Check π pulse positions on a scope (TRIGGER_AWG) or in the trace. | π pulse k is centred at Echo Center + (2k−1)·τ; echoes sit at Echo Center + 2k·τ, midway between π pulses. |
| 1.4 | Change N, τ, Parent pulse, Echo Center or the CPMG phase during the preview. | The preview restarts with the new train; no stale pulses. |
| 1.5 | Change the parent pulse amplitude or length. | The CPMG pulses follow the parent. |
| 1.6 | Set N·τ so the window exceeds 12.8 µs. | Clear error message; nothing is sent to the board. |
| 1.7 | CPMG Off, load an old preset (e.g. `Hahn Echo; 2S`). | Behaviour identical to before this change. |

## 2. CPMG phase cycle

| # | Step | Pass when |
| --- | --- | --- |
| 2.1 | `cpmg_2s` with phase `y` (2 steps). | Echo train in-phase; MG condition holds (echoes do not decay faster than with a single Hahn echo at the same spacing). |
| 2.2 | Phase `(y); y`, detection −1,2 (4 steps). | Same echo train, FIDs of CPMG pulse 1 removed. |
| 2.3 | Phase `[y]; y`, detection −1,2,2 (8 steps). | Same echo train. With −1,2 instead, the train cancels (expected). |

## 3. Decay mode (T₂)

| # | Step | Pass when |
| --- | --- | --- |
| 3.1 | Run `cpmg_2s` as an experiment, IQ correction on. | Decay plot shows N+1 points at x = (Echo Center − first-pulse centre) + 2k·τ (596.8, 1172.8, … ns for Ec 608). |
| 3.2 | Compare the first point with a Hahn echo at the same τ. | Same amplitude within noise. |
| 3.3 | Fit the decay (1D Data Treatment). | Sensible T₂; saved CSV has the Echo Time column and the CPMG header lines. |
| 3.4 | Save 2D on. | `_2d` file holds the whole trace. |

## 4. Sum of Echoes (DEER-style detection)

| # | Step | Pass when |
| --- | --- | --- |
| 4.1 | Load `4pDEER CPMG; 8S`, preview. | The CPMG block follows the refocused echo (Echo Center 3480 ns, τ 400 ns). |
| 4.2 | Run the experiment (Linear Time). | The DEER trace has the same shape as plain `4pDEER; 8S` with better SNR; `_echoes` file holds the per-echo integrals (2 × (N+1) × points). |
| 4.3 | Per-echo integrals. | Monotonic decay along the echo index; no echo integrates a π pulse (check the integration window vs τ). |
| 4.4 | ESEEM Avg sweep with a nonzero detection Start Increment 2, 2–3 cycles. | The CPMG block moves with the detection every point and every cycle (offline check passed; confirm on the trace); Save Each Cycle files hold the echo sums. |
| 4.5 | Decay mode with a non-Linear sweep. | Refused with 'CPMG Decay requires the Linear Time sweep'. |

## 5. Scripts

| # | Script | Pass when |
| --- | --- | --- |
| 5.1 | `AWG/Relaxation/cpmg_trace.py` (test, then real) | Trace identical in shape to the old script; phase cycle +x/−x, π at +y. |
| 5.2 | `AWG/ESEEM/hyscore_2d.py` (test ≈ 25 s at 128×128, then a small real run, e.g. 32×32) | Map fills row by row; final map equals the live map; saved CSV opens in the 2D tool with t1/t2 axes. |
| 5.3 | `AWG/ESEEM/hyscore_2d_h5.py` (same) | Raw `.h5` (points × time) and `_map.h5` both open in the 2D tool; the raw file re-integrated in the Reshape tab reproduces the map. |
| 5.4 | HYSCORE short phase cycle vs the old explicit one | Same map within noise (both select only the +00− pathway). |
| 5.5 | Stop mid-run for 5.2 / 5.3 | Partial map saved; no board left open. |

## 6. Presets

| # | Step | Pass when |
| --- | --- | --- |
| 6.1 | `HYSCORE; 16S` in the AWG tool and `hyscore_16s.phase` in the RECT tool | 16 steps; echo identical to the old preset. |
| 6.2 | Save and reload both CPMG presets from the GUI. | CPMG settings, Echo Center and phase text survive the round trip. |
