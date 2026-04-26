"""
Settings API endpoints:
- GET    /api/settings                   — return user preferences + schedules
- PUT    /api/settings/preferences       — update user.preferences JSON
- POST   /api/settings/schedules         — create a new UserSchedule (max 3 active)
- PUT    /api/settings/schedules/{id}    — update a schedule (enabled toggle, frequency)
- DELETE /api/settings/schedules/{id}    — delete a schedule
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from models.database import get_db
from models.models import User, UserSchedule

router = APIRouter()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_STRATEGIES = {"momentum", "value", "growth", "dividend"}
VALID_FREQUENCIES = {"daily", "every2days", "weekly"}
MAX_ACTIVE_SCHEDULES = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_next_run(frequency: str) -> datetime:
    """Return tomorrow/2-days/7-days from now at 09:00 UTC."""
    today = datetime.utcnow().replace(hour=9, minute=0, second=0, microsecond=0)
    if frequency == "daily":
        return today + timedelta(days=1)
    elif frequency == "every2days":
        return today + timedelta(days=2)
    else:  # weekly
        return today + timedelta(days=7)


def _validate_strategy(strategy: str) -> str:
    s = strategy.lower()
    if s not in VALID_STRATEGIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"strategy must be one of: {sorted(VALID_STRATEGIES)}",
        )
    return s


def _validate_frequency(frequency: str) -> str:
    f = frequency.lower()
    if f not in VALID_FREQUENCIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"frequency must be one of: {sorted(VALID_FREQUENCIES)}",
        )
    return f


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class ScheduleResponse(BaseModel):
    id: str
    strategy: str
    sector: str
    frequency: str
    enabled: bool
    next_run_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class SettingsResponse(BaseModel):
    email: str
    preferences: dict
    schedules: list[ScheduleResponse]


class PreferencesUpdate(BaseModel):
    default_strategy: Optional[str] = None
    default_sector: Optional[str] = None
    email_notifications: Optional[bool] = None


class ScheduleCreate(BaseModel):
    strategy: str
    sector: str
    frequency: str


class ScheduleUpdate(BaseModel):
    enabled: Optional[bool] = None
    frequency: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=SettingsResponse)
async def get_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the authenticated user's preferences and all their schedules."""
    result = await db.execute(
        select(UserSchedule)
        .where(UserSchedule.user_id == current_user.id)
        .order_by(UserSchedule.created_at)
    )
    schedules = result.scalars().all()

    return SettingsResponse(
        email=current_user.email,
        preferences=current_user.preferences or {},
        schedules=[ScheduleResponse.model_validate(s) for s in schedules],
    )


@router.put("/preferences", response_model=SettingsResponse)
async def update_preferences(
    body: PreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Merge the supplied fields into user.preferences JSON."""
    # Validate strategy if provided
    if body.default_strategy is not None:
        _validate_strategy(body.default_strategy)

    current_prefs: dict = dict(current_user.preferences or {})

    if body.default_strategy is not None:
        current_prefs["default_strategy"] = body.default_strategy.lower()
    if body.default_sector is not None:
        current_prefs["default_sector"] = body.default_sector
    if body.email_notifications is not None:
        current_prefs["email_notifications"] = body.email_notifications

    current_user.preferences = current_prefs
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    # Re-fetch schedules for the response
    result = await db.execute(
        select(UserSchedule)
        .where(UserSchedule.user_id == current_user.id)
        .order_by(UserSchedule.created_at)
    )
    schedules = result.scalars().all()

    return SettingsResponse(
        email=current_user.email,
        preferences=current_user.preferences or {},
        schedules=[ScheduleResponse.model_validate(s) for s in schedules],
    )


@router.post("/schedules", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: ScheduleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new memo schedule. Limit: 3 active schedules per user."""
    strategy = _validate_strategy(body.strategy)
    frequency = _validate_frequency(body.frequency)

    # Enforce max-3 active schedules
    count_result = await db.execute(
        select(func.count())
        .select_from(UserSchedule)
        .where(
            UserSchedule.user_id == current_user.id,
            UserSchedule.enabled == True,  # noqa: E712
        )
    )
    active_count = count_result.scalar_one()
    if active_count >= MAX_ACTIVE_SCHEDULES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum of {MAX_ACTIVE_SCHEDULES} active schedules allowed. "
                   "Disable or delete an existing schedule before adding a new one.",
        )

    schedule = UserSchedule(
        user_id=current_user.id,
        strategy=strategy,
        sector=body.sector,
        frequency=frequency,
        enabled=True,
        next_run_at=_compute_next_run(frequency),
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)

    return ScheduleResponse.model_validate(schedule)


@router.put("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: str,
    body: ScheduleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle a schedule on/off or change its frequency."""
    result = await db.execute(
        select(UserSchedule).where(
            UserSchedule.id == schedule_id,
            UserSchedule.user_id == current_user.id,
        )
    )
    schedule = result.scalar_one_or_none()
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    if body.enabled is not None:
        schedule.enabled = body.enabled

    if body.frequency is not None:
        frequency = _validate_frequency(body.frequency)
        schedule.frequency = frequency
        schedule.next_run_at = _compute_next_run(frequency)

    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)

    return ScheduleResponse.model_validate(schedule)


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete a schedule owned by the current user."""
    result = await db.execute(
        select(UserSchedule).where(
            UserSchedule.id == schedule_id,
            UserSchedule.user_id == current_user.id,
        )
    )
    schedule = result.scalar_one_or_none()
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    await db.delete(schedule)
    await db.commit()


# Register in main.py: app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
