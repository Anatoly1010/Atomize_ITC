# HDF5 saving of full 2D data — implementation plan

Scope fixed by prior decision: HDF5 is a *writer choice* for (1) the phasing tools'
"Save 2D" companion dump and (2) the TR EPR 2D data. Never CSV + HDF5 of the same
array. The 1D `np.c_[x_axis_plot, data_x, data_y]` result stays CSV, untouched.
CSV reading is supported forever, sniffed by extension.

## 0. Findings and owner rulings

1. **RECT is out of scope (ruled).** `phasing_insys.py` has no Save 2D and no 2D
   data to save — its workers keep only `data = np.zeros((2, POINTS))`
   (phasing_insys.py:3913, 4183, 4503), the window×points array is integrated on
   the fly and discarded, so there is nothing for an HDF5 writer to write.
2. **Save2D moves to the Settings tab (ruled).** It currently lives in the FFT
   tab (awg_phasing_insys.py:1284 label, :1344 checkbox, :1380 placement); the
   owner ruled that the existing control relocates to Settings (design_tab_6)
   next to the new HDF5 checkbox so both live together. Folded into Stage 2.1.
3. **The HDF5 checkbox governs every 2D dump in the AWG tool (ruled).** That
   includes the `iq_cor == 1` `_2d` companion, the `iq_cor == 0` *primary* full-2D
   dump (e.g. awg_phasing_insys.py:5527-5533), and the ESEEM per-cycle 2D dumps —
   same arrays, same `save_data` calls, only the filename extension changes. The
   1D result files stay CSV as before.
4. **Latent bug in tr_control p9==3**: `data` is allocated `(3, real_length,
   points+1)` (tr_control.py:1219) but the branch writes and saves `data[3, ...]`
   (tr_control.py:1518, 1604, 1773) — an out-of-bounds IndexError on a real
   3-channel run (y3 goes to `data[2]` in the off-resonance step at :1441 but
   `data[3]` in the sweep). Must be resolved (allocate 4 planes or index 2) before
   the HDF5 branch can mirror that save site. Fix separately, not smuggled into
   this feature.

## 1. HDF5 file layout

One file per array that today is one CSV (I and Q merge into a single file — this
replaces the `*_2d.csv` + `*_2d_1.csv` split of the `ndim == 3` branch,
csv_opener_saver.py:159-174).

The core is written **dimension-agnostic**: `.h5` is a drop-in alternative to
`.csv` for anything `save_data` already accepts, 1D included. Nothing in
`control_center/` writes 1D `.h5` — the 1D result files stay CSV per the ruling
in §0 — but the capability exists for experimental scripts and for whatever wants
it later, and costs nothing extra because it falls out of the same rule (§2).

```
example_2d.h5
├── attrs
│   ├── header          str   exact header text as passed to save_data (no '# ')
│   ├── format_version  int   1
│   └── source          str   'atomize'
├── I      float32  (npoints, nsamples)   same orientation as the CSV rows
├── Q      float32  (npoints, nsamples)   only when the source has a quadrature
├── t      float64  (nsamples,)           within-trace axis, seconds
└── sweep  float64  (npoints,)            tau (s) / field (G) / amplitude axis
```

A 1D file is the same layout with one axis fewer — no separate concept:

```
example_1d.h5
├── attrs                              same three
└── I      float32  (npoints, ncols)   the array verbatim, e.g. np.c_[x, I, Q]
                                       → (POINTS, 3), x in column 0 as in CSV
```

TR EPR with "Save Each Scan" adds one dataset:

```
├── scans  float32  (nscans, npoints, nsamples)  maxshape (None, ·, ·), chunks
│                                                (1, npoints, nsamples); slice
│                                                [j-1] written after scan j
```

Decisions and justifications:

- **Orientation** — rows = sweep points, columns = time samples, exactly what
  `np.transpose(data[i])` produces in the CSV path today, so `data_treatment_2d`'s
  "traces × points" convention holds without transposition logic.
- **dtype float32 for data** — the Insys readout path already produces float32
  (Insys_FPGA.py:2026-2071) from a 14-bit ADC (Insys_FPGA.py:2255); the Keysight
  2000-X in tr_control is an 8-bit scope. Averaging never pushes effective
  resolution near float32's 24-bit mantissa. Decisive: the current CSV writes
  `%.6e` = 7 significant digits ≈ float32 precision, so float32 loses nothing
  relative to the status quo while float64 doubles every file for no physical
  information. Axes are float64 (negligible size, exact). Quantitative case in
  §3, "Numeric precision".
