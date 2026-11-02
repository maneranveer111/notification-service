import argparse
import getpass
import sys
from pathlib import Path

# Add backend directory to sys.path so app modules can be imported
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from datetime import datetime, timezone
from sqlalchemy import select
from app.database import SessionLocal
from app.models.user import User
from app.models.workspace import Membership
from app.services.passwords import hash_password
from app.services.tenancy import get_default_workspace_id


def main():
    parser = argparse.ArgumentParser(description="Create a dashboard user")
    parser.add_argument("--email", required=True, help="User email address")
    parser.add_argument("--password", required=False, help="User password (min 8 chars)")
    parser.add_argument(
        "--role",
        choices=["admin", "viewer"],
        default="admin",
        help="User role (admin or viewer, default admin)",
    )
    parser.add_argument(
        "--superadmin",
        action="store_true",
        default=False,
        help="Grant superadmin privileges",
    )

    args = parser.parse_args()
    email = args.email.strip().lower()
    role = args.role

    password = args.password
    if not password:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Error: Passwords do not match", file=sys.stderr)
            sys.exit(1)

    if len(password) < 8:
        print("Error: Password must be at least 8 characters", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        existing = db.scalar(select(User).where(User.email == email))
        if existing:
            print(f"Error: User with email '{email}' already exists", file=sys.stderr)
            sys.exit(1)

        user = User(
            email=email,
            password_hash=hash_password(password),
            role=role,
            is_superadmin=args.superadmin,
            is_active=True,
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.flush()

        try:
            default_ws_id = get_default_workspace_id(db)
            ws_role = "owner" if role == "admin" else "viewer"
            membership = Membership(user_id=user.id, workspace_id=default_ws_id, role=ws_role)
            db.add(membership)
        except Exception as e:
            print(f"Warning: Could not add user to default workspace: {e}", file=sys.stderr)

        db.commit()
        db.refresh(user)
        print(f"Successfully created {role} user: {user.email} (id={user.id}, superadmin={args.superadmin})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
