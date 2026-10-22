"""Explicit, tenant-locked review and posting. Upload/OCR never create money."""
import hashlib
import json
import uuid
from datetime import timedelta
from django.utils import timezone
from . import document_spool
from pathlib import PurePath
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from . import access, document_storage
from .models import Document, DocumentJob, WorkflowCommand, Entry, BillTemplate, BillOccurrence, Category, Audit, Membership
from .financial_areas import current_area
from .models import ShoppingCommand
from .services import Conflict, save_entry, save_row, materialize_template, month_start, membership


def canonical(value):
    return json.loads(json.dumps(value, default=str, sort_keys=True))


def replay(member, key, operation, payload):
    shared = operation in ('shopping_list', 'shopping_item')
    if not shared: current_area(member, write=True)
    model = ShoppingCommand if shared else WorkflowCommand
    old = model.objects.filter(household=member.household, created_by=member.user, key=key).first()
    if old and (old.operation != operation or old.payload != canonical(payload)):
        raise Conflict('Bekreftelsesnøkkelen er allerede brukt med annet innhold.')
    return old


def remember(member, actor, key, operation, payload, result):
    model = ShoppingCommand if operation in ('shopping_list', 'shopping_item') else WorkflowCommand
    model.objects.create(household=member.household, created_by=actor, key=key,
                                  operation=operation, payload=canonical(payload), result_id=result.pk)


def version(row, expected):
    if row.version != expected:
        raise Conflict('Endret av et annet familiemedlem. Utkastet ditt er beholdt; last inn gjeldende versjon før du bekrefter igjen.')


def document_for(member, document_id):
    row = Document.objects.select_for_update().get(pk=document_id, household=member.household)
    access.require_row(member, row)
    return row


def upload(actor, uploaded, key):
    try:
        initial = membership(actor)
    except Membership.DoesNotExist:
        raise PermissionDenied('Bli med i en familie først.') from None
    access.require(initial, {'documents'})
    current_area(initial, write=True)
    data = uploaded.read(document_storage.MAX_BYTES + 1)
    digest = hashlib.sha256(data).hexdigest()
    # Replay is authorized under a short fresh lock before any decoder or disk write.
    with transaction.atomic():
        member = access.lock_member(actor)
        access.require(member, {'documents'})
        current_area(member, write=True)
        if member.household_id != initial.household_id:
            raise PermissionDenied('Medlemskapet er endret. Last inn på nytt.')
        old = Document.objects.filter(household=member.household, created_by=actor, upload_key=key).first()
        if old:
            access.require_row(member, old)
            if old.sha256 != digest:
                raise Conflict('Opplastingsnøkkelen er brukt med en annen fil.')
            return old
        if DocumentJob.objects.filter(document__household=member.household, document__financial_area=current_area(member), status__in=['pending', 'running']).count() >= 100:
            raise ValidationError('Familien har 100 dokumenter i kø. Vent til lokal OCR har behandlet noen før du laster opp flere.')
    # Parse/decode and immutable disk writes run without the household lock.
    mime = document_storage.inspect_content(data, image_only=True)
    storage_key = document_spool.store(data)
    registration_attempted = False
    try:
        with transaction.atomic():
            member = access.lock_member(actor)
            access.require(member, {'documents'})
            current_area(member, write=True)
            if member.household_id != initial.household_id:
                raise PermissionDenied('Medlemskapet er endret. Last inn på nytt.')
            old = Document.objects.filter(household=member.household, created_by=actor, upload_key=key).first()
            if old:
                access.require_row(member, old)
                if old.sha256 != digest:
                    raise Conflict('Opplastingsnøkkelen er brukt med en annen fil.')
                return old
            if DocumentJob.objects.filter(document__household=member.household, document__financial_area=current_area(member), status__in=['pending', 'running']).count() >= 100:
                raise ValidationError('Familien har 100 dokumenter i kø. Vent til lokal OCR har behandlet noen før du laster opp flere.')
            # From this point a commit/connection error can leave reference state
            # uncertain. Preserve the original even if the request then fails.
            registration_attempted = True
            row = Document.objects.create(household=member.household, created_by=actor, storage_key=storage_key,
                filename='', content_type=mime, transient=True,
                expires_at=timezone.now() + timedelta(seconds=document_spool.TTL_SECONDS),
                sha256=digest, size=len(data), upload_key=key)
            DocumentJob.objects.create(document=row)
            return row
    finally:
        if not registration_attempted:
            document_spool.discard(storage_key)


