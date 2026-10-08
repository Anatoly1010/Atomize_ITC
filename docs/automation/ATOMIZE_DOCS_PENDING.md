# Pending atomize_docs corrections

Apply in `../atomize_docs` (read its `CLAUDE.md` first), run the strict MkDocs build, then delete the entry here.

- [ ] 2026-10-08 transmit I/Q correction: add the `awg_iq_correction` section after `awg_amplitude` on the AWG function page.
  - Say the table covers −400 … 400 MHz (both signs), and that chirps are corrected sample by sample.
  - Add the `digitizer_iq_correction` section on the digitizer page and the one-line note in `digitizer_demodulate`; text and patch in the same folder (`atomize_docs_digitizer_iq_correction.patch`).
  - Remove any mention of the AWG phasing Amplitude I/Q and Phase boxes.
  - Correct any stated 533 mV Insys default: the default is 260 mV, which is also the full scale.
  - Text and patch: `~/experimental_data/Melnikov/2026_10_08_iq_monitor/atomize_docs_update.md` and `atomize_docs_awg_iq_correction.patch` on the Linux box.
