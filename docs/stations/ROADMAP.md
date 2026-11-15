# Two repos instead of five — roadmap

Created 2026-11-15. Status: Phase 1 done and committed in plain Atomize, the forks and `atomize_sync` (not synced).

## Resume here

State on 2026-11-15, end of session 2. Phase 1 is committed in every repo (not pushed, not synced).

| Repo | Commit |
|---|---|
| `Atomize` | `b5716b8` station hooks, runtime paths via `lconf.ROOT_DIR`, DAC config from the user copy, `awg.md` / `digitizer.md`, `np.row_stack` → `np.vstack` (numpy 2), Liveplot "Show current run" with pins and updated tests, `PyQt6>=6.12`, version 0.5.0 |
| `Atomize_ITC` | `atomize/station.py`, plain's `local_config.py`, the three `epr_auto` check scripts and `awg_phasing_insys.py` find `libs/` via `lconf.ROOT_DIR`, the same Liveplot change, `PyQt6>=6.12`, this roadmap |
| `Atomize_NIOCH` `8aeeb73`, `Atomize_NIOCH_Q` `a1470b8`, `Atomize_Cryomech` `73a2901` | `atomize/station.py`, plain's `local_config.py`, `PyQt6>=6.12` |
| `atomize_sync` | `8611b65` `local_config.py` and `atomize/__init__.py` plain-led, `station.py` per fork |

Checks done: plain `pytest tests` 187 passed, 0 failed; ITC `tests/test_liveplot_runs.py` 33 passed.
On a scratch copy of ITC with plain's files synced in, the three `epr_auto` check scripts and
`epr-auto run protocols/tune_up.yaml --test` pass, and the real `libs/exam_*.ini` stay unchanged.
Session 1: a real `--sync` on scratch copies of all repos gave no drift and identical results in
every fork. The Liveplot test crash (about 1 run in 4) came from PyQt6 6.9–6.11; both venvs now
have 6.12.1 (0 crashes in 30 runs). pytest is installed in both venvs (with `uv`).

Session 2, after the push: `sync_check.py --sync` copied plain's 9 shared files into each fork
(36 in all); the audit reports every fork in sync. The failing fork tests were old tests that the
code had moved past; they are fixed: the Liveplot tests in NIOCH, NIOCH_Q and Cryomech (as in
plain), ITC `test_save_cancellation.py` and NIOCH `test_phase_saving.py` (the detection correction
added to the AWG tools), ITC `test_tr_two_fields.py` (scope stand-in in test mode), NIOCH_Q
`test_tr_two_fields.py` (own temporary user config). In a clean venv with no Atomize installed:
ITC 361 passed, NIOCH 115, NIOCH_Q 130, Cryomech 186, plain 187, all 0 failed. In the real ITC
folder the three `epr_auto` check scripts and `epr-auto run protocols/tune_up.yaml --test` pass,
and `libs/exam_*.ini` stay unchanged. Example scripts fixed and passing in test mode: `math.py` (ITC,
Cryomech) and NIOCH `math_test.py` take plain's version (`csv_opener_saver`); NIOCH_Q
`CuPr_set_temperature.py` uses PyQt6; NIOCH `devices_tests/ask_PB_Insys.py` runs on
`PB_ESR_500_pro` (NIOCH has no Insys board or `libs/`) with the trigger on `DETECTION`. The sync, the
test fixes and the script fixes are committed in the four forks (not pushed).

Next, in order:

1. Push the four forks (the user does this).
2. Start Phase 2.

Decisions made: station repo `Atomize_stations`, fresh history; `Keysight_2000_Xseries_2.py` stays a
station device; `PB_Insys_DAC_config.ini` is read from the user copy. On the spectrometer PC only
`~/sources/Atomize_ITC` exists (no plain Atomize, no `atomize_sync`).

To continue, open Claude Code in `Atomize_ITC` and say: "Continue the station migration from
`docs/stations/ROADMAP.md`, Resume here."

## Goal

- **`Atomize`** stays the public core, with no station code.
- **One station repo** (`Atomize_stations`) holds ITC, NIOCH, NIOCH_Q and Cryomech,
  each in its own folder, installed on top of the core.
- No copies of the core in the stations, so nothing to sync from plain.
- ITC moves first. The other stations follow the same recipe.

## Design in short

- Each station folder keeps today's layout: `itc/atomize/control_center/`, `itc/atomize/epr_auto/`,
  `itc/atomize/main/main.py`, `itc/libs/`, `itc/protocols/`, `itc/icons/`, `itc/tests/`, `itc/docs/`.
- The station's files join the core under the same `atomize` name. Import lines, protocol files,
  user scripts and the `gui_vs_engine.py` harness therefore stay as they are.
