"""Private, session-bound browser subscriptions and transactional delivery outbox."""
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class PushKey(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    public_key = models.CharField(max_length=120)
    private_ciphertext = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class PushSubscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    household = models.ForeignKey('Household', on_delete=models.CASCADE)
    endpoint_digest = models.CharField(max_length=64, unique=True)
    session_digest = models.CharField(max_length=64, db_index=True)
    secret_ciphertext = models.TextField()
    active = models.BooleanField(default=True)
    state = models.CharField(max_length=20, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_test_at = models.DateTimeField(null=True, blank=True)


class CalendarNotification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    household = models.ForeignKey('Household', on_delete=models.CASCADE)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    event = models.ForeignKey('CalendarEvent', null=True, on_delete=models.SET_NULL)
    original_date = models.DateField()
    kind = models.CharField(max_length=16)
    # Details stay behind normal authenticated tenant access; never in push payloads.
    detail = models.CharField(max_length=400)
    action_key = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['household', 'recipient', 'action_key'], name='push_unique_action_recipient')]


class PushDelivery(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notification = models.ForeignKey(CalendarNotification, null=True, on_delete=models.CASCADE)
    subscription = models.ForeignKey(PushSubscription, on_delete=models.CASCADE, related_name='deliveries')
    state = models.CharField(max_length=16, default='pending')
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    lease_token = models.UUIDField(null=True, blank=True)
    last_error = models.CharField(max_length=24, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['notification', 'subscription'], name='push_unique_notification_device')]
        indexes = [
            models.Index(fields=['available_at', 'created_at'], condition=models.Q(state='pending'), name='push_pending_queue'),
            models.Index(fields=['lease_until'], condition=models.Q(state='sending'), name='push_sending_lease'),
        ]
