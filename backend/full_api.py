"""API routes for the generated full-data serving index.

The routes are opt-in at runtime: when ``data/processed/full-serving.sqlite``
does not exist they return a clear 404 instead of silently falling back to the
small demo payload. Trajectory list responses contain summaries only; detail
responses contain a bounded sampled point set.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

import os

from .full_data import FULL_INDEX_PATH
from .full_index_store import FullIndexStore
from .full_repository import PostgresFullRepository


router = APIRouter(prefix="/api/full", tags=["full dataset"])


def _store():
    if os.getenv("GEOTRACK_SERVING_BACKEND", "sqlite").lower() == "postgres":
        store = PostgresFullRepository(os.getenv("DATABASE_URL", "postgresql://geotrack:geotrack@localhost:5432/geotrack"))
    else:
        store = FullIndexStore(FULL_INDEX_PATH)
    if not store.is_ready:
        raise HTTPException(status_code=404, detail="full serving index not generated; run jobs/full_serving_index.py")
    return store


@router.get("/summary")
def full_summary() -> dict[str, Any]:
    return _store().full_summary


@router.get("/users")
def full_users(q: str | None = None, limit: int = Query(50, ge=1, le=500)) -> list[dict[str, Any]]:
    return _store().users(q, limit)


@router.get("/trajectories")
def full_trajectories(
    user_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
) -> list[dict[str, Any]]:
    # Direct Python callers (unit tests/CLI) see FastAPI's Query sentinel as
    # the default value; normalize it to the intended ``None``.
    west = None if not isinstance(west, (int, float)) else west
    south = None if not isinstance(south, (int, float)) else south
    east = None if not isinstance(east, (int, float)) else east
    north = None if not isinstance(north, (int, float)) else north
    values = (west, south, east, north)
    if any(value is not None for value in values):
        if any(value is None for value in values) or west > east or south > north:
            raise HTTPException(status_code=422, detail="invalid bounding box")
        bbox = (west, south, east, north)
    else:
        bbox = None
    store = _store()
    try:
        return store.trajectories(user_id, start, end, limit, offset, bbox)
    except TypeError:  # SQLite fallback predates bbox support.
        return store.trajectories(user_id, start, end, limit, offset)


@router.get("/trajectories/{trajectory_id}")
def full_trajectory(trajectory_id: str, sample_limit: int = Query(500, ge=1, le=2000)) -> dict[str, Any]:
    if not isinstance(sample_limit, int):
        sample_limit = 500
    store = _store()
    try:
        result = store.trajectory(trajectory_id, sample_limit)
    except TypeError:
        result = store.trajectory(trajectory_id)
    if result is None:
        raise HTTPException(status_code=404, detail="full trajectory not found")
    return result


@router.get("/spatiotemporal/at")
def full_spatiotemporal_at(trajectory_id: str, ts: str) -> dict[str, Any]:
    """Position of one trajectory at a single instant (MobilityDB valueAtTimestamp)."""
    store = _store()
    method = getattr(store, "trajectory_at", None)
    if method is None:
        raise HTTPException(status_code=501, detail="spatiotemporal queries require the Postgres/MobilityDB backend")
    result = method(trajectory_id, ts)
    if result is None:
        raise HTTPException(status_code=404, detail="trajectory not found or timestamp outside its extent")
    return result


@router.get("/spatiotemporal/segment")
def full_spatiotemporal_segment(trajectory_id: str, start: str, end: str) -> dict[str, Any]:
    """Trajectory geometry restricted to a time range (MobilityDB atTime)."""
    store = _store()
    method = getattr(store, "trajectory_segment", None)
    if method is None:
        raise HTTPException(status_code=501, detail="spatiotemporal queries require the Postgres/MobilityDB backend")
    result = method(trajectory_id, start, end)
    if result is None:
        raise HTTPException(status_code=404, detail="trajectory not found or no points in the requested range")
    return result


@router.get("/hotspots")
def full_hotspots(limit: int = Query(20, ge=1, le=200), min_users: int = Query(0, ge=0)) -> list[dict[str, Any]]:
    return _store().hotspots(limit, min_users)


@router.get("/patterns")
def full_patterns() -> list[dict[str, Any]]:
    return _store().patterns()


@router.get("/quality")
def full_quality() -> dict[str, Any]:
    return _store().quality()