- A box installs the core and its own station folder. That install is what tells the box which
  station it is.
- The app name stays `atomize-itc`, so the user configs on the box are found and left untouched.

## Open decisions

- [x] Name of the station repo: `Atomize_stations`.
- [x] History: start fresh; the old history stays in the archived repos.
- [ ] Where this roadmap lives after the move (proposed: `itc/docs/stations/` in the new repo).

## Phase 1 — Prepare plain Atomize

Small changes, invisible to a general user. Done and committed 2026-11-15 (`Atomize` `b5716b8`). `pytest tests` gives 9 failed / 178 passed both before and after; the 9 are old failures
in `tests/test_liveplot_runs.py`.

- [x] Lift what ITC leads on into plain: `documentation/functions/awg.md` and `digitizer.md`.
      `Keysight_2000_Xseries_2.py` stays a station device; the differing `script_examples/` and
      `tests/` stay with the station.
- [x] Let an installed station add its folders to `atomize` and to `atomize.device_modules`
      (one line in each `__init__.py`).
- [x] A station declares itself with a small `atomize/station.py` holding its app name. The core
      takes the app name and the station folder from it, otherwise `atomize-py` and its own folder
      (`local_config.py`, `last_dir.py`). ITC then uses plain's `last_dir.py`.
- [x] Runtime files (`libs/`, `bridge.param`, `libspinapi.so`, the Liveplot layout) are looked up in
      the station folder: `Insys_FPGA.py`, `Micran_X_band_MW_bridge_v2.py`, `insys_status.py`,
      `spinapi.py`, `main_window.py`. Without a station the places are today's.
- [x] `Insys_FPGA.py` reads `PB_Insys_DAC_config.ini` from the user copy, like every other config.
      Before, it read the copy in the code folder, which in the new layout would be plain's,
      without ITC's I/Q tables.
- [x] First-start copy of configs and example scripts: core defaults first, then the station's own
      files on top.
- [x] Each fork has an `atomize/station.py` with its app name and plain's `local_config.py`;
      `sync_check.py` treats `local_config.py` and `atomize/__init__.py` as plain-led and
      `station.py` as per fork. Not yet synced: `--sync -n` lists the same 7 files for each fork.
- [x] Before syncing ITC: the three `epr_auto` check scripts (`insys_ini_checks.py`,
      `live_rate_worker_checks.py`, `live_rate_driver_checks.py`) redirect `lconf.ROOT_DIR`
      instead of `insys.__file__`. The DAC config is only read, so it needs no redirect.
      `awg_phasing_insys.py` also found `libs/exam_adc.ini` through the driver's folder; it now
      uses `lconf.ROOT_DIR` too.
- [x] Version becomes 0.5.0.
- [x] Check: plain alone works as before (`pytest tests`, three scripts in test mode, the main
      window opens, configs still under `atomize-py`), and a made-up station joins correctly.

## Phase 2 — Build the station repo with the ITC folder

- [ ] Create the repo and the `itc/` folder with its own `pyproject.toml`
      (name `atomize-itc`, commands `atomize-itc` and `epr-auto`, needs `atomize-py>=0.5` and `pyyaml`).
- [ ] Move in everything ITC-only: `control_center/`, `epr_auto/`, `main/main.py`,
      `main/protocol_launcher.py`, `libs/`, `general_modules/libspinapi.so`, `protocols/`, `icons/`,
      `docs/`, the ITC-only `script_examples/` and `tests/`, `CLAUDE.md`, `AGENTS.md`, `.claude/agents/`.
- [ ] Station config files: the 9 device configs that differ from plain, `config.ini`, the Sibir
      calibration curve.
- [ ] `atomize/station.py` with the app name `atomize-itc`.
- [ ] The station states the lowest core version it accepts and says so clearly at start if the
      core is older.
- [ ] `python -m atomize` runs the core's `atomize/__main__.py` (plain window, no endstation tab),
      because the core folder comes first. Decide: drop that command from the ITC docs in favour of
      `atomize-itc`, or let the core's `__main__.py` start the station's window when one is installed.
- [ ] `main.py`: point the working folder at the station's own `libs/` (today's `ptm = '../../libs'`
      would land in the core folder).
- [ ] The Sibir calibration curve is read from the core's config folder by `ITC_FC.py`: same decision.
- [ ] `math_modules/tests/test_preset_loader.py` needs the presets folder: move it to the station.
- [ ] Leave out every file that is the same as in plain.

## Phase 3 — Check on the development machine

- [ ] Fresh environment, install the core and `itc/`.
- [ ] File check: core + `itc/` together give the same files as today's `Atomize_ITC`, apart from a
      short expected list.
