"""Explicit planning expectations, separate from booked income."""
import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from .models import FamilyRow
from .financial_models import FinancialRecord


class MonthlyBudgetHeader(FinancialRecord, FamilyRow):
    month = models.DateField()
    expected_income_ore = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        base_manager_name = 'objects'
        default_manager_name = 'objects'
        constraints = [models.UniqueConstraint(fields=['financial_area', 'month'], name='spending_unique_header'), models.UniqueConstraint(fields=['household', 'month'], condition=Q(financial_area__isnull=True), name='spending_unique_header_legacy')]


class PlanningRequest(FinancialRecord):
    household = models.ForeignKey('budget.Household', on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    key = models.UUIDField(default=uuid.uuid4)
    digest = models.CharField(max_length=64)
    result = models.JSONField(default=dict)

    class Meta:
        base_manager_name = 'objects'
        default_manager_name = 'objects'
        constraints = [models.UniqueConstraint(fields=['financial_area', 'actor', 'key'], name='spending_unique_request'), models.UniqueConstraint(fields=['household', 'key'], condition=Q(financial_area__isnull=True), name='spending_unique_request_legacy')]
