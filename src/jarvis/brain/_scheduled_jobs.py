"""Module-level job targets so apscheduler can serialise them."""
import asyncio

from loguru import logger


async def _fire_reliability_probe() -> None:
    """Run health_probe_and_surface; never raises into the loop."""
    try:
        from jarvis.brain.reliability import health_probe_and_surface
        msg = await health_probe_and_surface()
        if msg and "All systems green" not in msg:
            logger.warning(f"reliability probe: {msg}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reliability probe failed: {type(e).__name__}: {e}")


async def _fire_composio_catalog_refresh() -> None:
    """T12 — refresh the cached Composio catalog so the system prompt picks up new tools
    overnight (before the morning briefing, so the next session sees the full list)."""
    try:
        from jarvis.brain.composio_catalog import refresh, invalidate
        n = await refresh()
        invalidate()
        total = sum(len(v) for v in (n.get("toolkits") or {}).values())
        logger.info(f"composio catalog nightly refresh: {total} tools cached")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"composio catalog refresh failed: {type(e).__name__}: {e}")