import uuid
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from . import access, shopping_services as service
from .shopping_forms import ListForm, ItemForm, TripForm, ReceiptForm
from .document_views import form_error
from .models import ShoppingList, ShoppingItem, ShoppingTrip, WorkflowCommand, Document
from .document_services import canonical
from .views import NAV


def context(member, **extra):
    return dict(member=member, nav=NAV, page='handlelister', title='Handlelister', **extra)


def submissions(request, version):
    data = request.POST.copy() if request.method == 'POST' else None
    recovering = data is not None and data.get('refresh_version') == '1'
    if recovering:
        data['version'], data['key'] = str(version), str(uuid.uuid4())
        data.pop('confirmation', None)
    return data, recovering


def allow_receipt_replay(form, member, data, operation, target_id):
    """Only the exact previous command may admit its now-confirmed receipt."""
    if not data or 'receipt' not in form.fields or not data.get('receipt'): return
    try:
        key = form.fields['key'].clean(data.get('key'))
        version = form.fields['version'].clean(data.get('version'))
        receipt_id = uuid.UUID(data['receipt'])
        if operation == 'shopping_complete':
            cleaned = {name: form.fields[name].clean(data.get(name)) for name in
                       ('store', 'effective_date', 'amount', 'category', 'acknowledge_duplicate')}
            payload = dict(list=target_id, version=version, store=cleaned['store'], date=cleaned['effective_date'],
                amount=int(cleaned['amount'] * 100), category=cleaned['category'].pk,
                receipt=receipt_id, duplicate=cleaned['acknowledge_duplicate'])
        else:
            payload = dict(trip=target_id, document=receipt_id, version=version)
        old = WorkflowCommand.objects.filter(household=member.household, key=key, operation=operation).first()
        if old and old.payload == canonical(payload):
            authorized = access.safe_rows(member, Document.objects.filter(pk=receipt_id))
            form.fields['receipt'].queryset = form.fields['receipt'].queryset | authorized
    except (ValidationError, ValueError, TypeError, AttributeError):
        return


@login_required
@never_cache
@transaction.atomic
def lists(request):
    member = access.lock_member(request.user)
    access.require(member, {'shopping'})
    form = ListForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            row = service.save_list(request.user, form.cleaned_data['name'], form.cleaned_data['key'])
            return redirect('shopping_detail', list_id=row.pk)
        except ValidationError as error: form_error(form, error)
    return render(request, 'budget/shopping_lists.html', context(member, form=form,
        lists=ShoppingList.objects.filter(household=member.household, archived=False).order_by('name')))


@login_required
@never_cache
@transaction.atomic
def detail(request, list_id):
    member = access.lock_member(request.user)
    access.require(member, {'shopping'})
    row = get_object_or_404(ShoppingList, pk=list_id, household=member.household)
    data, recovering = submissions(request, row.version)
    form = ItemForm(data, member=member, initial={'version': row.version})
    if request.method == 'POST' and not recovering and form.is_valid():
        fields = form.cleaned_data.copy()
        key, version = fields.pop('key'), fields.pop('version')
        fields['price_ore'] = int(fields.pop('price') * 100) if fields['price'] is not None else None
        fields.pop('price', None)
        if 'category' in fields:
            category = fields.pop('category')
            fields['category_id'] = category.pk if category else None
        try:
            service.save_item(request.user, row.pk, version, key, **fields)
            return redirect('shopping_detail', list_id=row.pk)
        except ValidationError as error: form_error(form, error)
    trips = []
    for trip in row.trips.select_related('entry', 'receipt').order_by('-created_at'):
        visible = access.safe_rows(member, type(trip.entry).objects.filter(pk=trip.entry_id)).exists()
        receipt_visible = bool(trip.receipt_id and access.safe_rows(member, type(trip.receipt).objects.filter(pk=trip.receipt_id)).exists())
        trips.append({'id': trip.pk, 'store': trip.store, 'entry': trip.entry if visible else None,
                      'receipt': trip.receipt if receipt_visible else None,
                      'items': trip.items.filter(household=member.household).values('name', 'quantity', 'purchased'),
                      'can_attach': visible and access.allows(member, 'documents') and not trip.receipt_id})
    return render(request, 'budget/shopping_detail.html', context(member, listing=row,
        items=row.items.filter(removed=False, trip__isnull=True).order_by('created_at'),
        removed_items=row.items.filter(removed=True, trip__isnull=True).order_by('created_at'),
        form=form, trips=trips, recovered=recovering))


