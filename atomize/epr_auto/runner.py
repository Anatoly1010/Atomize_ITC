"""Protocol runner: step loop with autonomy gating, retry policy, the
rail-triggered coarse fallback, a run manifest and notifications.

Autonomy at a checkpoint: supervised pauses at every step, checkpointed at
`checkpoint: true` steps, autonomous never pauses — checkpoints are
auto-approved with a notification and the judges (StepFailure gating in
steps.py) are the only brake.

Failure policy per step: `retries: n` re-runs a failed step up to n extra
times; then `on_fail` decides — abort (default), skip (continue without the
step), ask (operator prompt: retry / skip / abort). A StepFailure carrying
`rails` additionally triggers the coarse fallback (once per step, its retry
granted on top of the retry budget): re-run the most recent earlier
tune.power_for_length (+ the tune.auto_phase steps that followed it — the
vane move invalidated the phase) and retry; the re-runs are recorded in the
manifest like ordinary steps.

The manifest (manifest.json in the run directory, live runs only) is
rewritten atomically after every step, so a crash still leaves a valid
record of everything that ran: resolved parameters, results, judge reports,
attempt counts, and a copy of the protocol file itself.
"""
import json
import shutil
import sys
import traceback
from datetime import datetime

from atomize.epr_auto.protocol import Foreach
from atomize.epr_auto.steps import STEPS, StepFailure


class RunnerAbort(Exception):
    """hard=True marks aborts a foreach on_fail:continue must NOT swallow:
    explicit operator decisions (checkpoint abort/EOF/no-tty, an interactive
    ask -> abort) and unexpected non-StepFailure errors (a code bug recurs
    identically in every iteration — continuing the series just repeats the
    traceback N times and then reports 'finished')."""

    def __init__(self, msg, hard=False):
        super().__init__(msg)
        self.hard = hard


def _count_steps(steps):
    """Total ordinary steps, expanding foreach blocks (values x sub-steps)."""
    return sum(sum(len(g) for g in it.iterations) if isinstance(it, Foreach)
               else 1 for it in steps)


def _loop_tag(var, val):
    """Filename-safe loop stamp, e.g. ('B', '3318 G') -> 'B_3318G'."""
    safe = ''.join(c for c in str(val) if c.isalnum() or c in '-_.')
    return f'{var}_{safe}'


class _Manifest:
    """Crash-safe run record; disabled (log-only) in dry-runs so tests never
    litter the data directory."""

    def __init__(self, protocol, session):
        self.session = session
        self.enabled = not session.test
        self.doc = {
            'protocol': protocol.path.name,
            'sample': protocol.sample,
            'autonomy': protocol.autonomy,
            'started': datetime.now().isoformat(timespec='seconds'),
            'status': 'running',
            'steps': [],
        }
        if not self.enabled:
            return
        run_dir = session.run_dir
        self.path = run_dir / 'manifest.json'
        try:  # keep the exact protocol next to the data it produced
            shutil.copy2(protocol.path, run_dir / f'protocol_{protocol.path.name}')
        except OSError as e:
            session.log(f'      [manifest] protocol snapshot failed: {e}')
        self._write()
        session.log(f'      run directory: {run_dir}')

    def record(self, step, status, attempts, result=None, judges=(), error=None):
        entry = {'name': step.name, 'line': step.line,
                 'params': {k: v for k, v in step.params.items() if v is not None},
                 'status': status, 'attempts': attempts}
        if self.session.loop_context:      # foreach: stamp var/value/index
            entry['loop'] = dict(self.session.loop_context)
        if result is not None:
            entry['result'] = result
        if judges:
            entry['judges'] = [j.as_dict() for j in judges]
        if error is not None:
            entry['error'] = str(error)
        self.doc['steps'].append(entry)
        self._write()

    def finish(self, status):
        self.doc['status'] = status
        self.doc['finished'] = datetime.now().isoformat(timespec='seconds')
        self._write()

    def _write(self):
        if not self.enabled:
            return
        tmp = self.path.with_name('manifest.json.tmp')
        # default=str: results may carry numpy scalars / Path objects
        tmp.write_text(json.dumps(self.doc, indent=2, default=str) + '\n',
                       encoding='utf-8')
        tmp.replace(self.path)


