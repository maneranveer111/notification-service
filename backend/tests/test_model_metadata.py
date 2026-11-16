import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import Base, SessionLocal
from app.models.notification import Notification
from app.models.template import Template
from app.tasks.notification_tasks import NotificationTask, _deliver


def test_model_metadata_contains_tables():
    """Verify Base.metadata contains both notifications and templates tables."""
    assert "notifications" in Base.metadata.tables
    assert "templates" in Base.metadata.tables
    assert "api_clients" in Base.metadata.tables

    # Verify foreign key on Notification.template_id resolves properly to templates.id
    col = Notification.__table__.c.template_id
    assert len(col.foreign_keys) == 1
    fk = next(iter(col.foreign_keys))
    # Resolving target column must not raise NoReferencedTableError
    target_col = fk.column
    assert target_col.table.name == "templates"
    assert target_col.name == "id"


def test_deliver_with_template_id_commits_cleanly():
    """Verify _deliver commits status changes for a notification with template_id without metadata errors."""
    db = SessionLocal()
    try:
        # Create a Template
        template = Template(
            id=uuid.uuid4(),
            name=f"Test Tpl {uuid.uuid4().hex[:6]}",
            channel="email",
            subject_template="Subject",
            body_template="Hello world",
        )
        db.add(template)
        db.commit()

        # Create a Notification referencing the template
        notif = Notification(
            id=uuid.uuid4(),
            channel="email",
            recipient="template_test@example.com",
            subject="Rendered Subject",
            body="Rendered Hello world",
            status="pending",
            priority="normal",
            template_id=template.id,
        )
        db.add(notif)
        db.commit()

        task = MagicMock()
        task.request = MagicMock()
        send_fn = MagicMock(return_value="msg-test-123")

        # Deliver should succeed and commit both "processing" and "sent" states
        res = _deliver(task, str(notif.id), send_fn)
        assert res["status"] == "sent"

        # Verify DB state
        db.refresh(notif)
        assert notif.status == "sent"
        assert notif.provider_message_id == "msg-test-123"

        # Clean up
        db.delete(notif)
        db.delete(template)
        db.commit()
    finally:
        db.close()


def test_on_failure_robust_against_db_commit_error():
    """Verify on_failure handles secondary database exceptions gracefully, rolls back, and does not crash."""
    notif_id = uuid.uuid4()
    db = SessionLocal()
    notif = Notification(
        id=notif_id,
        channel="email",
        recipient="fail_test@example.com",
        subject="Subject",
        body="Body",
        status="processing",
        priority="normal",
    )
    db.add(notif)
    db.commit()
    db.close()

    task = NotificationTask()

    with patch.object(Session, "commit", side_effect=SQLAlchemyError("DB commit failed in on_failure")), \
         patch.object(Session, "rollback") as mock_rollback:
        # on_failure must catch the DB error, log it, rollback the transaction, and NOT raise
        task.on_failure(
            Exception("Simulated worker delivery error"),
            "task-id-1",
            [str(notif_id)],
            {},
            None,
        )
        assert mock_rollback.call_count >= 1

    # Clean up
    clean_db = SessionLocal()
    n = clean_db.get(Notification, notif_id)
    if n:
        clean_db.delete(n)
        clean_db.commit()
    clean_db.close()


def test_on_retry_robust_against_db_commit_error():
    """Verify on_retry handles secondary database exceptions gracefully, rolls back, and does not crash."""
    notif_id = uuid.uuid4()
    db = SessionLocal()
    notif = Notification(
        id=notif_id,
        channel="email",
        recipient="retry_test@example.com",
        subject="Subject",
        body="Body",
        status="processing",
        priority="normal",
    )
    db.add(notif)
    db.commit()
    db.close()

    task = NotificationTask()

    with patch.object(Session, "commit", side_effect=SQLAlchemyError("DB commit failed in on_retry")), \
         patch.object(Session, "rollback") as mock_rollback:
        # on_retry must catch the DB error, log it, rollback the transaction, and NOT raise
        task.on_retry(
            Exception("Simulated transient network error"),
            "task-id-2",
            [str(notif_id)],
            {},
            None,
        )
        assert mock_rollback.call_count >= 1

    # Clean up
    clean_db = SessionLocal()
    n = clean_db.get(Notification, notif_id)
    if n:
        clean_db.delete(n)
        clean_db.commit()
    clean_db.close()


def test_deliver_rolls_back_on_initial_commit_error():
    """Verify _deliver rolls back the session if initial commit to 'processing' fails."""
    notif_id = uuid.uuid4()
    db = SessionLocal()
    notif = Notification(
        id=notif_id,
        channel="email",
        recipient="rollback_test@example.com",
        subject="Subject",
        body="Body",
        status="pending",
        priority="normal",
    )
    db.add(notif)
    db.commit()
    db.close()

    task = MagicMock()
    task.request = MagicMock()

    with patch.object(Session, "commit", side_effect=SQLAlchemyError("DB error on processing commit")), \
         patch.object(Session, "rollback") as mock_rollback:
        with pytest.raises(SQLAlchemyError) as exc_info:
            _deliver(task, str(notif_id), MagicMock())
        assert "processing commit" in str(exc_info.value)
        assert mock_rollback.call_count >= 1

    # Clean up
    clean_db = SessionLocal()
    n = clean_db.get(Notification, notif_id)
    if n:
        clean_db.delete(n)
        clean_db.commit()
    clean_db.close()
