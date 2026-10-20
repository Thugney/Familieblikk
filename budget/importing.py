"""Privat eierbundet import. Ingen kildeverdi logges eller brukes som felles seed."""
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Asset, Category, Entry, ImportBatch, ImportRecord, Membership, MonthPlan
from .services import save_entry

COLLECTIONS = ['categories', 'transactions', 'debts', 'savings_goals', 'annual_funds', 'recipients', 'fx_rate_settings']


def load_private_source():
    root = Path(settings.PRIVATE_IMPORT_ROOT).resolve()
    package = json.loads((root / 'import/import-package.json').read_text(encoding='utf-8'))
    binding = json.loads((root / 'profile-target.json').read_text(encoding='utf-8'))
    checksum = hashlib.sha256((root / 'source/family-budget-expandable.xlsx').read_bytes()).hexdigest()
    if checksum != package['source']['sha256'] or checksum != binding['source_sha256']:
        raise ValidationError('Kildens kontrollsum stemmer ikke. Import er stoppet.')
    return package, binding


def owner_membership(actor, verified_email, binding, auth_context=None):
    from .identity import binding_digest
    member = Membership.objects.select_related('household').get(user=actor)
    context = auth_context or {}
    verified = bool(member.verified_at and verified_email == actor.email.lower())
    provisioned = member.identity_method == 'preregistered_owner' and member.provisioned_at and member.provisioning_digest == binding_digest(binding) and context.get('identity_method') == 'preregistered_owner' and context.get('preregistered_membership_id') == member.pk and context.get('provisioning_digest') == member.provisioning_digest
    if not actor.is_active or member.role != 'admin' or not (verified or provisioned) or actor.email.lower() != binding.get('owner_email', '').lower():
        raise PermissionDenied('Importen krever riktig autentisert eier og administratorrolle. Forhåndsregistrering er ikke e-postverifisering.')
    if binding.get('household_id') and str(member.household_id) != str(binding['household_id']):
        raise PermissionDenied('Kilden er bundet til en annen familie.')
    return member


@transaction.atomic
def apply_import(actor, verified_email, package, binding, auth_context=None):
    member = owner_membership(actor, verified_email, binding, auth_context)
    type(member.household).objects.select_for_update().get(pk=member.household_id)
    existing = ImportBatch.objects.filter(household=member.household, series=package['import_series']).first()
    if existing:
        if existing.sha256 != package['source']['sha256']:
            raise ValidationError('Kildeversjonen er endret. Sammenlign og avstem forskjellene før en ny import; eksisterende rettinger er bevart.')
        return existing
    # En importserie kan aldri adopteres av en annen familie, selv med samme eier senere.
    if ImportBatch.objects.filter(series=package['import_series']).exists():
        raise PermissionDenied('Importserien er allerede bundet til en familie.')
    batch = ImportBatch.objects.create(household=member.household, created_by=actor, series=package['import_series'], sha256=package['source']['sha256'])
    targets = {}
    counts = {}
    for collection in COLLECTIONS:
        counts[collection] = 0
        for source in package.get(collection, []):
            record = ImportRecord.objects.create(household=member.household, created_by=actor, batch=batch, source_id=source['source_id'], source_kind=collection, raw=source, reason='; '.join(source.get('issue_codes', [])))
            counts[collection] += 1
            raw = source.get('raw', {})
            target = None
            if collection == 'categories':
                target = Category.objects.create(household=member.household, created_by=actor, name=raw.get('name') or source['source_id'])
                record.reason = 'Kategorien er bevart. Månedsramme krever dokumentert virkningsmåned.' if source.get('monthly_budget_ore') is not None else record.reason
                # Udatert budsjett er fortsatt et synlig utkast, aldri en gjettet månedsplan.
            elif collection == 'recipients':
                target = Asset.objects.create(household=member.household, created_by=actor, kind='recipient', name=raw.get('name') or source['source_id'], country=raw.get('country_note') or '', opening_date=timezone.localdate())
                record.status = 'confirmed'
            elif collection == 'debts' and source.get('reference_date') and source.get('reference_balance_ore') is not None:
                source_rate = source.get('annual_rate_decimal')
                # Staging lagrer brøk (0,12), domene/UI lagrer prosent (12).
                percentage = Decimal(source_rate) * 100 if source_rate is not None else None
                target = Asset.objects.create(household=member.household, created_by=actor, kind='debt', name=raw.get('name') or source['source_id'], opening_ore=source['reference_balance_ore'], opening_date=date.fromisoformat(source['reference_date']), annual_rate=percentage, minimum_ore=source.get('monthly_minimum_ore') or 0)
                record.reason = 'Referansesaldo bevart. Minimumsplan trenger eksplisitt virkningsmåned.'
            if target:
                targets[source['source_id']] = target
                record.target_id = target.pk
            record.save()
    for record in ImportRecord.objects.filter(batch=batch, source_kind='transactions'):
        source = record.raw
        kind = source.get('source_accounting_class')
        amount = source.get('amount_nok_ore')
        # Alle usikre koblinger og negative kildetall beholdes som avklaringsutkast.
        if source.get('issue_codes') or not source.get('effective_date') or not amount or amount < 0 or kind not in ('income', 'expense'):
            record.reason = record.reason or 'Bekreft dato, fortegn, regnskapsklasse og kobling før bokføring.'
            record.save()
            continue
        category = targets.get(source.get('category_id'))
        if not category:
            record.reason = 'Kategorien må avklares.'
            record.save()
            continue
        entry = Entry(kind=kind, category=category, amount_ore=amount, effective_date=date.fromisoformat(source['effective_date']), description=source.get('raw', {}).get('description') or category.name, income_attribution=source.get('legacy_income_person_label') or '')
        entry = save_entry(actor, entry)
        record.target_id, record.status = entry.pk, 'confirmed'
        record.approved_decision = decision_snapshot(entry)
        record.save()
    settings_record = package.get('settings')
    if settings_record:
        ImportRecord.objects.create(household=member.household, created_by=actor, batch=batch, source_id=settings_record.get('source_id', 'settings'), source_kind='settings', raw=settings_record, reason='Innstillinger bevart privat. Kildekurser er ikke bekreftet for bokføring.')
    batch.reconciliation = {'source_counts': counts, 'source_selected_month': package.get('source_selected_month'), 'source_transaction_totals_ore': package.get('source_ledger_totals_ore', {}), 'financial_totals_verified': False}
    reconcile_batch(batch)
    batch.save(update_fields=['reconciliation'])
    return batch


