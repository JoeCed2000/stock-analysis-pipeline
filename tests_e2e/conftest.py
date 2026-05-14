"""Pytest configuration for SA e2e tests."""
import pytest
from pathlib import Path


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Global browser context settings."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 900},
        "locale": "en-US",
    }


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Headless + no sandbox for WSL."""
    return {
        **browser_type_launch_args,
        "headless": True,
        "args": ["--no-sandbox", "--disable-setuid-sandbox"],
    }


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Take screenshot on test failure."""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        page = item.funcargs.get("page")
        if page:
            screenshot_dir = Path(__file__).parent / "screenshots"
            screenshot_dir.mkdir(exist_ok=True)
            name = f"{item.name}_{item.nodeid.split('[')[0]}.png"
            page.screenshot(path=str(screenshot_dir / name), full_page=True)
