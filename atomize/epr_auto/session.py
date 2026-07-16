"""EPRSession: run-scoped state and lazy device handles.

Device modules are imported here lazily (never at module scope) so that
cli.py can set sys.argv[1] = 'test' first — device __init__ reads it to pick
the test branch. The Insys driver also requires cwd == Atomize_ITC/libs at
instantiation time; cli.py chdirs before the runner starts.
"""


class EPRSession:

    def __init__(self, sample, autonomy, test):
        self.sample = sample
        self.autonomy = autonomy
        self.test = test
        # Cross-step results (calibrations, chosen field, ...); step functions
        # read what earlier steps stored here.
        self.state = {}
        self._pulser = None
        self._mw_bridge = None
        self._field_controller = None

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
