"""
Workspace plans and limits.
The numbers in PLANS are default limits to tune based on platform capacity.
"""
from typing import Any, Optional
from app.config import get_settings

PLANS: dict[str, dict[str, Optional[int]]] = {
    # Default plan for new workspaces
    "free": {
        "daily": 100,
        "monthly": 3000,
        "bulk_max": 100,
        "api_keys": 3,
        "members": 5,
    },
    # Paid tier with higher limits
    "pro": {
        "daily": 5000,
        "monthly": 100000,
        "bulk_max": 200,
        "api_keys": 20,
        "members": 25,
    },
    # Unlimited tier (default workspace and enterprise)
    "unlimited": {
        "daily": None,
        "monthly": None,
        "bulk_max": None,
        "api_keys": None,
        "members": None,
    },
}


def get_plan(plan_name: str) -> dict[str, Optional[int]]:
    """Retrieve plan dictionary, defaulting to 'free' if unknown."""
    return PLANS.get(plan_name, PLANS["free"])


def get_effective_bulk_max(plan_name: str) -> int:
    """
    Compute effective bulk recipient maximum.
    min(plan bulk_max, settings.bulk_max_recipients) when the plan has one,
    otherwise settings.bulk_max_recipients.
    """
    settings = get_settings()
    plan = get_plan(plan_name)
    plan_bulk = plan.get("bulk_max")
    if plan_bulk is not None:
        return min(plan_bulk, settings.bulk_max_recipients)
    return settings.bulk_max_recipients

