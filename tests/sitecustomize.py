"""Starts coverage in hook subprocesses when COVERAGE_PROCESS_START is set (CI only).

Python imports ``sitecustomize`` from the path at start-up; the test helpers put this folder on
PYTHONPATH for the subprocesses they run. Without coverage installed, this file does nothing.
"""

import os

if os.environ.get("COVERAGE_PROCESS_START"):
    try:
        import coverage

        coverage.process_startup()
    except ImportError:
        pass
