# I/Q balance correction (transmit and receive): plan

Status: plan only (2026-09-29), not started.

## Why

The two DAC channels (I, Q) and the two ADC channels each have a small gain and phase imbalance.
It creates a mirror image at −f:

- In transmission, the MW pulse gets an unwanted sideband at LO − f, which excites spins at the
  mirror frequency.
- In detection, a mirror appears in I + iQ.

IRR ≈ (ε² + θ²)/4, where ε is the relative gain error and θ the quadrature error in radians.

A DAC → ADC loopback test was made on 2026-09-29 (`insys_paper/2026_09_29_dac_adc_loopback/`,
README there). It gave:

| | ε | θ | image |
|---|---|---|---|
| 50 MHz | 0.8 % | 0.18° | −48 dBc |
| 250 MHz | 0.3 % | 0.08° | −57 dBc |

Scaling CH1 and shifting its phase moved the image to −65…−71 dBc. These loop values are not
suitable for the spectrometer, for two reasons:

- they mix the transmit and receive imbalances;
- they change when cables are moved.

On the spectrometer the I/Q modulator and demodulator will dominate, typically around 1 % and 1°.

What exists today:

- CH1 phase: `phase_shift_ch1_seq_mode_awg`, set from the GUI "Phase" box.
- Channel amplitudes: `awg_amplitude`, integer mV only.
- "IQ Correction" in the GUI is only digital demodulation plus phase orders. It does not correct
  the I/Q imbalance.

## Steps

1. **Module mechanism (transmit), no numbers.**
   - `Insys_FPGA`: a CH1 gain factor and a CH1 phase offset as functions of the carrier frequency.
   - The table lives in `PB_Insys_DAC_config.ini`, for example
     `iq_cal_freq_MHz`, `iq_cal_gain_ch1`, `iq_cal_phase_ch1_deg`, with linear interpolation.
   - Apply it per pulse at the pulse frequency (centre frequency for WURST and SECH/TANH).
   - It multiplies the CH1 samples and adds to `phase_shift_ch1_seq_mode_awg`.
   - Runtime API: `awg_iq_correction(on/off | table)`.
   - Default off, so the current behaviour is unchanged.
   - Allow fractional mV in `awg_amplitude`.
   - Tests: test mode, plus a loopback check with `loopback.py spectrum` (the image must drop).
2. **Receiver calibration on the spectrometer.**
   - Feed a clean tone at LO + f into the receiver, for example from SYNT2 if the bridge can route it.
   - From the image in I + iQ, get ε_rx(f) and θ_rx(f).
   - Correct it in software at readout: a matrix on (I, Q) before demodulation, in
     `digitizer_demodulate`, stored in `digitizer_insys.param`.
3. **Transmitter calibration on the spectrometer.**
   - Preferably with a spectrum analyzer at the modulator output (coupler, before the HPA):
     CW or a long pulse at +f.
   - Minimise the LO − f sideband with CH1 gain and phase at several f (for example 25, 50, 100,
     150, 200, 250 MHz) and fill the step 1 table.
   - Note the LO leakage at the same time.
   - Without an analyzer: through the receiver, but only after step 2.
4. **Check.**
   - Image before and after, in the MW spectrum and in the received signal.
   - Stability over time and after re-cabling.
   - Record where the table and the date of the calibration are stored.

## Open questions

- Can the bridge route SYNT2 (or another source) into the receiver input for step 2?
- Is a spectrum analyzer covering X-band available for step 3?
- How often to recalibrate. Recalibration is needed at least when the bridge or the cables change.