- **I and Q as separate datasets**, not a complex dtype — matches how every
  consumer holds them (two real matrices), keeps files readable from Origin /
  MATLAB / h5dump without compound-type support.
- **Header as one string attribute**, not parsed key attributes — the header is
  built as a single f-string at every save site; storing it verbatim is zero new
  code per site and reconstructs both consumer forms exactly:
  - `open_2d`-style `header_array`: `[('# ' + ln).split(':') for ln in
    attrs['header'].splitlines()]` — identical to what the CSV reader returns,
    since `np.savetxt` writes each header line prefixed `# `.
  - `header_view.read_header`-style: `attrs['header'].splitlines()` (that helper
    strips the `#` anyway).
- **Scan stacking** — per-scan snapshots go into the `scans` dataset (resizable
  axis 0), not per-scan files. The stored slices keep today's semantics: the
  cumulative average after scan j (that is what `_{j}_scans.csv` holds now);
  individual scans are recoverable by differencing, same as the documented ESEEM
  cycle recovery (awg_phasing_insys.py:6221-6228).
- **ESEEM `save_each_cycle` 2D dumps** (`iq_cor == 0` branch,
  awg_phasing_insys.py:6236-6241) keep the file-per-cycle naming
  (`*_cycle{idx}.h5`) so each file stays a plain (I, Q, t, sweep) unit any reader
  understands. Single-file cycle stacking rejected: it would need a second reader
  convention for a rare mode. The `iq_cor == 1` per-cycle files are 1D → stay CSV.
- No compression (gzip costs CPU in the acquisition process for ~3× on smooth
  data; files are already 3.5× smaller than CSV; can be added later without
  format change).

## 2. Writer/reader API — extend `Saver_Opener`, sniff by extension

All changes in `atomize/general_modules/csv_opener_saver.py` (byte-identical in
all 5 repos today — keep it that way, see Stage 7).

- `save_data(filename, data, header='', mode='w', axes=None)`
  (csv_opener_saver.py:142): if `filename` ends `.h5` → delegate to a new private
  `_save_h5(filename, data, header, axes)`; else the existing CSV code runs
  unchanged (new `axes` kwarg ignored). `import h5py` lazily inside `_save_h5`
  (house pattern, commit f96a907).
- **The rule `_save_h5` follows: store the array verbatim, exactly as
  `np.savetxt` would lay it out.** `ndim == 1` → dataset `I` shape `(n,)`;
  `ndim == 2` → dataset `I` with the same rows and columns the CSV would have;
  `ndim == 3` → `I` = `np.transpose(data[0])`, `Q` = `np.transpose(data[1])`,
  mirroring the CSV split. `axes` optional throughout. This is what makes the
  core dimension-agnostic: the writer never has to guess whether a `(POINTS, 3)`
  array is a 1D result or a 2D map — it doesn't care, and neither does CSV today.
- **Interpretation lives in the reader, as it already does for CSV.** The only
  difference between `open_1d` and `open_2d` today is a transpose — `open_1d`
  returns `np.transpose(temp)` (:193), `open_2d` returns `temp` as-is (:211).
  The `.h5` branches keep exactly that asymmetry, so `save_data(f'{p}.h5',
  np.c_[x, I, Q])` → `open_1d` gives back `(3, POINTS)` columns, bit-identical in
  role to the CSV round-trip. No `kind` attribute, no shape sniffing, no second
  writer entry point.
- Every call site then selects the format by the *filename it passes* — no second
  code path at the ~10 write sites.
- `save_header` (csv_opener_saver.py:121): `.h5` → create the file with the
  `header` attr only (keeps the crash-leaves-a-header property); `save_data`
  `mode='w'` later rewrites it whole.
- `open_1d` / `open_2d` / `open_2d_appended` (csv_opener_saver.py:181, 199, 217):
  first line of each real branch: if path ends `.h5` → common `_open_h5` returning
  `(header_array, data)`. `open_1d` transposes what it gets, per the rule above.
  `open_2d` on an `.h5` with both `I` and `Q` returns them
  stacked as `(2, npoints, nsamples)` (ruled); with only `I`, the single matrix as
  today. Safe because the CSV path is untouched and still returns one matrix, so
  no existing call site changes shape — only `.h5` reads see a 3D return, and
  every `.h5` reader is new code. `open_2d_appended`: `np.array_split` on the
  `scans` dataset is unnecessary — return the slices list. `header_array` built
  as in §1. Test-mode branches untouched.
