"""CAS upload: preview (parse in memory) -> review -> import. Upload history and deletion."""

from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from finadvisor import cas
from finadvisor.api import store
from finadvisor.api.deps import Current, current, db
from finadvisor.api.routes.holdings import _start_tracking
from finadvisor.db.models import CasUpload, Instrument, Transaction
from finadvisor.portfolio import engine as E
from finadvisor.portfolio import service as P

router = APIRouter(prefix="/api/cas", tags=["cas"])
MAX_BYTES = 10 * 1024 * 1024


def _match(s: Session, item: dict) -> Instrument | None:
    if item["kind"] == "mf":
        if item.get("amfi"):
            inst = s.scalar(select(Instrument).where(Instrument.kind == "mf", Instrument.key == str(item["amfi"])))
            if inst:
                return inst
        if item.get("isin"):
            return s.scalar(select(Instrument).where(Instrument.kind == "mf", Instrument.isin == item["isin"]))
        return None
    return s.scalar(select(Instrument).where(Instrument.isin == item["isin"], Instrument.kind.in_(("stock", "etf", "sgb"))))


def _reconcile(s: Session, user_id: str, preview: dict) -> dict:
    """Attach the matched instrument and what FinAdvisor already tracks, so the user sees differences before importing."""
    held = P.holdings_raw(s, user_id)
    for it in preview["items"]:
        inst = _match(s, it)
        it["instrument"] = P.instrument_dict(inst) if inst else None
        if inst and inst.id in held:
            acts = P.actions_for(s, inst.id)
            lots, _ = E.fifo([E.adjust_tx(P._tx(t), acts) for t in held[inst.id][1]])
            it["tracked_units"] = sum(l.qty for l in lots)
        else:
            it["tracked_units"] = 0.0
        it["difference"] = round(it["units"] - it["tracked_units"], 4)
    return preview


@router.post("/preview")
async def preview(file: UploadFile = File(...), password: str = Form(..., max_length=100), me: Current = Depends(current),
                  s: Session = Depends(db)):
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "The file is larger than 10 MB.")
    if not data.startswith(b"%PDF"):
        raise HTTPException(422, "Please upload the original PDF statement.")
    try:
        parsed = cas.normalise(cas.read(data, password))
    except cas.CasError as e:
        raise HTTPException(422, str(e))
    finally:
        del data, password
    up = CasUpload(user_id=me.id, filename=(file.filename or "statement.pdf")[:200], file_type=parsed["file_type"],
                   cas_type=parsed["cas_type"], period_from=parsed["period_from"], period_to=parsed["period_to"],
                   status="previewed", preview=None, counts={"items": len(parsed["items"])}, warnings=parsed["warnings"])
    s.add(up)
    s.flush()
    up.preview = _reconcile(s, me.id, parsed)
    store.track(s, me.id, "cas_previewed", file_type=up.file_type, items=len(parsed["items"]))
    s.commit()
    return {"id": up.id, **up.preview}


class Choice(BaseModel):
    key: str
    include: bool = True
    avg_price: float | None = None
    date: Date | None = None


class ImportIn(BaseModel):
    choices: list[Choice]


@router.post("/{upload_id}/import")
def do_import(upload_id: str, body: ImportIn, me: Current = Depends(current), s: Session = Depends(db)):
    up = s.get(CasUpload, upload_id)
    if up is None or up.user_id != me.id:
        raise HTTPException(404, "Not found")
    if up.status != "previewed" or not up.preview:
        raise HTTPException(409, "This statement was already imported.")
    items = {it["key"]: it for it in up.preview["items"]}
    added, skipped, unmatched = 0, 0, []
    touched: set[str] = set()
    existing = {(t.instrument_id, t.trade_date, t.kind, round(t.quantity, 4), round(t.price, 4))
                for t in s.scalars(select(Transaction).where(Transaction.user_id == me.id))}
    for ch in body.choices:
        it = items.get(ch.key)
        if it is None or not ch.include:
            continue
        inst = _match(s, it)
        if inst is None:
            unmatched.append(it["name"])
            continue
        try:
            txs = cas.transactions_for(it, {"avg_price": ch.avg_price, "date": ch.date.isoformat() if ch.date else None})
        except cas.CasError as e:
            raise HTTPException(422, str(e))
        for t in txs:
            d = Date.fromisoformat(t["date"])
            sig = (inst.id, d, t["kind"], round(t["units"], 4), round(t["price"], 4))
            if sig in existing:
                skipped += 1
                continue
            s.add(Transaction(user_id=me.id, instrument_id=inst.id, kind=t["kind"], trade_date=d, quantity=t["units"],
                              price=t["price"], charges=t.get("charges", 0.0), source="cas", cas_upload_id=up.id,
                              folio_last4=it.get("folio_last4"), note=f"CAS {up.file_type}: {t.get('type', '')}"))
            existing.add(sig)
            added += 1
        touched.add(inst.id)
    s.flush()
    for iid in touched:   # refuse an import that would leave negative holdings
        acts = P.actions_for(s, iid)
        txs = s.scalars(select(Transaction).where(Transaction.user_id == me.id, Transaction.instrument_id == iid)).all()
        try:
            E.fifo([E.adjust_tx(P._tx(t), acts) for t in txs])
        except ValueError:
            s.rollback()
            name = s.get(Instrument, iid).name
            raise HTTPException(422, f"Importing would sell more {name} than recorded. Check earlier statements first.")
    up.status, up.preview = "imported", None
    up.counts = {**up.counts, "transactions_added": added, "duplicates_skipped": skipped, "unmatched": unmatched}
    store.track(s, me.id, "cas_imported", added=added)
    s.commit()
    for iid in touched:
        _start_tracking(iid)
    return up.counts


@router.get("")
def history(me: Current = Depends(current), s: Session = Depends(db)):
    return [{"id": u.id, "filename": u.filename, "file_type": u.file_type, "cas_type": u.cas_type, "period_from": u.period_from,
             "period_to": u.period_to, "status": u.status, "counts": u.counts, "warnings": u.warnings,
             "created_at": u.created_at.isoformat()}
            for u in s.scalars(select(CasUpload).where(CasUpload.user_id == me.id).order_by(desc(CasUpload.created_at)))]


@router.delete("/{upload_id}", status_code=204)
def remove(upload_id: str, me: Current = Depends(current), s: Session = Depends(db)):
    """Deletes the upload record and every transaction imported from it."""
    up = s.get(CasUpload, upload_id)
    if up is None or up.user_id != me.id:
        raise HTTPException(404, "Not found")
    s.execute(delete(Transaction).where(Transaction.cas_upload_id == up.id))
    s.delete(up)
    s.commit()
