"""
Public unsubscribe endpoints – no API key required.
GET  /unsubscribe?token=  – confirm page (does NOT unsubscribe alone)
POST /unsubscribe          – form submission; verifies token, upserts suppression
"""
from html import escape
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.suppression import Suppression
from app.services.unsubscribe import verify_token

router = APIRouter(tags=["Unsubscribe"])

_CONFIRM_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Unsubscribe</title></head>
<body style="font-family:sans-serif;max-width:480px;margin:60px auto;text-align:center">
<h2>Unsubscribe</h2>
<p>You are about to unsubscribe <strong>{recipient}</strong> from <strong>{channel}</strong> marketing messages.</p>
<form method="post" action="/unsubscribe">
  <input type="hidden" name="token" value="{token}">
  <button type="submit" style="padding:10px 24px;background:#e53e3e;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:1rem">
    Confirm Unsubscribe
  </button>
</form>
</body></html>"""

_DONE_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Unsubscribed</title></head>
<body style="font-family:sans-serif;max-width:480px;margin:60px auto;text-align:center">
<h2>You have been unsubscribed</h2>
<p><strong>{recipient}</strong> has been removed from our marketing list.</p>
</body></html>"""


@router.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe_page(token: str, request: Request):
    result = verify_token(token)
    if result is None:
        raise HTTPException(status_code=400, detail="Invalid or tampered unsubscribe token")
    channel, recipient = result
    return HTMLResponse(
        _CONFIRM_PAGE.format(
            channel=escape(channel),
            recipient=escape(recipient),
            token=escape(token),
        )
    )


@router.post("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_confirm(
    request: Request,
    db: Session = Depends(get_db),
):
    body = await request.body()
    try:
        parsed = parse_qs(body.decode("utf-8"))
        token = parsed.get("token", [None])[0]
    except Exception:
        token = None

    if not token:
        # Also check JSON in case client sends JSON
        try:
            data = await request.json()
            token = data.get("token")
        except Exception:
            token = None

    if not token:
        raise HTTPException(status_code=400, detail="Invalid or missing token")

    result = verify_token(token)
    if result is None:
        raise HTTPException(status_code=400, detail="Invalid or tampered unsubscribe token")
    channel, recipient = result
    recipient_lower = recipient.strip().lower()

    ws_id = getattr(result, "workspace_id", None)
    if not ws_id:
        from app.services.tenancy import get_default_workspace_id
        ws_id = get_default_workspace_id(db)

    stmt = (
        pg_insert(Suppression)
        .values(
            workspace_id=ws_id,
            channel=channel,
            recipient=recipient_lower,
            reason="opt_out",
            source="unsubscribe_link",
        )
        .on_conflict_do_nothing(constraint="uq_suppressions_workspace_channel_recipient")
    )
    db.execute(stmt)
    db.commit()

    return HTMLResponse(_DONE_PAGE.format(recipient=escape(recipient_lower)))