- **`.h5` precision is derived from `fmt`, so the two formats can never drift
  apart.** `save_data` gains `dtype=None`; when it is not given, `_save_h5`
  picks the dtype from the same `fmt` the CSV path would have used — ≤ 7
  significant digits (`%.6e`, the default) → float32, more (`%.9e`) → float64.
  Axes are always float64. An explicit `dtype` overrides.
  One rule in one place: a call site that raises its CSV precision raises its
  HDF5 precision by the same act, and cannot forget the second half. No caller
  passes `fmt` today (ruling B withdrawn, §3), so every file is `%.6e` /
  float32; the rule is there so the general core stays honest for scripts.
- `save_data` gains an explicit `fmt='%.6e'` parameter, threaded into the
  `np.savetxt` calls of both the `ndim == 2` (:147) and `ndim == 3` (:167)
  branches; default unchanged so every existing caller keeps `%.6e`; ignored on
  the `.h5` path. Needed because 1D result files (`np.c_[x, I, Q]`, shape
  `(POINTS, 3)`) and TR EPR's genuine 2D CSV (`np.transpose(data[0])`) are both
  `ndim == 2` — the caller, not the shape, selects the precision (§3
  "Numeric precision").
- `create_file_dialog` (csv_opener_saver.py:79): add `fmt='csv'` parameter,
  passed through to `FileDialog` (replacing the hardcoded `fmt='csv'` at :91).
  `open_file_dialog`'s multiprocessing branch also hardcodes `fmt='csv'` (:66-68);
  callers that must see `.h5` files pass `name_filters` (already supported).
- **Test mode preserved**: `save_data`/`save_header` test branches already just
  create-and-remove the file whatever its extension (csv_opener_saver.py:176-179,
  137-140) — no change, no h5py import in test mode.

## 3. Sizes and timings (estimates, stated assumptions)

Assumptions: disk ≥ 200 MB/s; `np.savetxt` throughput ~0.5–1 M values/s
(measured orders on comparable hardware, not benchmarked here); `%.6e` CSV ≈ 14
bytes/value including delimiter.

| Case (shape from code) | CSV today | HDF5 (float32) |
|---|---|---|
| AWG `_2d` dump, `data (2, 2000, 200)` = 0.8 M values (window 800 ns / 0.4 ns res, 200 sweep points) | 2 files, ~11 MB, ~1–2 s, once at end | 1 file, ~3.2 MB, ≲ 0.1 s |
| TR EPR final, `data[0] (4000, 2002)` = 8 M values (GUI defaults: 3000→4000 G, 0.5 G step, 4000-sample record) | ~112 MB, ~10–30 s `np.savetxt` | ~32 MB, ~0.3 s |
| TR EPR "Save Each Scan", 10 scans | 10 full rewrites → ~1.1 GB on disk, ~2–5 min total formatting time inside the acquisition loop | 10 slice appends into `scans` → one ~320 MB file, ~0.3 s per scan |

The per-scan slice write is the headline win: the scan loop stops paying a
full-array text-format cost per scan, and the incremental write code is ~10 lines
(create dataset with `maxshape=(None, ...)` once, `resize` + slice-assign per
scan).

### Numeric precision (owner-reviewed analysis, recorded)

- `%.6e` = 7 significant digits → relative rounding error 5e-8 … 5e-7 depending
  on the mantissa (half of the 1e-6 last-digit unit, over mantissa 10 … 1).
  float32: 2^-24 ≈ 6e-8 … 2^-23 ≈ 1.2e-7. Comparable bands — the CSV→HDF5
  switch neither gains nor loses meaningful precision. This is the quantitative
  backing for the float32 choice in §1.
- Rounding is applied once, to the final average at save time, not per shot — it
  does not accumulate with averaging.
- Crossover estimate: signal at 10% FS on a 14-bit ADC (LSB = 2^-14 ≈ 6.1e-5
  FS), storage rounding ≈ 5e-7 relative × 0.1 FS = 5e-8 FS. Per-shot noise of
  1 LSB averages down as 6.1e-5/√N and meets the rounding error at N ≈ 1.5e6
  shots per point; at a more realistic 10 LSB per shot, N ≈ 1.5e8 (~1e8). A
  12-hour DEER at 1 kHz over 200 points is 4.3e7 shots / 200 ≈ 2e5 per point —
  real experiments sit 1–3 decades below the crossover (arithmetic re-checked;
  the 1.5e6 figure uses the worst-case `%.6e` bound, i.e. no regression vs CSV
  even at the crossover).