@transaction.atomic
def save_draft(actor, document_id, expected_version, key, **fields):
    member = access.lock_member(actor)
    row = document_for(member, document_id)
    allowed = {'supplier', 'amount_ore', 'document_date', 'due_date', 'invoice_number', 'kid', 'category_id'}
    if row.transient:
        allowed -= {'invoice_number', 'kid'}
    if set(fields) - allowed:
        raise ValidationError('Ukjente dokumentfelt.')
    payload = {'id': document_id, 'version': expected_version, **fields}
    if replay(member, key, 'document_draft', payload):
        return row
    version(row, expected_version)
    if row.cancelled:
        raise ValidationError('Skanningen er avbrutt. Ta et nytt bilde eller opprett et nytt manuelt utkast.')
    if row.confirmed:
        raise ValidationError('Bekreftet dokument bevares. Bruk postretting for beløp eller dato.')
    if fields.get('category_id'):
        if not access.category_choices(member, Category.objects.filter(archived=False)).filter(pk=fields['category_id']).exists():
            raise ValidationError('Velg en kategori du har tilgang til.')
    before = {name: str(getattr(row, name)) for name in fields}
    for name, value in fields.items():
        setattr(row, name, value)
    row.version += 1
    row.full_clean()
    row.save()
    Audit.objects.create(household=member.household, actor=actor, object_id=row.pk,
                         operation='dokumentutkast', changes={'before': before, 'after': canonical(fields)})
    remember(member, actor, key, 'document_draft', payload, row)
    return row


def duplicates(member, row):
    docs = access.safe_rows(member, Document.objects.all()).exclude(pk=row.pk)
    from django.db.models import Q
    match = Q(pk__in=[])
    if not row.transient:
        match |= Q(transient=False, sha256=row.sha256)
    if row.supplier and row.amount_ore and row.document_date:
        match |= Q(supplier__iexact=row.supplier, amount_ore=row.amount_ore, document_date=row.document_date)
    if row.supplier and row.invoice_number:
        match |= Q(supplier__iexact=row.supplier, invoice_number=row.invoice_number)
    result = list(docs.filter(match).order_by('-created_at')[:30])
    if row.supplier and row.amount_ore and row.document_date:
        result += list(access.safe_rows(member, Entry.objects.filter(amount_ore=row.amount_ore,
            effective_date=row.document_date, description__iexact=row.supplier)).order_by('-created_at')[:30])
        result += list(access.safe_rows(member, BillOccurrence.objects.filter(amount_ore=row.amount_ore,
            name__iexact=row.supplier)).filter(Q(due_date=row.due_date or row.document_date)).order_by('-created_at')[:30])
    return result


