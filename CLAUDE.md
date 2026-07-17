# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`Atomize_ITC` is the EPR-endstation variant of [Atomize](https://github.com/Anatoly1010/Atomize) — a modular instrument-control framework for spectrometers. It extends upstream Atomize with an "EPR Endstation Control" tab in the main window (`atomize/main/main.py`), Insys FM214x3GDA FPGA support (DAC / ADC / TTL pulser via ctypes against `libs/lib*.so`), and a set of dedicated control-center subprocesses (CW EPR, TR EPR, oscilloscopes, MW bridge, magnetic field, temperature, resonator tuning, RECT/AWG phasing).

Python is the scripting language. Experimental scripts are ordinary Python files that import device-module classes and call `general` functions to push data to the LivePlot-based GUI.

## Common commands

**This machine runs Linux and has `python3` only — there is no `python` on PATH.**
Install (`pip install -e .`), the optional extras, and the `atomize-itc` /
`epr-auto` entry points are all defined in `pyproject.toml` — read it rather than
trusting a copy here. The invocations that are NOT guessable from the manifest:

```bash
python3 -m atomize path/to/script.py    # launch the GUI and open a script in it
python3 path/to/script.py test          # smoke-test one script, no GUI (see "Test mode")
python3 -m atomize.epr_auto run <protocol>.yaml --test   # protocol runner, dry-run
```

There is no unit-test suite; the project's pre-flight check is **test mode** (see "Test mode" below). Example/demo scripts live in `atomize/script_examples/` (not `atomize/tests/` — that path in the upstream README is stale here).

## Big-picture architecture

### Multi-process model

The GUI is **one Qt process that spawns many `QProcess` children**, not a monolithic event loop:

- `atomize/main/main.py:MainExtended` — extends the upstream `MainWindow` with a third tab ("EPR Endstation Control"). Each control-center button (`start_tr_control`, `start_osc_control`, `start_cw`, `start_field_control`, `start_temp_control`, `start_mw_control`, `start_tune_preset`, `start_rect_phasing`, `start_awg_phasing`, …) launches a script under `atomize/control_center/` via a dedicated `QProcess` (`process_tr`, `process_osc`, etc.).
- `start_experiment` in `main.py` spawns the user's experimental script in `self.process_python`.
- Children communicate **upward** by writing `print "..."` to stdout; the parent's `handle_output*` parses lines prefixed with `print `, `before `, `closing `, or `ret = 0` and routes them to the in-app log (`text_errors`). The `before ` / `ret = 0` sentinels exist specifically to suppress Insys FPGA driver chatter.
- The parent communicates **downward** to the active script by writing JSON-ish responses to its stdin when the child prints `create_file_dialog` / `open_file_dialog` — this is how scripts trigger native file pickers.

When editing anything in `atomize/main/main.py` or the control-center scripts, remember every `general.message(...)` call becomes a `print` over a pipe — don't replace it with a normal `print` or it'll be eaten by the routing logic.

### LivePlot data path

Plotting is a second IPC layer parallel to stdout:

- The main window starts a `QLocalServer` named `LivePlot` (`atomize/main/main_window.py`).
- Each child script imports `atomize.general_modules.general_functions`, which instantiates a `LivePlotClient` (`atomize/main/client.py`). The client connects to the local socket, allocates a `QSharedMemory` block, and sends NumPy array payloads via shared memory plus a JSON metadata header over the socket.
- The main window's `accept` / `read_from` callbacks attach to the same shared memory and forward to the pyqtgraph DockArea.

This is why `general.plot_1d(...)` only works when called from a script launched **through** the main window — outside of that, the `LivePlotClient` constructor raises `EnvironmentError("Couldn't find LivePlotter instance")`.

### Device module convention

Every device gets a parallel pair:

- `atomize/device_modules/<Device>.py` — class named the same as the file, instantiated by experimental scripts (`import atomize.device_modules.Lakeshore_335 as ls; ls335 = ls.Lakeshore_335()`).
- `atomize/device_modules/config/<Device>_config.ini` — sectioned config (`DEFAULT`, `GPIB`, `SERIAL`, `MODBUS`, `ETHERNET`, `SPECIFIC`). The `DEFAULT.type` field (`gpib` / `rs232` / `ethernet` / `modbus`) picks which section is used at connect time.

