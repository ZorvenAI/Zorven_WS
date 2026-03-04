"""Pydantic models for multi-tenancy configuration and runtime context."""

from pydantic import BaseModel, Field


class TenantConfig(BaseModel):
    """Configuration for a single tenant's Odoo connection."""

    tenant_id: str
    odoo_url: str
    odoo_db: str
    odoo_username: str = "admin"
    odoo_password: str = ""
    plan_tier: str = "standard"  # standard | professional | enterprise
    allowed_modules: list[str] = Field(default_factory=list)  # empty = all
    pool_size: int = 5
    rate_limit: int = 60  # requests per minute
    tenancy_model: str = "shared_instance"  # dedicated_db | shared_instance | shared_db
    company_id: int = 1


class TenantContext(BaseModel):
    """Runtime context for an authenticated tenant request."""

    config: TenantConfig
    odoo_uid: int = 0
    user_roles: list[str] = Field(default_factory=list)
    company_id: int = 1
    authenticated: bool = False
