"""Custom managers and querysets for tenant-scoped models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from django.db.models import QuerySet


class TenantScopedQuerySet(models.QuerySet):
    """
    QuerySet that automatically filters by company_id.
    Used for all tenant-scoped models.
    """
    
    def for_company(self, company_id: int) -> QuerySet:
        """Filter queryset to a specific company."""
        return self.filter(company_id=company_id)


class TenantScopedManager(models.Manager):
    """
    Manager for tenant-scoped models.
    Provides convenience methods for company-scoped queries.
    """
    
    def get_queryset(self) -> TenantScopedQuerySet:
        """Return the custom tenant-scoped queryset."""
        return TenantScopedQuerySet(self.model, using=self._db)
    
    def for_company(self, company_id: int) -> QuerySet:
        """Get all objects for a specific company."""
        return self.get_queryset().for_company(company_id)


# Example usage in models:
# class SubUser(models.Model):
#     company = models.ForeignKey(Company, on_delete=models.CASCADE)
#     # ... other fields
#     
#     objects = TenantScopedManager()
#     
#     class Meta:
#         base_manager_name = 'objects'