- The genuine failure mode is not averaging but catastrophic cancellation:
  differencing two nearly equal traces with a large common offset *after*
  loading rounded values. tr_control.py:1600-1602 does its off-resonance
  subtraction in memory (float64) before saving, so it is safe today; the HDF5
  path must keep the subtraction pre-save and never move differencing to
  post-load.
- **Ruling B (1D result CSVs move to `%.9e`) was WITHDRAWN by the owner during
  implementation**: CSV and HDF5 precision stay in step at the default `%.6e` /
  float32 everywhere, so no call site passes `fmt`. Stage 2.6 is dropped. The
  `fmt` parameter itself still ships — it is the mechanism that couples the two
  formats (next bullet), and a script may raise both at once with it.
- **The two formats are kept in step by construction**: `_save_h5` derives its
  dtype from `fmt` unless told otherwise (§2), so `%.6e` ↔ float32 (both ~7
  digits) and `%.9e` ↔ float64 (10 digits, comfortably carried). Precision is
  chosen once per call site and applies to whichever container it writes.

## 4. Worker flag routing — mirror-rule analysis

`save2d` is threaded positionally through every `exp_*` signature and re-packed in
`atomize/epr_auto/engine/snapshot.py` (`WorkerArgs.save2d`, snapshot.py:259, used
at :299/:309/:318/:327) per the mirror rule. Two options for the new format flag:

- (a) extend each `exp_*` signature — trips the mirror rule: 5 GUI signatures ×2
  call-site blocks, plus `snapshot.py` `exp_*_args` packing, plus harness re-run.
- (b) **worker instance attribute** — the exact pattern already in use:
  `worker.awg_grid_cur = self.awg_grid()` (awg_phasing_insys.py:3689, 4142, 4169)
  and engine-side `worker.awg_grid_cur = ...` / `worker.scan_data_flag = 1`
  (executor.py:221, 225). The Worker instance is pickled with the bound method by
  `multiprocessing.Process`, so an attribute set before `.start()` reaches the
  child.

**Recommendation: (b).** Add class attribute `save_hdf5 = 0` on `Worker`
(awg_phasing_insys.py:4344) so unpatched engine code keeps working, set it in
`dig_start_exp` and `run_experiment`, read it in the workers via
`self.save_hdf5`. Signatures and `dig_start_exp` argument packing stay unchanged
→ `snapshot.py` needs no packing change; `executor.py` gets one optional line.
Re-run `~/epr_auto_dev/gui_vs_engine.py` regardless (it must report ALL PASS).
tr_control has no mirror constraint, but use the same attribute pattern there for
symmetry and to keep `exp_on`/`exp_test` signatures aligned.

## 5. Work plan (stages = separate reviewable commits)

### Stage 1 — writer/reader core (`csv_opener_saver.py`)
1. `_save_h5` + extension sniff in `save_data` (:142) and `save_header` (:121);
   `axes=None`, `dtype='float32'` and `fmt='%.6e'` kwargs on `save_data` (fmt
   into both savetxt branches, default keeps every existing caller at `%.6e`).
   Handle `ndim` 1, 2 and 3 by the verbatim rule (§2) — no dimension is a special
   case, and none of them needs a `control_center` caller to be worth having.
2. `_open_h5` + sniff in `open_1d` (:181), `open_2d` (:199),
   `open_2d_appended` (:217); `open_1d` transposes, `open_2d` does not.
3. `fmt='csv'` parameter on `create_file_dialog` (:79 → :91).
4. Lazy `import h5py` with a clear `general.message`-safe error if missing.
5. Round-trip check by hand, all three ranks: 1D `(n,)`, a `np.c_[x, I, Q]`
   `(POINTS, 3)` through `save_data`→`open_1d`, a 2D map through
   `save_data`→`open_2d`, and a `(2, ·, ·)` I/Q array through both writer and
   `open_2d`. Diff against the in-memory arrays (exact under `dtype=None`, within
   float32 rounding at the default); header string identity; and confirm the
   CSV and `.h5` round-trips return the same shapes for the same input.

