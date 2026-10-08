# I/Q calibration of the whole bridge (transmit and receive paths): plan

Status: plan written 2026-09-29. It covers the correction mechanism in the module and how to measure
the calibration on the complete spectrometer: card, bridge up-converter, MW path, bridge receiver
and card ADC.

**Done 2026-10-08 (transmit path):**
- Step 2 was measured on the bridge Amp-I/Q monitor output after the MW amplifier, not through a
  loopback. That output uses the same LO, and `fv_ctrl` lies in its path. The DSO-X 3034T recorded
  the monitor: CH1 I, CH2 Q, CH3 LASER_1 trigger.
- Stepping `fv_ctrl` separates the transmit image from the monitor's own image, as in the model below.
- **Result (transmit image vs IF):**

  | IF (MHz) | 20 | 30 | 50 | 75 | 100 | 125 | 150 | 200 | 250 | 300 | 350 | 400 |
  |---|---|---|---|---|---|---|---|---|---|---|---|---|
  | Uncorrected (dBc) | −33.5 | −33.8 | −33.9 | −32.9 | −32.4 | −31.1 | −30.8 | −29.8 | −29.2 | −28.5 | −28.6 | −29.2 |
  | Module correction (dBc) | −68.8 | −66.9 | −66.3 | −65.8 | −58.0 | −60.3 | −57.0 | −60.3 | −49.1 | −55.0 | −53.6 | −42.8 |

- **Correction found:**
  - CH1 phase: +0.3° at 20 MHz to +2.4° at 400 MHz. This is about 21 ps of CH1 delay plus a ripple
    of ±0.6°, so it needs a table per IF.
  - CH1/CH0 ratio: 1.04–1.07.
- **Step 0 (transmit) is implemented:**
  - The `iq_cal_*` table is in `PB_Insys_DAC_config.ini`.
  - `Insys_FPGA` applies it to every pulse at the pulse frequency, or at the centre frequency for
    WURST and SECH/TANH.
  - The gain only ever lowers a channel, so 260 mV (the DAC full scale) is never exceeded.
  - Negative IFs were added the same day, measured with 1000 ns pulses at −20 … −400 MHz. Uncorrected
    −28…−34 dBc; with the module correction −53.7…−71.9 dBc down to −250 MHz, −46.6 / −49.8 /
    −58.2 dBc at −300 / −350 / −400 MHz. One sweep taken right after the bridge restart was too noisy
    and was discarded.
  - `awg_iq_correction('On'|'Off')` switches it; it is on by default from `iq_cal_enable`.
  - The GUI amplitude and phase boxes were removed.
- **High-IF limit:** step-to-step fluctuation of the measured image. It averages down only slowly
  with the number of shots.
- **LO leakage:** 14.2 mV at the monitor, about −22 dBc of a 50 % pulse at AWG attenuator 16 dB.
  It cannot be nulled from the AWG, because the DAC → modulator I/Q path does not pass DC: an
  injected DC decays within about 0.5 µs.
- **±5 and ±10 MHz added** (28-point table):
  - Near zero the phase bends away (+0.6° at +5/+10 MHz, −0.3° at −5/−10 MHz). A 1/f phase like
    this fits slightly different AC-coupling in the I and Q paths.
  - With the module correction: −64.7…−81.7 dBc from −20 to +20 MHz.
  - Below ±5 MHz the table interpolates linearly across zero.
- **Chirps (step 3, done):**
  - WURST and SECH/TANH are corrected sample by sample at their instantaneous frequency.
  - Checked with `iq_chirp.py`, a WURST −200 → +200 MHz, 1000 ns on the monitor, analysed in 50 ns
    segments with a joint fit of the line and its mirror plus the `fv_ctrl` separation.
  - Image over |f| ≥ 40 MHz: median −32.7 → −53.0 dBc, worst segment −30.4 → −45.2 dBc.
