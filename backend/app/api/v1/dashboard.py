from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from decimal import Decimal, ROUND_HALF_UP

from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

# ✅ In a real app you'd query a properties table.
# For this skeleton (since DB may be unavailable), we enforce a simple tenant-property map.
# Replace this with a DB query when your properties table is available.
TENANT_PROPERTY_ALLOWLIST = {
    "tenant-a": {"prop-001", "prop-002"},
    "tenant-b": {"prop-003"},
}

def _tenant_owns_property(tenant_id: str, property_id: str) -> bool:
    allowed = TENANT_PROPERTY_ALLOWLIST.get(tenant_id, set())
    return property_id in allowed

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    # ✅ Correctly read tenant_id (your auth returns user object, not dict)
    tenant_id = getattr(current_user, "tenant_id", None) or "default_tenant"

    # ✅ FIX 1: Tenant authorization check (prevents privacy leak)
    if not _tenant_owns_property(tenant_id, property_id):
        # Use 404 to avoid leaking which property IDs exist
        raise HTTPException(status_code=404, detail="Property not found")

    revenue_data = await get_revenue_summary(property_id, tenant_id)

    # ✅ FIX 2: no float precision drift — keep Decimal and round 2dp
    total_decimal = Decimal(str(revenue_data["total"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "property_id": revenue_data["property_id"],
        "total_revenue": float(total_decimal),  # safe after quantize
        "currency": revenue_data["currency"],
        "reservations_count": int(revenue_data["count"]),
    }
