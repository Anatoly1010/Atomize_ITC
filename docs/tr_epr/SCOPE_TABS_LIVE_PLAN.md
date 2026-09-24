# TR-EPR — scope settings tabs, live preview and no-trigger handling (plan)

Written 2026-09-24. Status: planned, not implemented. One session, one commit; update the status line and the session log at the end.

Project: `atomize/control_center/tr_control.py` with two Keysight DSOX2012A scopes driven by `atomize/device_modules/Keysight_2000_Xseries.py` and `_2.py` (Ethernet VISA, `192.168.2.21` / `.22`). The standalone `osc_control.py` / `osc_control_2.py` windows talk raw SCPI over telnet port 5025 from `osc_config.ini` / `osc_2_config.ini`.

## Goal

1. Scope settings (timebase, delay, channel scale/offset, averages) are set from tabs inside `tr_control` through the Atomize device modules, with readback of what the instrument actually accepted.
2. A live mode streams the current averaged trace of each connected scope to LivePlot.
3. Start of an experiment stops the live mode first; the experiment worker keeps exclusive ownership of the scopes.
4. **No blind 180 s waits, no cap on accumulation.** Standing at one field point and accumulating for a long time is legitimate: `Acquisitions` goes to 2000, which is 200 s at the 10 Hz laser, already beyond the 180 s config timeout. The wait must therefore be bounded per *shot*, never per accumulation: a scope that stops triggering is detected within a couple of seconds however long the accumulation, in live mode and in the experiment, and Stop is served within a poll period.
5. **The window opens without instruments.** Nothing touches a scope until the operator presses Connect on a scope tab or starts an experiment.

## Facts the design rests on

