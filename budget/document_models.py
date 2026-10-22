"""Private originals, review drafts and durable local OCR work."""
import uuid
from django.db import models
from django.db.models import Q
from .models import FamilyRow
from .financial_models import FinancialRecord


class Document(FinancialRecord, FamilyRow):
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
        base_manager_name = 'objects'
        default_manager_name = 'objects'
        constraints = [models.UniqueConstraint(fields=['financial_area', 'created_by', 'upload_key'], name='document_upload_key'), models.UniqueConstraint(fields=['household', 'upload_key'], condition=Q(financial_area__isnull=True), name='document_upload_key_legacy')]


class DocumentJob(models.Model):
    generation = models.UUIDField(default=uuid.uuid4)
    document = models.OneToOneField(Document, on_delete=models.PROTECT, related_name='job')
    status = models.CharField(max_length=12, default='pending')
    attempts = models.PositiveIntegerField(default=0)
    lease_until = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=240, blank=True)


class WorkflowCommand(FinancialRecord, FamilyRow):
    key = models.UUIDField()
    operation = models.CharField(max_length=30)
    payload = models.JSONField()
    result_id = models.UUIDField()
    class Meta:
        base_manager_name = 'objects'
        default_manager_name = 'objects'
        constraints = [models.UniqueConstraint(fields=['financial_area', 'created_by', 'key'], name='workflow_command_key'), models.UniqueConstraint(fields=['household', 'key'], condition=Q(financial_area__isnull=True), name='workflow_command_key_legacy')]
