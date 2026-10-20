"""Explicit planning expectations, separate from booked income."""
import uuid
from django.conf import settings
from django.db import models
from .models import FamilyRow


class MonthlyBudgetHeader(FamilyRow):
    month = models.DateField()
    expected_income_ore = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['household', 'month'], name='spending_unique_header')]


class PlanningRequest(models.Model):
    household = models.ForeignKey('budget.Household', on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    key = models.UUIDField(default=uuid.uuid4)
    digest = models.CharField(max_length=64)
    result = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['household', 'key'], name='spending_unique_request')]
