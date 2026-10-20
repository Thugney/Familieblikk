"""Canonical family calendar records; dates/times are local Europe/Oslo values."""
import uuid
from django.conf import settings
from django.db import models
from .models import Household

class CalendarEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    household = models.ForeignKey(Household, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    series_key = models.UUIDField(default=uuid.uuid4, editable=False)
    payload = models.JSONField()
    revision = models.PositiveIntegerField(default=1)
    deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class CalendarException(models.Model):
    event = models.ForeignKey(CalendarEvent, on_delete=models.CASCADE, related_name='exceptions')
    original_date = models.DateField()
    payload = models.JSONField(null=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['event', 'original_date'], name='calendar_unique_exception')]

class CalendarResponse(models.Model):
    event = models.ForeignKey(CalendarEvent, on_delete=models.CASCADE, related_name='responses')
    original_date = models.DateField()
    member = models.ForeignKey('Membership', on_delete=models.CASCADE)
    status = models.CharField(max_length=4, choices=[('none','Ikke svart'),('yes','Passer'),('no','Passer ikke')])
    revision = models.PositiveIntegerField(default=1)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['event','original_date','member'], name='calendar_unique_response'), models.CheckConstraint(condition=models.Q(status__in=['none','yes','no']), name='calendar_response_status')]

class CalendarRequest(models.Model):
    household = models.ForeignKey(Household, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    key = models.UUIDField()
    digest = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['household','key'], name='calendar_unique_request')]
