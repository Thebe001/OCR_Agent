"""Development tenant registry."""

from dataclasses import dataclass
from typing import Optional

from app.config.settings import settings


@dataclass
class TenantConfig:
    tenant_id: str
    site_url: str
    api_key: str
    api_secret: str
    subscription_tier: str
    active_agents: list[str]
    is_active: bool = True

    def has_agent(self, agent_id: str) -> bool:
        return agent_id in self.active_agents


_TENANT_REGISTRY: dict[str, TenantConfig] = {
    settings.default_tenant_id: TenantConfig(
        tenant_id=settings.default_tenant_id,
        site_url=settings.erpnext_base_url,
        api_key=settings.erpnext_api_key or "test-api-key",
        api_secret=settings.erpnext_api_secret or "test-api-secret",
        subscription_tier="pro",
        active_agents=["invoice-ocr-agent"],
    )
}


def get_tenant(tenant_id: str) -> Optional[TenantConfig]:
    tenant = _TENANT_REGISTRY.get(tenant_id)
    if not tenant or not tenant.is_active:
        return None
    return tenant


def register_tenant(config: TenantConfig) -> None:
    _TENANT_REGISTRY[config.tenant_id] = config
