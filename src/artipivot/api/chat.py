"""Chat API — invoke agents via REST."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from artipivot.api.deps import get_agent_registry, get_gateway, get_memory_config, get_memory_storage, get_rate_limiter
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
        registry = get_agent_registry()
        agent_def = registry.get_def(agent_id) if registry else None
        effective_memory = agent_def.memory_config if agent_def else get_memory_config()
        result = await gateway.invoke(
            agent_id, req.message, req.thread_id, user_id=req.user_id,
            memory_config=effective_memory,
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
        streamed_any = False
        try:
            registry = get_agent_registry()
            agent_def = registry.get_def(agent_id) if registry else None
            effective_memory = agent_def.memory_config if agent_def else get_memory_config()
            async for chunk in gateway.stream(
                agent_id,
                req.message,
                req.thread_id,
                user_id=req.user_id,
                memory_config=effective_memory,
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
                elif isinstance(chunk, dict):
                    yield _sse_event({"type": "node", "data": chunk})

            # If no tokens were streamed, the response came from a non-LLM node
            # (e.g. clarify or fallback) that writes state updates instead of
            # streaming tokens. Read the final message directly from graph state.
            if not streamed_any:
                try:
                    graph = gateway._graphs.get(agent_id)
                    if graph:
                        full_tid = f"{agent_id}:{req.thread_id}"
                        state_cfg = {"configurable": {"thread_id": full_tid}}
                        try:
                            final_state = await graph.aget_state(state_cfg)
                        except NotImplementedError:
                            final_state = graph.get_state(state_cfg)
                        if final_state and final_state.values:
                            msgs = final_state.values.get("messages", [])
                            if msgs:
                                last = msgs[-1]
                                role = getattr(last, "type", None) or getattr(last, "role", None)
                                if role in ("ai", "assistant"):
                                    content = getattr(last, "content", "")
                                    if content and isinstance(content, str):
                                        yield _sse_event({"type": "token", "content": content})
                except Exception:
                    pass

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


# ── Thread / history management ──


class ThreadInfo(BaseModel):
    thread_id: str
    last_message: str = ""
    updated_at: str = ""


@chat_router.get("/chat/{agent_id}/threads", response_model=list[ThreadInfo])
async def list_threads(agent_id: str):
    """List all conversation threads for an agent."""
    sp = get_memory_storage()
    checkpointer = sp.checkpointer
    if checkpointer is None:
        return []

    prefix = f"{agent_id}:"
    seen: dict[str, ThreadInfo] = {}

    # Collect all checkpoints — handle both sync and async checkpointers
    try:
        tpls = []
        try:
            async for tpl in checkpointer.alist(config=None, limit=1000):
                tpls.append(tpl)
        except NotImplementedError:
            # Sync checkpointer (e.g. SqliteSaver) — run in thread
            for tpl in checkpointer.list(config=None, limit=1000):
                tpls.append(tpl)
    except Exception:
        return []

    for tpl in tpls:
        full_tid = tpl.config.get("configurable", {}).get("thread_id", "")
        if not full_tid.startswith(prefix):
            continue

        # Strip agent_id prefix to get user-facing thread_id
        short_tid = full_tid[len(prefix):]
        ts = tpl.checkpoint.get("ts", "")
        # Extract last user/assistant message as preview
        msgs = tpl.checkpoint.get("channel_values", {}).get("messages", [])
        preview = ""
        if msgs:
            last = msgs[-1]
            content = getattr(last, "content", "")
            if isinstance(content, str) and content:
                preview = content[:100]

        # Keep only the latest checkpoint per thread (list returns newest first)
        if short_tid not in seen:
            seen[short_tid] = ThreadInfo(
                thread_id=short_tid,
                last_message=preview,
                updated_at=ts,
            )

    return list(seen.values())


@chat_router.get("/chat/{agent_id}/threads/{thread_id}/messages")
async def get_thread_messages(agent_id: str, thread_id: str):
    """Load historical messages for a thread."""
    gw = get_gateway()
    if agent_id not in gw._graphs:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    graph = gw._graphs[agent_id]
    full_thread_id = f"{agent_id}:{thread_id}"
    config = {"configurable": {"thread_id": full_thread_id}}

    try:
        state = await graph.aget_state(config)
    except NotImplementedError:
        state = graph.get_state(config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load state: {e}")
    if state is None:
        return {"thread_id": thread_id, "messages": []}

    values = state.values if hasattr(state, "values") else {}
    raw_messages = values.get("messages", [])

    messages = []
    for m in raw_messages:
        role = getattr(m, "type", None) or getattr(m, "role", None)
        content = getattr(m, "content", "")
        if role in ("human", "user"):
            role = "user"
        elif role in ("ai", "assistant"):
            role = "assistant"
        else:
            continue
        if isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content})

    return {"thread_id": thread_id, "messages": messages}


@chat_router.delete("/chat/{agent_id}/threads/{thread_id}")
async def delete_thread(agent_id: str, thread_id: str):
    """Delete a conversation thread."""
    sp = get_memory_storage()
    checkpointer = sp.checkpointer
    if checkpointer is None:
        raise HTTPException(status_code=500, detail="No checkpointer configured")

    full_thread_id = f"{agent_id}:{thread_id}"
    try:
        if hasattr(checkpointer, "adelete_thread"):
            await checkpointer.adelete_thread(full_thread_id)
        elif hasattr(checkpointer, "delete_thread"):
            checkpointer.delete_thread(full_thread_id)
        else:
            raise HTTPException(status_code=501, detail="Checkpointer does not support thread deletion")
    except NotImplementedError:
        if hasattr(checkpointer, "delete_thread"):
            checkpointer.delete_thread(full_thread_id)

    return {"status": "deleted", "thread_id": thread_id}
