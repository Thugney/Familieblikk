from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.db import IntegrityError
from . import financial_areas as areas
from .financial_areas import participant_ids
from .models import Membership
from .financial_models import FinancialArea, AreaAccessChange

ACTIVATION_ERROR = 'Oppsettet kunne ikke aktiveres fordi eksisterende poster har en ugyldig kobling. Ingen tilgang eller økonomiposter er endret. Kontakt administrator for kontroll av oppsettet.'

class SetupForm(forms.Form):
    owner = forms.ChoiceField(label='Budsjetteier')
    readers = forms.MultipleChoiceField(label='Navngitte foreldre med lesetilgang', required=False, widget=forms.CheckboxSelectMultiple)
    editors = forms.MultipleChoiceField(label='Foreldre som kan administrere fellesbudsjettet', required=False, widget=forms.CheckboxSelectMultiple)
    fingerprint = forms.CharField(widget=forms.HiddenInput)
    def __init__(self, *args, member, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(str(m.pk), m.user.get_full_name() or m.user.email) for m in Membership.objects.filter(household=member.household, user__is_active=True).select_related('user')]
        for key in ('owner', 'readers', 'editors'):
            self.fields[key].choices = choices

class SharingForm(SetupForm):
    def __init__(self, *args, area, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('owner')
        self.fields.pop('fingerprint')
        if area.kind != 'shared':
            self.fields.pop('editors')
        for key in ('readers', 'editors'):
            if key in self.fields:
                self.fields[key].choices = [(value, label) for value, label in self.fields[key].choices if value != str(area.owner_id)]
        if not self.is_bound:
            self.initial['readers'] = list(area.grants.filter(role='reader').values_list('member_id', flat=True))
            self.initial['editors'] = list(area.grants.filter(role='editor').values_list('member_id', flat=True))

class CreateAreaForm(forms.Form):
    name = forms.CharField(label='Budsjettnavn', max_length=120)
    kind = forms.ChoiceField(label='Type', choices=[('personal', 'Personlig'), ('shared', 'Felles foreldrebudsjett')])
    sharing = forms.ChoiceField(label='Innsyn', choices=[('', 'Velg tilgang'), ('private', 'Privat'), ('named', 'Navngitte foreldre')])
    readers = forms.MultipleChoiceField(label='Foreldre med lesetilgang', required=False, widget=forms.CheckboxSelectMultiple)
    editors = forms.MultipleChoiceField(label='Foreldre som administrerer fellesbudsjettet sammen med deg', required=False, widget=forms.CheckboxSelectMultiple)
    def __init__(self, *args, member, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(str(m.pk), m.user.get_full_name() or m.user.email) for m in Membership.objects.filter(household=member.household, user__is_active=True).exclude(pk=member.pk).select_related('user')]
        self.fields['readers'].choices = choices
        self.fields['editors'].choices = choices
    def clean(self):
        data = super().clean()
        if data.get('sharing') == 'private' and data.get('readers') or data.get('sharing') == 'named' and not data.get('readers'):
            raise ValidationError('Velg ingen lesere for privat innsyn, eller minst én navngitt leser.')
        if data.get('kind') == 'personal' and data.get('editors'):
            raise ValidationError('Et personlig budsjett administreres bare av eieren.')
        if data.get('kind') == 'shared' and not data.get('editors'):
            raise ValidationError('Velg den andre forelderen som skal administrere fellesbudsjettet.')
        return data

def context(member, **extra):
    from .views import NAV
    return {'member': member, 'nav': NAV, 'title': 'Dine budsjetter', **extra}

@login_required
def index(request):
    member = get_object_or_404(Membership, user=request.user)
    inventory = areas.legacy_inventory(member)
    pending = any(inventory['groups'].values())
    form = SetupForm(request.POST or None, member=member, initial={'fingerprint': inventory['fingerprint']}) if pending and member.role == 'admin' else None
    create_form = CreateAreaForm(request.POST if request.POST.get('action') == 'create' else None, member=member) if not pending else None
    if request.method == 'POST' and request.POST.get('action') == 'create':
        if not create_form:
            raise PermissionDenied('Fullfør eksisterende oppsett først.')
        if create_form.is_valid():
            try:
                areas.create_area(member, create_form.cleaned_data['name'], create_form.cleaned_data['readers'], create_form.cleaned_data['editors'], create_form.cleaned_data['kind'])
                return redirect('financial_areas')
            except ValidationError as error:
                create_form.add_error(None, error)
    elif request.method == 'POST':
        if not form:
            raise PermissionDenied('Oppsett krever familieadministrator.')
        if form.is_valid():
            try:
                proposal = areas.propose_legacy_setup(member, form.cleaned_data['owner'], form.cleaned_data['readers'], form.cleaned_data['editors'], form.cleaned_data['fingerprint'])
                areas.confirm_access_change(member, proposal.pk, proposal.digest)
                return redirect('financial_proposal', proposal_id=proposal.pk)
            except (ValidationError, ValueError) as error:
                form.add_error(None, error)
            except IntegrityError:
                form.add_error(None, ACTIVATION_ERROR)
    proposals = list(AreaAccessChange.objects.filter(household=member.household, applied=False).select_related('owner__user', 'admin_confirmation__user', 'area'))
    if member.role != 'admin':
        proposals = [proposal for proposal in proposals if proposal.owner_id == member.pk or member.pk in participant_ids(proposal)]
    proposals.sort(key=lambda proposal: bool(proposal.owner_confirmation_id) + bool(proposal.admin_confirmation_id), reverse=True)
    unique = {}
    for proposal in proposals:
        proposal.problem = areas.proposal_problem(proposal)
        proposal.confirmed_by_me = member.pk in (proposal.owner_confirmation_id, proposal.admin_confirmation_id)
        key = (proposal.digest, bool(proposal.problem))
        unique.setdefault(key, proposal)
    proposals = list(unique.values())
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    from django.urls import resolve, Resolver404
    from .area_requests import financial_url, FINANCIAL_NAMES, OPTIONAL_NAMES, NONFINANCIAL_PAGES, WRITE_FORM_NAMES
    destination = request.GET.get('next', '/app/oversikt/')
    parts = urlsplit(destination)
    try:
        match = resolve(parts.path)
        valid = not parts.scheme and not parts.netloc and parts.path.startswith('/') and (match.url_name in FINANCIAL_NAMES | OPTIONAL_NAMES or match.url_name == 'page' and match.kwargs.get('page') not in NONFINANCIAL_PAGES)
    except Resolver404:
        valid = False
    if not valid:
        destination = '/app/oversikt/'
    else:
        destination = urlunsplit(('', '', parts.path, urlencode([(key, value) for key, value in parse_qsl(parts.query) if key != 'area']), parts.fragment))
    available = list(areas.allowed_areas(member))
    if valid and match.url_name in WRITE_FORM_NAMES:
        available = [area for area in available if areas.can_write(member, area)]
    for area in available:
        area.can_write = areas.can_write(member, area)
        area.open_url = financial_url(destination, area.pk)
    return render(request, 'budget/areas.html', context(member, areas=available, pending=pending, setup_form=form, create_form=create_form, proposals=proposals))

@login_required
def sharing(request, area_id):
    member = get_object_or_404(Membership, user=request.user)
    area = get_object_or_404(FinancialArea, pk=area_id, household=member.household)
    if member.pk != area.owner_id and member.role != 'admin':
        raise PermissionDenied('Bare eier og familieadministrator kan foreslå deling.')
    form = SharingForm(request.POST or None, member=member, area=area)
    if request.method == 'POST' and form.is_valid():
        try:
            proposal = areas.propose_access_change(member, area.pk, form.cleaned_data['readers'], form.cleaned_data.get('editors', []))
            areas.confirm_access_change(member, proposal.pk, proposal.digest)
            return redirect('financial_proposal', proposal_id=proposal.pk)
        except ValidationError as error:
            form.add_error(None, error)
        except IntegrityError:
            form.add_error(None, ACTIVATION_ERROR)
    return render(request, 'budget/form.html', context(member, title='Foreslå endret deling', form=form,
        explanation='Når du sender forslaget, bekrefter du den valgte tilgangen. Delingen aktiveres når budsjetteieren og én annen person har bekreftet samme forslag.',
        submit_label='Bekreft og send forslag', back='/budsjetter/'))

@login_required
def proposal(request, proposal_id):
    member = get_object_or_404(Membership, user=request.user)
    change = get_object_or_404(AreaAccessChange, pk=proposal_id, household=member.household)
    if member.pk != change.owner_id and member.role != 'admin' and member.pk not in participant_ids(change):
        raise PermissionDenied
    error = None
    if request.method == 'POST':
        try:
            change = areas.confirm_access_change(member, change.pk, request.POST.get('digest'))
            messages.success(request, 'Forslaget er aktivert.' if change.applied else 'Din bekreftelse er registrert. Den andre personen må også bekrefte.')
            return redirect('financial_proposal', proposal_id=change.pk)
        except ValidationError as exc:
            error = ' '.join(exc.messages)
            # A failed atomic confirmation rolls back; discard in-memory flags too.
            change.refresh_from_db()
        except IntegrityError:
            error = ACTIVATION_ERROR
            change.refresh_from_db()
    people = {m.pk: m.user.get_full_name() or m.user.email for m in Membership.objects.filter(household=member.household).select_related('user')}
    roles = {'owner': 'Eier', 'reader': 'Kun innsyn', 'editor': 'Kan administrere'}
    participants = []
    for entry in change.after if isinstance(change.after, list) else []:
        if not isinstance(entry, dict):
            continue
        member_id, role = entry.get('member'), entry.get('role')
        participants.append({
            'name': people.get(member_id, 'Ikke lenger aktiv') if type(member_id) is int else 'Ugyldig deltaker',
            'role': roles.get(role, 'Ukjent rolle') if isinstance(role, str) else 'Ukjent rolle',
        })
    problem = areas.proposal_problem(change)
    confirmed = member.pk in (change.owner_confirmation_id, change.admin_confirmation_id)
    may_propose = member.pk == change.owner_id or member.role == 'admin'
    open_url = None
    if change.applied and change.area_id and areas.allowed_areas(member).filter(pk=change.area_id).exists():
        from .area_requests import financial_url
        open_url = financial_url('/app/oversikt/', change.area_id)
    return render(request, 'budget/area_proposal.html', context(member, change=change, participants=participants,
        error=error, problem=problem, confirmed=confirmed, may_propose=may_propose, open_url=open_url))