def reconcile_batch(batch):
    records = batch.importrecord_set.all()
    batch.reconciliation.update(preserved=records.count(), confirmed=records.filter(status='confirmed').count(), needs_review=records.filter(status='needs_review').count())
    posted, approved, record_differences = {}, {}, {}
    transaction_records = records.filter(source_kind='transactions', status='confirmed', target_id__isnull=False)
    for record in transaction_records:
        entry = Entry.objects.filter(household=batch.household, pk=record.target_id).first()
        actual = decision_snapshot(entry) if entry else {}
        decision = record.approved_decision
        if not decision or decision != actual:
            record_differences[record.source_id] = {'approved': decision, 'actual': actual}
        for snapshot, totals in [(actual, posted), (decision, approved)]:
            if not snapshot: continue
            period = snapshot['effective_date'][:7]
            totals.setdefault(period, {})
            kind = snapshot['accounting_class']
            totals[period][kind] = totals[period].get(kind, 0) + snapshot['signed_amount_ore']
    expected = batch.reconciliation.get('source_transaction_totals_ore', {})
    differences = {}
    for period in set(expected) | set(posted):
        for kind in set(expected.get(period, {})) | set(posted.get(period, {})):
            difference = posted.get(period, {}).get(kind, 0) - expected.get(period, {}).get(kind, 0)
            if difference: differences.setdefault(period, {})[kind] = difference
    approved_differences = {}
    for period in set(approved) | set(posted):
        for kind in set(approved.get(period, {})) | set(posted.get(period, {})):
            delta = posted.get(period, {}).get(kind, 0) - approved.get(period, {}).get(kind, 0)
            if delta: approved_differences.setdefault(period, {})[kind] = delta
    batch.reconciliation.update(posted_transaction_totals_ore=posted, raw_source_differences_ore=differences, approved_transaction_totals_ore=approved, transaction_differences_ore=approved_differences, approved_record_differences=record_differences, financial_totals_verified=transaction_records.exists() and not approved_differences and not record_differences and not records.filter(source_kind='transactions').exclude(status='confirmed').exists())
    batch.save(update_fields=['reconciliation'])
    return batch.reconciliation


def decision_snapshot(entry):
    base_kind = entry.original.kind if entry.kind == 'refund' and entry.original_id else 'deposit' if entry.kind == 'withdrawal' else entry.kind
    accounting = {'debt': 'debt_payment', 'deposit': 'savings_deposit', 'fund': 'annual_fund_payment'}.get(base_kind, base_kind)
    return {'kind': entry.kind, 'accounting_class': accounting, 'effective_date': entry.effective_date.isoformat(), 'amount_ore': entry.amount_ore, 'signed_amount_ore': -entry.amount_ore if entry.kind in ('refund', 'withdrawal') else entry.amount_ore, 'category_id': str(entry.category_id) if entry.category_id else None, 'asset_id': str(entry.asset_id) if entry.asset_id else None, 'original_id': str(entry.original_id) if entry.original_id else None, 'received': entry.received}