`atomize/device_modules/config/config_utils.py` has the shared `read_conf_util` / `read_specific_parameters` helpers that every device module calls. Transport layers: pyvisa (GPIB/RS-232/Ethernet/VXI-11), pyserial directly, minimalmodbus, raw sockets for TCP/UDP, and **ctypes** for vendor binaries — `libs/libNvsbLib.so`, `libs/libConfigGIM.so`, `libs/GIM.so`, `libs/libbambpex.so` (Insys FPGA) and `atomize/general_modules/libspinapi.so` (SpinCore Pulse Blaster).

When adding a new device, model after an existing one of the same transport class (e.g. copy `Lakeshore_335.py` for a new GPIB/RS-232 device) and add its config file. The class name **must** match the module filename.

### Test mode (the pre-flight check)

In lieu of a unit-test suite, the whole framework has a **test mode** toggled by the first CLI argument. `general_functions.py` reads `test_flag = sys.argv[1]` at import; `is_test()` is `test_flag == 'test'`. Device modules do the same in `__init__` (`self.test_flag = sys.argv[1]`). The GUI's `Test Scripts` checkbox re-launches the experimental script with `argv[1] == 'test'`, so ticking it exercises this path for the whole run.

What test mode does — it is **more than a syntax/import check**:

- **No real I/O.** Every device-module function guards its hardware access with `if self.test_flag != 'test':`. In the `elif self.test_flag == 'test':` branch it instead returns canned values (e.g. `Insys_FPGA.py` sets `test_rep_rate_pulser = '200 Hz'`, `test_sample_rate_adc = '2500 MHz'`, …) so the script runs end-to-end with no board attached.
- **Argument validation.** Those `elif ... == 'test':` branches also range-check and type-check their arguments and raise on bad input — so running under test mode surfaces illegal pulse lengths, out-of-range settings, sequence-overlap asserts, etc. before they ever reach hardware. This is why the phasing tools spin up a *throwaway* test-mode `Insys_FPGA()` to validate a live edit (see "Pulse-EPR experiment presets").
- **Message / plot twins.** `general.message(...)`/`general.plot_1d(...)` have `_test`-suffixed counterparts (`message_test`, `plot_1d_test`, `plot_2d_test`). The `_test` variants fire **only** in test mode and the plain ones **only** in a real run — use `message_test(...)` for diagnostics you want during the pre-flight check but not during acquisition.

When adding hardware-touching code, always preserve the `argv[1] == 'test'` branch — omitting it means the script can't be pre-flighted and will try to talk to absent hardware in test mode.

### Config-file lifecycle (important gotcha)

`atomize/main/local_config.py:copy_config` runs on every startup and copies:
- `atomize/config.ini` → `<user_config_dir>/atomize-py/main_config.ini`
- `atomize/device_modules/config/*` → `<user_config_dir>/atomize-py/device_config/`

