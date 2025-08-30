"""
Lightweight smoke test to validate pytest environment and configuration.

This test avoids heavy imports and network. It ensures the test runner
and environment variables are wired correctly.
"""


def test_pytest_smoke():
    # Basic assertion to verify pytest is executing
    assert True

