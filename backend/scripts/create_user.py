import argparse
import getpass
import sys
from pathlib import Path

# Add backend directory to sys.path so app modules can be imported
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import select
from app.database import SessionLocal
from app.models.user import User
from app.services.passwords import hash_password


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
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"Successfully created {role} user: {user.email} (id={user.id})")
    finally:
        db.close()


if __name__ == "__main__":
    main()

