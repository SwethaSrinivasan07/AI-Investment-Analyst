"""
APScheduler-based memo delivery scheduler.

One job per enabled UserSchedule. Each job triggers the full multi-agent memo
pipeline and emails the result to the user.

Frequency → APScheduler trigger mapping:
  daily      → IntervalTrigger(days=1)
  every2days → IntervalTrigger(days=2)
  weekly     → IntervalTrigger(weeks=1)
"""

import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from models.database import AsyncSessionLocal
from models.models import Memo, User, UserSchedule

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level scheduler instance (one per process)
# ---------------------------------------------------------------------------

scheduler = AsyncIOScheduler()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_trigger(frequency: str, start_date: Optional[datetime]) -> IntervalTrigger:
    """Build an IntervalTrigger from a UserSchedule.frequency string."""
    kwargs: dict = {}
    if start_date and start_date > datetime.utcnow():
        kwargs["start_date"] = start_date

    if frequency == "daily":
        return IntervalTrigger(days=1, **kwargs)
    elif frequency == "every2days":
        return IntervalTrigger(days=2, **kwargs)
    elif frequency == "weekly":
        return IntervalTrigger(weeks=1, **kwargs)
    else:
        # Fallback: treat unknown frequencies as daily
        logger.warning("Unknown schedule frequency '%s' — defaulting to daily", frequency)
        return IntervalTrigger(days=1, **kwargs)


def _job_id(schedule_id: str) -> str:
    return f"memo_schedule_{schedule_id}"


# ---------------------------------------------------------------------------
# The job function executed by APScheduler
# ---------------------------------------------------------------------------

