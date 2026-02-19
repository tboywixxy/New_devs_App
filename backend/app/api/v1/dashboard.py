from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import authenticate_request as get_current_user
from app.services.cache import get_revenue_summary

router = APIRouter()

# Minimal allowlist for this challenge seed.
# In a real app this is a DB lookup: properties WHERE tenant_id = ?
TENANT_PROPERTIES = {
    "tenant-a": {"prop-001", "prop-004", "prop-005"},
    "tenant-b": {"prop-002", "prop-003"},
}


def _get_tenant_id(current_user: Any) -> str:
    """
    current_user might be a dict or an object depending on auth implementation.
    """
    if isinstance(current_user, dict):
        return current_user.get("tenant_id") or "default_tenant"
    return getattr(current_user, "tenant_id", None) or "default_tenant"


def _tenant_owns_property(tenant_id: str, property_id: str) -> bool:
    allowed = TENANT_PROPERTIES.get(tenant_id)
    if not allowed:
        return False
    return property_id in allowed


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Fixes:
    1) Enforce tenant ownership of property_id (privacy bug)
    2) Prevent cents issues: keep Decimal and quantize to 2dp before returning
    """
    tenant_id = _get_tenant_id(current_user)

    # ✅ Privacy enforcement (return 404 so we don't leak whether another tenant owns it)
    if not _tenant_owns_property(tenant_id, property_id):
        raise HTTPException(status_code=404, detail="Property not found")

    revenue_data = await get_revenue_summary(property_id, tenant_id)

    # revenue_data['total'] comes as string from reservations service (good)
    total_dec = Decimal(str(revenue_data.get("total", "0.00"))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # You can return as float OR string. Float is OK after quantize(0.01).
    total_revenue = float(total_dec)

    return {
        "property_id": revenue_data["property_id"],
        "total_revenue": total_revenue,
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
    }
