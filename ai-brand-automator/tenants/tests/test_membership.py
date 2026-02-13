"""
Tests for the Membership model and Tenant helper methods.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from tenants.models import Membership, Tenant

User = get_user_model()


@pytest.mark.django_db
class TestMembershipModel:
    """Tests for the Membership join table."""

    def test_create_membership(self, tenant, user):
        """A membership links a user to a tenant with a role."""
        m = Membership.objects.create(
            user=user,
            tenant=tenant,
            role=Membership.Role.OWNER,
        )
        assert m.user == user
        assert m.tenant == tenant
        assert m.role == "owner"
        assert m.is_active is True
        assert m.accepted_at is None

    def test_membership_str(self, tenant, user):
        m = Membership.objects.create(
            user=user,
            tenant=tenant,
            role=Membership.Role.EDITOR,
        )
        assert user.email in str(m)
        assert tenant.name in str(m)
        assert "editor" in str(m)

    def test_unique_user_tenant_constraint(self, tenant, user):
        """Cannot create duplicate membership for same user+tenant."""
        Membership.objects.create(
            user=user,
            tenant=tenant,
            role=Membership.Role.OWNER,
        )
        with pytest.raises(IntegrityError):
            Membership.objects.create(
                user=user,
                tenant=tenant,
                role=Membership.Role.EDITOR,
            )

    def test_multiple_tenants_per_user(self, tenant, tenant2, user):
        """A user can belong to multiple tenants."""
        m1 = Membership.objects.create(
            user=user,
            tenant=tenant,
            role=Membership.Role.OWNER,
        )
        m2 = Membership.objects.create(
            user=user,
            tenant=tenant2,
            role=Membership.Role.EDITOR,
        )
        assert user.memberships.count() == 2
        assert m1.role == "owner"
        assert m2.role == "editor"

    def test_multiple_users_per_tenant(self, tenant, user):
        """A tenant can have multiple members."""
        user2 = User.objects.create_user(
            username="user2",
            email="user2@test.com",
            password="TestPass123!",
        )
        Membership.objects.create(
            user=user,
            tenant=tenant,
            role=Membership.Role.OWNER,
        )
        Membership.objects.create(
            user=user2,
            tenant=tenant,
            role=Membership.Role.VIEWER,
        )
        assert tenant.memberships.count() == 2

    def test_invited_by_field(self, tenant, user):
        """Track who invited a member."""
        editor = User.objects.create_user(
            username="editor",
            email="editor@test.com",
            password="TestPass123!",
        )
        m = Membership.objects.create(
            user=editor,
            tenant=tenant,
            role=Membership.Role.EDITOR,
            invited_by=user,
        )
        assert m.invited_by == user

    def test_soft_deactivate(self, membership_owner):
        """Deactivating a membership keeps the record."""
        membership_owner.is_active = False
        membership_owner.save()
        membership_owner.refresh_from_db()
        assert membership_owner.is_active is False
        assert Membership.objects.filter(id=membership_owner.id).exists()

    def test_role_choices(self):
        """All four roles are available."""
        choices = [c[0] for c in Membership.Role.choices]
        assert "owner" in choices
        assert "admin" in choices
        assert "editor" in choices
        assert "viewer" in choices

    def test_cascade_delete_user(self, tenant, user):
        """Deleting a user cascades to memberships."""
        Membership.objects.create(
            user=user,
            tenant=tenant,
            role=Membership.Role.OWNER,
        )
        user_id = user.id
        user.delete()
        assert not Membership.objects.filter(user_id=user_id).exists()

    def test_cascade_delete_tenant(self, tenant, user):
        """Deleting a tenant cascades to memberships."""
        Membership.objects.create(
            user=user,
            tenant=tenant,
            role=Membership.Role.OWNER,
        )
        tenant_id = tenant.id
        tenant.delete()
        assert not Membership.objects.filter(tenant_id=tenant_id).exists()


@pytest.mark.django_db
class TestTenantSlug:
    """Tests for the Tenant.slug auto-generation."""

    def test_slug_auto_generated(self, db):
        t = Tenant(name="My Cool Brand", subscription_status="trial")
        t.auto_create_schema = False
        t.save()
        assert t.slug == "my-cool-brand"

    def test_slug_uniqueness(self, db):
        t1 = Tenant(name="Duplicate Name", subscription_status="trial")
        t1.auto_create_schema = False
        t1.save()

        t2 = Tenant(name="Duplicate Name", subscription_status="trial")
        t2.auto_create_schema = False
        # Name uniqueness is enforced at serializer level, not model;
        # but slug must be unique, so we set a different slug
        t2.slug = "duplicate-name-1"
        t2.schema_name = "tenant_dup_2"
        t2.save()
        assert t2.slug == "duplicate-name-1"

    def test_slug_preserved_if_set(self, db):
        t = Tenant(
            name="Some Brand",
            slug="custom-slug",
            subscription_status="trial",
        )
        t.auto_create_schema = False
        t.save()
        assert t.slug == "custom-slug"

    def test_schema_name_derived_from_slug(self, db):
        t = Tenant(name="Fresh Bake", subscription_status="trial")
        t.auto_create_schema = False
        t.save()
        assert t.slug == "fresh-bake"
        assert t.schema_name == "tenant_fresh_bake"


@pytest.mark.django_db
class TestTenantMembershipHelpers:
    """Tests for Tenant helper methods that query Membership."""

    def test_get_members(self, tenant, membership_owner, membership_editor):
        members = tenant.get_members()
        assert members.count() == 2

    def test_get_members_excludes_inactive(self, tenant, membership_owner):
        membership_owner.is_active = False
        membership_owner.save()
        assert tenant.get_members().count() == 0

    def test_get_owner(self, tenant, membership_owner, membership_editor):
        owner = tenant.get_owner()
        assert owner == membership_owner.user

    def test_get_owner_returns_none(self, tenant):
        assert tenant.get_owner() is None

    def test_has_member(self, tenant, user, membership_owner):
        assert tenant.has_member(user) is True

    def test_has_member_false(self, tenant, user):
        assert tenant.has_member(user) is False

    def test_has_member_inactive(self, tenant, user, membership_owner):
        membership_owner.is_active = False
        membership_owner.save()
        assert tenant.has_member(user) is False

    def test_get_user_role(self, tenant, user, membership_owner):
        assert tenant.get_user_role(user) == "owner"

    def test_get_user_role_none(self, tenant, user):
        assert tenant.get_user_role(user) is None

    def test_get_user_role_editor(self, tenant, membership_editor):
        assert tenant.get_user_role(membership_editor.user) == "editor"
