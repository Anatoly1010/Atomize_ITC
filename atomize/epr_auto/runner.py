"""Protocol runner: step loop with autonomy gating, retry policy, the
rail-triggered coarse fallback, a run manifest and notifications.

Autonomy at a checkpoint: supervised pauses at every step, checkpointed at
`checkpoint: true` steps, autonomous never pauses — checkpoints are
auto-approved with a notification and the judges (StepFailure gating in
steps.py) are the only brake.

Failure policy per step: `retries: n` re-runs a failed step up to n extra
times; then `on_fail` decides — abort (default), skip (continue without the
step), ask (operator prompt: retry / skip / abort). A StepFailure carrying
`rails` additionally triggers the coarse fallback (once per step): re-run
the protocol's earlier tune.power_for_length (+ tune.auto_phase, if
present — the vane move invalidated the phase) and retry.

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

from atomize.epr_auto.steps import STEPS, StepFailure


class RunnerAbort(Exception):
    pass


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
    n = len(protocol.steps)
    mode = 'DRY-RUN (test mode)' if session.test else 'LIVE'
    session.log(f'=== {protocol.path.name} | sample: {protocol.sample} | '
                f'autonomy: {protocol.autonomy} | {n} steps | {mode} ===')
    manifest = _Manifest(protocol, session)

    results = []
    try:
        for i, step in enumerate(protocol.steps, 1):
            session.log(f'[{i}/{n}] {step.name}  (line {step.line})')
            for key, value in step.params.items():
                if value is not None:
                    session.log(f'      {key} = {value}')

            if _gate(session, step) == 'skip':
                session.log('      skipped by operator')
                manifest.record(step, 'skipped-by-operator', attempts=0)
                results.append((step, None))
                continue

            result, status, attempts = _run_step(protocol, session, manifest,
                                                 step, i - 1)
            if status != 'ok':
                results.append((step, None))
                continue
            session.log('      -> ' + ', '.join(f'{k}={v}' for k, v in result.items()))
            session.state[step.name] = result
            manifest.record(step, 'ok', attempts, result=result,
                            judges=session.last_judges)
            results.append((step, result))
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


def _run_step(protocol, session, manifest, step, index):
    """One step with retries + the rail fallback. Returns (result, 'ok',
    attempts) or (None, 'failed-skipped', attempts); raises RunnerAbort."""
    attempts = 0
    fallback_used = False
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
                              '(see above)') from None

        # rail-triggered coarse fallback: once per step, an extra attempt on
        # top of the retry budget (it re-tunes the power regime first)
        if getattr(error, 'rails', None) and not fallback_used:
            fallback_used = True
            if _rail_fallback(protocol, session, index, error.rails):
                continue

        if attempts <= step.retries:
            session.log(f'      retrying ({attempts} of {step.retries} '
                        'retries used)')
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
        raise RunnerAbort(f'step {step.name} failed: {error}')


def _on_fail_decision(session, step, error):
    """Map the step's on_fail policy to 'retry' / 'skip' / 'abort'."""
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
    while True:
        try:
            answer = input(f'      step failed: {error}\n'
                           '      retry / skip / abort? [r/s/a] ').strip().lower()
        except EOFError:
            return 'abort'
        if answer in ('r', 'retry'):
            return 'retry'
        if answer in ('s', 'skip'):
            return 'skip'
        if answer in ('a', 'abort', ''):
            return 'abort'


def _rail_fallback(protocol, session, index, rail):
    """Re-run the coarse power stage (and auto-phase, which any vane move
    invalidates) after an amplitude-rail failure. Only available when the
    protocol itself declared a tune.power_for_length step earlier — its
    resolved parameters define the coarse stage. Returns True when the
    chain ran and the failed step should be retried."""
    coarse = next((s for s in protocol.steps[:index]
                   if s.name == 'tune.power_for_length'), None)
    if coarse is None:
        session.log(f'      amplitude rail ({rail}) hit, but the protocol has '
                    'no earlier tune.power_for_length step — no fallback')
        return False

    if session.test:
        session.log('      [rail fallback] would re-run the coarse stage — '
                    'auto-continuing in dry-run')
    elif session.autonomy == 'autonomous':
        session.notify(f'amplitude rail ({rail}): re-running the coarse power '
                       'stage automatically')
    else:
        if not sys.stdin.isatty():
            return False
        try:
            answer = input(f'      amplitude rail ({rail}): re-run '
                           'tune.power_for_length (+ auto-phase) and retry? '
                           '[y/n] ').strip().lower()
        except EOFError:
            return False
        if answer not in ('y', 'yes'):
            return False

    chain = [coarse] + [s for s in protocol.steps[:index]
                        if s.name == 'tune.auto_phase']
    for s in chain:
        session.log(f'      [fallback] re-running {s.name}')
        try:
            session.state[s.name] = STEPS[s.name].func(session, **s.params)
        except StepFailure as e:
            session.log(f'      [fallback] {s.name} failed: {e}')
            return False
    return True


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
                          '(GUI checkpoint support is a later item)')
    while True:
        try:
            answer = input('      [checkpoint] continue / skip / abort? [c/s/a] ').strip().lower()
        except EOFError:
            raise RunnerAbort('checkpoint prompt closed (EOF)') from None
        if answer in ('c', 'continue', ''):
            return 'run'
        if answer in ('s', 'skip'):
            return 'skip'
        if answer in ('a', 'abort'):
            raise RunnerAbort('aborted by operator at checkpoint')
