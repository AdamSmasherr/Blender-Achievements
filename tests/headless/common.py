"""
Lightweight assertion/reporting for the headless suite.

No pytest here on purpose: Blender's bundled Python usually doesn't have it
installed, and getting pip working inside `blender --background` is more
moving parts than this suite needs. Each test is a plain function that
raises on failure; `run_suite()` catches that per test so one failure
doesn't stop the rest of the suite, and prints a pass/fail line you can read
straight off the console.
"""

import traceback


class Failure(AssertionError):
    pass


def expect(condition, message):
    if not condition:
        raise Failure(message)


def run_suite(name, tests):
    """`tests` is a list of (label, callable) pairs. Returns the number of
    failures (0 = clean)."""
    print(f"\n=== {name} ===")
    failed = 0
    for label, fn in tests:
        try:
            fn()
        except Exception as err:  # noqa: BLE001 — every failure should surface, not just Failure
            failed += 1
            print(f"  FAIL {label}: {err}")
            if not isinstance(err, Failure):
                traceback.print_exc()
        else:
            print(f"  PASS {label}")
    return failed
