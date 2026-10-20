import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Household(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    modules = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)
    entry_sequence = models.PositiveBigIntegerField(default=0)


class Membership(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    household = models.ForeignKey(Household, on_delete=models.PROTECT)
    role = models.CharField(max_length=10, choices=[('admin', 'Administrator'), ('member', 'Medlem')])
    verified_at = models.DateTimeField(null=True, blank=True)
    identity_method = models.CharField(max_length=30, default='email_code', choices=[('email_code', 'E-postkode'), ('preregistered_owner', 'Eksplisitt forhåndsregistrert eier'), ('preregistered_admin', 'Lokalt registrert administrator'), ('preregistered_member', 'Lokalt registrert medlem')])
    provisioned_at = models.DateTimeField(null=True, blank=True)
    provisioning_digest = models.CharField(max_length=64, blank=True)
    can_register_households = models.BooleanField(default=False)
    provisioned_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='provisioned_memberships')


class LoginCode(models.Model):
    email = models.EmailField(unique=True)
    digest = models.CharField(max_length=64)
    sent_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    consumed = models.BooleanField(default=False)
    ip_digest = models.CharField(max_length=64)


class LoginRequest(models.Model):
    email_digest = models.CharField(max_length=64, db_index=True)
    ip_digest = models.CharField(max_length=64, db_index=True)
    sent_at = models.DateTimeField(db_index=True)


class PasswordAttempt(models.Model):
    email_digest = models.CharField(max_length=64, db_index=True)
    ip_digest = models.CharField(max_length=64, db_index=True)
    attempted_at = models.DateTimeField(db_index=True)


class Invitation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    household = models.ForeignKey(Household, on_delete=models.PROTECT)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    email = models.EmailField()
    digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    accepted = models.BooleanField(default=False)
    revoked = models.BooleanField(default=False)


class FamilyRow(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    household = models.ForeignKey(Household, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        for field in self._meta.fields:
            if isinstance(field, models.ForeignKey) and field.name not in ('household', 'created_by') and getattr(self, field.attname):
                related = getattr(self, field.name)
                if hasattr(related, 'household_id') and related.household_id != self.household_id:
                    raise ValidationError({field.name: 'Koblingen må tilhøre samme familie.'})


class Category(FamilyRow):
    name = models.CharField(max_length=120)
    color = models.CharField(max_length=7, default='#456EB1')
    archived = models.BooleanField(default=False)
    def __str__(self): return self.name


class Asset(FamilyRow):
    TYPES = [('savings', 'Sparemål'), ('debt', 'Gjeld'), ('fund', 'Årsutgift'), ('recipient', 'Mottaker')]
    kind = models.CharField(max_length=12, choices=TYPES)
    name = models.CharField(max_length=120)
    opening_ore = models.BigIntegerField(default=0)
    opening_date = models.DateField()
    target_ore = models.PositiveBigIntegerField(default=0)
    target_date = models.DateField(null=True, blank=True)
    annual_rate = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    minimum_ore = models.PositiveBigIntegerField(default=0)
    country = models.CharField(max_length=120, blank=True)
    archived = models.BooleanField(default=False)
    def __str__(self): return self.name


class MonthPlan(FamilyRow):
    month = models.DateField()
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.PROTECT)
    asset = models.ForeignKey(Asset, null=True, blank=True, on_delete=models.PROTECT)
    amount_ore = models.PositiveBigIntegerField()
    derived = models.BooleanField(default=False)
    annual_total_ore = models.PositiveBigIntegerField(null=True, blank=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=(Q(category__isnull=False, asset__isnull=True) | Q(category__isnull=True, asset__isnull=False)), name='plan_exactly_one_target'), models.UniqueConstraint(fields=['household', 'month', 'category'], name='unique_category_month'), models.UniqueConstraint(fields=['household', 'month', 'asset'], name='unique_asset_month')]


