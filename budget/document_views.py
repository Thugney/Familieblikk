import uuid
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from . import access, document_services as service
from .document_forms import UploadForm, DraftForm, ConfirmForm
from .document_storage import path_for
from .models import Document
from .views import NAV, get_member


def context(member, **extra):
    return dict(member=member, nav=NAV, page='dokumenter', title='Skann kvittering', **extra)


def form_error(form, error):
    form.add_error(None, ' '.join(error.messages))


@login_required
@never_cache
def documents(request):
    member = get_member(request)
    if member is None: return redirect('family_gate')
    access.require(member, {'documents'})
    if request.method == 'POST' and request.POST.get('mode') == 'manual':
        try:
            key = uuid.UUID(request.POST.get('key', ''))
        except ValueError:
            key = uuid.uuid4()
        row = service.manual(request.user, key)
        return redirect('document_detail', document_id=row.pk)
    form = UploadForm(request.POST or None, request.FILES or None)
    upload_error = getattr(request, 'document_upload_error', None)
    if upload_error:
        form.add_error(None, upload_error)
    if request.method == 'POST' and not upload_error and form.is_valid():
        try:
            row = service.upload(request.user, form.cleaned_data['file'], form.cleaned_data['key'])
            return redirect('document_detail', document_id=row.pk)
        except ValidationError as error: form_error(form, error)
    rows = Paginator(access.safe_rows(member, Document.objects.all()).select_related('job').order_by('-created_at', '-pk'), 30).get_page(request.GET.get('document_page'))
    return render(request, 'budget/documents.html', context(member, rows=rows, form=form))


@login_required
@never_cache
@transaction.atomic
def detail(request, document_id):
    member = access.lock_member(request.user)
    row = get_object_or_404(access.safe_rows(member, Document.objects.all()), pk=document_id)
    fields = ('supplier', 'document_date', 'due_date')
    initial = {name: getattr(row, name) for name in fields}
    initial.update(version=row.version, amount=Decimal(row.amount_ore)/100 if row.amount_ore else None, category=row.category_id)
    action = request.POST.get('form')
    submitted = request.POST.copy() if request.method == 'POST' else None
    recovering = submitted is not None and submitted.get('refresh_version') == '1'
    if recovering:
        submitted['version'], submitted['key'] = str(row.version), str(uuid.uuid4())
        submitted.pop('confirmation', None)
    draft = DraftForm(submitted if action == 'draft' else None, member=member, initial=initial)
    confirm = ConfirmForm(submitted if action == 'confirm' else None, member=member, initial={'version': row.version})
    active = draft if action == 'draft' else confirm
    if request.method == 'POST' and action == 'cancel':
        from .document_forms import CommandForm
        cancellation = CommandForm(request.POST)
        if cancellation.is_valid():
            try:
                service.cancel(request.user, row.pk, cancellation.cleaned_data['version'], cancellation.cleaned_data['key'])
                return redirect('document_detail', document_id=row.pk)
            except ValidationError as error: form_error(draft, error)
    elif request.method == 'POST' and not recovering and active.is_valid():
        data = active.cleaned_data
        try:
            if action == 'draft':
                values = {name: data[name] for name in fields}
                values['amount_ore'] = int(data['amount'] * 100) if data['amount'] is not None else None
                if 'category' in data: values['category_id'] = data['category'].pk if data['category'] else None
                service.save_draft(request.user, row.pk, data['version'], data['key'], **values)
            elif action == 'confirm':
                target = data.get('entry') if data['action'] == 'link_entry' else data.get('bill')
                service.confirm(request.user, row.pk, data['version'], data['key'], data['action'],
                    target.pk if target else None, data['acknowledge_duplicate'])
            return redirect('document_detail', document_id=row.pk)
        except ValidationError as error: form_error(active, error)
    labels = {'supplier': 'Leverandør / butikk', 'invoice_number': 'Fakturanummer', 'kid': 'KID',
              'document_date': 'Dokumentdato', 'due_date': 'Forfallsdato', 'amount': 'Beløp i NOK'}
    suggestions = [(labels[key], value) for key, value in row.suggestions.items() if key in labels]
    return render(request, 'budget/document_detail.html', context(member, document=row, draft=draft,
        confirm=confirm, duplicates=service.duplicates(member, row), recovered=recovering, suggestions=suggestions, cancel_key=uuid.uuid4()))


@login_required
@never_cache
@require_GET
@transaction.atomic
def original(request, document_id):
    member = access.lock_member(request.user)
    row = get_object_or_404(access.safe_rows(member, Document.objects.all()), pk=document_id)
    if row.transient: raise Http404
    response = FileResponse(path_for(row.storage_key).open('rb'), content_type=row.content_type,
        as_attachment=row.content_type == 'application/pdf' or request.GET.get('download') == '1', filename=row.filename)
    response['Content-Security-Policy'] = "default-src 'none'; sandbox"
    response['X-Content-Type-Options'] = 'nosniff'
    return response
