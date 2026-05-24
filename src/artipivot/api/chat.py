"""Chat API — invoke agents via REST."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
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


def _sse_event(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@chat_router.post("/chat/{agent_id}/stream")
async def chat_stream(agent_id: str, req: ChatRequest):
    """Stream a chat response using SSE."""
    gateway = get_gateway()
    rate_limiter = get_rate_limiter()

    try:
        await rate_limiter.check(agent_id, req.user_id)
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))

    async def _generate():
        # Collect final messages from the stream to avoid re-running the graph.
        # Some nodes (e.g. clarify) produce static text via state updates rather
        # than stream tokens, so we need to extract them from the accumulated state.
        final_messages: list = []
        streamed_any = False
        try:
            async for chunk in gateway.stream(
                agent_id,
                req.message,
                req.thread_id,
                user_id=req.user_id,
                memory_config=get_memory_config(),
                stream_mode="messages",
            ):
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    msg_chunk, meta = chunk
                    node_name = meta.get("langgraph_node", "") if isinstance(meta, dict) else ""

                    if node_name == "classify":
                        continue

                    content = getattr(msg_chunk, "content", None)
                    if content and isinstance(content, str) and content.strip():
                        streamed_any = True
                        yield _sse_event({"type": "token", "content": content})

                    # Accumulate messages for fallback extraction
                    chunk_type = getattr(msg_chunk, "type", None)
                    if chunk_type in ("ai", "assistant") and content:
                        final_messages.append(msg_chunk)
                elif isinstance(chunk, dict):
                    yield _sse_event({"type": "node", "data": chunk})

            # If no tokens were streamed (e.g. clarify node with static text),
            # extract the reply from accumulated messages instead of re-invoking.
            if not streamed_any and final_messages:
                last = final_messages[-1]
                content = getattr(last, "content", "")
                if content:
                    yield _sse_event({"type": "token", "content": content})

            yield _sse_event({"type": "done", "thread_id": req.thread_id})

        except ValueError:
            yield _sse_event({"type": "error", "message": f"Agent not found: {agent_id}"})
        except Exception as e:
            yield _sse_event({"type": "error", "message": str(e)})

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