def run_protocol(protocol, session):
    n = _count_steps(protocol.steps)
    mode = 'DRY-RUN (test mode)' if session.test else 'LIVE'
    session.log(f'=== {protocol.path.name} | sample: {protocol.sample} | '
                f'autonomy: {protocol.autonomy} | {n} steps | {mode} ===')
    manifest = _Manifest(protocol, session)

    results = []
    pos = 0
    try:
        for struct_idx, item in enumerate(protocol.steps):
            if isinstance(item, Foreach):
                pos = _run_foreach(protocol, session, manifest, item, results,
                                   pos, n)
            else:
                pos += 1
                _do_step(protocol, session, manifest, item, struct_idx, results,
                         f'[{pos}/{n}]')
    except RunnerAbort as e:
        manifest.finish(f'aborted: {e}')
        session.notify(f'{protocol.path.name}: ABORTED — {e}')
        raise
    except KeyboardInterrupt:
        manifest.finish('aborted: operator interrupt')
        session.notify(f'{protocol.path.name}: ABORTED — operator interrupt')
        raise

    ran = sum(1 for _, r in results if r is not None)
    session.log(f'=== finished: {ran}/{n} steps ran ===')
    manifest.finish('finished')
    session.notify(f'{protocol.path.name}: finished ({ran}/{n} steps ran)')
    return results


def _do_step(protocol, session, manifest, step, index, results, header):
    """Run one ordinary step: log, gate, execute, record, append to results.
    Raises RunnerAbort on an abort decision (a foreach in on_fail:continue mode
    catches it). Returns True if the step ran and produced a result."""
    session.log(f'{header} {step.name}  (line {step.line})')
    for key, value in step.params.items():
        if value is not None:
            session.log(f'      {key} = {value}')

    if _gate(session, step) == 'skip':
        session.log('      skipped by operator')
        manifest.record(step, 'skipped-by-operator', attempts=0)
        results.append((step, None))
        return False

    result, status, attempts = _run_step(protocol, session, manifest, step, index)
    if status != 'ok':
        results.append((step, None))
        return False
    session.log('      -> ' + ', '.join(f'{k}={v}' for k, v in result.items()))
    session.state[step.name] = result
    manifest.record(step, 'ok', attempts, result=result,
                    judges=session.last_judges)
    results.append((step, result))
    return True


def _run_foreach(protocol, session, manifest, block, results, pos, total):
    """Run a foreach block: its sub-steps once per value, with the loop tag set
    for save_path/manifest. A failed iteration (RunnerAbort from a sub-step)
    is recorded and, in on_fail:continue mode, the series moves to the next
    value; on_fail:abort re-raises. Sub-steps get index 0 (the rail fallback,
    which scans protocol.steps for an earlier coarse stage, does not apply
    inside a series — tune once before the loop). Returns the updated position
    counter."""
    nvals = len(block.values)
    session.log(f'=== foreach {block.var}: {nvals} value(s) {block.values} '
                f'(on_fail: {block.on_fail}) ===')
    for vi, (val, group) in enumerate(zip(block.values, block.iterations), 1):
        session.log(f'--- foreach {block.var} = {val}  ({vi}/{nvals}) ---')
        session.loop_tag = _loop_tag(block.var, val)
        session.loop_context = {'var': block.var, 'value': val, 'index': vi}
        try:
            for step in group:
                pos += 1
                _do_step(protocol, session, manifest, step, 0, results,
                         f'[{pos}/{total}]')
        except RunnerAbort as e:
            if block.on_fail != 'continue' or getattr(e, 'hard', False):
                raise          # policy abort, or an operator/unexpected abort
            session.log(f'      foreach {block.var}={val}: iteration aborted '
                        f'({e}) — continuing to next value')
            session.notify(f'foreach {block.var}={val} failed ({e}) — '
                           'continuing to next value')
        finally:
            session.loop_tag = None
            session.loop_context = None
    return pos


