"""EPRSession: run-scoped state and lazy device handles.

Device modules are imported here lazily (never at module scope) so that
cli.py can set sys.argv[1] = 'test' first — device __init__ reads it to pick
the test branch. The Insys driver also requires cwd == Atomize_ITC/libs at
instantiation time; cli.py chdirs before the runner starts.
"""
import datetime
from pathlib import Path


class EPRSession:

    def __init__(self, sample, autonomy, test, output=None, notify='none'):
        self.sample = sample
        self.autonomy = autonomy
        self.test = test
        self.output = output          # run-dir template ({date}, {sample})
        self.notify_mode = notify     # 'none' | 'telegram'
        # Cross-step results (calibrations, chosen field, ...); step functions
        # read what earlier steps stored here.
        self.state = {}
        # Judge reports of the most recent primitive call (set by the step
        # layer); the runner snapshots them into the run manifest.
        self.last_judges = []
        self._pulser = None
        self._mw_bridge = None
        self._field_controller = None
        self._temp_controller = None
        self._run_dir = None
        self._save_counter = 0
        self._locked = False
        # foreach series context (runner sets/clears per iteration): loop_tag
        # is stamped into save_path filenames, loop_context into the manifest.
        self.loop_tag = None
        self.loop_context = None

    def log(self, text):
        # Terminal-first output. When the runner gains a GUI launch path
        # (Phase 3) this must route via general.message instead of print —
        # bare stdout is re-parsed by the main window's line router.
        print(text, flush=True)

    @property
    def pulser(self):
        if self._pulser is None:
            import atomize.device_modules.Insys_FPGA as pb_pro
            self._pulser = pb_pro.Insys_FPGA()
        return self._pulser

    @property
    def mw_bridge(self):
        if self._mw_bridge is None:
            import atomize.device_modules.Micran_X_band_MW_bridge_v2 as mwb
            self._mw_bridge = mwb.Micran_X_band_MW_bridge_v2()
        return self._mw_bridge

    @property
    def field_controller(self):
        if self._field_controller is None:
            import atomize.device_modules.BH_15 as bh
            self._field_controller = bh.BH_15()
        return self._field_controller

    @property
    def temp_controller(self):
        if self._temp_controller is None:
            import atomize.device_modules.Lakeshore_335 as ls
            self._temp_controller = ls.Lakeshore_335()
        return self._temp_controller

    # ------------------------------------------------------------- run dir

    @property
    def run_dir(self):
        """Directory for this run's acquisitions + manifest (created lazily).
        Honors the protocol's 'output' template; {date} and {sample} expand."""
        if self._run_dir is None:
            stamp = datetime.date.today().isoformat()
            safe_sample = ''.join(c if c.isalnum() or c in '-_' else '_'
                                  for c in str(self.sample))
            if self.output:
                self._run_dir = Path(self.output.format(
                    date=stamp, sample=safe_sample)).expanduser()
            else:
                self._run_dir = Path.home() / 'epr_data' / f'epr_auto_{stamp}_{safe_sample}'
            self._run_dir.mkdir(parents=True, exist_ok=True)
        return self._run_dir

    def save_path(self, tag):
        """A fresh CSV path in the run directory (counter-unique per session).
        Inside a foreach iteration the loop tag (e.g. 'B_3318G') is stamped in
        so a field/temperature series' files are self-identifying."""
        self._save_counter += 1
        if self.loop_tag:
            tag = f'{tag}_{self.loop_tag}'
        return str(self.run_dir / f'{self._save_counter:03d}_{tag}.csv')

    # ------------------------------------------------- cross-process locks

    def ensure_hardware_locks(self):
        """Seize the field.param / temp.param locks (same discipline as the
        four experiment-runner GUIs: seize at run start so the interactive
        field/temperature tools stay off the GPIB devices). Idempotent;
        no-op in test mode — a dry-run must not touch the real lock files."""
        if self.test or self._locked:
            return
        from atomize.control_center import field_param, temp_param
        for mod, name in ((field_param, 'field'), (temp_param, 'temperature')):
            if mod.is_locked() and mod.lock_source() not in ('', 'epr_auto'):
                raise RuntimeError(
                    f'{name} lock is held by {mod.lock_source()!r} — another '
                    'tool is driving the hardware; close it or wait')
        field_param.set_lock('epr_auto')
        temp_param.set_lock('epr_auto')
        self._locked = True
        # never leave the interactive tools locked out after a crash/exit —
        # the runner GUIs clear their locks on every exit path, mirror that
        import atexit
        atexit.register(self.release_hardware_locks)

    def release_hardware_locks(self):
        if not self._locked:
            return
        from atomize.control_center import field_param, temp_param
        field_param.clear_lock()
        temp_param.clear_lock()
        self._locked = False

    # ---------------------------------------------------------- notifications

    def notify(self, text):
        """Operator notification (Telegram via general.bot_message when the
        protocol enables it). Logged always; a notification failure must
        never take down a run, and dry-runs never message anyone."""
        self.log(f'      [notify] {text}')
        if self.notify_mode != 'telegram' or self.test:
            return
        try:
            # lazy: general_functions needs the GUI's LivePlot socket at
            # import in a real run, and bot credentials from main_config.ini
            import atomize.general_modules.general_functions as general
            general.bot_message(text)
        except Exception as e:
            self.log(f'      [notify] telegram failed: {e}')

    # ------------------------------------------------- calibration validity

    def invalidate_fine_calibrations(self, reason):
        """Any rotary-vane move changes B1 for everything: auto-phase and the
        fine amplitude calibration are no longer valid (ARCHITECTURE.md
        'Vane rules')."""
        self._drop(('auto_phase', 'pi_calibration'), reason)

    def invalidate_phase(self, reason):
        """Temperature detunes the resonator, so the demod zero-order drifts —
        but B1 is untouched, so the fine calibration survives (ARCHITECTURE.md
        'Temperature rules'). Drop auto_phase only."""
        self._drop(('auto_phase',), reason)

    def invalidate_rep_rate(self, reason):
        """T1 — the basis of the tune.rep_rate recommendation — is strongly
        temperature-dependent, so a temperature move makes the stored rate
        stale. Field moves deliberately do NOT drop it: the field effect on
        T1 is minor and appears only in systems with two different spins."""
        self._drop(('rep_rate',), reason)

    def _drop(self, keys, reason):
        dropped = [k for k in keys if self.state.pop(k, None)]
        if dropped:
            self.log(f'      calibrations invalidated ({reason}): {", ".join(dropped)}')