- [ ] `pytest` passes.
- [ ] `atomize-itc` opens with the endstation tab; every control-center tool opens.
- [ ] One script per experiment type passes in test mode.
- [ ] `epr-auto run protocols/tune_up.yaml --test` passes.
- [ ] A fresh start with no user configs copies the right ITC values.

## Phase 4 — Spectrometer PC

Linux box, `python3`. Today only `~/sources/Atomize_ITC` is there; plain Atomize and `atomize_sync`
are not installed and are not needed on the box. Needs about half a day with no experiment planned.
`~/sources/Atomize_ITC` is not touched, so going back takes a minute.

**A. Record and back up**

- [ ] Close Atomize and all control-center windows.
- [ ] `cd ~/sources/Atomize_ITC && git status` — commit and push any local edits made on the box.
- [ ] `pip show atomize-itc` and `which atomize-itc epr-auto` — note how it is installed now.
- [ ] Reference results: `gui_vs_engine.py` reports ALL PASS (if the harness is on the box); record a
      standard echo on the usual sample (amplitude, phase, settings).
- [ ] Compare `PB_Insys_DAC_config.ini` in the repo and in `~/.config/atomize-itc/device_config/`;
      the repo one is in use today and holds the I/Q tables.
- [ ] Back up the user configs: `cp -a ~/.config/atomize-itc ~/atomize-itc_config_backup`.
- [ ] Back up the local files kept inside the repo folder (not in git, or changed at runtime):

      ```bash
      cd ~/sources/Atomize_ITC
      git ls-files --others --modified | grep -v __pycache__ | sort -u > ~/itc_local_files.txt
      rsync -a --files-from=$HOME/itc_local_files.txt . ~/itc_local_backup/
      ```

      This covers the `*.param` files, `libs/status`, the Liveplot layout, saved presets in
      `atomize/epr_auto/presets/`, `protocols/tuned/` and `protocols/runs/`.

**B. Install**

- [ ] `pip uninstall atomize-itc`
- [ ] `git clone` plain Atomize to `~/sources/Atomize`, then `pip install -e ~/sources/Atomize`.
- [ ] `git clone` the station repo to `~/sources/Atomize_stations`, then `pip install -e ~/sources/Atomize_stations/itc`.
- [ ] Copy the I/Q tables (`iq_cal_*`, `rx_cal_*`) into the user copy of `PB_Insys_DAC_config.ini`.
- [ ] Put the local files back: `rsync -a ~/itc_local_backup/ ~/sources/Atomize_stations/itc/`
- [ ] Desktop launcher and icons: `python3 ~/sources/Atomize_stations/itc/icons/install_desktop.py`
- [ ] `gui_vs_engine.py` (if on the box): point it at the new presets folder if the old path is written in it.

**C. Checks without hardware**

- [ ] `atomize-itc` starts with the endstation tab.
- [ ] `diff -r ~/.config/atomize-itc ~/atomize-itc_config_backup` shows no differences.
- [ ] A known script passes with Test Scripts ticked.
- [ ] `epr-auto run protocols/tune_up.yaml --test` passes.
- [ ] `gui_vs_engine.py` reports ALL PASS (if on the box).
- [ ] `pytest` passes.

**D. Checks with hardware (operator present)**

- [ ] Open each tool once: MW bridge, field, temperature, tune preset, RECT phasing, AWG phasing,
      CW, TR with its scopes.
- [ ] The Insys board opens and the standard echo matches the reference from step A.
- [ ] Live edit works in the AWG phasing tool.
- [ ] One short protocol runs live from the launcher.

**Going back**

```bash
pip uninstall atomize-itc atomize-py
pip install -e ~/sources/Atomize_ITC
```

The user configs are the same folder in both setups, so nothing is lost either way. Copy back any
`*.param` or preset changed in the meantime.

## Phase 5 — Settle ITC

- [ ] One week of normal use on the new setup.
- [ ] Repeat the install on the Windows development machine (`python`, test mode only).
- [ ] `sync_check.py` (development machine): ITC leaves the list of forks; it stays the source for the shared
      control-center tools of NIOCH and NIOCH_Q, read from `Atomize_stations/itc/`.
- [ ] Archive `Atomize_ITC` on GitHub (read-only) with a readme line pointing to the new repo.
- [ ] Update install instructions in `atomize_docs` where they mention the ITC repo.

## Phase 6 — Later

- [ ] NIOCH_Q, NIOCH and Cryomech, each with Phases 2–5. Device differences: values go to config
      files, station behaviour goes to a small extension in the station folder.
- [ ] Merge the control-center tools that exist in several versions, one at a time when touched.
- [ ] Archive `atomize_sync` once the last station has moved.