…but **only if** the user config directory is missing or empty. After first launch, device modules read from the user-config copy (via `lconf.load_config_device()`), not the repo copy. Editing `atomize/device_modules/config/Foo_config.ini` in-repo will **not** affect a running install; either edit the file under `user_config_dir("atomize-py")/device_config/` or wipe that directory to force a re-copy. On Windows this is typically `%LOCALAPPDATA%\atomize-py\atomize-py\` (resolved by `platformdirs`).

`atomize/main/main_window.py` also `os.chdir`'s into `libs/` early in startup, so any relative paths after that point are resolved against `libs/`. The `libs/status` file and `*.param` files (`field.param`, `bridge.param`, `digitizer*.param`, `correction.param`) are runtime IPC files between control-center widgets and other processes — they're git-ignored and intentionally mutated at runtime.

### Pulse-EPR experiment presets

`atomize/control_center/experiments/*.phase` and `*.phase_awg` are saved phase-cycle/pulse-sequence presets consumed by the phasing/tune control scripts (`phasing_insys.py`, `awg_phasing_insys.py`, `tune_preset.py`, etc.). The `_insys` suffix in `atomize/control_center/other_versions/` marks Insys-FPGA-specific variants; non-suffixed siblings target Spectrum / oscilloscope hardware.

**Live edit.** The Insys phasing tools (`phasing_insys.py`, `awg_phasing_insys.py`) can re-arm a *running* sequence without restarting the experiment. Editing a pulse parameter, with "Live mode" on, pushes the change to the acquisition worker after a debounced "Apply delay" instead of tearing down and rebuilding the scan. Supporting pieces:

- **Settings tab** holds the Live/Apply-delay controls and a "Link Parameter" combo; **Link mode** gives each pulse a No/0.5×/1×/2× coupling factor so one edit proportionally shifts the linked pulses together.
- Not every change can be applied in place: a change to the phase-cycle *structure* (number of steps, per-pulse phase text) forces an announced restart rather than a silent no-op — the tool hashes the sequence structure to decide. Loading a preset or pressing Open while a preview is live stops that preview first.
- **Worker-side validation.** Before accepting a live edit the worker rebuilds the sequence under a throwaway **test-mode** `Insys_FPGA()` (see "Test mode") so the overlap/length asserts — which only fire in test mode — reject an illegal edit as `('LiveReject', reason)`; the GUI shows the reason and keeps the previous sequence running.
- The AWG DETECTION-pulse frequency also re-arms live: it only drives the per-scan `digitizer_demodulate` demod (`iq_freq`), not an AWG waveform, so it is plumbed separately through the snapshot/payload.

### EPR automation layer (`atomize/epr_auto/`) — mirror rule

`atomize/epr_auto/` is the protocol-runner/automation layer (design + roadmap in `docs/automation/`). Its engine does **not** duplicate the phasing tool: `engine/executor.py` runs the very same `Worker` class from `awg_phasing_insys.py`, and `engine/snapshot.py` re-implements only the GUI's snapshot pipeline — preset parsing (`open_file`/`setter` line indices), value formatting (grid snap — 3.2 ns default / 0.8 ns for fine-grid presets with a trailing `AWG grid:  0.8` line, `' ns'`/`' MHz'` strings, `TimeLogSpinBox` log-grid), `expand_phase_cycling`, unit conversions, and the `dig_start_exp`/`worker.exp*` argument packing.

**Any change to the phasing GUIs (`awg_phasing_insys.py`, and `phasing_insys.py` once RECT support lands) that touches the preset format, the `update_*` value formatting, `expand_phase_cycling`, the `Worker` method signatures / pipe protocol, or the `dig_start_exp` argument packing MUST be mirrored in `atomize/epr_auto/engine/`, and the equivalence harness `~/epr_auto_dev/gui_vs_engine.py` re-run** — it drives the real GUI offscreen and diffs the built worker args against the engine for every preset in `atomize/control_center/experiments/`; it must report ALL PASS.

### General script-side API

Experimental scripts almost always start with:

```python
import atomize.general_modules.general_functions as general
import atomize.general_modules.csv_opener_saver as openfile
```

- `general.message(...)`, `general.message_test(...)` — print to the main-window log (and only in non-test / only-in-test runs respectively).
- `general.wait('10 ms')` — string-with-unit time API used everywhere (`ks/s/ms/us/ns/ps`). Time arguments to device functions follow the same convention.
- `general.plot_1d`, `general.plot_2d` — push to LivePlot.
- `general.to_infinity()` — generator for `Stop`-button-aware infinite loops.
- `general.bot_message(...)` — Telegram (requires token+chat-id in `main_config.ini`).
- `atomize.general_modules.returned_thread.rThread` — `threading.Thread` subclass whose `join()` returns the target's return value; this is the project's standard concurrency primitive (see `atomize/documentation/concurrency.md`).
- `openfile.Saver_Opener()` — CSV I/O with header support and Tk-style file dialogs.

### Documentation

The per-instrument function reference is markdown in `atomize/documentation/` (rendered as the Jekyll site at `anatoly1010.github.io/atomize_docs`). When changing a device module's public API, also touch the matching `*.md` there.

## Conventions worth knowing

- Time strings everywhere use the `"<float> <unit>"` form (`'10 ms'`, `'1.5 us'`). Never pass bare floats.
- Module class name == filename. Breaking that breaks the `import X as foo; foo.X()` convention used in every example.
- `test_flag = sys.argv[1]` is the standard way modules detect test mode. Preserve the `argv[1] == 'test'` branch when adding code that touches hardware.
- Don't introduce `print()` statements in scripts launched by the GUI — use `general.message(...)`. Bare `print` to stdout is interpreted by the parent's line-parser and either dropped or shown raw.
- `.param`, `.csv` temp files, `libs/status`, `libs/exam_adc.ini`, `libs/exam_edac.ini`, and `Metrolab_PT2025*` are git-ignored on purpose (see `.gitignore`). Don't commit local edits to them.
