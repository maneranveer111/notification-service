from datetime import datetime, timezone
import re
import secrets
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.provider_credential import ProviderCredential
from app.models.workspace import Workspace
from app.security import Principal, require_admin
from app.services.crypto import CryptoNotConfigured, decrypt_json, encrypt_json
from app.services.email_service import _send_brevo, _send_smtp
from app.services.net_safety import assert_public_host
from app.services.providers import BrevoConfig, SmtpConfig, TwilioConfig
from app.services.rate_limit import check_rate_limit
from app.services.sms_service import send_sms

router = APIRouter(
    prefix="/providers",
    tags=["Providers"],
    dependencies=[Depends(require_admin)],
)
settings = get_settings()


class BrevoCreateOrUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: str | None = None
    from_email: EmailStr | None = None
    from_name: str | None = None


class SmtpCreateOrUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    from_email: EmailStr | None = None
    use_tls: bool = True


class TwilioCreateOrUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_sid: str | None = None
    auth_token: str | None = None
    from_number: str | None = None


class TestProviderRequest(BaseModel):
    to: str


def _format_credential_response(cred: ProviderCredential) -> dict[str, Any]:
    try:
        conf = decrypt_json(cred.config_encrypted)
    except CryptoNotConfigured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Encryption is not configured on this server",
        )
    except Exception:
        conf = {}

    provider = cred.provider
    fields: dict[str, Any] = {}
    secrets_set: list[str] = []
    hints: dict[str, str] = {}

    if provider == "brevo":
        fields = {
            "from_email": conf.get("from_email"),
            "from_name": conf.get("from_name"),
        }
        if conf.get("api_key"):
            secrets_set.append("api_key")
            hints["api_key"] = conf["api_key"][-4:]
    elif provider == "smtp":
        fields = {
            "host": conf.get("host"),
            "port": conf.get("port"),
            "username": conf.get("username"),
            "from_email": conf.get("from_email"),
            "use_tls": conf.get("use_tls", True),
        }
        if conf.get("password"):
            secrets_set.append("password")
            # Nothing for password hints
    elif provider == "twilio":
        fields = {
            "from_number": conf.get("from_number"),
        }
        if conf.get("auth_token"):
            secrets_set.append("auth_token")
            hints["auth_token"] = conf["auth_token"][-4:]
        if conf.get("account_sid"):
            hints["account_sid"] = conf["account_sid"][-4:]

    return {
        "provider": provider,
        "is_active": cred.is_active,
        "fields": fields,
        "secrets_set": secrets_set,
        "hints": hints,
        "last_verified_at": cred.last_verified_at,
        "last_error": cred.last_error,
        "updated_at": cred.updated_at,
    }


def _sanitize_error(error_msg: str, secrets_list: list[str]) -> str:
    cleaned = error_msg
    for s in secrets_list:
        if s and len(s) > 3:
            cleaned = cleaned.replace(s, "[REDACTED]")
    return cleaned[:300]


