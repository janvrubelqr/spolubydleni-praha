"""Run all configured scrapers."""
from __future__ import annotations

import importlib
import logging
import os
from collections.abc import Callable

log = logging.getLogger(__name__)

DEFAULT_SOURCES = ("sreality", "realingo", "ulovdomov")


def _configured_sources() -> list[str]:
    value = os.getenv("SCRAPER_SOURCES")
    if not value:
        return list(DEFAULT_SOURCES)
    return [source.strip() for source in value.split(",") if source.strip()]


def _load_runner(source: str) -> Callable[[], None]:
    module = importlib.import_module(f"scrapers.{source}")
    runner = getattr(module, "run", None)
    if not callable(runner):
        raise ValueError(f"scrapers.{source} does not expose a callable run()")
    return runner


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    failures: list[tuple[str, str]] = []

    for source in _configured_sources():
        log.info("Starting scraper: %s", source)
        try:
            _load_runner(source)()
        except Exception as exc:
            log.exception("Scraper failed: %s", source)
            failures.append((source, str(exc)))

    if failures:
        names = ", ".join(source for source, _ in failures)
        raise SystemExit(f"Some scrapers failed: {names}")


if __name__ == "__main__":
    main()