### Stage 2 — AWG phasing tool (`awg_phasing_insys.py`)
1. Move Save2D to Settings and add the HDF5 checkbox beside it:
   - FFT tab (design_tab_3): drop `("Save 2D", "label_fft2")` from the labels
     list (:1284), `("Save2D", self.save_2d)` from `check_boxes` (:1341-1344),
     the tooltip (:1361) and the row-3 placement (:1379-1380); pull the hline
     (row 4, :1382), the four spin rows (5-8, :1384-1391), the closing hline
     (row 9, :1393) and the stretch row (:1395) up one row each. Move
     `self.save2d = 0` (:1404) to design_tab_6.
   - Settings tab (design_tab_6): create both label+checkbox pairs inline (the
     house pattern there, cf. `live_label` :1659) — "Save 2D" reconnecting the
     existing `save_2d()` handler (:2539), and "Save 2D as HDF5" with new
     handler `save_2d_hdf5()` + `self.save_hdf5 = 0` init. Place them as rows
     9-10 after the Accumulation Mode hline (row 8, :1758), close with an
     hline at row 11, and bump the stretch row `setRowStretch(9, 1)` (:1761)
     to 12.
   - Checked: nothing else references the FFT-tab grid rows or the Save2D
     widget beyond the handler (:2539-2545); presets do not persist either
     checkbox; `setTabTextColor` uses tab indices, not layout rows —
     unaffected.
   - Tooltips: Save2D keeps its current meaning (save the full 2D array
     alongside the 1D result); HDF5: "When Save 2D is on, every 2D dump is
     written as a single .h5 file instead of CSV; 1D result files stay CSV."
2. `Worker` class attr `save_hdf5 = 0` (:4344); set `worker.save_hdf5 =
   self.save_hdf5` beside `worker.awg_grid_cur` in `dig_start_exp` (:3689) and
   `run_experiment` (:4169). (`run_main_experiment`/`dig_on` never saves — skip.)
3. At each `if save2d == 1:` site (:5542, 6211, 6710, 7273, 7788):
   `file_data2 = file_data.replace(".csv", "_2d.h5" if self.save_hdf5 else
   "_2d.csv")`; pass `axes=(x_axis_plot·…, sweep)` (per-worker: time/field/tau
   axis already in scope at each site).
4. `iq_cor == 0` primary dumps (:5527-5533, 6196-6202, and the exp_field /
   exp_log / exp_amplitude twins): same filename swap under `self.save_hdf5`
   (ruled in, §0.3).
5. ESEEM `save_each` (:6229-6241): the `iq_cor == 0` per-cycle 2D dumps switch
   to `_cycle{idx}.h5` (ruled in, §0.3); `iq_cor == 1` 1D rows stay CSV.
6. ~~1D result CSVs go to `fmt='%.9e'`~~ — **dropped**, ruling B withdrawn (§3):
   every writer keeps the default `%.6e`, matching the float32 HDF5 data.
7. Pre-flight in test mode; then live check on the bench.

### Stage 3 — epr_auto engine mirror
1. `executor.py`: set `worker.save_hdf5` from an optional protocol/config knob
   (default 0), one line next to :221–225. No `snapshot.py` packing change
   (attribute route).
2. Re-run `~/epr_auto_dev/gui_vs_engine.py` → ALL PASS required.

### Stage 4 — TR EPR (`tr_control.py`)
1. UI: "Save as HDF5" in the `labels` list (:67), checkbox in `check_boxes`
   (:162-164), handler + `self.save_hdf5 = 0` init (:29-30), grid row inserted
   after Two-Side Measurement (:240-241, renumber rows 10+).
2. `open_dialog` (:581-590): `create_file_dialog(..., fmt='h5' if
   self.save_hdf5 else 'csv')`; fix the preset-name derivation
   `file_data.split(".csv")[0]` → `file_data.rsplit('.', 1)[0]` (:587).
3. Worker: class attr `save_hdf5 = 0` (:1117); GUI sets `worker.save_hdf5` in
   `run_main_experiment` (:594) and the test spawn (:468). Derived filenames
   `_osc2` / `_pulse` (:1253-1256) switch extension with the primary.
