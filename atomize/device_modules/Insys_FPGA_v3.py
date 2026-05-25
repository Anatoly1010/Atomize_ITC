"""Atomize ITC — Insys_FPGA v4 (drop-in subclass for hardware tests).

v4 = v3 + two fixes uncovered by the first hardware-test cycle on
DAC sine-wave input. v3 alone reproduced two symptoms in real ops:
  - Live mode: only the first buffer of a snapshot ever parsed; no
    new data afterward; the live plot froze on the first frame.
  - Exp mode: only the first buffer's nids accumulated, other points
    stayed at zero, drain loop's `count_nip[-1] >= 1` exit condition
    was never satisfied → experiment stuck at the last point.

Both symptoms have a single underlying cause: the c_int driver buffer
is over-allocated 4x relative to the actual stream. Only the first
`nStrmBufSizeb_brd / 4` int32 hold packet data; the remaining 3/4 is
zero padding (description.txt: "A quarter of this buffer is occupied
by digitized data, the rest is filled with zeros"). v1 encodes this
via `ind = np.append(ind, [int(nStrmBufSizeb_brd / 4)])` (L3948) as
its upper split bound. v3 was reshape-ing the WHOLE int32 array and
then carrying the trailing zeros into `tail_carry` for the next call,
which made every subsequent buffer's parse start with a non-header
row and return zero packets.

v4 fixes:
  1. Slice `data` to `data[:int(nStrmBufSizeb_brd / 4)]` at the top of
     `gen_2d_array_from_buffer` so only the real data portion is
     parsed (matches v1's L3948 upper bound). Under the harness this
     is a no-op because `make_instance` sets
     `nStrmBufSizeb_brd = buf_size_i32 * 4`.
  2. Only retain `leftover` as `tail_carry` when its first int32 is
     `HEADER_SIG`. Under the streaming model (packets pack across the
     1/4 data boundary into the next buffer's 1/4) this is true and
     the partial packet carries forward. Otherwise the leftover is
     under-fill padding inside the data portion and must be dropped.

Replaces three buffer-handling methods on top of stock Insys_FPGA:
  * gen_2d_array_from_buffer   — stride-indexed streaming parser,
                                 data-portion slice (v4 fix 1),
                                 HEADER_SIG-on-leftover (v4 fix 2),
                                 in-place direct write into self.data_raw /
                                 self.count_nip, vectorised per-nid grouping.
  * pulser_acquisition_cycle   — slice-only recompute with direct-assign
                                 semantics; no n_scans / ind_test /
                                 correction / m / nid_pc_prev_no_reset state.
  * digitizer_get_curve        — drains ready buffers, recomputes the
                                 touched answer slice, sets self.data_i_ph
                                 and self.data_q_ph for digitizer_at_exit().

Everything else inherits unchanged. test_flag == 'test' delegates to
the v1 implementation so test scripts continue to work.

DEPLOY:
  Place this file at:
      atomize/device_modules/Insys_FPGA_v4.py
  Then in any experimental / control-center script, change:
      import atomize.device_modules.Insys_FPGA as pb_pro
  to:
      import atomize.device_modules.Insys_FPGA_v4 as pb_pro
  No other change is needed — the class name stays `Insys_FPGA`, so
  `pb_pro.Insys_FPGA()` instantiation sites work as-is. Roll back by
  reverting the import; v1 stays in Insys_FPGA.py unchanged.

WHAT v3 ALREADY FIXED (still in v4; validated by 12-scenario harness):
  Scenario D — single-scan, packets straddle aligned buffer boundary.
              v1 mis-averages; v3/v4 correct.
  Scenario G/H — realistic multi-scan transitional buffer.
              v1 produces ~5% amplitude error; v3/v4 correct.
  Scenario I — 4-phase cycling + transitional buffer.
              v1 ~16% error at last point; v3/v4 correct.
  Scenario K — live-mode multi-buffer snapshot with missing nids.
              v1 produces nan; v3/v4 cleanly 0.
  Scenario L — single-scan, cut on last nid's packet run.
              v1 ~6% residual amplitude error at last point even with
              the existing n_scans==2/3 fix; v3/v4 correct.
  Live-mode without pulser_pulse_reset (= first iteration of
              awg_phasing_insys.py's live loop, line 3494):
              v1's count_nip is off by 1 because count_nip += -1 assumes
              reset_count_nip == 1. v3/v4 have no such assumption.

WHAT v4 ADDS (NOT in the harness — caught only on hardware):
  Live mode: subsequent buffers now parse correctly after the first.
              Plot should update on every snapshot rather than freezing.
  Exp mode:  all 196 buffers/scan parse instead of just buf 0. The
              drain loop's `count_nip[-1] >= 1` exit fires when the last
              nid arrives. Experiment finishes.

PERFORMANCE: ~40% faster than v1 on get_curve hot path at production
sizes (74 ms vs 124 ms isolated, on p=50, ph=2, reps=20, scans=2,
adc_window=160, buf=256 kB; scales with p).
"""

