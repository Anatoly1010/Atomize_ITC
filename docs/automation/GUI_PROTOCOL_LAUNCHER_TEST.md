# Protocol launcher: dummy-data check

1. Restart Atomize_ITC and open the **EPR Endstation Control** tab.
2. Leave the new **Dry run** checkbox checked. It is separate from **Test Scripts**.
3. Click **Run protocol…** and select `protocols/preliminary_tuning.yaml`.
4. Click **Continue** at each checkpoint. Expect five steps and a final **Protocol finished** message in the application log. Dummy mode accesses no hardware and creates no acquisition or handoff files.
5. Start it again and choose **Abort**, close the checkpoint dialog, or press **Stop protocol** while the dialog is open. Expect **Protocol aborted**, followed by the ability to start another run.
6. To check Stop during work, continue a checkpoint and press **Stop protocol** while that step runs. The GUI should stay responsive while the runner drains its worker. **Force stop** sends a second interrupt during cleanup; allow the first stop to finish normally for this check.
7. Select an invalid YAML file. Its error should appear in the log as **Protocol invalid**. A second concurrent launch is blocked, and the application refuses to close while the protocol process is active.

Checkpoint Skip is available. Skipping a prerequisite in the preliminary protocol can make a later step fail; this is expected dependency checking.

A live Stop during the ringing ladder returns RV to 60 dB. A Stop at a checkpoint or in another step leaves RV unchanged. Acquisition workers still close and instrument locks are released. Live operation is a separate supervised check; leave Dry run checked for the steps above.

## Offline regression commands

```bash
QT_QPA_PLATFORM=offscreen python3 atomize/script_examples/epr_auto/gui_launcher_checks.py test
python3 atomize/script_examples/epr_auto/gui_runner_checks.py test
python3 atomize/script_examples/epr_auto/worker_stop_checks.py test
QT_QPA_PLATFORM=offscreen python3 atomize/script_examples/epr_auto/preliminary_checks.py test
```

The GUI checks use real dry-run child processes and offscreen dialogs. The runner checks inject dummy failures to exercise Retry, the coarse-stage fallback, Stop during a step, and stdin closure. These checks do not operate hardware.
