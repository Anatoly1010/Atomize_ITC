"""Failures that protocol retry/skip policies must never override."""


class PreliminaryAbort(Exception):
    """Preliminary tuning stopped after attempting a safe RV return."""