def _run_step(protocol, session, manifest, step, index):
    """One step with retries + the rail fallback. Returns (result, 'ok',
    attempts) or (None, 'failed-skipped', attempts); raises RunnerAbort."""
    attempts = 0
    fallback_used = False
    fallback_bonus = 0          # a successful fallback grants one extra attempt
    fallback_blocker = None     # what stopped the fallback chain, if anything
    while True:
        attempts += 1
        session.last_judges = []
        try:
            result = STEPS[step.name].func(session, **step.params)
            return result, 'ok', attempts
        except StepFailure as e:
            error = e
            session.log(f'      step failed (attempt {attempts}): {e}')
        except RunnerAbort:
            raise
        except Exception:
            session.log(traceback.format_exc())
            manifest.record(step, 'failed', attempts,
                            error='unexpected error (see log)')
            raise RunnerAbort(f'step {step.name} raised an unexpected error '
                              '(see above)', hard=True) from None

        # rail-triggered coarse fallback: once per step, an extra attempt on
        # top of the retry budget (it re-tunes the power regime first)
        if getattr(error, 'rails', None) and not fallback_used:
            fallback_used = True
            ran, fallback_blocker = _rail_fallback(protocol, session, manifest,
                                                   index, error.rails)
            if ran:
                fallback_bonus = 1
                continue

        if attempts <= step.retries + fallback_bonus:
            session.log(f'      retry {attempts - fallback_bonus} of '
                        f'{step.retries}')
            continue

        decision = _on_fail_decision(session, step, error)
        if decision == 'retry':
            continue
        manifest.record(step, 'failed-skipped' if decision == 'skip' else 'failed',
                        attempts, judges=session.last_judges, error=error)
        if decision == 'skip':
            session.log(f'      on_fail: continuing without {step.name}')
            session.notify(f'step {step.name} failed ({error}) — skipped '
                           'per on_fail policy')
            return None, 'failed-skipped', attempts
        msg = f'step {step.name} failed: {error}'
        if fallback_blocker is not None:
            msg += f' (rail fallback blocked: {fallback_blocker})'
        # 'abort-op' = the operator chose abort interactively — hard, so a
        # foreach on_fail:continue does not overrule the human
        raise RunnerAbort(msg, hard=decision == 'abort-op')


def _on_fail_decision(session, step, error):
    """Map the step's on_fail policy to 'retry' / 'skip' / 'abort' /
    'abort-op' (an interactive operator abort — see RunnerAbort.hard)."""
    if step.on_fail == 'skip':
        return 'skip'
    if step.on_fail != 'ask':
        return 'abort'
    if session.test:
        session.log('      [on_fail: ask] would prompt the operator — '
                    'aborting in dry-run')
        return 'abort'
    if session.autonomy == 'autonomous' or not sys.stdin.isatty():
        session.notify(f'step {step.name} failed ({error}); on_fail: ask '
                       'with no operator — aborting')
        return 'abort'
    return _ask(f'      step failed: {error}\n'
                '      retry / skip / abort? [r/s/a] ',
                {'r': 'retry', 'retry': 'retry', 's': 'skip', 'skip': 'skip',
                 'a': 'abort-op', 'abort': 'abort-op', '': 'abort-op'},
                on_eof='abort-op')


def _ask(prompt, answers, on_eof):
    """One operator prompt: re-ask until the reply matches a key in `answers`
    (reply -> return value); EOF returns `on_eof`. The tty/autonomy guards
    stay at the call sites — the policies differ per prompt."""
    while True:
        try:
            reply = input(prompt).strip().lower()
        except EOFError:
            return on_eof
        if reply in answers:
            return answers[reply]


