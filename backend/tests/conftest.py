import pytest

from app.main import cases


@pytest.fixture(autouse=True)
def clear_cases() -> None:
    cases.clear()

    yield

    cases.clear()