- `tr_control` is one grid layout, one worker process (`exp_test` pre-flight, then `exp_on`), one `Pipe`, a 300 ms `check_messages` timer and a `monitor_timer` for stop/exit. Field and temperature locks are set on Start and cleared when the worker ends. The GUI process imports no device module; the modules are imported inside the worker functions, so the window already opens without instruments and only the scope tabs are new territory.
- `exp_on` sets trigger channel (scope 1 from the TR tab, scope 2 fixed `Ext`), `Average` mode, record length 4000, and reads the timebase. Timebase, delay, scales and offsets are whatever the instrument holds, so settings applied earlier through a scope tab survive into the experiment unchanged.
- Today one point is `oscilloscope_start_acquisition()` = `*CLS;:DIGitize` (blocks the scope's parser until COUNt shots are averaged), `oscilloscope_wait_acquisition()` = `*OPC?`, `oscilloscope_get_curve()` = `:WAVeform:DATA?`. Both queries block the VISA read until the acquisition completes, and the VISA timeout is `timeout = 180000` ms from the module config, set once at connect. With no trigger the worker sits in that read for 3 minutes, and Stop cannot reach it. A timeout raises `pyvisa.VisaIOError` from `device_query`, which is catchable. Measured: COUNt 10 ≈ 1.2 s, COUNt 20 ≈ 2.1 s at the 10 Hz laser ([HRES_AVERAGING_PLAN.md](HRES_AVERAGING_PLAN.md)).
- `:SINGle` arms one acquisition and, unlike `:DIGitize`, does not block the parser, so the host can keep querying while the scope accumulates. `:OPERegister:CONDition?` bit 3 (RUN, value 8) stays set while the acquisition runs and clears when it stops. `:TER?` returns 1 if a trigger event happened since the last read, then clears. Keysight's own programming guide uses `:SINGle` + polling as the non-blocking alternative to `:DIGitize` + `*OPC?`. **Gate 0 on the bench:** confirm that in `Average` mode `:SINGle` collects COUNt shots before stopping (the user guide says the Single key does), and that `:WAVeform:DATA?` after it returns the averaged WORD trace identical to the `:DIGitize` result.
- The module constructor calls `sys.exit()` / `os._exit(0)` when the scope does not answer. Any process that instantiates the module can die that way, so the GUI process must never import it.
- The module setters silently ignore out-of-range values (no message, nothing written). Getters exist for every setting: `oscilloscope_timebase()`, `oscilloscope_horizontal_offset()`, `oscilloscope_sensitivity('CH1')`, `oscilloscope_offset('CH1')`, `oscilloscope_number_of_averages()`. Generic `oscilloscope_command()` / `oscilloscope_query()` exist for raw SCPI. `oscilloscope_read_settings()` reads a `.param` file, not the instrument.
- `osc_control.py`: the CH2 scale/offset boxes are wired to the CH1 handlers (`self.ch1_scale`, `self.ch1_offset`), so CH2 edits change CH1 on the scope. Same in `osc_control_2.py`.
- `Atomize_NIOCH_Q` also carries `tr_control.py`; the Keysight modules exist in every fork.

## Design

### Non-blocking acquisition (the core change)

A helper shared by live mode and the experiment, in `tr_control.py`:

```python
def _arm(scope):                       # :SINGle through oscilloscope_command
def _wait_armed(scopes, conn, trigger_timeout_s, poll_s=0.05):
    # returns 'done' | 'exit' | ('no_trigger', index)
```

`_wait_armed` polls every 50 ms: the pipe for `'exit'`, then for each scope `:OPERegister:CONDition?` (RUN bit) and `:TER?`. A scope whose RUN bit clears is done. A scope that is still running but has returned `:TER?` = 0 for `trigger_timeout_s` continuously has lost its trigger: `:STOP` is sent to it and the helper returns `('no_trigger', index)`. Because no query is ever left pending, no `device.clear()` is needed and the VISA timeout can be short: the worker sets it to 5 s through a new module method right after opening each scope, so even a dead network link is reported in seconds.

`trigger_timeout_s` is a scope-tab setting, default 2 s (20 laser periods at 10 Hz). It bounds the wait for the *next shot*, not for the whole accumulation, so it is independent of `Acquisitions` and needs no knowledge of the laser rate. An accumulation of 2000 shots runs for its full 200 s untouched as long as shots keep arriving; the 5 s VISA timeout only guards single queries, which never wait for the accumulation.

Cost: the poll adds at most 50 ms per point against `*OPC?` (which returns the instant the accumulation ends), plus two short queries per scope per poll. At COUNt 10 (≈1.2 s per point) that is under 5 %.

Module additions in `Keysight_2000_Xseries.py` and `_2.py`, documented in `atomize/documentation/functions/oscilloscope.md` and the published reference:

```python
def oscilloscope_timeout(self, *timeout):   # '5 s' style argument; no argument returns the current value (VISA timeout)
```

`:SINGle`, `:OPERegister:CONDition?` and `:TER?` go through the existing `oscilloscope_command` / `oscilloscope_query`, so no further module surface is needed.

### Experiment worker

In `exp_on` and `exp_test`, the forward and backward loops replace `start_acquisition` + `wait_acquisition` with `_arm` on each scope, the magnet step (the existing readout overlap is kept), then `_wait_armed`. On `('no_trigger', i)`: log `scope i: no trigger for T s at field F`, re-arm and wait once more; on a second loss at the same point raise, so the existing `('Error', ...)` path ends the run with that message instead of a raw VISA traceback. On `'exit'` the loop stops the scopes and leaves through the existing stop path, so Stop is served within 50 ms instead of after the accumulation. Data assignment, magnet end state and ramp-back are unchanged; the two-field path in `tr_two_fields.acquire` gets the same helper.

### Scope session worker

One new `Worker.scope_on(conn, num_osc, settings, script_test=False)` child process owns the scope connections whenever the experiment worker does not. It starts only when the operator presses **Connect** on a scope tab and ends on **Disconnect**, Exit, or an experiment Start. Messages from the GUI:

- `('SET', scope_index, name, value)` — apply one setting through the module setter, read it back, answer `('Settings', scope_index, {name: actual, ...})`.
- `('READ', scope_index)` — read back everything.
- `('LIVE', scope_index, 0|1)` — toggle the live loop for that scope.
- `'exit'` — close both modules (`close_connection`) and end.

Right after connecting, the session reads back every setting so the boxes show the instrument state before the operator edits anything. Only one process ever holds a scope. `start()` refuses to launch `exp_test` while the session is alive: it sends `'exit'`, sets `pending_start = True`, and the existing `monitor_timer` path calls the real start once the session has ended. While `exp_process` is alive the scope tabs are read-only (boxes, Connect and Live disabled), the same way `set_half_editable` greys the half-field panel.

A scope that does not answer at Connect kills the child through the module's `sys.exit()`. `check_messages` already notices a dead worker; when no `finished` or `Error` message preceded the death the GUI logs `scope N did not answer — check power and network of 192.168.2.21/.22`, flips the tab back to *Not connected* and re-enables Connect. The TR EPR tab and the other scope tab are unaffected.

### Live loop

Inside `scope_on`, while any scope has live on: for each live scope `oscilloscope_number_of_averages(live_averages)`, `_arm`, `_wait_armed` with the tab's trigger timeout, then `oscilloscope_get_curve('CH1')` (and `'CH2'` when the TR tab's scope count is 3), and `general.plot_1d('TR Live', t, y, xname='Time', xscale='s', yname='Signal', yscale='V', label='Scope 1 CH1')`; scope 2 goes into the same plot under its own label. The time axis is `np.arange(n) * time_resolution` plus the horizontal offset read back. A `SET` is applied between traces, never mid-acquisition. When live is off for both scopes the loop idles on `conn.poll(0.2)`.