@router.get("")
def list_providers(
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not principal.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    creds = db.execute(
        select(ProviderCredential).where(ProviderCredential.workspace_id == principal.workspace_id)
    ).scalars().all()

    return [_format_credential_response(c) for c in creds]


@router.put("/{provider}")
async def create_or_update_provider(
    provider: str,
    request: Request,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    provider = provider.strip().lower()
    if provider not in ("brevo", "smtp", "twilio"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unknown provider: {provider}")

    if not principal.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid JSON body")

    if not isinstance(body, dict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Body must be a JSON object")

    cred = db.execute(
        select(ProviderCredential).where(
            ProviderCredential.workspace_id == principal.workspace_id,
            ProviderCredential.provider == provider,
        )
    ).scalar_one_or_none()

    existing_conf: dict[str, Any] = {}
    if cred:
        try:
            existing_conf = decrypt_json(cred.config_encrypted)
        except CryptoNotConfigured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Encryption is not configured on this server",
            )
        except Exception:
            existing_conf = {}

    is_create = cred is None

    # Validate and assemble merged config
    if provider == "brevo":
        try:
            parsed = BrevoCreateOrUpdate(**body)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

        api_key = parsed.api_key if parsed.api_key is not None else existing_conf.get("api_key")
        from_email = parsed.from_email if parsed.from_email is not None else existing_conf.get("from_email")
        from_name = parsed.from_name if parsed.from_name is not None else existing_conf.get("from_name")

        if is_create and (not api_key or not from_email):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="api_key and from_email are required to configure Brevo",
            )

        merged_conf = {
            "api_key": api_key,
            "from_email": str(from_email) if from_email else None,
            "from_name": from_name,
        }

    elif provider == "smtp":
        try:
            parsed = SmtpCreateOrUpdate(**body)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

        host = parsed.host if parsed.host is not None else existing_conf.get("host")
        port = parsed.port if parsed.port is not None else existing_conf.get("port")
        username = parsed.username if parsed.username is not None else existing_conf.get("username")
        password = parsed.password if parsed.password is not None else existing_conf.get("password")
        from_email = parsed.from_email if parsed.from_email is not None else existing_conf.get("from_email")
        use_tls = parsed.use_tls if "use_tls" in body else existing_conf.get("use_tls", True)

        if is_create and (not host or port is None or not username or not password or not from_email):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="host, port, username, password, and from_email are required to configure SMTP",
            )

        if port not in (25, 465, 587, 2525):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="SMTP port must be one of 25, 465, 587, 2525",
            )

        if host:
            try:
                assert_public_host(host)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid SMTP host: {e}",
                )

        merged_conf = {
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "from_email": str(from_email) if from_email else None,
            "use_tls": use_tls,
        }

    elif provider == "twilio":
        try:
            parsed = TwilioCreateOrUpdate(**body)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

        account_sid = parsed.account_sid if parsed.account_sid is not None else existing_conf.get("account_sid")
        auth_token = parsed.auth_token if parsed.auth_token is not None else existing_conf.get("auth_token")
        from_number = parsed.from_number if parsed.from_number is not None else existing_conf.get("from_number")

        if is_create and (not account_sid or not auth_token or not from_number):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="account_sid, auth_token, and from_number are required to configure Twilio",
            )

        if from_number and not re.match(r"^\+[1-9]\d{6,14}$", from_number):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="from_number must be a valid E.164 phone number (e.g. +1234567890)",
            )

        merged_conf = {
            "account_sid": account_sid,
            "auth_token": auth_token,
            "from_number": from_number,
        }

    try:
        encrypted_data = encrypt_json(merged_conf)
    except CryptoNotConfigured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Encryption is not configured on this server",
        )

    now = datetime.now(timezone.utc)
    if not cred:
        cred = ProviderCredential(
            workspace_id=principal.workspace_id,
            provider=provider,
            config_encrypted=encrypted_data,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(cred)
    else:
        cred.config_encrypted = encrypted_data
        cred.updated_at = now

    db.commit()
    db.refresh(cred)
    return _format_credential_response(cred)


@router.delete("/{provider}")
def delete_provider(
    provider: str,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    provider = provider.strip().lower()
    cred = db.execute(
        select(ProviderCredential).where(
            ProviderCredential.workspace_id == principal.workspace_id,
            ProviderCredential.provider == provider,
        )
    ).scalar_one_or_none()

    if not cred:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    db.delete(cred)
    db.commit()
    return {"ok": True}


@router.post("/{provider}/test")
def test_provider(
    provider: str,
    payload: TestProviderRequest,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    provider = provider.strip().lower()
    if provider not in ("brevo", "smtp", "twilio"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    # Rate limit: 5 tests per minute per workspace
    rl_key = f"provider_test:{principal.workspace_id}"
    if not check_rate_limit(rl_key, 5):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded for provider tests")

    cred = db.execute(
        select(ProviderCredential).where(
            ProviderCredential.workspace_id == principal.workspace_id,
            ProviderCredential.provider == provider,
        )
    ).scalar_one_or_none()

    if not cred:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    try:
        conf = decrypt_json(cred.config_encrypted)
    except CryptoNotConfigured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Encryption is not configured on this server",
        )
    except Exception as e:
        return {"ok": False, "error": f"Failed to decrypt credentials: {e}"}

    secrets_to_sanitize: list[str] = []
    test_ok = False
    error_msg: str | None = None

    try:
        if provider == "brevo":
            secrets_to_sanitize.append(conf.get("api_key", ""))
            cfg = BrevoConfig(
                api_key=conf["api_key"],
                from_email=conf["from_email"],
                from_name=conf.get("from_name"),
            )
            _send_brevo(
                recipient=payload.to,
                subject="Test Notification",
                body="This is a test notification verifying your Brevo credentials.",
                config=cfg,
            )
            test_ok = True

        elif provider == "smtp":
            secrets_to_sanitize.append(conf.get("password", ""))
            assert_public_host(conf["host"])
            cfg = SmtpConfig(
                host=conf["host"],
                port=int(conf["port"]),
                username=conf["username"],
                password=conf["password"],
                from_email=conf["from_email"],
                use_tls=conf.get("use_tls", True),
                is_platform=False,
            )
            _send_smtp(
                recipient=payload.to,
                subject="Test Notification",
                body="This is a test notification verifying your SMTP credentials.",
                config=cfg,
            )
            test_ok = True

        elif provider == "twilio":
            secrets_to_sanitize.append(conf.get("auth_token", ""))
            cfg = TwilioConfig(
                account_sid=conf["account_sid"],
                auth_token=conf["auth_token"],
                from_number=conf["from_number"],
                status_callback=None,
            )
            send_sms(
                recipient=payload.to,
                message="This is a test SMS verifying your Twilio credentials.",
                config=cfg,
            )
            test_ok = True

    except Exception as exc:
        test_ok = False
        error_msg = _sanitize_error(str(exc), secrets_to_sanitize)

    now = datetime.now(timezone.utc)
    if test_ok:
        cred.last_verified_at = now
        cred.last_error = None
    else:
        cred.last_error = error_msg

    db.commit()

    if test_ok:
        return {"ok": True}
    return {"ok": False, "error": error_msg}


@router.get("/webhooks")
def get_provider_webhooks(
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not principal.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    ws = db.get(Workspace, principal.workspace_id)
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    token = ws.webhook_token
    return {
        "token": token,
        "brevo_url": f"{settings.public_base_url}/webhooks/brevo/{token}",
        "twilio_url": f"{settings.public_base_url}/webhooks/twilio/{token}",
    }


@router.post("/webhooks/regenerate")
def regenerate_provider_webhooks(
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not principal.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    ws = db.get(Workspace, principal.workspace_id)
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    ws.webhook_token = secrets.token_urlsafe(32)
    db.commit()
    db.refresh(ws)

    token = ws.webhook_token
    return {
        "token": token,
        "brevo_url": f"{settings.public_base_url}/webhooks/brevo/{token}",
        "twilio_url": f"{settings.public_base_url}/webhooks/twilio/{token}",
    }

