"""Root conftest — register custom pytest markers."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
