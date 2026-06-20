"""Test runner for ShareX.

Runs all unit and integration tests.
"""

import unittest
import sys
import os

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_tests():
    """Run all ShareX tests."""
    # Discover tests
    loader = unittest.TestLoader()

    # Unit tests
    unit_suite = loader.discover(
        start_dir="sharex/tests/unit",
        pattern="test_*.py",
    )

    # Integration tests
    integration_suite = loader.discover(
        start_dir="sharex/tests/integration",
        pattern="test_*.py",
    )

    # Combine suites
    all_tests = unittest.TestSuite()
    all_tests.addTests(unit_suite)
    all_tests.addTests(integration_suite)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(all_tests)

    # Return exit code
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