On `('no_trigger', i)` the loop logs `scope i: no trigger for T s`, waits 1 s and re-arms while live stays on; after three consecutive losses it turns live off for that scope and says so, so an unplugged trigger does not spin forever. Live uses its own small `live_averages` (default 2) so the preview refreshes at a few Hz; the TR tab `Acquisitions` value stays the experiment setting and is untouched.

### Pre-flight

The scope session gets the house test-mode pre-flight: `scope_on(..., script_test=True)` runs once with the current tab values before the real session starts, so the module's test-mode asserts reject an out-of-range timebase or a malformed unit string before hardware is touched. Because real-mode setters ignore bad values silently, the GUI spinbox ranges are taken from the module config: `timebase_min/max`, `sensitivity_min/max` from the `[SPECIFIC]` section, read with `config_utils` in the GUI process (this does not instantiate the module and needs no instrument).

### GUI

`tr_control` central widget becomes a `QTabWidget`:

- **TR EPR** — the existing grid, unchanged, including the trigger channel combo and the scope count combo.
- **Scope 1**, **Scope 2** — one widget class instantiated twice.

```
┌ TR EPR ┬ Scope 1 ┬ Scope 2 ┐
│  Status                 Not connected             │
│  [ Connect ]            [ Read ]                  │
│  ─────────────────────────────────────            │
│  Window                 [   500.0 us ]            │
│  Horizontal Offset      [     0.0 us ]            │
│  ─────────────────────────────────────            │
│  CH1 Scale              [     200 mV ]            │
│  CH1 Offset             [       0 mV ]            │
│  CH2 Scale              [     200 mV ]            │
│  CH2 Offset             [       0 mV ]            │
│  ─────────────────────────────────────            │
│  Live Acquisitions      [         2  ]            │
│  Trigger Timeout        [      2.0 s ]            │
│  Live                   [ ]                       │
│  ─────────────────────────────────────            │
│  [ Run ]   [ Stop ]                               │
└───────────────────────────────────────────────────┘
```

Before Connect the boxes hold the last values (or defaults) and are editable but nothing is sent; Connect starts the session, the status turns to *Connected*, the boxes are overwritten by the readback and from then on every edit is applied and read back with signals blocked so no `SET` echoes. Connect toggles to Disconnect. Read repeats the full readback. Run and Stop free-run or stop the instrument for its own screen. Live is enabled only while connected. Scope 2 is enabled only while `Number of Oscilloscopes` is above 1. Trigger channel is not duplicated: scope 1 uses the TR tab value, scope 2 keeps `Ext` in the experiment. `Trigger Timeout` is also the experiment's per-shot watchdog. Values are sent as the module's unit strings (`'500 us'`, `'200 mV'`).

