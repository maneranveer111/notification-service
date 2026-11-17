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
    db: Session,
    workspace: Workspace | None,
    requested_provider: str | None = None,
) -> list[tuple[str, BrevoConfig | SmtpConfig]]:
    """
    Resolve ordered list of (name, config) for email sending.
    Own workspace credentials always win over use_platform_providers.
    1. If workspace has own active brevo/smtp credentials, use them.
    2. Else if workspace is None or use_platform_providers is True, use platform settings.
    3. Else return empty list.

    Selection logic:
    - If requested_provider is set: use only that provider (strict, no fallback).
    - Else if workspace.preferred_email_provider is set and in resolved list: put it first with others as fallback.
    - Else: unchanged order.
    """
    providers: list[tuple[str, BrevoConfig | SmtpConfig]] = []

    # Step 1: own active credentials always take precedence
    if workspace is not None:
        creds = db.execute(
            select(ProviderCredential).where(
                ProviderCredential.workspace_id == workspace.id,
                ProviderCredential.provider.in_(["brevo", "smtp"]),
                ProviderCredential.is_active == True,
            )
        ).scalars().all()

        if creds:
            settings = get_settings()
            raw_order = settings.email_provider_order.split(",")
            order = [p.strip().lower() for p in raw_order if p.strip()]

            cred_by_provider = {c.provider: c for c in creds}

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

    # Step 2: platform fallback if allowed
    if not providers and (workspace is None or workspace.use_platform_providers):
        providers = get_platform_email_providers()

    # Step 3: apply requested_provider or preferred_email_provider ordering
    if requested_provider:
        return [p for p in providers if p[0] == requested_provider]

    pref = getattr(workspace, "preferred_email_provider", None) if workspace else None
    if pref and any(p[0] == pref for p in providers):
        return [p for p in providers if p[0] == pref] + [p for p in providers if p[0] != pref]

    return providers


def resolve_sms_provider(db: Session, workspace: Workspace | None) -> TwilioConfig | None:
    """
    Resolve TwilioConfig for SMS sending.
    Own workspace credentials always win over use_platform_providers.
    1. If workspace has own active Twilio credential, use it.
    2. Else if workspace is None or use_platform_providers is True, use platform settings.
    3. Else return None.
    """
    # Step 1: own active credential always takes precedence
    if workspace is not None:
        cred = db.execute(
            select(ProviderCredential).where(
                ProviderCredential.workspace_id == workspace.id,
                ProviderCredential.provider == "twilio",
                ProviderCredential.is_active == True,
            )
        ).scalar_one_or_none()

        if cred:
            try:
                data = decrypt_json(cred.config_encrypted)
            except Exception:
                return None

            settings = get_settings()
            callback = f"{settings.public_base_url}/webhooks/twilio/{workspace.webhook_token}"
            return TwilioConfig(
                account_sid=data["account_sid"],
                auth_token=data["auth_token"],
                from_number=data["from_number"],
                status_callback=callback,
            )

    # Step 2: platform fallback if allowed
    if workspace is None or workspace.use_platform_providers:
        return get_platform_sms_provider()

    # Step 3: no provider
    return None


def has_email_provider(db: Session, workspace: Workspace | None) -> bool:
    # Step 1: own active credentials always take precedence
    if workspace is not None:
        count = db.scalar(
            select(ProviderCredential.id).where(
                ProviderCredential.workspace_id == workspace.id,
                ProviderCredential.provider.in_(["brevo", "smtp"]),
                ProviderCredential.is_active == True,
            ).limit(1)
        )
        if count is not None:
            return True

    # Step 2: platform fallback if allowed
    if workspace is None or workspace.use_platform_providers:
        return len(get_platform_email_providers()) > 0

    # Step 3: no provider
    return False


def has_sms_provider(db: Session, workspace: Workspace | None) -> bool:
    # Step 1: own active credential always takes precedence
    if workspace is not None:
        count = db.scalar(
            select(ProviderCredential.id).where(
                ProviderCredential.workspace_id == workspace.id,
                ProviderCredential.provider == "twilio",
                ProviderCredential.is_active == True,
            ).limit(1)
        )
        if count is not None:
            return True

    # Step 2: platform fallback if allowed
    if workspace is None or workspace.use_platform_providers:
        return get_platform_sms_provider() is not None

    # Step 3: no provider
    return False

