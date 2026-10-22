"""Explicit financial domains. NULL rows are quarantined legacy data."""
import uuid
from django.db import models
from django.core.exceptions import PermissionDenied, ValidationError


class FinancialArea(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    household = models.ForeignKey('budget.Household', on_delete=models.PROTECT)
    owner = models.ForeignKey('budget.Membership', on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=12, default='personal', choices=[('personal', 'Personlig'), ('shared', 'Felles')])
    status = models.CharField(max_length=12, default='active')
    modules = models.JSONField(default=dict)
    access_version = models.PositiveIntegerField(default=1)
    financial_revision = models.PositiveBigIntegerField(default=0)


class FinancialAreaGrant(models.Model):
    area = models.ForeignKey(FinancialArea, on_delete=models.PROTECT, related_name='grants')
    member = models.ForeignKey('budget.Membership', on_delete=models.PROTECT)
    role = models.CharField(max_length=10, choices=[('owner', 'Eier'), ('reader', 'Innsyn'), ('editor', 'Redigerer')])
    class Meta:
        constraints = [models.UniqueConstraint(fields=['area', 'member'], name='unique_area_member')]


class AreaAccessChange(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    household = models.ForeignKey('budget.Household', on_delete=models.PROTECT)
    area = models.ForeignKey(FinancialArea, null=True, on_delete=models.PROTECT)
    owner = models.ForeignKey('budget.Membership', on_delete=models.PROTECT, related_name='+')
    kind = models.CharField(max_length=12, default='sharing')
    before = models.JSONField(default=list)
    after = models.JSONField(default=list)
    expected_version = models.PositiveIntegerField(default=1)
    inventory = models.JSONField(default=dict)
    digest = models.CharField(max_length=64)
    owner_confirmation = models.ForeignKey('budget.Membership', null=True, on_delete=models.PROTECT, related_name='+')
    admin_confirmation = models.ForeignKey('budget.Membership', null=True, on_delete=models.PROTECT, related_name='+')
    applied = models.BooleanField(default=False)


class FinancialQuerySet(models.QuerySet):
    def _clone(self):
        clone = super()._clone()
        clone._financial_scope = getattr(self, '_financial_scope', None)
        return clone

    def _require_write(self):
        from .financial_areas import current_area
        area = current_area(write=True)
        if getattr(self, '_financial_scope', None) != area.pk:
            raise PermissionDenied('Spørringen tilhører et annet budsjett.')
        return area

    def update(self, **kwargs):
        area = self._require_write()
        if 'financial_area' in kwargs or 'financial_area_id' in kwargs:
            raise ValidationError('Budsjettet kan ikke endres ved vanlig redigering.')
        for name, value in kwargs.items():
            field = self.model._meta.get_field(name.removesuffix('_id'))
            if field.is_relation and value is not None and issubclass(field.related_model, FinancialRecord):
                identity = value.pk if hasattr(value, 'pk') else value
                if not field.related_model.objects.filter(pk=identity, financial_area=area).exists():
                    raise ValidationError('Koblingen må tilhøre samme budsjett.')
        return super().update(**kwargs)

    def delete(self):
        self._require_write()
        return super().delete()

    def bulk_create(self, objs, **kwargs):
        for obj in objs:
            obj.clean()
        return super().bulk_create(objs, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        for obj in objs:
            obj.clean()
        return super().bulk_update(objs, fields, **kwargs)


class FinancialManager(models.Manager.from_queryset(FinancialQuerySet)):
    def get_queryset(self):
        from .financial_areas import scope_state
        queryset = super().get_queryset()
        scope = scope_state()
        if scope is None:
            return queryset.none()
        # Keep revocation live even when evaluation is delayed until after scope exit.
        queryset = queryset.filter(financial_area_id=scope['area_id'],
            financial_area__status='active', financial_area__grants__member_id=scope['member_id'],
            financial_area__grants__member__user__is_active=True,
            financial_area__grants__member__household_id=scope['household_id'])
        queryset._financial_scope = scope['area_id']
        return queryset


class FinancialRecord(models.Model):
    financial_area = models.ForeignKey(FinancialArea, null=True, blank=True, on_delete=models.PROTECT)
    objects = FinancialManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
        base_manager_name = 'objects'
        default_manager_name = 'objects'

    def clean(self):
        super().clean()
        from .financial_areas import current_area
        area = current_area(write=True)
        if self.financial_area_id is None and self._state.adding:
            self.financial_area = area
        if self.financial_area_id != area.pk or self.household_id != area.household_id:
            raise PermissionDenied('Posten tilhører et annet budsjett.')
        if not self._state.adding:
            old = type(self).all_objects.filter(pk=self.pk).values_list('financial_area_id', flat=True).first()
            if old != self.financial_area_id:
                raise ValidationError('Budsjettet kan ikke endres ved vanlig redigering.')
        for field in self._meta.fields:
            if field.is_relation and field.name != 'financial_area' and getattr(self, field.attname):
                related = getattr(self, field.name)
                if hasattr(related, 'financial_area_id') and related.financial_area_id != self.financial_area_id:
                    raise ValidationError({field.name: 'Koblingen må tilhøre samme budsjett.'})
        if self._meta.model_name == 'importrecord' and self.target_id:
            from .models import Category, Entry, Asset
            target_model = {'categories': Category, 'transactions': Entry, 'debts': Asset,
                            'savings_goals': Asset, 'annual_funds': Asset, 'recipients': Asset}.get(self.source_kind)
            if target_model is None or not target_model.objects.filter(pk=self.target_id).exists():
                raise ValidationError('Importmålet må tilhøre samme budsjett og riktig type.')
        if self._meta.model_name == 'correctionevent':
            from .models import Entry, BillOccurrence, BillTemplate
            from .correction_services import authorize_snapshot
            from .financial_areas import scope_state
            from .models import Membership
            target_model = {'entry': Entry, 'billoccurrence': BillOccurrence, 'billtemplate': BillTemplate}.get(self.object_type)
            if target_model is None or not target_model.objects.filter(pk=self.object_id).exists():
                raise ValidationError('Historikkmålet må tilhøre samme budsjett.')
            member = Membership.objects.get(pk=scope_state()['member_id'])
            authorize_snapshot(member, target_model, self.before)
            authorize_snapshot(member, target_model, self.after)

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.clean()
        return super().delete(*args, **kwargs)
