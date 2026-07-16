"""Protocol runner: step loop with autonomy gating.

Phase 0 scope: sequential execution, checkpoint prompts (annotation-only in
dry-run), fail-fast on step errors. Retry policy, run-directory manifest and
notifications are Phase 3 (see docs/automation/ROADMAP.md).
"""
import sys
import traceback

from atomize.epr_auto.steps import STEPS, StepFailure


class RunnerAbort(Exception):
    pass


def run_protocol(protocol, session):
    n = len(protocol.steps)
    mode = 'DRY-RUN (test mode)' if session.test else 'LIVE'
    session.log(f'=== {protocol.path.name} | sample: {protocol.sample} | '
                f'autonomy: {protocol.autonomy} | {n} steps | {mode} ===')

    results = []
    for i, step in enumerate(protocol.steps, 1):
        session.log(f'[{i}/{n}] {step.name}  (line {step.line})')
        for key, value in step.params.items():
            if value is not None:
                session.log(f'      {key} = {value}')

        action = _gate(session, step)
        if action == 'skip':
            session.log('      skipped by operator')
            results.append((step, None))
            continue

        try:
            result = STEPS[step.name].func(session, **step.params)
        except StepFailure as e:
            raise RunnerAbort(f'step {step.name} failed: {e}') from None
        except RunnerAbort:
            raise
        except Exception:
            session.log(traceback.format_exc())
            raise RunnerAbort(f'step {step.name} raised an unexpected error (see above)') from None

        session.log('      -> ' + ', '.join(f'{k}={v}' for k, v in result.items()))
        session.state[step.name] = result
        results.append((step, result))

    session.log(f'=== finished: {sum(1 for _, r in results if r is not None)}/{n} steps ran ===')
    return results


def _gate(session, step):
    """Autonomy gating before a step: 'run' or 'skip', or raise RunnerAbort."""
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
                          '(GUI checkpoint support is a Phase 3 item)')
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