Optional, only if cheap: append the scope rows to the `Save to file` preset. `open_file` indexes fixed line numbers, so new lines go at the end and are read only when present.

### osc_control windows

Keep `osc_control.py` / `osc_control_2.py` and their main-window buttons until the tabs pass on the bench; then remove them, their `osc_*_config.ini`, the two `QProcess` entries and buttons in `atomize/main/main.py`.

## Checks without hardware

- Open `tr_control` with no scope on the network: the window opens, TR EPR tab works, scope tabs show *Not connected*; Connect logs the did-not-answer hint within the 5 s VISA timeout and the tab recovers.
- Pre-flight: scope session with every setting at its range limits and one deliberately wrong unit string; the assert message reaches the GUI log.
- Start while live is on: live ends, experiment starts, tabs are read-only, tabs re-enable after the run; Exit while live is on closes cleanly.
- `_wait_armed` with a stub scope (monkeypatched `oscilloscope_query`): RUN clear returns `done`; RUN set with `:TER?` = 0 for longer than the timeout returns `no_trigger` and sent `:STOP`; `'exit'` on the pipe returns within one poll. Three live losses turn live off; one experiment loss retries once, a second aborts with the field in the message.
- `exp_test` traced two-sided sweep with p9 = 1/2/3 still assigns data to the same fields as before the helper.

## Checks on hardware

- **Gate 0 first:** on scope 1 in Average mode, `:SINGle` with COUNt 10 and 20: RUN bit clears after ≈1.2 s / ≈2.1 s, `:WAVeform:DATA?` returns a 3839-point averaged trace matching a `:DIGitize` trace of the same setting within noise. If `:SINGle` does not honor COUNt, fall back to `:DIGitize` with `write('*OPC?')` + repeated short `read()` (a timed-out VISA read leaves the response queued), which keeps Stop interruptible and puts no cap on the accumulation, but detects a lost trigger only through a per-point maximum wait derived from `Acquisitions` and a laser-rate setting.
- Apply each setting from a tab, confirm readback equals the front panel; an out-of-range value is rejected in the pre-flight, not silently dropped.
- Live on scope 1, then both scopes, laser running: refresh rate at live averages 2 and 10; no LivePlot stall.
- Laser off during live: `no trigger for 2 s` appears within about 2 s, live stops itself after three, the scope is left stopped and responsive.
- Laser off during an experiment: the point is retried once, the run ends with the field in the message within about 5 s, locks are cleared.
- Per-point time at COUNt 10 and 16 against the 2026-09-17 figures (1.86 s per point at COUNt 16): the poll must cost under 50 ms per point.
- Start with live on: the experiment begins after the session ends; results identical to a run started with live off.
- Unplug the scope's Ethernet during live and during an experiment: the hint appears within the 5 s VISA timeout, `tr_control` remains usable, Connect reconnects.
- Stop during a no-trigger wait: served within one poll.

## Documentation and ports

- `atomize/documentation/functions/oscilloscope.md`: `oscilloscope_timeout`; mirror in `atomize_docs` (read its `CLAUDE.md` first). The endstation page gets no UI details.
- Port the module addition to every fork through `sync_check.py`; port the `tr_control` change to `Atomize_NIOCH_Q`.

## Decisions (confirmed 2026-09-24)

- One scope-session child process for settings and live, exclusive with the experiment worker; the GUI process never imports the scope module, and the session exists only between Connect and Disconnect.
- Acquisition waits are `:SINGle` + 50 ms polling of the RUN bit and the trigger event register, with a per-shot trigger timeout (default 2 s) instead of a per-accumulation VISA timeout; the VISA timeout drops to 5 s.
- Experiment timeout policy: retry the point once, then abort with the field in the message.
- The standalone `osc_control` windows stay until the tabs pass on the bench, then they are removed with their configs, `QProcess` entries and main-window buttons.