4. Save sites — all p9 branches (`.h5` filename makes `save_data` route itself):
   - each-scan p9==1/p11==1 (:1637-1642): first scan creates the file with `I`,
     `t`, `sweep` and the `scans` dataset (`maxshape=(None, points+1,
     real_length)`); later scans append a slice instead of writing
     `_{j}_scans.csv`. This is the one site needing an explicit h5 branch in the
     worker (a small `_append_scan_h5` helper or direct h5py calls, ~10 lines)
     because slice-append is not expressible through `save_data`.
   - end-of-run (:1678, :1724-1725, :1771-1773): unchanged calls, `.h5` names;
     pass `axes=(t = arange(real_length)·t_step, sweep = START_FIELD +
     arange(points+1)·FIELD_STEP)` — note column 0 is the off-resonance trace,
     record that in the header text.
   - `exp_test` (:1789): its save calls are already commented out (:1964-2441);
     leave untouched.
5. Resolve the p9==3 `data[3]` bug first (§0.4) as its own commit.

### Stage 5 — readers (treatment tools + main window)
1. `data_treatment_2d.py` `open_iq` (:845-881): extension branch — `.h5` loads
   through `open_2d` (§2). A stacked `(2, npoints, nsamples)` return splits as
   `raw_i, raw_q = arr[0], arr[1]`; an I-only `.h5` returns 2D → `raw_i = arr`,
   `raw_q = zeros_like` with the same status message as a missing `_1.csv`
   today (:857-858). Axis widgets are driven directly from the `t`/`sweep`
   datasets (`dx = t[1]-t[0]`, `x0 = t[0]`, likewise `sweep` → Y), skipping the
   regex `_parse_axis_header`; header lines come from the attr. The tool's
   display pipeline is unchanged — it already holds and shows I/Q as a pair.
   The leading-plane stacking convention itself is the one `plot_2d` consumers
   already use: LivePlot's 2D dock is a pyqtgraph `ImageView`, so a
   `(planes, x, y)` push (tr_control.py:1609/1611, the AWG live plots) shows
   the leading axis as the frame selector, and widgets.py:2040-2051 explicitly
   preserves the viewed frame across re-pushes ("e.g. real/imag") — no new
   convention is invented. `.csv` path untouched incl. the `_1.csv` companion.
   Pass `name_filters=['Data (*.csv *.h5)', 'All files (*)']` to the open dialog
   (today it falls into the hardcoded csv filter). Model on `open_bruker`
   (:937) which already does multi-format + axis population.
2. `data_treatment.py` (1D tool) — **in scope: it must open 1D `.h5`.** Its
   loader already routes through `self.opener.open_1d` (:983), so the data half
   is inherited from Stage 1 with no change, including the `> 6 columns → use
   the 2D tool` guard, which keeps working since `open_1d` transposes `.h5` the
   same way it transposes CSV. Two things do need doing:
   - `open_csv` (:1002) calls `read_header(file_path)` (:1008) before loading —
     a text scan that returns nothing useful for an `.h5`. Give it an `.h5`
     branch (see 3) so column labels and the header viewer still populate.
   - `_open_dialog` for this path takes no `name_filters` (:1003), so it falls
     to the default CSV filter — widen it to `['Data (*.csv *.h5)',
     'All files (*)']`, the same list Stage 5.1 gives the 2D tool. Model the
     multi-format dialog on `open_bruker` (:1029-1035), which already does it.
   `deer_analysis.py` (open_1d at :1231) inherits the data path identically;
   widen its filter too if it is to accept `.h5`, otherwise leave it.
3. `header_view.py` `read_header` (:60): add an `.h5` branch returning
   `attrs['header'].splitlines()`. One place, and both treatment tools plus the
   header viewer window pick it up. The 2D tool passes lines it already holds,
   so it is unaffected either way.
4. **Main-window openers — the "Open 1D / 2D / TR Data" context-menu actions.**
   These are a fourth consumer the earlier draft missed, and they do *not* go
   through `Saver_Opener` at all — each scans leading `#` lines itself and calls
   `np.genfromtxt` directly, so none of them inherits `.h5` from Stage 1:
   - `main_window.py` `open_file` (1D, :1417; genfromtxt :1439,
     `skip_header=1, comments='#'`, then `np.transpose`).
   - `main_window.py` `open_file_2d` (:1481; genfromtxt :1502 with a counted
     header; `setImage(data, axes={'y': 0, 'x': 1})`).
   - `main.py` `open_file_tr` (:163; genfromtxt :199), which additionally regex-
     parses Start Field / Field Step / Time Resolution out of the header text
     (:184-186) to set the axes, then stacks raw + baseline-subtracted planes
     into `data_3d` for the frame view (:205).
   Change for each: sniff the extension, and for `.h5` take data and header text
   from the shared reader (`open_1d` / `open_2d`, §2) instead of the
   `#`-line scan. The regex axis parsing in `open_file_tr` needs no rework — the
   header attr yields the same text those regexes already expect — but prefer
   the `t`/`sweep` datasets when present, falling back to the regexes. An `.h5`
   returning a stacked `(2, ·, ·)` array goes straight to `setImage` as frames,
   the same convention as `data_3d` there today. Leave the CSV paths untouched
   rather than refactoring them onto `Saver_Opener`; that is a separate cleanup.