class BillTemplate(FamilyRow):
    name = models.CharField(max_length=120)
    amount_ore = models.PositiveBigIntegerField()
    first_due = models.DateField()
    monthly = models.BooleanField(default=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.PROTECT)
    asset = models.ForeignKey(Asset, null=True, blank=True, on_delete=models.PROTECT)
    accounting_class = models.CharField(max_length=12, default='ordinary', choices=[('ordinary', 'Vanlig'), ('debt', 'Gjeld'), ('fund', 'Årsfond')])
    archived = models.BooleanField(default=False)


class BillOccurrence(FamilyRow):
    template = models.ForeignKey(BillTemplate, on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    due_date = models.DateField()
    amount_ore = models.PositiveBigIntegerField()
    accounting_class = models.CharField(max_length=12)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.PROTECT)
    asset = models.ForeignKey(Asset, null=True, blank=True, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['template', 'due_date'], name='unique_bill_occurrence')]


class Entry(FamilyRow):
    KINDS = [('income', 'Inntekt'), ('expense', 'Utgift'), ('refund', 'Refusjon'), ('deposit', 'Spareinnskudd'), ('withdrawal', 'Spareuttak'), ('debt', 'Gjeldsbetaling'), ('fund', 'Fondsbetaling'), ('remittance', 'Sendt utenlands')]
    kind = models.CharField(max_length=12, choices=KINDS)
    amount_ore = models.PositiveBigIntegerField()
    effective_date = models.DateField()
    description = models.CharField(max_length=240)
    received = models.BooleanField(default=True)
    income_attribution = models.CharField(max_length=120, blank=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.PROTECT)
    asset = models.ForeignKey(Asset, null=True, blank=True, on_delete=models.PROTECT)
    original = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='refunds')
    occurrence = models.OneToOneField(BillOccurrence, null=True, blank=True, on_delete=models.PROTECT, related_name='payment')
    idempotency_key = models.UUIDField(default=uuid.uuid4)
    original_amount = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    exchange_rate = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    fee_ore = models.PositiveBigIntegerField(default=0)
    sequence = models.PositiveBigIntegerField(default=0, editable=False)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['household', 'idempotency_key'], name='unique_entry_request'), models.CheckConstraint(condition=Q(amount_ore__gt=0), name='entry_positive_amount'), models.UniqueConstraint(fields=['household', 'sequence'], name='unique_entry_sequence')]

    def save(self, *args, **kwargs):
        from django.db import transaction
        with transaction.atomic():
            if self._state.adding:
                house = Household.objects.select_for_update().get(pk=self.household_id)
                house.entry_sequence += 1
                house.save(update_fields=['entry_sequence'])
                self.sequence = house.entry_sequence
            elif Entry.objects.get(pk=self.pk).sequence != self.sequence:
                raise ValidationError('Postens opprinnelige sekvens kan ikke endres.')
            return super().save(*args, **kwargs)


class FundTopUp(FamilyRow):
    occurrence = models.OneToOneField(BillOccurrence, on_delete=models.PROTECT)
    effective_month = models.DateField()
    amount_ore = models.PositiveBigIntegerField()


class Audit(models.Model):
    household = models.ForeignKey(Household, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    object_id = models.UUIDField()
    operation = models.CharField(max_length=30)
    changes = models.JSONField(default=dict)
    at = models.DateTimeField(auto_now_add=True)


class ImportBatch(FamilyRow):
    series = models.CharField(max_length=120)
    sha256 = models.CharField(max_length=64)
    reconciliation = models.JSONField(default=dict)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['household', 'series'], name='unique_import_series')]


class ImportRecord(FamilyRow):
    batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT)
    source_id = models.CharField(max_length=240)
    source_kind = models.CharField(max_length=60)
    raw = models.JSONField()
    status = models.CharField(max_length=20, default='needs_review')
    reason = models.TextField(blank=True)
    target_id = models.UUIDField(null=True, blank=True)
    approved_decision = models.JSONField(default=dict)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['household', 'batch', 'source_id'], name='unique_import_source')]

from .calendar_models import CalendarEvent, CalendarException, CalendarResponse, CalendarRequest  # noqa: E402,F401
from .spending_models import MonthlyBudgetHeader, PlanningRequest  # noqa: E402,F401