- **Receive path (step 1, done):**
  - Measured with `iq_rx.py`: coal echo, two-step ±x cycle, 3441 G, RV 0 dB, 5 kHz, 2000 shots per
    step, 3 repeats.
  - The synthesizer was retuned with the IF (LO = 9670 + f) so the RF and field stay fixed.
    IFs ±20 … ±300 MHz.
  - The receive mirror b is −26…−32 dBc and varies only slowly with IF, so the bridge demodulator
    dominates (card alone −48 dBc).
  - The `rx_cal_*` table is in `PB_Insys_DAC_config.ini`. `digitizer_demodulate` applies
    z → (z − κ·b·conj(z))/(1 − |κb|²), where κ is the mean squared receiver phase factor (1 for ±x
    cycles, 0 for x/y cycles, which already cancel the mirror). It is skipped at 0 MHz.
  - `digitizer_iq_correction('On'|'Off')` switches it, on by default.
  - Checked on fresh data: the mirror drops from −26…−32 to a median of −51.6 dBc (worst −40.7 at
    +75 MHz), at the single-run noise floor.
  - **±10 MHz added:** measured with 160 ns pulses at 10.1/18.5 %, which give a ~200 ns echo that
    separates from its mirror.
    - The ±20 MHz overlap check agrees with the short-pulse table within 0.003–0.005.
    - b = 0.0244 − 0.0013j at +10 MHz and 0.0395 − 0.0093j at −10 MHz, so the mirror changes near
      zero as on the transmit side.
    - ±5 MHz was not usable: at +5 the echo and its mirror still overlap, and at −5 the echo is
      halved by the AC coupling. Below ±10 MHz the table interpolates; 0 MHz is skipped.
  - **Offline correction of raw 2D data** (Shift Offset Off saves raw data):
    - Normally, demodulating at the IF and low-pass filtering (or integrating) removes the mirror
      exactly, as long as the echo spectrum is narrower than 2·|IF|.
    - At low IF or for broadband signals, apply z → (z − κb·conj(z))/(1 − |κb|²) with b from the
      table at the AWG IF before demodulating.
  - **Digitizer stall:** the acquisition stopped ("no new data for 60 s") whenever one point took
    longer than about 1–1.5 s:
    - 1 kHz × 2000 shots and 10 kHz × 16000 shots stalled;
    - 5 kHz × 4000 and 10 kHz × 4000 ran fine;
    - the cause is under investigation.
  - **Open:** b may depend on the video attenuation (VA1/VA2); spot-check at another VA setting.
  - At 1 kHz a long run stopped with a digitizer timeout; 5 kHz was fine.
- **Spin checks (coal, RV 0 dB, `iq_spin_check.py`):**
  - *Normal echo* (3441 G, +50 MHz, 38.4 ns at 42/77 %): with the correction On vs Off the echo is
    101.5 ± 1.3 % and −0.25 ± 0.47°. The correction does not change ordinary experiments.
  - *Image side:* the AWG −50 MHz probe is on resonance at 3477.9 G, i.e. on the high-field side.
    So the image of a +f pulse lies 2f above the main RF line.
  - *Pump-probe at the image field (step 4 spin check):* **non-essential and not pursued.**
    - The +50 MHz pump image lowered the probe echo by about 2.9 ± 0.8 % more with the correction
      Off than with it On.
    - But the pump also causes a 7 % dip that does not depend on the correction (main tone 100 MHz
      away), which hides any residual image.
    - Long full-power pumps (1500–1600 ns, RV 0 dB) made the bridge stop the pulses after about
      5000 pulses, even at 300 Hz.
    - The calibration therefore rests on the monitor measurement.
- **Open:**
  - stability (step 4).
- **Data and scripts:** `~/experimental_data/Melnikov/2026_10_08_iq_monitor/` on the Linux box.