@login_required
@never_cache
@transaction.atomic
def item(request, item_id):
    member = access.lock_member(request.user)
    access.require(member, {'shopping'})
    row = get_object_or_404(ShoppingItem, pk=item_id, household=member.household, trip__isnull=True)
    data, recovering = submissions(request, row.shopping_list.version)
    initial = dict(name=row.name, quantity=row.quantity, purchased=row.purchased, removed=row.removed,
        price=Decimal(row.price_ore)/100 if row.price_ore is not None else None, category=row.category_id, version=row.shopping_list.version)
    form = ItemForm(data, member=member, initial=initial)
    if request.method == 'POST' and not recovering and form.is_valid():
        fields = form.cleaned_data.copy()
        key, version = fields.pop('key'), fields.pop('version')
        price = fields.pop('price')
        fields['price_ore'] = int(price * 100) if price is not None else None
        if 'category' in fields:
            category = fields.pop('category')
            fields['category_id'] = category.pk if category else None
        try:
            service.save_item(request.user, row.shopping_list_id, version, key, item_id=row.pk, **fields)
            return redirect('shopping_detail', list_id=row.shopping_list_id)
        except ValidationError as error: form_error(form, error)
    return render(request, 'budget/workflow_form.html', context(member, form=form, heading='Endre vare / kjøptstatus',
        button='Lagre vare uten bokføring', list_id=row.shopping_list_id, recovered=recovering))


@login_required
@never_cache
@transaction.atomic
def complete(request, list_id):
    member = access.lock_member(request.user)
    access.require(member, {'shopping', 'budget'})
    row = get_object_or_404(ShoppingList, pk=list_id, household=member.household)
    data, recovering = submissions(request, row.version)
    form = TripForm(data, member=member, initial={'version': row.version})
    if not recovering: allow_receipt_replay(form, member, data, 'shopping_complete', row.pk)
    candidates = []
    if request.method == 'POST' and not recovering and form.is_valid():
        fields = form.cleaned_data
        candidates = service.trip_duplicates(member, fields['store'], fields['effective_date'],
            int(fields['amount'] * 100), fields.get('receipt'))
        try:
            service.complete_trip(request.user, row.pk, fields['version'], fields['key'], fields['store'],
                fields['effective_date'], int(fields['amount'] * 100), fields['category'].pk,
                fields['receipt'].pk if fields.get('receipt') else None, fields['acknowledge_duplicate'])
            return redirect('shopping_detail', list_id=row.pk)
        except ValidationError as error: form_error(form, error)
    return render(request, 'budget/workflow_form.html', context(member, form=form, heading='Fullfør handletur',
        button='Bekreft én utgift', list_id=row.pk, recovered=recovering, duplicates=candidates,
        explanation='Bare avkryssede varer tas med. Flere butikker krever separate turer. Anslåtte varepriser erstatter ikke faktisk total.'))


@login_required
@never_cache
@transaction.atomic
def receipt(request, trip_id):
    member = access.lock_member(request.user)
    access.require(member, {'shopping', 'budget', 'documents'})
    trip = get_object_or_404(ShoppingTrip, pk=trip_id, household=member.household)
    access.require_row(member, trip.entry)
    data, recovering = submissions(request, trip.version)
    form = ReceiptForm(data, member=member, initial={'version': trip.version})
    if not recovering: allow_receipt_replay(form, member, data, 'shopping_receipt', trip.pk)
    if request.method == 'POST' and not recovering and form.is_valid():
        fields = form.cleaned_data
        try:
            service.attach_receipt(request.user, trip.pk, fields['receipt'].pk, fields['version'], fields['key'])
            return redirect('shopping_detail', list_id=trip.shopping_list_id)
        except ValidationError as error: form_error(form, error)
    return render(request, 'budget/workflow_form.html', context(member, form=form, heading='Koble sen kvittering',
        button='Bekreft kobling', list_id=trip.shopping_list_id, recovered=recovering))


@login_required
@never_cache
@require_GET
@transaction.atomic
def revision(request, list_id):
    member = access.lock_member(request.user)
    access.require(member, {'shopping'})
    listing = get_object_or_404(ShoppingList, pk=list_id, household=member.household)
    # No money, category, document or expense metadata in the refresh channel.
    return JsonResponse({'version': listing.version})