async def _run_memo_job(
    schedule_id: str,
    user_id: str,
    strategy: str,
    sector: str,
) -> None:
    """
    Called by APScheduler when a scheduled memo is due.

    Steps:
    1. Acquire a DB session.
    2. Verify the schedule is still enabled (user may have disabled it since boot).
    3. Run orchestrator.run() to generate a full IC memo.
    4. Fetch user email.
    5. Send the memo via SendGrid.
    6. Update UserSchedule.next_run_at to the next scheduled firing time.
    7. Log success or failure — never raise (APScheduler will not retry on exception).
    """
    logger.info(
        "[Scheduler] Running memo job: schedule_id=%s user_id=%s strategy=%s sector=%s",
        schedule_id, user_id, strategy, sector,
    )

    memo: Optional[Memo] = None
    user_email: Optional[str] = None

    try:
        # ------------------------------------------------------------------
        # 1. Open DB session and verify schedule is still enabled
        # ------------------------------------------------------------------
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(UserSchedule).where(UserSchedule.id == schedule_id)
            )
            schedule_obj: Optional[UserSchedule] = result.scalar_one_or_none()

            if schedule_obj is None:
                logger.warning(
                    "[Scheduler] Schedule %s no longer exists — removing job", schedule_id
                )
                _remove_job_if_exists(_job_id(schedule_id))
                return

            if not schedule_obj.enabled:
                logger.info(
                    "[Scheduler] Schedule %s is disabled — skipping this run", schedule_id
                )
                return

            # Fetch user email while the session is open
            user_result = await db.execute(
                select(User).where(User.id == user_id)
            )
            user_obj: Optional[User] = user_result.scalar_one_or_none()
            if user_obj:
                user_email = user_obj.email

        # ------------------------------------------------------------------
        # 2. Run the orchestrator pipeline
        # ------------------------------------------------------------------
        # Import here to avoid circular imports at module load time
        from agents.orchestrator import Orchestrator  # noqa: PLC0415

        orchestrator = Orchestrator()
        memo = await orchestrator.run(
            user_id=user_id,
            strategy=strategy,
            sector=sector,
            num_picks=1,
        )

        logger.info(
            "[Scheduler] Memo generated: memo_id=%s ticker=%s recommendation=%s",
            memo.id, memo.ticker, memo.recommendation,
        )

    except Exception as exc:
        logger.error(
            "[Scheduler] Memo generation failed for schedule %s: %s",
            schedule_id,
            exc,
            exc_info=True,
        )
        # Do not re-raise — APScheduler should keep running future jobs
        return

    # ------------------------------------------------------------------
    # 3. Send email (only if we have a memo and an email address)
    # ------------------------------------------------------------------
    if memo and user_email:
        try:
            from services.emailer import send_memo_email  # noqa: PLC0415

            sent = await send_memo_email(
                to_email=user_email,
                memo_ticker=memo.ticker,
                memo_company=memo.company_name or memo.ticker,
                memo_recommendation=memo.recommendation or "Watch",
                memo_conviction=memo.conviction or "Medium",
                memo_markdown=memo.markdown_text or "",
                memo_id=memo.id,
            )
            if sent:
                logger.info(
                    "[Scheduler] Email delivered to %s for memo %s", user_email, memo.id
                )
            else:
                logger.warning(
                    "[Scheduler] Email delivery failed for %s (memo %s)", user_email, memo.id
                )
        except Exception as exc:
            logger.error(
                "[Scheduler] Email step threw an exception for schedule %s: %s",
                schedule_id,
                exc,
                exc_info=True,
            )
            # Still update next_run_at below — don't let email failure block scheduling

    elif not user_email:
        logger.warning(
            "[Scheduler] No email address found for user_id=%s — skipping email", user_id
        )

    # ------------------------------------------------------------------
    # 4. Update next_run_at on the UserSchedule
    # ------------------------------------------------------------------
    try:
        job = scheduler.get_job(_job_id(schedule_id))
        next_fire: Optional[datetime] = job.next_run_time if job else None

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(UserSchedule).where(UserSchedule.id == schedule_id)
            )
            schedule_obj = result.scalar_one_or_none()
            if schedule_obj and next_fire:
                schedule_obj.next_run_at = next_fire
                await db.commit()
                logger.info(
                    "[Scheduler] next_run_at updated for schedule %s → %s",
                    schedule_id, next_fire.isoformat(),
                )
    except Exception as exc:
        logger.error(
            "[Scheduler] Failed to update next_run_at for schedule %s: %s",
            schedule_id,
            exc,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Helper: safe job removal
# ---------------------------------------------------------------------------

def _remove_job_if_exists(job_id: str) -> None:
    try:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info("[Scheduler] Removed APScheduler job %s", job_id)
    except Exception as exc:
        logger.warning("[Scheduler] Could not remove job %s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Public API: add / remove individual schedules
# ---------------------------------------------------------------------------

async def schedule_memo_for_user(
    schedule_id: str,
    user_id: str,
    strategy: str,
    sector: str,
    frequency: str,
    next_run_at: Optional[datetime] = None,
) -> None:
    """
    Add (or replace) an APScheduler job for a UserSchedule.

    Safe to call at any time — replace_existing=True handles updates.
    """
    job_id = _job_id(schedule_id)
    trigger = _make_trigger(frequency, next_run_at)

    scheduler.add_job(
        _run_memo_job,
        trigger=trigger,
        id=job_id,
        replace_existing=True,
        args=[schedule_id, user_id, strategy, sector],
        misfire_grace_time=3600,   # fire up to 1 hour late if server was down
        coalesce=True,             # collapse multiple missed fires into one
    )

    logger.info(
        "[Scheduler] Job registered: %s (user=%s, %s/%s, freq=%s, next=%s)",
        job_id, user_id, strategy, sector, frequency,
        next_run_at.isoformat() if next_run_at else "immediate",
    )


async def unschedule_memo(schedule_id: str) -> None:
    """Remove the APScheduler job for a UserSchedule, if it exists."""
    _remove_job_if_exists(_job_id(schedule_id))


# ---------------------------------------------------------------------------
# Lifecycle: start / stop (called from main.py lifespan)
# ---------------------------------------------------------------------------

async def _run_daily_monitor() -> None:
    """APScheduler wrapper for the daily portfolio monitor."""
    try:
        from services.monitor_service import run_daily_monitor
        await run_daily_monitor()
    except Exception as exc:
        logger.error("[Scheduler] Daily monitor failed: %s", exc, exc_info=True)


async def start_scheduler() -> None:
    """
    Load all enabled UserSchedules from the DB and register APScheduler jobs.
    Then start the scheduler.

    Called once at application startup inside the FastAPI lifespan handler.
    """
    logger.info("[Scheduler] Loading enabled schedules from DB...")

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(UserSchedule).where(UserSchedule.enabled == True)  # noqa: E712
            )
            schedules = result.scalars().all()

        registered = 0
        for s in schedules:
            try:
                await schedule_memo_for_user(
                    schedule_id=s.id,
                    user_id=s.user_id,
                    strategy=s.strategy,
                    sector=s.sector,
                    frequency=s.frequency,
                    next_run_at=s.next_run_at,
                )
                registered += 1
            except Exception as exc:
                logger.error(
                    "[Scheduler] Failed to register schedule %s at startup: %s",
                    s.id, exc, exc_info=True,
                )

        logger.info("[Scheduler] Registered %d jobs from DB.", registered)

    except Exception as exc:
        # DB might not be populated yet on a fresh install — that is fine.
        logger.warning(
            "[Scheduler] Could not load schedules from DB at startup: %s", exc
        )

    # Register daily portfolio monitor at 07:00
    from apscheduler.triggers.cron import CronTrigger  # noqa: PLC0415
    scheduler.add_job(
        _run_daily_monitor,
        trigger=CronTrigger(hour=7, minute=0),
        id="daily_portfolio_monitor",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )
    logger.info("[Scheduler] Daily portfolio monitor registered at 07:00.")

    scheduler.start()
    logger.info("[Scheduler] APScheduler started.")


async def stop_scheduler() -> None:
    """Gracefully shut down the APScheduler (called from FastAPI lifespan)."""
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("[Scheduler] APScheduler shut down.")
    except Exception as exc:
        logger.warning("[Scheduler] Error during scheduler shutdown: %s", exc)
