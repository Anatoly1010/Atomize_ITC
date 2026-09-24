# Pending atomize_docs corrections

Apply in `../atomize_docs` (read its `CLAUDE.md` first), run the strict MkDocs build, then delete the entry here.

## Accumulated echo traces (2026-09-24)

Change: the accumulating preview readout no longer waits at the last phase of each cycle. Before, the board repeated that phase for ~300 ms per cycle while a 1 MB data block filled (hardware: count_nip `[41 40 40 2444]`). Now all phases get equal shots (`[321 320 320 321]`), with about 10× more complete cycles per second. Same change in the AWG and RECT phasing tools (Accumulation mode). Live mode is unchanged.

Runner (`executor.acquire_trace`, used by `tune.echo_window` and the preliminary echo checks):

- `sweeps` / `n_sweeps` is now a **minimum** number of complete phase cycles. The trace is returned at the first data block after that count is reached, so it usually holds more cycles than requested, about one block's worth (≈15 cycles for a 4-step cycle at 5 averages, 1 kHz, 816 ns window).
- Progress is counted as complete cycles, `min(count_nip)`, not as preview redraws.
- A trace step now finishes much faster: 300 cycles took 12 s including board start-up; before, 40 cycles took ~12 s.

Docs to update:

- `docs/projects/epr_auto/steps.md`: regenerate with `docgen`. The `tune.echo_window` `sweeps` help now reads "minimum full phase cycles to average for the trace".
- Any prose page that says the echo-window or preliminary trace averages exactly N phase cycles, or that describes the accumulating preview as waiting for each cycle: reword to "at least N cycles".
- Phasing-tool pages, only if they describe Accumulation mode timing or per-phase counts.

## Phase correction (2026-09-24)

- Digitizer reference, `digitizer_read_settings` / `digitizer_demodulate`: copy the new wording from `atomize/documentation/functions/digitizer.md`. The phasing tools store only Zero Order in `digitizer_insys.param` and write 0 for the first and second orders.
- Phasing-tool pages, if they describe Phase Correction: one Zero Order now works for both the time trace and the FFT, so the Auto phase value carries over. First/Second Order (deg/MHz, deg/MHz²) affect only the FFT view and never experiments. First Order range is ±5400 deg/MHz; Points to Drop is 0–37500 pts.
