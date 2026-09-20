# Phasing reference curves

The AWG and RECT Insys phasing windows have a **T** button beside Repetition
Rate, 4 px before its spinbox, matching the link-reset button placement.
During a running preview, click it to keep a frozen copy of the displayed
I/Q curves in Dig and, if Live FFT is enabled, the displayed FFT curves. The
references use the original colours at 30% opacity, behind the incoming data.
Click T again to remove the references.

Both preview readout modes are supported: `l_mode=0` calls
`digitizer_get_curve(live_mode=1)` for live snapshots; `l_mode=1` calls
`digitizer_get_curve(live_mode=0)` for accumulation. The Live Mode editing
checkbox does not control Track, Auto Window, or Auto Phase. New captures and
auto requests are blocked during preflight and full experiments.

The checked state and references survive preview stop, restart, and worker
failure while the same phasing window stays open. T can clear them while
stopped. References retain their original axes, phase, and any plot movement or
scaling; subsequent data updates do not modify them. Different acquisition
lengths, starting coordinates, or sample spacings keep separate x-axes for the
reference and incoming curve. They are not stretched or resampled to match.
Auto range includes both curves; a manually zoomed view can hide portions
outside that view. Closing the phasing window,
deleting/clearing the plot, or another tool taking over that plot removes them.
References are held only in memory and are excluded from the live-curve export
dictionary and acquisition results.

FFT capture stores either the magnitude spectrum or both phase-corrected
components. Changing Phase Correction or toggling Live FFT clears the FFT
reference while retaining Dig. Enable FFT and wait for current data before
capturing it. If T is clicked before current curves arrive, the main log requests
an off/on retry; T remains checked. Dig and FFT capture their displayed frames,
which can come from adjacent acquisitions because plotting updates separately.

## Implementation and review

The control-center output channel carries the capture/clear command to the main
window. The plot dock copies the displayed arrays into separate reference items.
References use the same plotting helper as live curves so auto-range considers
their full original axes. Bare plot items could report truncated or empty bounds
after display downsampling, hiding reference tails when the live window changed.
Plot frames identify the worker and its parent process so capture rejects stale
data and a new worker in the same phasing window can reuse its reference. No
plotting client is created in the phasing GUI, avoiding inheritance of a live
socket by later acquisition workers. Worker arguments and protocols are unchanged.

The Auto Window/Phase audit confirmed that both use the preview's current data
in either readout mode. Auto Phase already updates the Zero Order spinbox;
its value-change signal converts degrees to radians and sends `ZO` to the
worker. The phase sign and wrapping were checked against demodulation. The only
auto-control change blocks requests during preflight.

## Validation

- 112 focused tests passed: reference copies, colours, position/scaling,
  hidden FFT, stale data rejection, ownership, restart retention, both readout
  modes, auto-phase spinbox feedback, and Stop handling.
- Follow-up: all 28 plot tests passed, including eight new combinations of
  shorter, longer, shifted, and differently spaced axes with both FFT modes.
  This verified independent reference/live coordinates and combined auto-range.
- Offscreen checks of both phasing windows at widths 1720 and 2300 confirmed
  the 4 px button-to-spinbox gap matches link reset and the input columns align.
- The GUI/engine equivalence harness reported **ALL PASS**, including worker
  preflights and the trace-capture handshake.
- Hardware acquisition and Windows execution were not run.