@transaction.atomic
def confirm(actor, document_id, expected_version, key, action, target_id=None, acknowledge_duplicate=False):
    member = access.lock_member(actor)
    row = document_for(member, document_id)
    if action == 'expense': access.require(member, {'budget'})
    elif action == 'bill': access.require(member, {'bills'})
    elif action not in ('link_entry', 'link_bill'): raise ValidationError('Velg en kjent bekreftelse.')
    payload = dict(id=document_id, version=expected_version, action=action, target=target_id, duplicate=acknowledge_duplicate)
    old = replay(member, key, 'document_confirm', payload)
    if old:
        return row
    version(row, expected_version)
    require_active(row)
    if row.confirmed:
        raise Conflict('Dokumentet er allerede bekreftet. Åpne den eksisterende koblingen.')
    if action in ('link_entry', 'link_bill'):
        model = Entry if action == 'link_entry' else BillOccurrence
        target = model.objects.select_for_update().get(pk=target_id, household=member.household)
        access.require_row(member, target)
        if isinstance(target, Entry) and target.kind not in ('expense', 'debt', 'fund', 'remittance'):
            raise ValidationError('Velg en utgift eller betaling.')
        if row.amount_ore is not None and row.amount_ore != target.amount_ore:
            raise ValidationError('Beløpet avviker. Rett dokumentutkastet eller bruk uttrykkelig postretting før kobling.')
        if action == 'link_entry': row.entry = target
        else: row.bill = target
    else:
        if not row.supplier or not row.amount_ore or not row.document_date or not row.category_id:
            raise ValidationError('Bekreft leverandør, positivt beløp, dato og kategori først.')
        if duplicates(member, row) and not acknowledge_duplicate:
            raise ValidationError('Mulig duplikat. Se eksisterende dokument/regning/betaling før du uttrykkelig bekrefter en ny post.')
        if action == 'expense':
            row.entry = save_entry(actor, Entry(kind='expense', amount_ore=row.amount_ore,
                effective_date=row.document_date, description=row.supplier, category=row.category,
                idempotency_key=key), command_key=key)
        else:
            if not row.due_date: raise ValidationError('Bekreft forfallsdato for fakturaen.')
            template = save_row(actor, BillTemplate(name=row.supplier, amount_ore=row.amount_ore,
                first_due=row.due_date, monthly=False, category=row.category))
            materialize_template(template, month_start(row.due_date))
            row.bill = BillOccurrence.objects.get(template=template)
    row.confirmed = True
    row.version += 1
    row.save()
    remember(member, actor, key, 'document_confirm', payload, row)
    Audit.objects.create(household=member.household, actor=actor, object_id=row.pk,
                         operation='dokument bekreftet', changes=canonical(payload))
    return row


def require_active(row):
    if row.transient and (not row.supplier.strip() or not row.amount_ore or not row.document_date or not row.category_id):
        raise ValidationError('Gjennomgå og lagre betalingsmottaker, positivt beløp, dato og kategori før kobling eller bokføring.')
    if row.cancelled:
        raise ValidationError('Skanningen er avbrutt. Opprett et nytt utkast.')


@transaction.atomic
def cancel(actor, document_id, expected_version, key):
    member = access.lock_member(actor)
    row = document_for(member, document_id)
    payload = dict(id=document_id, version=expected_version)
    if replay(member, key, 'scan_cancel', payload):
        return row
    version(row, expected_version)
    if not row.transient or row.confirmed:
        raise ValidationError('Bekreftede poster og eldre originaler bevares.')
    job = DocumentJob.objects.select_for_update().get(document=row)
    job.generation, job.status, job.lease_until = uuid.uuid4(), 'cancelled', None
    job.save()
    row.cancelled, row.cleanup_pending = True, row.photo_deleted_at is None
    row.suggestions, row.ocr_text = {}, ''
    row.supplier, row.invoice_number, row.kid = '', '', ''
    row.amount_ore = row.document_date = row.due_date = row.category = None
    row.version += 1
    row.save()
    remember(member, actor, key, 'scan_cancel', payload, row)
    from .document_ocr import clean_photo
    transaction.on_commit(lambda: clean_photo(row.pk))
    return row


@transaction.atomic
def manual(actor, key):
    member = access.lock_member(actor)
    access.require(member, {'documents'})
    current_area(member, write=True)
    old = Document.objects.filter(household=member.household, created_by=actor, upload_key=key).first()
    if old:
        access.require_row(member, old)
        return old
    row = Document.objects.create(household=member.household, created_by=actor,
        storage_key='scan-' + uuid.uuid4().hex, transient=True, filename='',
        content_type='', sha256='', size=0, upload_key=key, photo_deleted_at=timezone.now())
    DocumentJob.objects.create(document=row, status='ready')
    return row
