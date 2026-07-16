"""Tuning / field / experiment primitives.

Every primitive returns ``(result, judges)`` where ``result`` is a plain dict
of the physical outcome and ``judges`` is a list of
:class:`~atomize.epr_auto.primitives.judges.JudgeReport` — quality verdicts
the caller (the step layer, or a plain script) decides how to act on.

Layering rule: primitives talk to the engine (WorkerArgs/run_worker) and to
device modules via the session; they never import the protocol/runner layers,
so they stay callable from a plain script:

    import sys; sys.argv = [sys.argv[0], 'test']   # or a real run without it
    from atomize.epr_auto.session import EPRSession
    from atomize.epr_auto.primitives import tune
    session = EPRSession(sample='X', autonomy='supervised', test=True)
    result, judges = tune.auto_phase(session)
"""
