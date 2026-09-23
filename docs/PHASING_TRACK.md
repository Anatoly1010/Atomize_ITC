# Phasing reference curves

The AWG and RECT Insys phasing windows have **T** and **×** buttons between the
Repetition Rate label and its spinbox. During a running preview, click T to keep
a frozen copy of the displayed I/Q curves in Dig and, if Live FFT is enabled,
the displayed FFT curves. Each click captures anew and replaces the previous
references. × clears them at any time, including while stopped.

References are drawn behind the incoming data at 70% opacity in fixed colours,
cyan for the first curve and magenta for the second, with the source curve's
line width. Each has a legend entry such as `ch ref` or `FFT ref`.

Both preview readout modes are supported: `l_mode=0` calls
`digitizer_get_curve(live_mode=1)` for live snapshots; `l_mode=1` calls
`digitizer_get_curve(live_mode=0)` for accumulation. The Live Mode editing
checkbox does not control T, Auto Window, or Auto Phase. T is disabled while the
preview is stopped, during preflight, and during full experiments.

References survive preview stop, restart, and worker failure while the same
phasing window stays open. They retain their original axes, phase, and any plot
movement or scaling; subsequent data updates do not modify them. Different
acquisition lengths, starting coordinates, or sample spacings keep separate
x-axes for the reference and incoming curve. They are not stretched or resampled
to match. Auto range includes both curves; a manually zoomed view can hide
portions outside that view. Closing the phasing window, deleting/clearing the
plot, or another tool taking over that plot removes them. References are held
only in memory and are excluded from the live-curve export dictionary and
acquisition results.

FFT capture stores either the magnitude spectrum or both phase-corrected
components. Changing Phase Correction or toggling Live FFT clears the FFT
reference while retaining Dig. If any requested plot has no current curves yet
(for example FFT was just enabled), the capture changes nothing: existing
references stay and the main log names the missing plot. Click T again once the
curves appear. Dig and FFT capture their displayed frames, which can come from
adjacent acquisitions because plotting updates separately.

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

- Full test suite passed (356 passed, 7 skipped, 2 xfailed), including new
  checks that one T click replaces references, that a failed capture keeps them
  and logs the missing plot, reference colours/opacity/width and legend names,
  legend cleanup on clear, and T/× enabled states while stopped, in preflight
  and in experiments.
- Replaying recorded 2026-06-24 sifter echo traces through the real main window
  confirmed one-click replacement, old references kept on a failed capture
  during restart, cyan/magenta colours, and legend cleanup on ×.
- Offscreen builds of both phasing windows at width 1720 confirmed the
  Repetition Rate spinbox stays aligned with the column below.
- The GUI/engine equivalence harness was not re-run; worker arguments and
  protocols are unchanged. Hardware acquisition was not run.
