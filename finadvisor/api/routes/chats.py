"""Chats and streaming answers (Server-Sent Events over a POST)."""

from __future__ import annotations

import asyncio
import json
import queue
import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, or_, select
from sqlalchemy.orm import Session

from finadvisor.advisor.pipeline import TurnInput, TurnOutput
from finadvisor.api import store
from finadvisor.portfolio import shelf_map
from finadvisor.api.deps import Current, current, db, rt
from finadvisor.api.runtime import Runtime
from finadvisor.db.models import Chat, Feedback, Message

router = APIRouter(prefix="/api", tags=["chats"])


class NewChat(BaseModel):
    title: str | None = None


class PatchChat(BaseModel):
    title: str | None = Field(None, max_length=200)
    pinned: bool | None = None


class Send(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    route: str | None = Field(None, pattern="^(learn|plan|check)$")


class FeedbackIn(BaseModel):
    rating: int = Field(..., ge=-1, le=1)
    comment: str = Field("", max_length=2000)


def _chat(s: Session, me: Current, chat_id: str) -> Chat:
    c = s.get(Chat, chat_id)
    if c is None or c.user_id != me.id:
        raise HTTPException(404, "Chat not found")
    return c


def _chat_dict(c: Chat) -> dict:
    return {"id": c.id, "title": c.title, "pinned": c.pinned, "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat()}


@router.get("/chats")
def list_chats(q: str | None = None, me: Current = Depends(current), s: Session = Depends(db)):
    stmt = select(Chat).where(Chat.user_id == me.id)
    if q:
        like = f"%{q.strip()}%"
        sub = select(Message.chat_id).where(Message.user_id == me.id, Message.content.ilike(like))
        stmt = stmt.where(or_(Chat.title.ilike(like), Chat.id.in_(sub)))
    rows = s.scalars(stmt.order_by(desc(Chat.pinned), desc(Chat.updated_at)).limit(500)).all()
    return [_chat_dict(c) for c in rows]


@router.post("/chats")
def create_chat(body: NewChat, me: Current = Depends(current), s: Session = Depends(db)):
    c = Chat(user_id=me.id, title=body.title or "New chat")
    s.add(c)
    s.commit()
    return _chat_dict(c)


@router.get("/chats/{chat_id}")
def get_chat(chat_id: str, me: Current = Depends(current), s: Session = Depends(db)):
    c = _chat(s, me, chat_id)
    fb = {f.message_id: {"rating": f.rating, "comment": f.comment}
          for f in s.scalars(select(Feedback).join(Message).where(Message.chat_id == chat_id, Feedback.user_id == me.id))}
    msgs = [store.message_dict(m, fb.get(m.id)) for m in c.messages if not m.superseded]
    return {**_chat_dict(c), "messages": msgs, "generating": chat_id in rt().live}


@router.patch("/chats/{chat_id}")
def patch_chat(chat_id: str, body: PatchChat, me: Current = Depends(current), s: Session = Depends(db)):
    c = _chat(s, me, chat_id)
    if body.title is not None:
        c.title = body.title.strip() or c.title
    if body.pinned is not None:
        c.pinned = body.pinned
    s.commit()
    return _chat_dict(c)


@router.delete("/chats/{chat_id}", status_code=204)
def delete_chat(chat_id: str, me: Current = Depends(current), s: Session = Depends(db)):
    c = _chat(s, me, chat_id)
    s.execute(delete(Message).where(Message.chat_id == c.id))
    s.delete(c)
    s.commit()


@router.post("/chats/{chat_id}/messages")
async def send(chat_id: str, body: Send, request: Request, me: Current = Depends(current), s: Session = Depends(db),
               runtime: Runtime = Depends(rt)):
    c = _chat(s, me, chat_id)
    if chat_id in runtime.live:
        raise HTTPException(409, "An answer is still being written in this chat")
    first = not any(m.role == "user" for m in c.messages)
    um = Message(chat_id=c.id, user_id=me.id, role="user", content=body.text.strip())
    s.add(um)
    if first and c.title == "New chat":
        c.title = store.chat_title(body.text)
    store.track(s, me.id, "message_sent", first=first)
    s.commit()
    return _stream(runtime, me.id, c.id, body.text.strip(), body.route, request, user_message_id=um.id)


@router.post("/chats/{chat_id}/regenerate")
async def regenerate(chat_id: str, request: Request, me: Current = Depends(current), s: Session = Depends(db),
                     runtime: Runtime = Depends(rt)):
    c = _chat(s, me, chat_id)
    if chat_id in runtime.live:
        raise HTTPException(409, "An answer is still being written in this chat")
    live = [m for m in c.messages if not m.superseded]
    users = [m for m in live if m.role == "user"]
    if not users:
        raise HTTPException(400, "Nothing to regenerate")
    for m in live:
        if m.role == "assistant" and m.created_at >= users[-1].created_at:
            m.superseded = True
    store.track(s, me.id, "regenerate")
    s.commit()
    return _stream(runtime, me.id, c.id, users[-1].content, None, request, user_message_id=users[-1].id)


@router.post("/chats/{chat_id}/stop", status_code=204)
def stop(chat_id: str, me: Current = Depends(current), s: Session = Depends(db), runtime: Runtime = Depends(rt)):
    _chat(s, me, chat_id)
    ev = runtime.live.get(chat_id)
    if ev:
        ev.set()


@router.post("/messages/{message_id}/feedback")
def feedback(message_id: str, body: FeedbackIn, me: Current = Depends(current), s: Session = Depends(db)):
    m = s.get(Message, message_id)
    if m is None or m.user_id != me.id or m.role != "assistant":
        raise HTTPException(404, "Message not found")
    f = s.scalar(select(Feedback).where(Feedback.message_id == message_id, Feedback.user_id == me.id))
    if body.rating == 0:
        if f:
            s.delete(f)
    elif f:
        f.rating, f.comment = body.rating, body.comment
    else:
        s.add(Feedback(message_id=message_id, user_id=me.id, rating=body.rating, comment=body.comment))
    s.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- streaming

def _sse(kind: str, data: dict) -> bytes:
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n".encode()


def _stream(runtime: Runtime, user_id: str, chat_id: str, text: str, forced_route: str | None, request: Request,
            user_message_id: str) -> StreamingResponse:
    cancel = threading.Event()
    with runtime.lock:
        runtime.live[chat_id] = cancel
    q: queue.Queue = queue.Queue()

    def worker():
        s = runtime.Session()
        try:
            profile, version, _ = store.latest_profile(s, user_id)
            earlier = [m.content for m in s.scalars(select(Message).where(
                Message.chat_id == chat_id, Message.role == "user", Message.id != user_message_id,
                Message.superseded.is_(False)).order_by(Message.created_at))]
            inp = TurnInput(text=text, confirmed=profile, profile_version=version, earlier_user_turns=earlier,
                            forced_route=forced_route,
                            holdings=lambda: shelf_map.existing(s, user_id, runtime.bundle.tax))
            try:
                out = runtime.advisor.turn(inp, lambda k, d: q.put((k, d)), cancel)
            except Exception:  # noqa: BLE001 - error event already emitted by the advisor
                out = TurnOutput(route="error", status="error", text="")
            mid, run_id = store.persist_turn(s, user_id, chat_id, out)
            if out.advice is not None:
                store.track(s, user_id, "advice_shown", route=out.route, latency_s=out.latency_s)
            s.commit()
            q.put(("done", {"message_id": mid, "advice_run_id": run_id, "status": out.status, "latency_s": out.latency_s}))
        except Exception as e:  # noqa: BLE001
            s.rollback()
            q.put(("error", {"message": "Could not save this answer.", "detail": type(e).__name__}))
        finally:
            s.close()
            with runtime.lock:
                runtime.live.pop(chat_id, None)
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    async def gen():
        yield _sse("start", {"chat_id": chat_id, "user_message_id": user_message_id})
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                if await request.is_disconnected():
                    cancel.set()   # the worker still saves what was written, marked as stopped
                await asyncio.sleep(0.03)
                continue
            if item is None:
                break
            yield _sse(*item)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
