# Full 2D data saving for epr_auto

Written 2026-09-24. Status: implemented 2026-09-24 (all sections below); hardware check open in [HARDWARE_CHECKLIST.md](HARDWARE_CHECKLIST.md).

## Goal

`exp.t1`, `exp.t2` and `field.edfs` get an opt-in `save_2d: true` that keeps the complete I/Q matrices (one time-domain trace per sweep point) next to the ordinary 1D CSV, as HDF5 only. Adaptive decisions (SNR, `max_duration`, `adjust_range`) keep working on the worker-side per-column integrals sent as ScanData; the matrix is written by the worker at the end of the acquisition, never shipped over the pipe.

## What already exists

- `awg_phasing_insys.Worker`: every experiment branch (Linear Time, Log Time, Field, Amplitude, ESEEM) writes `<base>_2d.h5` beside `<base>.csv` when `save2d == 1` and `self.save_hdf5 == 1` (`iq_cor == 1` keeps the 1D CSV as the primary file). Datasets `I`, `Q` (sweep points × window samples), axes `t` and `sweep` in seconds, attrs `t_unit`/`sweep_unit`, and the full text header (field, RV, attenuators, synthesizer, repetition rate, temperatures, pulse lists) as file attrs. Writer: `csv_opener_saver.Saver_Opener._save_h5`.
- `engine/snapshot.py`: `WorkerArgs.save2d` field; `build_worker_args(..., save2d=)`.
- `engine/executor.py::_hand_attrs`: already forwards `worker_args.save_hdf5` to `worker.save_hdf5`.
- `h5py>=3.8` is a hard dependency in `pyproject.toml`.
- `primitives/preliminary.py::_amplitude_sweep` already uses `save2d=1` with CSV and reads `_2d.csv` / `_2d_1.csv` back. Leave it untouched.

The GUI worker does not change. The `gui_vs_engine.py` harness is affected only by a defaulted `WorkerArgs` field.

## Changes

### 1. Step parameter (`atomize/epr_auto/steps.py`)

Add to `exp.t2`, `exp.t1` and `field.edfs`:

```python
'save_2d': Bool(default=False,
                help='also save the full I/Q matrices of every sweep point '
                     'as <file>_2d.h5 (datasets I, Q, t, sweep); size is '
                     'points x window samples x 8 bytes'),
```

Thread `save_2d` through `exp_t2`, `exp_t1`, `field_edfs` into the primitives.

### 2. WorkerArgs (`atomize/epr_auto/engine/snapshot.py`)

Add `save_hdf5: int = 0` to the `WorkerArgs` dataclass. Arg tuples are unchanged, so engine and GUI stay equivalent.

### 3. Shared helpers (`atomize/epr_auto/primitives/tune.py`, next to `_build`/`_acquire`)

```python
def _full_2d(wa, enabled):
    wa.save2d = wa.save_hdf5 = int(bool(enabled))

def _data_files(path):
    files = {'data_file': str(path)}
    path_2d = Path(path).with_suffix('').as_posix() + '_2d.h5'
    if os.path.exists(path_2d):
        files['data_file_2d'] = path_2d
    return files
```

The existence check covers Stop/partial saves and dry runs without a file. Nothing reads the matrix back.

### 4. Wiring

`primitives/exp.py`:

- `t2` (after `_build`, line ~617) and `t1` (~671): `_full_2d(wa, save_2d)`.
- `_revised_sweep` (`T2_revised` ~371, `T1_revised` ~396 and ~405) and `_reuse_range` (~436): after each `_build`, `_full_2d(args, wa.save2d)` so the revised/reused acquisition inherits the flag. Without this the early range extension's main acquisition would lose its matrix.
- `_finish`: replace `'data_file': path` with `**_data_files(path)`.
- `_range_record`: same, so `range_adjustment.initial` / `.final` list both matrices.

`primitives/field.py::edfs`: `_full_2d(wa, save_2d)` after `_build` (~121); both result dicts (~163, ~172) use `_data_files(path)`; the one-time wider-span escalation call passes `save_2d` on.

### 5. Stop path

`exit → readout → Open/FL → save` writes the matrix in the same worker branch as the CSV, so partial data survive Stop. The `_WIND_DOWN_S = 60` grace is ample: a T1 with 100 points and a 15 µs window at decimation 1 is 100 × 37500 × 2 × 4 B ≈ 30 MB, written in well under a second.

## Checks without hardware

- `python3 -m atomize.epr_auto validate` and `run --test` on a copy of `protocols/t2_auto_range.yaml` with `save_2d: true` on the T2 step and on an EDFS step.
- Regenerate the step reference with `atomize/epr_auto/docgen.py`.
- Re-run `~/epr_auto_dev/gui_vs_engine.py` (must report ALL PASS) because `WorkerArgs` gained a field.
- Extend `atomize/script_examples/epr_auto/early_range_checks.py`: the flag is inherited by `_revised_sweep` and `_reuse_range`, and `_data_files` reports `data_file_2d` only when the file exists.

## Checks on hardware (add to HARDWARE_CHECKLIST.md)

- T2 with `save_2d: true` and `target_snr`: `_2d.h5` appears; `I`/`Q`/`t`/`sweep` shapes match the CSV; integrating `I`/`Q` over the echo window through `digitizer_demodulate` reproduces the 1D CSV.
- Stop mid-scan: a partial matrix is written and the manifest records `data_file_2d`.
- `adjust_range` with an extension: two matrices, both recorded under `range_adjustment`.
- EDFS with `save_2d: true`: `sweep` axis in Gauss units per the worker header, matrix shape = field points × window samples.

## Documentation

- `atomize_docs/docs/projects/epr_auto/protocols.md`: paragraph on `save_2d`, file naming, HDF5 layout, size estimate; `steps.md` from docgen.
- `protocols/t2_auto_range.yaml`: add `save_2d: true` as the example.
- `ROADMAP.md`: move the "Full-2D acquisitions" backlog item to Implemented, add a session-log entry.

## Decisions

- HDF5 only; no CSV option for the matrices (2026-09-24).
- Scope: `exp.t1`, `exp.t2`, `field.edfs`. `tune.*` and the preliminary amplitude sweep stay as they are.
- Per-step parameter, no protocol-level default.
