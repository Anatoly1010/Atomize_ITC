"""Preset parsing and Worker argument building.

Mirrors the GUI pipeline in awg_phasing_insys.py exactly:
    open_file/setter        -> load_preset          (same line indices)
    update_pulse_value etc. -> _snap/_ns/_mhz       (grid snap + suffix strings)
    update_pulse_phase      -> _expand_phases       (same expand_phase_cycling)
    win_left/win_right etc. -> build_worker_args    (same unit conversions)
    dig_start_exp packing   -> WorkerArgs.exp_args / exp_log_args / ...

Any change to the corresponding GUI code must be mirrored here; the
equivalence harness (~/epr_auto_dev/gui_vs_engine.py) compares the two
against the real GUI headless and must be re-run after either side changes.
"""
import math
from dataclasses import dataclass, field
from pathlib import Path

# Same constants as awg_phasing_insys.MainWindow.__init__
GRID_NS = 3.2
AWG_GRID_NS = 0.8              # fine grid (one DAC sample), 'AWG grid' preset line
AWG_OUTPUT_SHIFT_NS = 0        # MainWindow.awg_output_shift
DEG_RAD = 180 / math.pi        # zero-order phase: deg -> rad
FIRST_ORDER_COEF = 180 / math.pi * 1e-9    # first order: deg/ns -> rad/s
SEC_ORDER_COEF = 180 / math.pi * 1e-18     # second order: deg/ns^2 -> rad/s^2

SWEEP_TYPES = ('Linear Time', 'Log Time', 'Amplitude', 'Field', 'ESEEM Avg')

# Worker attributes the GUI copies onto a fresh Worker before launching it
# (_hand_correction_to_worker, called next to the awg_grid_cur assignment in
# dig_start_exp). The executor must hand over the same set from WorkerArgs,
# and the equivalence harness compares them alongside awg_grid_cur.
CORRECTION_ATTRS = ('cor_model_cur', 'f0_cur', 'q_cur', 'phase_cor_cur',
                    'meas_freq_cur', 'meas_H_cur')


class PresetError(ValueError):
    pass


