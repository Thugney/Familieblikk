"""Private originals, review drafts and durable local OCR work."""
import uuid
from django.db import models
from .models import FamilyRow


class Document(FamilyRow):
    # Legacy originals are never swept. New scans use a separate transient root.
    transient = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    cleanup_pending = models.BooleanField(default=False)
    photo_deleted_at = models.DateTimeField(null=True, blank=True)
    cancelled = models.BooleanField(default=False)
    storage_key = models.CharField(max_length=160, unique=True)
    filename = models.CharField(max_length=180, blank=True)
    content_type = models.CharField(max_length=40, blank=True)
    sha256 = models.CharField(max_length=64, db_index=True, blank=True)
    size = models.PositiveIntegerField()
    upload_key = models.UUIDField(default=uuid.uuid4)
    supplier = models.CharField(max_length=120, blank=True)
    amount_ore = models.PositiveBigIntegerField(null=True, blank=True)
    document_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    invoice_number = models.CharField(max_length=100, blank=True)
    kid = models.CharField(max_length=30, blank=True)
    category = models.ForeignKey('budget.Category', null=True, blank=True, on_delete=models.PROTECT)
    entry = models.ForeignKey('budget.Entry', null=True, blank=True, on_delete=models.PROTECT, related_name='documents')
    bill = models.ForeignKey('budget.BillOccurrence', null=True, blank=True, on_delete=models.PROTECT, related_name='documents')
    confirmed = models.BooleanField(default=False)
    ocr_text = models.TextField(blank=True)
    suggestions = models.JSONField(default=dict, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['household', 'upload_key'], name='document_upload_key')]


class DocumentJob(models.Model):
    generation = models.UUIDField(default=uuid.uuid4)
    document = models.OneToOneField(Document, on_delete=models.PROTECT, related_name='job')
    status = models.CharField(max_length=12, default='pending')
    attempts = models.PositiveIntegerField(default=0)
    lease_until = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=240, blank=True)


class WorkflowCommand(FamilyRow):
    key = models.UUIDField()
    operation = models.CharField(max_length=30)
    payload = models.JSONField()
    result_id = models.UUIDField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=['household', 'key'], name='workflow_command_key')]
