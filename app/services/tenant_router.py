"""Tenant resolution and entitlement checks."""

from app.config.tenants import TenantConfig, get_tenant
from app.models.errors import ErrorCode, MCPError


def resolve_tenant(tenant_id: str) -> TenantConfig:
    if not tenant_id or not tenant_id.strip():
        raise MCPError(
            ErrorCode.TENANT_ERROR,
            "Tenant ID is required.",
            "tenant_id is missing",
        )

    clean_tenant_id = tenant_id.strip().lower()
    tenant = get_tenant(clean_tenant_id)
    if tenant is None:
        raise MCPError(
            ErrorCode.TENANT_ERROR,
            "Unknown tenant. Please verify the tenant ID.",
            f"tenant '{clean_tenant_id}' was not found or is inactive",
        )
    return tenant


def check_agent_entitlement(tenant: TenantConfig, agent_id: str) -> None:
    if not tenant.has_agent(agent_id):
        raise MCPError(
            ErrorCode.ENTITLEMENT_ERROR,
            "This feature is not available on your current plan. Please contact your administrator.",
            f"agent '{agent_id}' is not active for tenant '{tenant.tenant_id}'",
        )
