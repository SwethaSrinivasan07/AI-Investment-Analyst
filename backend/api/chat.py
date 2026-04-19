"""
Chat API endpoints:
- POST /api/chat/{memo_id}          — SSE streaming chat response
- GET  /api/chat/{memo_id}/history  — get chat message history
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.memo_writer import MemoWriter
from api.auth import get_current_user
from models.database import get_db
from models.models import Memo, MemoChatMessage, User

router = APIRouter()
logger = logging.getLogger(__name__)

# Shared memo writer instance for chat responses
_memo_writer = MemoWriter()

# Path to the chat system prompt
CHAT_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "system" / "chat_analyst.txt"


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str


class ChatMessageResponse(BaseModel):
    id: str
    memo_id: str
    role: str  # user | assistant
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/{memo_id}")
async def chat_with_memo(
    memo_id: str,
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    SSE streaming chat endpoint.

    Loads the memo + full chat history, streams a response from Claude,
    and persists both the user message and assistant response to the DB.
    """
    # Verify memo ownership
    result = await db.execute(
        select(Memo).where(
            Memo.id == memo_id,
            Memo.user_id == current_user.id,
        )
    )
    memo = result.scalar_one_or_none()
    if memo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo not found")

    if not req.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty",
        )

    # Load full chat history
    history_result = await db.execute(
        select(MemoChatMessage)
        .where(MemoChatMessage.memo_id == memo_id)
        .order_by(asc(MemoChatMessage.created_at))
    )
    history_messages = history_result.scalars().all()

    # Convert to list of dicts for the memo writer
    chat_history = [
        {"role": msg.role, "content": msg.content}
        for msg in history_messages
    ]

    # Save user message immediately
    user_msg = MemoChatMessage(
        memo_id=memo_id,
        role="user",
        content=req.message,
    )
    db.add(user_msg)
    await db.commit()

    # Build data_package from memo — use markdown + any stored data
    data_package = {
        "ticker": memo.ticker,
        "company_name": memo.company_name,
        "strategy": memo.strategy,
        "sector": memo.sector,
        "recommendation": memo.recommendation,
        "conviction": memo.conviction,
    }

    async def event_generator():
        """Stream assistant response and save to DB when complete."""
        response_chunks = []

        try:
            async for chunk in _memo_writer.generate_with_chat_context(
                system_prompt_path=CHAT_PROMPT_PATH,
                memo_markdown=memo.markdown_text or "",
                data_package=data_package,
                chat_history=chat_history,
                new_user_message=req.message,
            ):
                response_chunks.append(chunk)
                # Stream each chunk as SSE
                import json
                payload = json.dumps({"type": "token", "content": chunk})
                yield f"data: {payload}\n\n"

        except Exception as e:
            logger.error(f"Chat streaming error for memo {memo_id}: {e}", exc_info=True)
            import json
            yield f"data: {json.dumps({'type': 'error', 'message': 'Generation failed'})}\n\n"
            return

        # Save the complete assistant response to DB
        full_response = "".join(response_chunks)
        if full_response.strip():
            assistant_msg = MemoChatMessage(
                memo_id=memo_id,
                role="assistant",
                content=full_response,
            )
            # We need a fresh DB session here since this runs in a generator
            # Use the session from the outer scope — it's still active
            db.add(assistant_msg)
            try:
                await db.commit()
            except Exception as e:
                logger.error(f"Failed to save chat message: {e}")

        import json
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/{memo_id}/history", response_model=list[ChatMessageResponse])
async def get_chat_history(
    memo_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the full chat history for a memo."""
    # Verify memo ownership
    result = await db.execute(
        select(Memo).where(
            Memo.id == memo_id,
            Memo.user_id == current_user.id,
        )
    )
    memo = result.scalar_one_or_none()
    if memo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo not found")

    history_result = await db.execute(
        select(MemoChatMessage)
        .where(MemoChatMessage.memo_id == memo_id)
        .order_by(asc(MemoChatMessage.created_at))
    )
    messages = history_result.scalars().all()
    return [ChatMessageResponse.model_validate(msg) for msg in messages]
