from dataclasses import dataclass
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.provider_credential import ProviderCredential
from app.models.workspace import Workspace
from app.services.crypto import decrypt_json


@dataclass
class BrevoConfig:
    api_key: str
    from_email: str
    from_name: str | None = None


@dataclass
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    from_email: str
    use_tls: bool = True
    is_platform: bool = False


@dataclass
class TwilioConfig:
    account_sid: str
    auth_token: str
    from_number: str
    status_callback: str | None = None


def get_platform_email_providers() -> list[tuple[str, BrevoConfig | SmtpConfig]]:
    settings = get_settings()
    raw_order = settings.email_provider_order.split(",")
    order = [p.strip().lower() for p in raw_order if p.strip()]

    providers: list[tuple[str, BrevoConfig | SmtpConfig]] = []
    for p in order:
        if p == "brevo" and settings.brevo_api_key and settings.brevo_from_email:
            providers.append(
                (
                    "brevo",
                    BrevoConfig(
                        api_key=settings.brevo_api_key,
                        from_email=settings.brevo_from_email,
                    ),
                )
            )
        elif (
            p == "smtp"
            and settings.smtp_host
            and settings.smtp_user
            and settings.smtp_password
            and settings.smtp_from_email
        ):
            providers.append(
                (
                    "smtp",
                    SmtpConfig(
                        host=settings.smtp_host,
                        port=settings.smtp_port,
                        username=settings.smtp_user,
                        password=settings.smtp_password,
                        from_email=settings.smtp_from_email,
                        use_tls=settings.smtp_use_tls,
                        is_platform=True,
                    ),
                )
            )
    return providers


def get_platform_sms_provider() -> TwilioConfig | None:
    settings = get_settings()
    if (
        settings.twilio_account_sid
        and settings.twilio_auth_token
        and settings.twilio_from_number
    ):
        return TwilioConfig(
            account_sid=settings.twilio_account_sid,
            auth_token=settings.twilio_auth_token,
            from_number=settings.twilio_from_number,
            status_callback=f"{settings.public_base_url}/webhooks/twilio",
        )
    return None


def resolve_email_providers(
    db: Session, workspace: Workspace | None
) -> list[tuple[str, BrevoConfig | SmtpConfig]]:
    """
    Resolve ordered list of (name, config) for email sending.
    If workspace.use_platform_providers is True (or workspace is None), use platform settings.
    Otherwise, decrypt active workspace credentials in settings.email_provider_order.
    """
    if workspace is None or workspace.use_platform_providers:
        return get_platform_email_providers()

    settings = get_settings()
    raw_order = settings.email_provider_order.split(",")
    order = [p.strip().lower() for p in raw_order if p.strip()]

    creds = db.execute(
        select(ProviderCredential).where(
            ProviderCredential.workspace_id == workspace.id,
            ProviderCredential.provider.in_(["brevo", "smtp"]),
            ProviderCredential.is_active == True,
        )
    ).scalars().all()

    cred_by_provider = {c.provider: c for c in creds}
    providers: list[tuple[str, BrevoConfig | SmtpConfig]] = []

    for name in order:
        cred = cred_by_provider.get(name)
        if not cred:
            continue
        try:
            data = decrypt_json(cred.config_encrypted)
        except Exception:
            continue

        if name == "brevo":
            providers.append(
                (
                    "brevo",
                    BrevoConfig(
                        api_key=data["api_key"],
                        from_email=data["from_email"],
                        from_name=data.get("from_name"),
                    ),
                )
            )
        elif name == "smtp":
            providers.append(
                (
                    "smtp",
                    SmtpConfig(
                        host=data["host"],
                        port=int(data["port"]),
                        username=data["username"],
                        password=data["password"],
                        from_email=data["from_email"],
                        use_tls=data.get("use_tls", True),
                        is_platform=False,
                    ),
                )
            )

    return providers


def resolve_sms_provider(db: Session, workspace: Workspace | None) -> TwilioConfig | None:
    """
    Resolve TwilioConfig for SMS sending.
    If workspace.use_platform_providers is True (or workspace is None), use platform settings.
    Otherwise, decrypt active workspace Twilio credentials.
    """
    if workspace is None or workspace.use_platform_providers:
        return get_platform_sms_provider()

    settings = get_settings()
    cred = db.execute(
        select(ProviderCredential).where(
            ProviderCredential.workspace_id == workspace.id,
            ProviderCredential.provider == "twilio",
            ProviderCredential.is_active == True,
        )
    ).scalar_one_or_none()

    if not cred:
        return None

    try:
        data = decrypt_json(cred.config_encrypted)
    except Exception:
        return None

    callback = f"{settings.public_base_url}/webhooks/twilio/{workspace.webhook_token}"
    return TwilioConfig(
        account_sid=data["account_sid"],
        auth_token=data["auth_token"],
        from_number=data["from_number"],
        status_callback=callback,
    )


def has_email_provider(db: Session, workspace: Workspace | None) -> bool:
    if workspace is None or workspace.use_platform_providers:
        return len(get_platform_email_providers()) > 0

    count = db.scalar(
        select(ProviderCredential.id).where(
            ProviderCredential.workspace_id == workspace.id,
            ProviderCredential.provider.in_(["brevo", "smtp"]),
            ProviderCredential.is_active == True,
        ).limit(1)
    )
    return count is not None


def has_sms_provider(db: Session, workspace: Workspace | None) -> bool:
    if workspace is None or workspace.use_platform_providers:
        return get_platform_sms_provider() is not None

    count = db.scalar(
        select(ProviderCredential.id).where(
            ProviderCredential.workspace_id == workspace.id,
            ProviderCredential.provider == "twilio",
            ProviderCredential.is_active == True,
        ).limit(1)
    )
    return count is not None