5. Both file dialogs hardcode `filter = "CSV (*.csv)"` — `file_dialog`
   (main_window.py:1517) and `file_dialog_2d` (:1762, shared by Open 2D and, via
   `is_2d=True` at main.py:27, Open TR). Widen both to `"Data (*.csv *.h5)"`.
   Without this the new files are simply invisible in the picker.

### Stage 6 — packaging + docs
1. `pyproject.toml` (:27): add `"h5py>=3.8"` to core `dependencies`.
   Rationale: a save-time ImportError loses a finished acquisition; an optional
   extra invites exactly that. The lazy import keeps test mode and non-saving
   paths import-clean anyway. Both boxes need one install (`python -m pip` on
   Windows dev, `python3 -m pip` on the Linux spectrometer box; carry a wheel if
   the box is offline).
2. Docs repo `/home/anatoly/atomize_docs` (MkDocs):
   - `docs/functions/general_functions/data_managment.md` — new `.h5` behavior of
     `save_data` / `save_header` / `open_1d` / `open_2d` / `open_2d_appended`
     (incl. the stacked I/Q return), the new `fmt` / `axes` / `dtype` parameters
     of `save_data`, the `fmt` parameter of `create_file_dialog`, and the file
     layout tree from §1. Document `.h5` as available at every rank, not as a
     2D-only feature — a script may save and reopen 1D data this way even though
     no control-center tool does; include the `dtype=None` note for scripts that
     want more than float32 precision.
   - `docs/projects/endstation.md` — TR EPR machine section (:25) and the
     phasing-tool section: the two checkboxes, file naming, `scans` dataset.
   - The main-window "Open 1D / 2D / TR Data" actions and the 1D/2D Data
     Treatment tools now accept `.h5` as well as `.csv` — say so wherever those
     openers are described.
   - `docs/projects/epr_auto/protocol_settings-adjacent pages` only if the Stage 3
     protocol knob is exposed (then `docs/projects/epr_auto/protocols.md`).
   - In-tree mirror `atomize/documentation/functions/general_functions/
     data_managment.md` is byte-identical to the docs-repo copy today — update
     both identically.

### Stage 7 — port to the fork family
Authoritative list from `/home/anatoly/atomize_sync/sync_check.py`: lead
`Atomize` (plain) + forks `Atomize_ITC`, `Atomize_NIOCH`, `Atomize_NIOCH_Q`,
`Atomize_Cryomech`, all under `/home/anatoly/`. Verified per-fork state:

| File | Atomize (plain) | NIOCH | NIOCH_Q | Cryomech | Port route |
|---|---|---|---|---|---|
| `general_modules/csv_opener_saver.py` | present, byte-identical to ITC (all 5, LF) | same | same | same | plain-led (`PLAIN_LEAD`): `--lift` ITC→plain, then `--sync` plain→forks; stays identical everywhere |
| `control_center/data_treatment_2d.py`, `data_treatment.py`, `deer_analysis.py`, `header_view.py` | absent | present | present | absent | ITC-led shared CC tools: `--sync-cc` ITC→{NIOCH, NIOCH_Q} |
| `main/main_window.py` (Open 1D/2D handlers + both dialog filters, Stage 5.4-5.5) | **byte-identical to ITC in all 4** (verified) | same | same | same | plain-led like `csv_opener_saver.py`: `--lift` ITC→plain, `--sync` plain→forks; must stay identical |
| `main/main.py` (`open_file_tr`, Stage 5.4) | **absent** (no extended main) | present, differs | present, differs | present, differs | **hand-port** into the three forks that have it; each carries its own tab set, so locate `open_file_tr` fresh per fork |
| `control_center/awg_phasing_insys.py` | absent | absent | absent | absent | ITC-only, nothing to port |
| `control_center/awg_phasing.py` (Spectrum variant, has `save2d`, 23 hits, own Settings tab at NIOCH :1747) | absent | present | present | absent | **hand-port** Stage-2 pattern (checkbox, worker attr, write-site renames); Spectrum digitizer differs — adapt per file, verify each write site, no blind copy |
| `control_center/phasing_insys.py` / `phasing.py` | absent | `phasing.py`, no save2d | `phasing.py`, no save2d | absent | out of scope — no 2D data (§0.1) |
| `control_center/tr_control.py` | absent | absent | present, **differs from ITC's** | absent | **hand-port** Stage 4 diff-by-diff (fork-divergent; verify its p9 modes/oscilloscope set first) |
| `pyproject.toml` | no h5py | no h5py | no h5py | no h5py | add `h5py>=3.8` to every repo that carries the h5 core (all 5, since `csv_opener_saver.py` is shared identical; the lazy import means plain/Cryomech only hard-need it when an `.h5` file is actually touched — still add it for uniformity so a synced saver never lands ahead of its dependency) |

