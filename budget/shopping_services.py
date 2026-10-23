"""Shared edits serialized with membership; completion is one atomic expense."""
from django.core.exceptions import ValidationError
from django.db import transaction
from . import access
from .models import ShoppingList, ShoppingItem, ShoppingTrip, Entry, Category, Audit
from .document_services import replay, remember, version, canonical, document_for, duplicates, require_active
from .services import save_entry, Conflict


def trip_duplicates(member, store, effective_date, amount_ore, receipt=None):
    candidates = list(access.safe_rows(member, Entry.objects.filter(description__iexact=store,
        effective_date=effective_date, amount_ore=amount_ore)).order_by('-created_at')[:30])
    if receipt:
        access.require_row(member, receipt)
        candidates.extend(duplicates(member, receipt))
    return list({(row._meta.label, row.pk): row for row in candidates}.values())


@transaction.atomic
def save_list(actor, name, key, list_id=None, expected_version=None):
    member = access.lock_member(actor)
    access.require(member, {'shopping'})
    payload = dict(name=name, id=list_id, version=expected_version)
    old = replay(member, key, 'shopping_list', payload)
    if old: return ShoppingList.objects.get(pk=old.result_id, household=member.household)
    if list_id:
        row = ShoppingList.objects.select_for_update().get(pk=list_id, household=member.household)
        version(row, expected_version)
        row.version += 1
    else:
        row = ShoppingList(household=member.household, created_by=actor)
    row.name = name
    row.full_clean()
    row.save()
    remember(member, actor, key, 'shopping_list', payload, row)
    return row


@transaction.atomic
def save_item(actor, list_id, expected_version, key, item_id=None, **fields):
    member = access.lock_member(actor)
    access.require(member, {'shopping'})
    listing = ShoppingList.objects.select_for_update().get(pk=list_id, household=member.household)
    payload = dict(list=list_id, version=expected_version, item=item_id, **fields)
    old = replay(member, key, 'shopping_item', payload)
    if old: return ShoppingItem.objects.get(pk=old.result_id, household=member.household)
    version(listing, expected_version)
    if set(fields) - {'name', 'quantity', 'price_ore', 'category_id', 'purchased', 'removed'}:
        raise ValidationError('Ukjente varefelt.')
    row = ShoppingItem.objects.select_for_update().get(pk=item_id, shopping_list=listing) if item_id else ShoppingItem(household=member.household, created_by=actor, shopping_list=listing)
    if row.trip_id: raise ValidationError('Varen tilhører en fullført tur. Legg til en ny vare.')
    if fields.get('price_ore') is not None or fields.get('category_id'):
        raise ValidationError('Pris og kategori registreres privat ved fullføring av turen.')
    if fields.get('category_id'):
        access.require(member, {'budget'})
        Category.objects.get(pk=fields['category_id'], household=member.household, archived=False)
    before = {name: str(getattr(row, name)) for name in fields}
    for name, value in fields.items(): setattr(row, name, value)
    row.version += 1
    row.full_clean()
    row.save()
    listing.version += 1
    listing.save(update_fields=['version', 'updated_at'])
    Audit.objects.create(household=member.household, actor=actor, object_id=row.pk, operation='handlelistevare', changes={'before': before, 'after': canonical(fields)})
    remember(member, actor, key, 'shopping_item', payload, row)
    from .notification_services import record_shopping_change
    if any(before[name] != str(value) for name, value in fields.items()):
        record_shopping_change(member, listing, key)
    return row


@transaction.atomic
def complete_trip(actor, list_id, expected_version, key, store, effective_date, amount_ore, category_id, receipt_id=None, acknowledge_duplicate=False):
    member = access.lock_member(actor)
    access.require(member, {'shopping', 'budget'})
    listing = ShoppingList.objects.select_for_update().get(pk=list_id, household=member.household)
    receipt = document_for(member, receipt_id) if receipt_id else None
    payload = dict(list=list_id, version=expected_version, store=store, date=effective_date,
                   amount=amount_ore, category=category_id, receipt=receipt_id, duplicate=acknowledge_duplicate)
    old = replay(member, key, 'shopping_complete', payload)
    if old:
        trip = ShoppingTrip.objects.get(pk=old.result_id, household=member.household)
        access.require_row(member, trip.entry)
        return trip
    version(listing, expected_version)
    if receipt: require_active(receipt)
    items = listing.items.filter(purchased=True, removed=False, trip__isnull=True)
    if not items.exists(): raise ValidationError('Kryss av minst én kjøpt vare før turen fullføres.')
    category = Category.objects.get(pk=category_id, household=member.household, archived=False)
    if not store.strip(): raise ValidationError('Oppgi én butikk for denne turen.')
    if receipt and (receipt.confirmed or receipt.entry_id or receipt.bill_id):
        raise ValidationError('Kvitteringen har allerede en økonomikobling. Åpne eksisterende post.')
    if receipt and receipt.amount_ore is not None and receipt.amount_ore != amount_ore:
        raise ValidationError('Kvitteringens beløp avviker fra faktisk total. Gjennomgå dokumentet først.')
    if not acknowledge_duplicate and trip_duplicates(member, store, effective_date, amount_ore, receipt):
        raise ValidationError('Mulig duplikat. Gjennomgå eksisterende poster og kvitteringens dokumentkjede, eller bekreft uttrykkelig en separat tur.')
    entry = save_entry(actor, Entry(kind='expense', amount_ore=amount_ore, effective_date=effective_date,
                       description=store, category=category, idempotency_key=key), command_key=key)
    trip = ShoppingTrip(household=member.household, created_by=actor, shopping_list=listing, store=store, entry=entry, receipt=receipt)
    trip.full_clean()
    trip.save()
    items.update(trip=trip)
    if receipt:
        receipt.entry, receipt.confirmed = entry, True
        receipt.version += 1
        receipt.save()
    listing.version += 1
    listing.save(update_fields=['version', 'updated_at'])
    remember(member, actor, key, 'shopping_complete', payload, trip)
    return trip


@transaction.atomic
def attach_receipt(actor, trip_id, document_id, expected_version, key):
    member = access.lock_member(actor)
    access.require(member, {'shopping', 'budget', 'documents'})
    trip = ShoppingTrip.objects.select_for_update().get(pk=trip_id, household=member.household)
    access.require_row(member, trip.entry)
    doc = document_for(member, document_id)
    payload = dict(trip=trip_id, document=document_id, version=expected_version)
    if replay(member, key, 'shopping_receipt', payload): return trip
    version(trip, expected_version)
    require_active(doc)
    if trip.receipt_id and trip.receipt_id != doc.pk: raise Conflict('Turen har allerede en kvittering.')
    if doc.bill_id or doc.entry_id and doc.entry_id != trip.entry_id:
        raise ValidationError('Dokumentet er koblet til en annen post.')
    if doc.amount_ore is not None and doc.amount_ore != trip.entry.amount_ore:
        raise ValidationError('Beløpet avviker. Bruk uttrykkelig postretting før kvitteringen kobles.')
    doc.entry, doc.confirmed = trip.entry, True
    doc.version += 1
    doc.save()
    trip.receipt = doc
    trip.version += 1
    trip.save()
    remember(member, actor, key, 'shopping_receipt', payload, trip)
    return trip
