"""Acquisition engine: preset -> worker-args -> running experiment.

Rather than duplicating the acquisition logic, the engine REUSES the Worker
class from atomize/control_center/awg_phasing_insys.py (the known-good,
hardware-validated implementation the phasing tool itself pickles into a
multiprocessing.Process). What lives here is the part the GUI normally does:

- snapshot.py — parse a *.phase_awg preset and build the exact positional
  argument tuples Worker.exp / exp_log / exp_amplitude / exp_field expect,
  reproducing the GUI's formatting pipeline (3.2 ns grid snap, ' ns'/' MHz'
  suffix strings, awg_output_shift, phase-cycle expansion, deg->rad and
  window ns->points conversions).
- executor.py — run a Worker method in a child process and speak its pipe
  protocol (Status/Message/Error/Open/exit) without the GUI.

Import note: importing this package pulls in awg_phasing_insys (PyQt6 +
general_functions), so cli.py must have set sys.argv[1] before any engine
import — steps import the engine lazily at run time, never at validate time.
"""
