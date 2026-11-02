"""
Plain-text email body and subject builders for account lifecycle events.
"""
from app.config import get_settings


def verification_email(link: str) -> tuple[str, str]:
    settings = get_settings()
    subject = f"Verify your email – {settings.app_name}"
    body = (
        f"Hello,\n\n"
        f"Please verify your email address by clicking the link below:\n\n"
        f"{link}\n\n"
        f"This link will expire in 24 hours.\n\n"
        f"If you did not sign up for {settings.app_name}, please ignore this email."
    )
    return subject, body


def reset_email(link: str) -> tuple[str, str]:
    settings = get_settings()
    subject = f"Reset your password – {settings.app_name}"
    body = (
        f"Hello,\n\n"
        f"We received a request to reset your password for {settings.app_name}.\n\n"
        f"Click the link below to set a new password:\n\n"
        f"{link}\n\n"
        f"This link will expire in 1 hour and can only be used once.\n\n"
        f"If you did not request a password reset, you can safely ignore this email."
    )
    return subject, body


def invitation_email(workspace_name: str, inviter_email: str, role: str, link: str) -> tuple[str, str]:
    settings = get_settings()
    subject = f"You're invited to {workspace_name} on {settings.app_name}"
    body = (
        f"Hello,\n\n"
        f"{inviter_email} has invited you to join '{workspace_name}' as a {role} on {settings.app_name}.\n\n"
        f"Accept the invitation by clicking the link below:\n\n"
        f"{link}\n\n"
        f"This invitation will expire in 7 days."
    )
    return subject, body

