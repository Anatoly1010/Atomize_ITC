# GUI protocol launcher plan

Status: implemented, 2026-09-13; operator confirms GUI dry runs and Stop work. Live validation remains pending. The reviewed epr-auto documentation is committed in atomize_docs as `6e994ab`; the launcher is approved for commit and push.

## Scope and constraints

Add protocol controls to the ITC EPR Endstation extension in `atomize/main/main.py`. Do not
modify `atomize/main/main_window.py`, which is shared with other forks. Keep protocol
communication in a small dedicated module. Existing terminal execution remains available.

## Decisions

- **Stop is a proper stop, not a terminate.** An experimental script owns its own cleanup,
  but a protocol has no script: the runner drives `.phase_awg` presets through worker
  processes that hold the FPGA card and the instrument locks. A terminate would kill the
  runner without its cleanup and orphan a worker. Stop therefore goes through the runner's
  existing interrupt path (the Ctrl-C path): the current worker is told to exit and
  drained, the run is marked aborted in the manifest, and the locks are released.
- **RV to 60 dB only for the ringing check.** The ringing-check step already homes the
  RV when its ladder is interrupted; that stays. The runner-level return to 60 dB that
  fires on any abort after the ringing check has passed is removed: a stop elsewhere in a
  run leaves the RV where it is.
- **A separate Dry run checkbox** next to the file picker, checked by default. The
  existing Test Scripts box means "pre-flight, then run live" for experimental scripts and
  must not be given a second meaning.
- **Own QProcess, own output handler.** The protocol process is not added to the shared
  control-center handler; its handler parses the structured lines below and forwards the
  rest to the log unchanged. It is added to the process lists in the constructor, in
  `closeEvent` and in `quit`, so the window refuses to close while a protocol runs.
- **Merged stdout and stderr.** The runner reports invalid YAML and abort reasons on
  stderr; with only stdout read they never reach the log.

## Runner changes (`atomize/epr_auto`)

- A `--gui` flag on `run`. It sets one session attribute that the three `isatty` checks in
  `runner.py` consult first; without it the runner aborts every checkpoint under a pipe
  ("no terminal attached").
- All operator prompts go through the existing `_ask`; in GUI mode it prints one
  structured request line and reads one reply line from stdin instead of calling `input`.
  Three prompts exist and all three need a dialog: checkpoint (Continue / Skip / Abort),
  `on_fail: ask` (Retry / Skip / Abort), and the rail fallback (Re-run coarse stage / No).
- GUI dry run keeps the dialogs: the GUI flag is checked before the `session.test`
  short-circuits, so checkpoints pause and `on_fail: ask` prompts even on canned data.
  Ordinary CLI `--test` stays noninteractive.
- Stop channel: in GUI mode a small thread reads stdin; a `stop` line raises the
  keyboard interrupt in the main thread, so `run_protocol`, the executor's drain and
  `cli.py`'s lock release run unchanged on Linux and Windows alike. Prompt replies and the
  stop line share the same stdin reader.
- Remove the runner-level RV return on abort (the `ringing_check` state check in
  `run_protocol`); the step's own handler keeps homing the RV during the ladder.
- `session.log` keeps bare stdout lines; they already pass the GUI line router.

## Implementation checklist

- [x] Run protocol, Stop protocol, a YAML file picker and a Dry run checkbox on the EPR
      Endstation tab. Launch `sys.executable -m atomize.epr_auto run <yaml> [--test] --gui`
      in a dedicated QProcess with merged channels; no working directory is needed, the
      CLI changes to `libs/` itself. Refuse a second launch while one is active.
- [x] Output handler: forward lines to the log; on a structured request line open the
      matching dialog and write the reply line to the child's stdin. Closing a dialog
      means abort. Map exit codes 0 / 1 / 2 / 3 to finished / invalid / aborted /
      unsupported in the log.
- [x] Stop button: if a dialog is open, close it with abort; otherwise write the stop
      line. Log "stop requested" and show a stopping state. The button becomes Force stop;
      a second press sends another interrupt so the executor can terminate its worker
      during drain, mirroring a second Ctrl-C without directly killing the runner.
      The worker drain allows up to 60 s for a mid-scan save. The GUI stays
      responsive throughout since the process is asynchronous.
- [x] Runner: `--gui` flag, structured prompt lines for the three prompts, the stdin
      reader with the stop line, removal of the runner-level RV return.
- [x] Validate on dummy data: normal completion, skip at a checkpoint, abort at a
      checkpoint, dialog closed, stop during a step, stop while a dialog is open, invalid
      YAML, process failure, repeated launches, window close refused while running. Failure and rail prompts are additionally covered with injected dummy steps.
- [x] Update ROADMAP and publish concise dummy-data test instructions.

## Delivery order

1. Completed 2026-09-13: update the existing epr-auto documentation for implemented
   preliminary tuning and the September hardware results. All eight existing pages
   updated, step reference regenerated, strict MkDocs build passed. Changes are local in
   the documentation checkout; do not commit until the operator reviews the prose.
2. Runner changes, checked from the terminal first (`--gui` with hand-typed replies and a
   hand-typed stop line).
3. Launcher, dialogs and Stop in `main.py`; dummy-data validation.
4. Verify on hardware that a Stop during the ringing ladder homes the RV, that a Stop
   elsewhere leaves it in place, and that the FPGA card and locks are freed, before the
   operator's first supervised run.

## Acceptance

The operator can choose `protocols/preliminary_tuning.yaml` from the EPR Endstation tab with
Dry run checked, see progress in the log, respond to every checkpoint, complete or stop the
run, and start another run. Invalid YAML and an aborted run are reported in the log. No
hardware is accessed in a dry run; `main_window.py` has no changes.

## Implementation notes

`gui_io.py` uses unbuffered file-descriptor reads in the stdin thread. Buffered stdin reads can hold a Python stream lock across Linux fork and deadlock acquisition-worker startup. Full preliminary dry-run coverage exercises this path.

`protocol_launcher.py` owns the QProcess, line buffering, dialogs and run state. `main.py` embeds it and includes its process in exit guards. The protocol process does not use the control-center output parser. `main_window.py` is unchanged.

Use the current [hardware checklist](HARDWARE_CHECKLIST.md) for launch, Stop and relaunch checks. Live cleanup and Windows execution remain operator-validation items. The operator completed prose review and approved commit and push after confirming GUI dry runs and Stop.

## Independent verification

An independent agent verified the launcher before the operator dummy-data test. The review corrected the executor's unbounded first-interrupt drain and repeated grace after a second interrupt. Cleanup now uses one bounded drain and terminates the worker on a second interrupt. On POSIX, the GUI stop reader sends SIGINT to the runner process so blocking waits are interrupted; the non-POSIX fallback remains scheduled Python interruption and still needs platform validation.

The full launcher, runner, preliminary and worker-stop offline checks pass. No blocker remains for Linux dummy-data testing. No hardware was operated and the public documentation prose was left untouched during this review.

## Current acquisition paths — 2026-09-19

The launcher also runs [live rate tuning](../../protocols/rep_rate_live.yaml), [one T2 with automatic 2τ range](../../protocols/t2_auto_range.yaml) and [T1/T2 temperature series](../../protocols/temperature_series_t1t2.yaml). Live-rate tuning keeps the card open across frequencies and preserves its observation history on interruption. Adaptive T1/T2 can stop one early acquisition to extend its time range, then continue toward target SNR with a second acquisition. These paths use the existing runner interrupt and worker cleanup; CLI/worker checks pass. Check GUI Stop during rate convergence, range assessment and the revised acquisition on hardware before marking live cancellation complete.