def _rail_fallback(protocol, session, manifest, index, rail):
    """Re-run the coarse power stage (and the auto-phase steps tuned after
    it, which the vane move invalidates) after an amplitude-rail failure.
    Only available when the protocol itself declared a tune.power_for_length
    step earlier — the most recent one before the failing step defines the
    coarse stage. The re-runs are recorded in the manifest. Returns
    (ran, blocker): ran is True when the chain ran and the failed step
    should be retried; blocker names what stopped the chain, if anything."""
    coarse_idx = next((j for j in range(index - 1, -1, -1)
                       if getattr(protocol.steps[j], 'name', None)
                       == 'tune.power_for_length'), None)
    if coarse_idx is None:
        session.log(f'      amplitude rail ({rail}) hit, but the protocol has '
                    'no earlier tune.power_for_length step — no fallback')
        return False, None

    if session.test:
        session.log('      [rail fallback] would re-run the coarse stage — '
                    'auto-continuing in dry-run')
    elif session.autonomy == 'autonomous':
        session.notify(f'amplitude rail ({rail}): re-running the coarse power '
                       'stage automatically')
    else:
        if not sys.stdin.isatty():
            return False, None
        if not _ask(f'      amplitude rail ({rail}): re-run '
                    'tune.power_for_length (+ auto-phase) and retry? [y/n] ',
                    {'y': True, 'yes': True, 'n': False, 'no': False,
                     '': False},
                    on_eof=False):
            return False, None

    chain = [protocol.steps[coarse_idx]] + [
        s for s in protocol.steps[coarse_idx + 1:index]
        if getattr(s, 'name', None) == 'tune.auto_phase']
    failing_judges = session.last_judges  # keep the failing step's own judges
    try:
        for s in chain:
            session.log(f'      [fallback] re-running {s.name}')
            session.last_judges = []
            try:
                result = STEPS[s.name].func(session, **s.params)
            except StepFailure as e:
                session.log(f'      [fallback] {s.name} failed: {e}')
                manifest.record(s, 'failed (rail fallback)', attempts=1,
                                judges=session.last_judges, error=e)
                return False, f'{s.name}: {e}'
            except RunnerAbort:
                raise
            except Exception:
                session.log(traceback.format_exc())
                manifest.record(s, 'failed (rail fallback)', attempts=1,
                                error='unexpected error (see log)')
                return False, f'{s.name} raised an unexpected error (see log)'
            session.state[s.name] = result
            manifest.record(s, 'ok (rail fallback)', attempts=1, result=result,
                            judges=session.last_judges)
        return True, None
    finally:
        session.last_judges = failing_judges


def _gate(session, step):
    """Autonomy gating before a step: 'run' or 'skip', or raise RunnerAbort."""
    if session.autonomy == 'autonomous':
        if step.checkpoint:
            session.notify(f'checkpoint {step.name}: auto-approved '
                           '(autonomous mode)')
        return 'run'
    pause = (session.autonomy == 'supervised'
             or (session.autonomy == 'checkpointed' and step.checkpoint))
    if not pause:
        return 'run'
    if session.test:
        session.log(f'      [checkpoint] would pause here ({session.autonomy} mode) '
                    '— auto-continuing in dry-run')
        return 'run'
    if not sys.stdin.isatty():
        raise RunnerAbort('checkpoint reached with no terminal attached '
                          '(GUI checkpoint support is a later item)', hard=True)
    answer = _ask('      [checkpoint] continue / skip / abort? [c/s/a] ',
                  {'c': 'run', 'continue': 'run', '': 'run',
                   's': 'skip', 'skip': 'skip',
                   'a': 'abort', 'abort': 'abort'},
                  on_eof='eof')
    if answer == 'eof':
        raise RunnerAbort('checkpoint prompt closed (EOF)', hard=True)
    if answer == 'abort':
        raise RunnerAbort('aborted by operator at checkpoint', hard=True)
    return answer