What exists today:
- **CH1 phase:** `phase_shift_ch1_seq_mode_awg`, module base value from config `ch1_phase_shift`; the GUI "Phase" box was removed.
- **Channel amplitudes:** `awg_amplitude`, integer mV only.
- **"IQ Correction" in the GUI** is only digital demodulation plus phase orders. It does not correct
  the I/Q imbalance.

## Model

Complex baseband at the IF offset f, with z = exp(iφ) exp(2πi f t) the programmed waveform:

- **Transmitter** (DAC I/Q and the bridge I/Q modulator): s = α z + β z*.
  - β/α is the transmit image, which appears as a sideband at LO − f.
  - The modulator also adds LO leakage λ at f = 0.
- **MW path** between the modulator and the demodulator: a phase θ, which the bridge phase shifters
  set in 5.625° steps (`mw_bridge_fv_ctrl`, `mw_bridge_fv_prm`).
- **Receiver** (bridge I/Q demodulator and the two ADC channels):
  r = γ e^{iθ} s + δ e^{−iθ} s* + offset. δ/γ is the receive image.

**Image seen in r at −f:**

  c(θ) = γβ e^{iθ} + δα* e^{−iθ}

The two contributions rotate in opposite directions with θ. Stepping one phase shifter through
360° and fitting c(θ) to A e^{iθ} + B e^{−iθ} therefore separates the transmit image (A/(γα)) from
the receive image (B/(γα*)). The rest of the method is built on this.

Useful facts from the 2026-09-29 tests:
- The DAC → ADC loopback alone has an image of −48 dBc (50 MHz) and −57 dBc (250 MHz), with
  ε ≤ 0.8 % and θ ≤ 0.2°. The bridge modulator and demodulator are expected to dominate
  (≈ 1 %, 1°, i.e. about −40 dBc).
- The four-step quadrature cycle (π/2 +x, +y, −x, −y; receiver +x, −y, −x, +y) already cancels
  the receive image and the offsets in averaged data. The echo test in
  `insys_paper/2026_09_29_echo_adc/` showed no mirror.
  - Receive correction therefore matters only for experiments without such a cycle: fast
    two-step cycles, single-shot or live data.
  - The transmit image cannot be cycled away. It is a real excitation at LO − f, so it has priority
    for broadband and two-frequency experiments (chirps, DEER pump and observer).

## Steps

### 0. Module mechanism and preparation
- **Transmit correction in `Insys_FPGA`:** a CH1 gain factor and a CH1 phase offset as functions of
  the carrier frequency.
  - The table lives in `PB_Insys_DAC_config.ini`, for example `iq_cal_freq_MHz`,
    `iq_cal_gain_ch1`, `iq_cal_phase_ch1_deg`, with linear interpolation.
  - It is applied per pulse at the pulse frequency (centre frequency for WURST and SECH/TANH):
    it multiplies the CH1 samples and adds to `phase_shift_ch1_seq_mode_awg`.
  - Runtime API: `awg_iq_correction(on/off | table)`. Default off, so the current behaviour is
    unchanged.
  - Allow fractional mV in `awg_amplitude`.
- **Receive correction:** a 2 × 2 matrix on (I, Q) as a function of f, applied before
  `digitizer_demodulate`. It is stored in `digitizer_insys.param`, default off.
- **Tests:** test mode, plus the DAC → ADC loopback (`SI_loopback.py spectrum`), where the image
  must drop.
- Test script with the same single-sequence-per-point and warm-up procedure as
  `insys_paper/submission_ieee_tim/supplementary/SI_loopback.py`.
- Record: bridge settings (attenuators, phase shifters, LO), IF list, date.

### 1. Receiver from the spin echo (no extra hardware)
- **Why the echo works.** An echo is a single-sideband signal at +f. Transmit images excite spins
  only at LO − f, which is far outside the EPR line for f ≥ 20 MHz. The image of the echo at −f in
  r is therefore purely δ/γ.
