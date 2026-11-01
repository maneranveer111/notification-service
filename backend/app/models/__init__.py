from sqlalchemy import event, text

from app.models.api_client import ApiClient
from app.models.delivery_event import DeliveryEvent
from app.models.notification import Notification
from app.models.template import Template
from app.models.suppression import Suppression
from app.models.user import User
from app.models.delivery_attempt import DeliveryAttempt
from app.models.workspace import Workspace, Membership

__all__ = [
    "ApiClient",
    "DeliveryEvent",
    "Notification",
    "Template",
    "Suppression",
    "User",
    "DeliveryAttempt",
    "Workspace",
    "Membership",
]

_DEFAULT_WS_ID_CACHE = None


def _get_default_ws_id(connection):
    global _DEFAULT_WS_ID_CACHE
    if _DEFAULT_WS_ID_CACHE is not None:
        return _DEFAULT_WS_ID_CACHE
    try:
        row = connection.execute(text("SELECT id FROM workspaces WHERE slug = 'default' LIMIT 1")).fetchone()
        if row:
            _DEFAULT_WS_ID_CACHE = row[0]
            return _DEFAULT_WS_ID_CACHE
        row = connection.execute(text("SELECT id FROM workspaces ORDER BY created_at ASC LIMIT 1")).fetchone()
        if row:
            _DEFAULT_WS_ID_CACHE = row[0]
            return _DEFAULT_WS_ID_CACHE
    except Exception:
        pass
    return None


def _before_insert_tenant_model(mapper, connection, target):
    if hasattr(target, "workspace_id") and target.workspace_id is None:
        def_id = _get_default_ws_id(connection)
        if def_id:
            target.workspace_id = def_id


event.listen(Notification, "before_insert", _before_insert_tenant_model)
event.listen(Template, "before_insert", _before_insert_tenant_model)
event.listen(ApiClient, "before_insert", _before_insert_tenant_model)
event.listen(Suppression, "before_insert", _before_insert_tenant_model)