import numpy as np
from atomize.device_modules.Insys_FPGA import Insys_FPGA as _Insys_FPGA_v1


HEADER_SIG = np.int32(-1437269761)        # 0xAA5500FF as signed int32

_PHASE_SIGN = {
    '+x': 1,  '+': 1,
    '-x': -1, '-': -1,
    '+y': 1j, '+i': 1j,
    '-y': -1j,'-i': -1j,
}


class Insys_FPGA(_Insys_FPGA_v1):
    """v3 buffer-handling on top of stock Insys_FPGA. All other behaviour
    (AWG, GIM, configuration, test mode, …) inherits unchanged.
    """

    def __init__(self):
        super().__init__()
        # Carry-over bytes from a buffer that ended mid-packet.
        self.tail_carry = np.empty(0, dtype=np.int32)
        # Last nid actually accumulated; used by skip_redundant=True to
        # dedup same-nid packet runs across buffer boundaries.
        self._last_processed_nid = -1

    # ----------------------------------------------------------------- #
    # Streaming parser: in-place direct write, vectorised per-nid sum.  #
    # ----------------------------------------------------------------- #

    def gen_2d_array_from_buffer(self, data, adc_window, p, ph, live_mode,
                                 skip_redundant=False):
        """Parse one driver-buffer worth of int32 data into the running
        self.data_raw / self.count_nip accumulators.

        skip_redundant=False (default): every parsed packet contributes
            to data_raw[nid] and bumps count_nip[nid]. Final
            data_raw/count_nip gives the true average across all
            on-board-averaged packets — this is what produces correct
            noise reduction in standard EPR experiments.

        skip_redundant=True: matches the old digitizer_get_curve2
            semantics. Within each contiguous run of same-nid packets
            (carry across buffer boundaries via self._last_processed_nid)
            only the FIRST packet is accumulated; subsequent packets in
            the run are dropped. Equivalent to running with effectively
            "one packet per nid per call", regardless of how many extras
            the FPGA emitted. Use this when the extra repetitions are
            spurious / non-physical, or to reproduce v2's behaviour.

        Returns (lo_nid, hi_nid) — the inclusive range of nids touched
        in this call, or (None, None) if no complete packets were
        processed (rare: buffer was all leftover tail or all zero pad).
        """
        self.buffer_ready = 1
        full_adc = adc_window * 16
        pkt_size = full_adc + 8
        total_points = p * ph

        # v4 fix 1: the c_int driver buffer is over-allocated 4x relative
        # to the actual stream. Only the first nStrmBufSizeb_brd/4 int32
        # hold packet data; the rest is zero padding (description.txt).
        # v1 encodes this via `ind = np.append(ind, [int(nStrmBufSizeb_brd/4)])`
        # (Insys_FPGA.py L3948) as the upper split bound. Without this
        # slice v3 reshape-d over the zero region, pulled the zeros into
        # tail_carry, and the next buffer's parse always returned zero
        # packets. Under the harness this is a no-op because
        # make_instance sets nStrmBufSizeb_brd = buf_size_i32 * 4.
        data_len = int(self.nStrmBufSizeb_brd / 4)
        if data.size > data_len:
            data = data[:data_len]

        if self.tail_carry.size:
            stream = np.concatenate((self.tail_carry, data))
        else:
            stream = data

        n_complete = len(stream) // pkt_size
        if n_complete == 0:
            # Stream shorter than one packet — only worth carrying if it
            # actually looks like the head of a packet.
            if stream.size > 0 and stream[0] == HEADER_SIG:
                self.tail_carry = (stream.copy()
                                   if stream is data else stream)
            else:
                self.tail_carry = np.empty(0, dtype=np.int32)
            return None, None

        pkts = stream[:n_complete * pkt_size].reshape(n_complete, pkt_size)

        # Header validation. Trailing zero-pad on a partially-filled
        # buffer (or any misalignment) shows up as a row whose first
        # int32 is NOT the signature 0xAA5500FF. Truncate at the first.
        hdr_match = pkts[:, 0] == HEADER_SIG
        if not hdr_match.all():
            n_complete = int(np.argmax(~hdr_match))
            pkts = pkts[:n_complete]

        # v4 fix 2: leftover after the last consumed packet is EITHER the
        # head of the next packet (streaming model — packets pack across
        # the data-portion boundary into the next buffer's data portion)
        # OR intra-data-portion under-fill padding. HEADER_SIG => real
        # partial packet, carry it; anything else => drop. Carrying zero
        # padding here was the original bug that froze the live plot
        # after one frame and prevented exp mode from finishing.
        leftover = stream[n_complete * pkt_size:]
        if leftover.size > 0 and leftover[0] == HEADER_SIG:
            self.tail_carry = leftover.copy()
        else:
            self.tail_carry = np.empty(0, dtype=np.int32)

        if n_complete == 0:
            return None, None

        # Extract nids in one vectorised slice (was an int.from_bytes
        # Python call per packet in v1).
        nids_all = pkts[:, 2].astype(np.intp)
        in_range = (nids_all >= 0) & (nids_all < total_points)
        if in_range.all():
            nids = nids_all
            payloads = pkts[:, 8:]
        else:
            nids = nids_all[in_range]
            payloads = pkts[in_range, 8:]

        if nids.size == 0:
            return None, None

        # Optional: dedup consecutive same-nid packets (v2 semantics).
        # Comparing each nid with the previous one (carried from prev
        # buffer via self._last_processed_nid) drops every packet that
        # repeats the immediately-preceding nid -> only the first
        # packet of each run survives.
        if skip_redundant:
            prev_nids = np.concatenate(
                ([self._last_processed_nid], nids[:-1]))
            keep = nids != prev_nids
            if not keep.all():
                nids = nids[keep]
                payloads = payloads[keep]
            if nids.size == 0:
                # Whole buffer was a continuation of the previous run.
                return None, None

        # count_nip += bincount of nids in this buffer (one numpy call).
        self.count_nip += np.bincount(nids,
                                       minlength=total_points).astype(np.int32)

        # data_raw[nid] += sum of all this-buffer's payloads of that nid.
        # In real ops a buffer holds ~5 unique nids out of ~100 packets,
        # so iterating unique nids and summing the sub-mask is much
        # faster than a per-packet Python loop.
        unique_nids, inverse = np.unique(nids, return_inverse=True)
        for k, nid in enumerate(unique_nids):
            mask = inverse == k
            self.data_raw[nid * full_adc:(nid + 1) * full_adc] += \
                payloads[mask].sum(axis=0, dtype=np.int32)

        last_nid = int(unique_nids[-1])
        self.N_IP = last_nid
        # Track for cross-buffer skip_redundant dedup.
        self._last_processed_nid = int(nids[-1])
        return int(unique_nids[0]), last_nid

    # ----------------------------------------------------------------- #
    # Phase combine — recomputes only the touched point slice.          #
    # ----------------------------------------------------------------- #

    def pulser_acquisition_cycle(self, data1, data2, points, phases,
                                 adc_window, acq_cycle=('+x',),
                                 lo=None, hi=None):
        """Recompute the answer for the point-range whose nids span
        [lo, hi]. Direct ASSIGN to self.answer[i_pt:j_pt] (no
        accumulation across calls, no zeroing pass for multi-scan):
        the running data_raw[nid] / count_nip[nid] already encodes
        every scan that's happened so far.

        Legacy ``data1`` and ``data2`` arguments are accepted (so any
        external caller using v1's (data1, data2, points, ...) signature
        still works) but ignored; the inputs come from self.data_raw /
        self.count_nip.
        """
        if self.test_flag == 'test':
            return _Insys_FPGA_v1.pulser_acquisition_cycle(
                self, data1, data2, points, phases, adc_window, acq_cycle)

        counts_adc = int(adc_window * 8 / self.dec_coef)
        counts_adc_full = int(adc_window * 16)
        total_points = int(points * phases)

        # (Re-)allocate the answer array if its shape or dtype changes.
        if (not hasattr(self, 'answer')
                or self.answer.shape != (points, counts_adc)
                or self.answer.dtype != np.complex64):
            self.answer = np.zeros((points, counts_adc), dtype=np.complex64)

        # No new data signal: return None so the caller skips replot
        # (uniform "no new data -> no action" contract with
        # digitizer_get_curve). External direct callers that want a
        # full recompute should pass lo=0, hi=points*phases-1 explicitly.
        if lo is None:
            return None, None

        # Expand the nid range to phase-cycle boundaries.
        i_nid = (lo // phases) * phases
        j_nid = min(((hi // phases) + 1) * phases, total_points)
        i_pt = i_nid // phases
        j_pt = j_nid // phases
        n_nid = j_nid - i_nid

        counts = self.count_nip[i_nid:j_nid]
        safe_counts = np.where(counts > 0, counts, 1)
        data_2d = self.data_raw[
            i_nid * counts_adc_full:j_nid * counts_adc_full
        ].reshape(n_nid, counts_adc_full)

        norm = self.adc_sens / (self.gimSum_brd * phases)
        data_i = (data_2d[:, 0::2 * self.dec_coef].astype(np.float64)
                  * norm / safe_counts[:, None])
        data_q = (data_2d[:, 1::2 * self.dec_coef].astype(np.float64)
                  * norm / safe_counts[:, None])

        new_slice = np.zeros((j_pt - i_pt, counts_adc), dtype=np.complex64)
        for phase_idx, label in enumerate(acq_cycle):
            s = _PHASE_SIGN[label]
            new_slice += s * (data_i[phase_idx::phases]
                              + 1j * data_q[phase_idx::phases])

        self.answer[i_pt:j_pt] = new_slice
        return self.answer.real, self.answer.imag

    # ----------------------------------------------------------------- #
    # Top-level get_curve.                                              #
    # ----------------------------------------------------------------- #

    def digitizer_get_curve(self, p, ph, live_mode=0, integral=False,
                            current_scan=1, total_scan=1,
                            skip_redundant=False):
        """Drain ready buffers (in-place direct write), then recompute
        the answer for whichever point range was touched this call.

        In live mode (live_mode=1), self.data_raw / self.count_nip /
        self.tail_carry are reset at entry so the call returns a
        snapshot of just the buffers that arrived since the previous
        call (matches v1's documented contract and awg_phasing_insys.py's
        usage).

        skip_redundant=False (default): every parsed packet is summed
            into the running average. Correct on-board-averaging
            semantics, lowest noise.
        skip_redundant=True: matches the old digitizer_get_curve2
            behaviour — only the first packet of each consecutive
            same-nid run contributes (across buffer boundaries via
            self._last_processed_nid). Use when the FPGA's extra
            repetitions are spurious or you specifically want the v2
            data path.
        """
        self.l_mode = live_mode

        if self.test_flag == 'test':
            return _Insys_FPGA_v1.digitizer_get_curve(
                self, p, ph, live_mode, integral, current_scan, total_scan)

        total_points = int(p * ph)
        adc_window = self.adc_window

        # Lazy allocate on first non-test call (or every call in live mode).
        if (self.flag_adc_buffer == 0 and live_mode == 0) or live_mode == 1:
            self.data_raw = np.zeros(int(total_points * adc_window * 16),
                                      dtype=np.int32)
            self.count_nip = np.zeros(total_points, dtype=np.int32)
            self.tail_carry = np.empty(0, dtype=np.int32)
            # Reset cross-buffer dedup state on (re-)init.
            self._last_processed_nid = -1
            # Force re-allocation of self.answer next time it's needed.
            if hasattr(self, 'answer'):
                del self.answer
            if live_mode == 0:
                self.flag_adc_buffer = 1

        is_drain = (self.nIP_No_brd == total_points
                    and current_scan == total_scan
                    and live_mode == 0)

        lo, hi = None, None
        any_processed = False

        while True:
            BufCnt = self.AdcStreamGetBufState()
            new_bufs = BufCnt - self.nStrmBufTotalCnt_brd
            new_bufs = self.overflow_check(self.strmBufNum_brd, new_bufs,
                                           BufCnt,
                                           self.nStrmBufTotalCnt_brd)

            if new_bufs > 0:
                for _ in range(new_bufs):
                    self.AdcStreamGetBuf_buf(self.brdDataBuf_brd)
                    if self.flag_sum_brd == 1:
                        buf_lo, buf_hi = self.gen_2d_array_from_buffer(
                            np.frombuffer(self.brdDataBuf_brd,
                                          dtype=np.int32),
                            adc_window, p, ph, live_mode,
                            skip_redundant=skip_redundant)
                        if buf_lo is not None:
                            lo = buf_lo if lo is None else min(lo, buf_lo)
                            hi = buf_hi if hi is None else max(hi, buf_hi)
                            any_processed = True
                self.nStrmBufTotalCnt_brd = BufCnt

            if not is_drain:
                break
            # Drain exit: any packet of the last nid has been observed.
            if self.count_nip[-1] >= 1 and self.N_IP == total_points - 1:
                break

        if not any_processed:
            return None, None

        di, dq = self.pulser_acquisition_cycle(
            None, None, p, ph, adc_window,
            acq_cycle=self.detection_phase_list, lo=lo, hi=hi)

        # digitizer_at_exit() and any downstream caller that reads the
        # last computed answer expect these attributes.
        self.data_i_ph = di
        self.data_q_ph = dq

        if integral:
            scale = 0.4 * self.dec_coef
            res_i = np.sum(di[:, self.win_left:self.win_right],
                           axis=1) * scale
            res_q = np.sum(dq[:, self.win_left:self.win_right],
                           axis=1) * scale
            return res_i, res_q
        return di.T, dq.T