def _snap(value, grid=GRID_NS):
    """MainWindow.round_to_closest(x, grid): snap UP to the grid."""
    x, y = float(value), grid
    return round((y * ((x // y) + (round(x % y, 2) > 0))), 1)


def _log_snap(log_ns, fine=False):
    """TimeLogSpinBox.setValue quantization: pick the largest display unit
    (ns/us/ms/s), snap 10**log_ns onto that unit's grid (every grid is a
    base-grid multiple: 3.2 ns default, 0.8 ns fine — see
    time_log_spinbox._UNIT_STEP / _UNIT_STEP_FINE), return round(log10, 3)
    — the widget's value() form."""
    ns_raw = 10.0 ** float(log_ns)
    if ns_raw >= 1e9:
        grid = 0.01 * 1e9
    elif ns_raw >= 1e6:
        grid = 0.01 * 1e6
    elif ns_raw >= 1e3:
        grid = (0.02 if fine else 0.08) * 1e3
    else:
        grid = 0.8 if fine else 3.2
    ns = grid if ns_raw <= grid else round(ns_raw / grid) * grid
    return round(math.log10(ns), 3)


def _ns(value):
    return f'{value} ns'


def _mhz(value):
    return f'{value} MHz'


@dataclass
class PulseSlot:
    """One P1..P9 row of a preset (raw, unsnapped preset numbers)."""
    typ: str
    start: float
    length: float
    sigma: float
    freq: int
    sweep: int
    coef: float
    phase_text: str      # preset field with outer brackets stripped, as the GUI stores it
    st_inc: float
    len_inc: float
    st_inc2: float = 0.0

    @property
    def active(self):
        return self.length != 0.0


@dataclass
class Preset:
    path: str
    slots: list                 # 9 PulseSlot entries, P1..P9
    rep_rate: float
    field: float
    ampl_1: int
    ampl_2: int
    phase_deg: float            # CH1 IQ phase shift (Phase box)
    n_wurst: int
    b_sech: float
    win_left_ns: float
    win_right_ns: float
    averages: int
    p_to_drop: int
    zero_order_deg: float
    first_order_deg: float
    second_order_deg: float
    laser: str
    decimation: int
    points: int
    scans: int
    log_start: float
    log_end: float
    start_field: float
    end_field: float
    step_field: float
    sweep_type: str
    iq_corr: int                # preset convention: 2 = on, else off
    x0: float
    xdelta: float
    step_ampl: float = 1.0
    cycles: int = 1
    save_each: int = 0
    awg_grid: float = GRID_NS   # 'AWG grid' trailing line; 3.2 when absent


def load_preset(path):
    """Parse a *.phase_awg preset with the same line indices as open_file()."""
    path = Path(path)
    lines = path.read_text(encoding='utf-8').split('\n')

    def val(idx):
        return lines[idx].split(':  ')[1]

    try:
        slots = []
        for i in range(9):
            a = val(i).split(',  ')
            slots.append(PulseSlot(
                typ=a[0], start=float(a[1]), length=float(a[2]), sigma=float(a[3]),
                freq=int(a[4]), sweep=int(a[5]), coef=float(a[6]),
                phase_text=str(a[7])[1:-1],
                st_inc=float(a[8]), len_inc=float(a[9]),
                st_inc2=float(a[10]) if len(a) > 10 else 0.0,
            ))

        preset = Preset(
            path=str(path), slots=slots,
            rep_rate=float(val(9)), field=float(val(10)),
            ampl_1=int(val(12)), ampl_2=int(val(13)), phase_deg=float(val(14)),
            n_wurst=int(val(15)), b_sech=float(val(16)),
            win_left_ns=round(float(val(19)), 1), win_right_ns=round(float(val(20)), 1),
            averages=int(val(21)),
            p_to_drop=0, zero_order_deg=0.0, first_order_deg=0.0,
            second_order_deg=0.0, laser='Nd:YaG',
            decimation=int(val(27)), points=int(val(28)), scans=int(val(29)),
            log_start=float(val(30)), log_end=float(val(31)),
            start_field=float(val(32)), end_field=float(val(33)),
            step_field=float(val(34)), sweep_type=str(val(35)),
            iq_corr=0, x0=0.0, xdelta=0.0,
        )
    except (IndexError, ValueError) as e:
        raise PresetError(f'{path}: not a valid .phase_awg preset ({e})') from None

    # Optional tails, same fallbacks as open_file()
    try:
        preset.p_to_drop = int(val(22))
        preset.zero_order_deg = float(val(23))
        preset.first_order_deg = float(val(24))
        preset.second_order_deg = float(val(25))
        preset.laser = str(val(26))
    except IndexError:
        pass
    try:
        preset.iq_corr = int(val(36))
        preset.x0 = float(val(37))
        preset.xdelta = float(val(38))
        preset.step_ampl = float(val(39))
    except IndexError:
        pass
    try:
        preset.cycles = int(val(40))
        preset.save_each = int(int(val(41)) == 2)
    except (IndexError, ValueError):
        pass
    # AWG timing grid (trailing line, like open_file's guarded parse)
    for line in lines:
        if line.startswith('AWG grid:'):
            try:
                if float(line.split(':  ')[1]) == AWG_GRID_NS:
                    preset.awg_grid = AWG_GRID_NS
            except (IndexError, ValueError):
                pass
            break

    if preset.sweep_type not in SWEEP_TYPES:
        raise PresetError(f'{path}: unknown sweep type {preset.sweep_type!r}')
    return preset


def _expand_phases(slots):
    """MainWindow.update_pulse_phase: expand the phase-cycle notation of the
    ACTIVE pulses together. Returns ph[0..8]; inactive slots get a ['+x']
    placeholder (the worker never reads them)."""
    # Single source of truth for the notation: call the GUI's own expander
    # (an effectively-static method; it never touches self). NOTE: because
    # both sides share it, the equivalence harness cannot catch a bug INSIDE
    # expand_phase_cycling — its phase comparison only verifies the
    # active-slot selection and the ph[] index mapping done below.
    from atomize.control_center.awg_phasing_insys import MainWindow

    active = [(i, s.phase_text) for i, s in enumerate(slots) if s.active]
    texts = [t for _, t in active]
    expanded = MainWindow.expand_phase_cycling(None, *texts)

    ph = [['+x'] for _ in range(9)]
    ph[0] = expanded['receiver']
    for k, pulse_phases in enumerate(expanded['pulses']):
        ph[active[k + 1][0]] = pulse_phases
    return ph


@dataclass
class WorkerArgs:
    """Everything Worker.exp* takes, in GUI attribute form. Build the exact
    positional tuple with exp_args()/exp_log_args()/exp_amplitude_args()/
    exp_field_args() and prepend the pipe end + append script_test."""
    decimation: int
    averages: int
    scans: int
    points: int
    exp_name: str
    curve_name: str
    rect: list          # p1_exp .. p9_exp (index 0 = P1/DETECTION)
    n_wurst: int
    rep_rate: str       # number-only string, e.g. '500.0'
    field: float
    ch0_ampl: int
    ch1_ampl: int
    awg: list           # p2_awg_exp .. p9_awg_exp (index 0 = P2)
    b_sech: float
    combo_cor: int      # 0 No / 1 Only Pi/2 / 2 All
    combo_synt: int
    laser_flag: int
    laser_num: int
    q_switch_delay: float
    iq_phase: float     # rad (Phase box * 2pi/360)
    iq_cor: int         # 1 = IQ-corrected 1D, 0 = raw 2D
    win_left: int       # points, after ns -> points conversion + clamp
    win_right: int
    zero_order: float   # rad
    x0: float
    xdelta: float
    first_order: float  # rad/s
    second_order: float # rad/s^2
    save2d: int
    # sweep-specific extras
    log_start: float = 1.0
    log_end: float = 7.0
    start_field: float = 0.0
    end_field: float = 0.0
    step_field: float = 0.5
    step_ampl: float = 1.0
    eseem_inc2: list = field(default_factory=list)   # P1..P9 'X ns' strings
    cycles: int = 1
    save_each: int = 0
    awg_grid: float = GRID_NS  # -> worker.awg_grid_cur (attribute, not an arg)
    # Resonator-correction state, handed to the worker as attributes exactly
    # like awg_grid (the GUI's _hand_correction_to_worker). Not stored in
    # presets; defaults = Worker.__init__ = GUI defaults. Set these on the
    # returned WorkerArgs to run with a non-default correction model.
    cor_model_cur: str = 'measured'
    f0_cur: float = 9700.0
    q_cur: float = 88.0
    phase_cor_cur: str = 'False'
    meas_freq_cur: object = None   # np.ndarray (MHz) when a measured H(f) is loaded
    meas_H_cur: object = None      # matching complex np.ndarray

    def _common_tail(self):
        return (self.b_sech, self.combo_cor, self.combo_synt,
                self.laser_flag, self.laser_num, self.q_switch_delay,
                self.iq_phase, self.iq_cor, self.win_left, self.win_right,
                self.zero_order)

    def _pulse_block(self):
        return (*self.rect, self.n_wurst, self.rep_rate)

    def exp_args(self):
        """worker.exp (Linear Time), matching dig_start_exp's packing."""
        return ((self.decimation, self.averages, self.scans, self.points,
                 self.exp_name, self.curve_name, *self._pulse_block(),
                 self.field, self.ch0_ampl, self.ch1_ampl, *self.awg)
                + self._common_tail()
                + (self.x0, self.xdelta, self.first_order, self.second_order,
                   self.save2d))

    def exp_log_args(self):
        """worker.exp_log (Log Time)."""
        return ((self.decimation, self.averages, self.scans, self.points,
                 self.log_start, self.log_end,
                 self.exp_name, self.curve_name, *self._pulse_block(),
                 self.field, self.ch0_ampl, self.ch1_ampl, *self.awg)
                + self._common_tail()
                + (self.x0, self.xdelta, self.first_order, self.second_order,
                   self.save2d))

    def exp_amplitude_args(self):
        """worker.exp_amplitude (Amplitude sweep)."""
        return ((self.decimation, self.averages, self.scans, self.points,
                 self.step_ampl, self.field,
                 self.exp_name, self.curve_name, *self._pulse_block(),
                 self.ch0_ampl, self.ch1_ampl, *self.awg)
                + self._common_tail()
                + (self.first_order, self.second_order, self.save2d))

    def exp_field_args(self):
        """worker.exp_field (Field sweep)."""
        return ((self.decimation, self.averages, self.scans,
                 self.start_field, self.end_field, self.step_field,
                 self.exp_name, self.curve_name, *self._pulse_block(),
                 self.ch0_ampl, self.ch1_ampl, *self.awg)
                + self._common_tail()
                + (self.first_order, self.second_order, self.save2d))

    def exp_eseem_args(self):
        """worker.exp_eseem (ESEEM Avg): exp args + tau-averaging tail."""
        return self.exp_args() + (self.eseem_inc2, self.cycles, self.save_each)


def build_worker_args(preset, exp_name, curve_name='exp', combo_cor=0,
                      combo_synt=1, save2d=0, **overrides):
    """Turn a Preset into WorkerArgs, reproducing the GUI's formatting.

    combo_cor / combo_synt / save2d are not stored in presets; defaults match
    the GUI defaults ('No' correction, synthesizer 1, no 2D save). overrides
    may replace scalar Preset fields (points, scans, field, rep_rate,
    averages, decimation, ...) before formatting.
    """
    for key, value in overrides.items():
        if not hasattr(preset, key):
            raise PresetError(f'unknown preset override {key!r}')
        setattr(preset, key, value)

    slots = preset.slots

    # LASER: P2 becomes the laser pulse (worker's laser branch shifts the MW
    # pulses to P3+); the laser combo picks the flavour, and Nd:YaG forces the
    # 9.9 Hz repetition-rate cap exactly like the GUI's rep_rate() handler.
    laser_flag = 1 if slots[1].typ == 'LASER' else 0
    laser_num = 2 if preset.laser == 'NovoFEL' else 1
    rep_rate = str(float(preset.rep_rate))
    if laser_flag == 1 and laser_num == 1:
        rep_rate = str(9.9)

    ph = _expand_phases(slots)

    # AWG timing grid: mirrors MainWindow.grid_for -- on the fine grid all
    # P2..P9 timing fields and the P1 start / start increments snap to
    # 0.8 ns; the P1 length (ADC window) stays on the 3.2 ns tick.
    g = preset.awg_grid
    fine = g == AWG_GRID_NS

    # P1 / DETECTION: p1_exp = [type, start(+shift), length, receiver phases,
    # start inc, length inc, detection frequency]
    p1 = slots[0]
    rect = [[p1.typ,
             _ns(round(_snap(p1.start, g) + AWG_OUTPUT_SHIFT_NS, 1)),
             _ns(_snap(p1.length)), ph[0],
             _ns(_snap(p1.st_inc, g)), _ns(_snap(p1.len_inc)),
             _mhz(p1.freq)]]
    awg = []
    for i in range(1, 9):
        s = slots[i]
        # p{i}_exp: TRIGGER_AWG gate = [start(+shift), length, d_start, len_inc]
        rect.append([_ns(round(_snap(s.start, g) + AWG_OUTPUT_SHIFT_NS, 1)),
                     _ns(_snap(s.length, g)),
                     _ns(_snap(s.st_inc, g)), _ns(_snap(s.len_inc, g))])
        # p{i}_awg_exp: [func, freq, sweep, length, sigma, start, amplitude,
        # phases, d_start, len_inc]
        awg.append([s.typ, _mhz(s.freq), _mhz(s.sweep),
                    _ns(_snap(s.length, g)), _ns(_snap(s.sigma, g)),
                    _ns(_snap(s.start, g)), s.coef, ph[i],
                    _ns(_snap(s.st_inc, g)), _ns(_snap(s.len_inc, g))])

    # Integration window: ns -> points at 0.4 ns * decimation, clamped to the
    # detection length (win_left()/win_right()).
    tpp = 0.4 * preset.decimation
    p1_len = _snap(p1.length)

    def win_points(win_ns):
        pts = int(float(win_ns) / tpp)
        if round(pts * tpp, 1) > round(p1_len, 1):
            pts = int(round(p1_len, 1) / tpp)
        return pts

    return WorkerArgs(
        decimation=preset.decimation, averages=preset.averages,
        scans=preset.scans, points=preset.points,
        exp_name=exp_name, curve_name=curve_name,
        rect=rect, awg=awg,
        n_wurst=preset.n_wurst, rep_rate=rep_rate,
        field=preset.field, ch0_ampl=preset.ampl_1, ch1_ampl=preset.ampl_2,
        b_sech=preset.b_sech, combo_cor=combo_cor, combo_synt=combo_synt,
        laser_flag=laser_flag, laser_num=laser_num, q_switch_delay=0,
        iq_phase=preset.phase_deg * math.pi * 2 / 360,
        iq_cor=1 if preset.iq_corr == 2 else 0,
        win_left=win_points(preset.win_left_ns),
        win_right=win_points(preset.win_right_ns),
        zero_order=preset.zero_order_deg / DEG_RAD,
        x0=_snap(preset.x0), xdelta=_snap(preset.xdelta),
        first_order=preset.first_order_deg / FIRST_ORDER_COEF,
        second_order=preset.second_order_deg / SEC_ORDER_COEF,
        save2d=save2d,
        log_start=_log_snap(preset.log_start, fine), log_end=_log_snap(preset.log_end, fine),
        start_field=preset.start_field, end_field=preset.end_field,
        step_field=preset.step_field, step_ampl=preset.step_ampl,
        eseem_inc2=[_ns(_snap(s.st_inc2, g)) for s in slots],
        cycles=preset.cycles, save_each=preset.save_each,
        awg_grid=g,
    )
