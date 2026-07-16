"""Automated pulsed-EPR experiments on top of Atomize (ITC endstation).

Primitives library + declarative YAML protocol runner. Design and roadmap:
docs/automation/ARCHITECTURE.md, docs/automation/ROADMAP.md.

Keep this module import-light: nothing here (or in params/steps/protocol)
may import atomize.general_modules or device modules at module scope —
protocol validation must work headless, and test/real mode is decided by
cli.py via sys.argv[1] *before* any device import happens.
"""