- **Sample and pulses.** Coal (or another narrow-line, strong-echo sample); 22.4 ns pulses, as in
  the 2026-09-29 echo test.
- **Acquisition.**
  - Use a two-step cycle only (π/2 ±x, receiver ±x), so that the receive image is not cancelled.
  - Set the field for each IF so that the echo is on resonance at LO + f.
  - IF list: 20, 30, 50, 75, 100, 150 MHz, limited by the resonator bandwidth.
- **Analysis.**
  - Take the FFT of the echo, or demodulate at +f and at −f.
  - ε_rx(f), θ_rx(f) follow from the ratio of the −f and +f components.
  - Repeat at 2–3 settings of `mw_bridge_fv_prm`. The ratio must not depend on it, which checks
    that the transmit image does not contribute.
- **Result.** Receive table → `digitizer_insys.param`. The matrix on (I, Q) is applied before
  `digitizer_demodulate`.

### 2. Transmitter through a bridge loopback (preferred), or a spectrum analyzer
- **Path.** Needs a low-power TX → RX path without spins, for example:
  - the field far off resonance (no echo), the resonator strongly overcoupled or replaced by an
    attenuator or a short;
  - both transmit attenuators at maximum;
  - a long pulse (1–2 µs) at +f and the detection window inside the pulse, as far as the receiver
    protection allows.
  - **Open question for the user:** is there a safe setting of the protection gates and
    attenuators for this path, or a dedicated calibration or monitor path in the bridge?
- **Measurement.**
  - Step `mw_bridge_fv_prm` (or `fv_ctrl`) over 0–354.375° in 5.625° steps (64 points).
  - At each step record the −f and +f components.
  - Fit c(θ) = A e^{iθ} + B e^{−iθ}. A gives the transmit image and B cross-checks step 1.
- **Correction.**
  - Minimise the transmit image with CH1 gain and phase at each f and fill the transmit table.
  - Iterate once: measure, correct, measure.
  - Target: below −55 dBc, i.e. ε ≲ 0.3 %, θ ≲ 0.3°.
- **LO leakage.** Record the component at f = 0 during the same scan. If needed, add I/Q offset
  words: a new module option. The phase cycle removes it from the data, but not from the excitation.
- **Without a loopback path:** a spectrum analyzer on the bridge coupler or monitor output before
  the power amplifier (CW or a long pulse), minimising the LO − f sideband directly.

### 3. Frequency dependence and chirps
- Tables at 10–280 MHz, with linear interpolation, applied per pulse at the carrier.
- For WURST and SECH/TANH the correction at the centre frequency is a first step.
  - The residual image over the sweep is checked by recording a chirp in the step 2 path.
  - If it is too large, a per-sample correction along the sweep follows, i.e. gain and phase as
    functions of the instantaneous frequency.

### 4. Power and stability checks
- **Power.** Repeat the step 2 check at the working transmit power (after the HPA) with a spectrum
  analyzer, if one is available. HPA AM/PM distortion is out of scope, but it should be noted.
- **Stability.** Repeat steps 1–2 after 1 day, after re-cabling and after the bridge is re-tuned;
  define the recalibration rule.
- **Spin check.** Echo with the field set on the transmit mirror frequency (LO − f): the echo from
  the image excitation must drop after correction. This is a low-sensitivity sanity check only.

## Deliverables
- A calibration script (steps 1–2), with its data saved under a dated folder.
- Transmit and receive tables in the config/param files, each with its date and bridge settings.
- A short report: image before and after, per f, both paths.

## Open questions
- Is there a safe low-power TX → RX path in the bridge (step 2), and which settings are needed:
  protection gates, attenuators, rotary vane?
- Is an X-band spectrum analyzer available for step 2 without a loopback path, and for step 4?
- Is `fv_prm` in the signal path or in the receiver LO? The model holds in both cases, but the sign
  of θ in the fit differs.
