"""Chat API — invoke agents via REST."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from artipivot.api.deps import get_gateway, get_memory_config, get_rate_limiter
from artipivot.config.ratelimit import RateLimitError

chat_router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"
    user_id: str = "anonymous"


class ChatResponse(BaseModel):
    response: str
    thread_id: str


@chat_router.post("/chat/{agent_id}", response_model=ChatResponse)
async def chat(agent_id: str, req: ChatRequest):
    """Send a message to an agent and get a response."""
    gateway = get_gateway()
    rate_limiter = get_rate_limiter()

    # Rate limit check
    try:
        await rate_limiter.check(agent_id, req.user_id)
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))

    # Invoke agent
    try:
        result = await gateway.invoke(
            agent_id, req.message, req.thread_id, user_id=req.user_id,
            memory_config=get_memory_config(),
        )
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Extract response text
    messages = result.get("messages", [])
    response_text = ""
    if messages:
        last = messages[-1]
        response_text = getattr(last, "content", str(last))

    return ChatResponse(response=response_text, thread_id=req.thread_id)
