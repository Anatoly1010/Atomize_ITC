# I/Q calibration of the whole bridge (transmit and receive paths): plan

Status: plan only (2026-09-29), not started. The module mechanism (CH1 gain and phase table, receive
matrix) is described in `IQ_BALANCE_CORRECTION_PLAN.md`, step 1. This file covers how to measure
the calibration on the complete spectrometer: card, bridge up-converter, MW path, bridge receiver
and card ADC.

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

### 0. Preparation
- Implement the module mechanism (`IQ_BALANCE_CORRECTION_PLAN.md`, step 1), default off.
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