Line endings: every port target above checked LF (the known CRLF file in the
family is `widgets.py`, untouched here). Still re-check any file the port edits
before committing — `sync_check.py` normalizes CRLF in comparisons, git does not.

Port checklist (ordered):
1. Lift `csv_opener_saver.py` ITC→plain (`sync_check.py --lift`), review, then
   `--sync` plain→NIOCH, NIOCH_Q, Cryomech.
2. `--sync-cc` the treatment tools + `header_view.py` ITC→NIOCH, NIOCH_Q.
2b. Lift `main/main_window.py` ITC→plain then `--sync` to all forks (identical
   everywhere today — the Open 1D/2D handlers and both dialog filters). Then
   hand-port `open_file_tr` into `main/main.py` for NIOCH, NIOCH_Q and Cryomech;
   plain has no `main.py` and needs nothing.
3. Hand-port the AWG checkbox/flag/write-site changes into
   `Atomize_NIOCH/…/awg_phasing.py` and `Atomize_NIOCH_Q/…/awg_phasing.py`
   (their Settings tabs and `save2d` sites exist but line numbers and the
   Spectrum acquisition code differ — locate each `if save2d == 1:` site fresh).
   The `%.9e` 1D sites are NOT part of this (ruling B withdrawn, §3): every 1D
   writer in the forks keeps the default `%.6e`, as in ITC.
4. Hand-port the TR EPR changes into `Atomize_NIOCH_Q/…/tr_control.py` against
   its own diff from ITC.
5. Add `h5py>=3.8` to the four other `pyproject.toml`s.
6. Update each fork's own docs page in `atomize_docs` if it has one
   (`docs/projects/xband.md`, `qband.md` for the NIOCH pair — check whether they
   document Save 2D once the port lands).
7. Re-run `/home/anatoly/atomize_sync/sync_check.py` — must show no DRIFT (add
   nothing to EXPECTED: no file becomes newly divergent; `csv_opener_saver.py`
   must come back identical across all 5).
8. Re-run `~/epr_auto_dev/gui_vs_engine.py` (ITC only) if anything in the engine
   or the AWG GUI moved during the port — ALL PASS.

## 6. Risks / open questions

- tr_control p9==3 `data[3]` out-of-bounds (§0.4) — precondition fix.
- `create_file_dialog` gains `fmt`; the file it pre-creates (`open(file_path,
  'w').close()`, csv_opener_saver.py:86/94) is then a 0-byte `.h5` until the end
  of the run — harmless (h5py `'w'` overwrites), but a crashed run leaves an
  invalid `.h5` where a crashed CSV run left a valid header-only file. The
  `save_header`-creates-attrs behavior (Stage 1.2) restores that property for TR.
- h5py availability on the spectrometer box: verify/install before landing Stage
  2+; the remote bench box (`fel@172.16.16.1`) has no internet — needs a carried
  wheel if it ever runs these tools.
- The GUI checkbox does not persist across restarts (matches Save2D behavior —
  none of these checkboxes persist; not a regression).
- Timing/size numbers in §3 are estimates from array shapes and `%.6e` width;
  the `np.savetxt` throughput figure is an assumption — measure once on the
  Linux box during Stage 4 review if the per-scan win needs defending.
