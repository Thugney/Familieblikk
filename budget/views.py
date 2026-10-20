import json
import re
import uuid
from datetime import date
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from urllib.parse import urlencode
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from . import forms, identity, importing, services
from .models import Asset, BillOccurrence, BillTemplate, Category, Entry, ImportBatch, ImportRecord, Invitation, Membership, MonthPlan


NAV = [('oversikt', 'Oversikt'), ('poster', 'Poster'), ('budsjett', 'Budsjett'), ('sparing', 'Sparing'), ('kalender', 'Kalender'), ('mer', 'Mer')]
TITLES = dict(NAV + [('kategorier', 'Kategorier og rammer'), ('regninger', 'Regninger'), ('gjeld', 'Gjeld'), ('arsutgifter', 'Årsutgifter'), ('utland', 'Sendt utenlands'), ('arsoversikt', 'Årsoversikt'), ('familie', 'Familie og innstillinger'), ('tilpass', 'Tilpass appen'), ('import', 'Familiens kildeimport'), ('varsler', 'Varsler')])


def source_money(value):
    return Decimal(value) / 100 if value is not None else None


def error_text(error): return ' '.join(error.messages) if hasattr(error, 'messages') else str(error)


def login_view(request):
    form = forms.EmailForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            identity.send_code(form.cleaned_data['email'], request.META.get('REMOTE_ADDR', ''))
            request.session['login_email'] = form.cleaned_data['email'].lower()
            messages.info(request, 'Hvis adressen kan brukes, er en kode sendt. Vent minst 60 sekunder før du ber om ny kode.')
            return redirect('verify')
        except Exception:
            form.add_error(None, 'Koden kunne ikke sendes. Prøv igjen senere.')
    local_mail = settings.DEBUG and settings.EMAIL_BACKEND in ('django.core.mail.backends.console.EmailBackend', 'django.core.mail.backends.filebased.EmailBackend', 'django.core.mail.backends.locmem.EmailBackend')
    return render(request, 'budget/auth.html', {'form': form, 'title': 'Logg inn', 'button': 'Send engangskode', 'local_mail': local_mail})


def verify_view(request):
    form = forms.CodeForm(request.POST or None, initial={'email': request.session.get('login_email', '')})
    if request.method == 'POST' and form.is_valid():
        try:
            identity.verify_code(request, **form.cleaned_data)
            token = request.session.pop('invitation_token', None)
            return redirect('invitation', token=token) if token else redirect('family_gate')
        except ValidationError as error: form.add_error(None, error)
    return render(request, 'budget/auth.html', {'form': form, 'title': 'Skriv engangskoden', 'button': 'Bekreft kode'})


def password_view(request):
    form = forms.PasswordLoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            identity.password_login(request, form.cleaned_data['email'], form.cleaned_data['password'], request.META.get('REMOTE_ADDR', ''))
            member = services.membership(request.user)
            batch = ImportBatch.objects.filter(household=member.household).order_by('-created_at').first()
            period = batch.reconciliation.get('source_selected_month') if batch else None
            if period:
                try:
                    date.fromisoformat(period + '-01')
                    return redirect(reverse('page', args=['oversikt']) + '?month=' + period)
                except (ValueError, TypeError): pass
            return redirect('family_gate')
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, 'budget/auth.html', {'form': form, 'title': 'Logg inn med passord', 'button': 'Logg inn', 'password_login': True, 'email_code_available': settings.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend' and bool(settings.EMAIL_HOST)})


@login_required
def password_change_view(request):
    member = get_member(request)
    if not member or not member.identity_method.startswith('preregistered_'): raise PermissionDenied
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, 'Passordet er endret.')
        return redirect('page', page='familie')
    return render(request, 'budget/form.html', {'form': form, 'title': 'Endre passord', 'member': member, 'nav': NAV, 'back': reverse('page', args=['familie'])})


@login_required
def register_account_view(request, new_household=False):
    member = services.authorize(request.user, admin=True)
    if new_household and not member.can_register_households: raise PermissionDenied
    form = (forms.RegisterHouseholdForm if new_household else forms.RegisterAccountForm)(request.POST or None)
    if new_household: form.fields.pop('role')
    if request.method == 'POST' and form.is_valid():
        try:
            identity.register_family_account(request.user, form.cleaned_data['email'], form.cleaned_data['password1'], family_name=form.cleaned_data['family_name'] if new_household else None, role=form.cleaned_data.get('role', 'admin'))
            messages.success(request, 'Ny privat familie med egen administrator er opprettet. Du har ikke tilgang til familiens budsjett.' if new_household else 'Familiemedlemmet er registrert. Del startpassordet privat; ingen e-post er sendt.')
            return redirect('page', page='familie')
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, 'budget/form.html', {'form': form, 'title': 'Opprett en ny familie' if new_household else 'Legg til familiemedlem', 'explanation': 'Kontoen forhåndsregistreres lokalt. E-postadressen er ikke verifisert. Eksisterende kontoer kan ikke overtas.', 'member': member, 'nav': NAV, 'back': reverse('page', args=['familie'])})


@login_required
def family_gate(request):
    if Membership.objects.filter(user=request.user).exists(): return redirect('page', page='oversikt')
    form = forms.FamilyForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            identity.create_household(request.user, form.cleaned_data['name'], request.session.get('verified_email'))
            return redirect('page', page='oversikt')
        except ValidationError as error: form.add_error(None, error)
    return render(request, 'budget/auth.html', {'form': form, 'title': 'Opprett familien', 'button': 'Opprett familie'})


def invitation_view(request, token):
    if not request.user.is_authenticated:
        request.session['invitation_token'] = token
        return redirect('login')
    error = None
    if request.method == 'POST':
        try:
            identity.accept_invite(request.user, token, request.session.get('verified_email'))
            return redirect('page', page='oversikt')
        except ValidationError as exc: error = error_text(exc)
    invitation = Invitation.objects.filter(digest=identity.digest(token), email=request.session.get('verified_email')).select_related('household').first()
    return render(request, 'budget/invitation.html', {'invitation': invitation, 'error': error})


@require_POST
def logout_view(request):
    logout(request)
    response = redirect('password_login')
    response['Clear-Site-Data'] = '"cache", "storage"'
    return response


def get_member(request):
    try: return services.membership(request.user)
    except Membership.DoesNotExist: return None


def selected_month(request):
    value = request.GET.get('month', '').strip()
    if not value: return timezone.localdate().replace(day=1)
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}', value): raise Http404('Ugyldig måned')
    try: return date.fromisoformat(value + '-01')
    except ValueError: raise Http404('Ugyldig måned')


def add_calendar_months(day, count):
    absolute = day.year * 12 + day.month - 1 + count
    if absolute < 12 or absolute >= 10000 * 12: return None
    return date(absolute // 12, absolute % 12 + 1, 1)


@login_required
def page_view(request, page='oversikt'):
    if page in ('budsjett', 'arsoversikt'):
        from .spending_views import render_shell
        return render_shell(request, 'annual' if page == 'arsoversikt' else 'spending')
    if page not in TITLES: raise Http404
    member = get_member(request)
    if not member: return redirect('family_gate')
    month = selected_month(request)
    services.prepare_month(member.household, month)
    house = member.household
    totals = services.calculate(house, month)
    month_entries = Entry.objects.filter(household=house, effective_date__range=(month, services.month_end(month)))
    totals['gross_deposits'] = services.total(month_entries.filter(kind='deposit'))
    totals['planned_savings'] = services.total(MonthPlan.objects.filter(household=house, month=month, asset__kind='savings'))
    chart = []
    for offset in [-2, -1, 0]:
        period = add_calendar_months(month, offset)
        if period is None: continue
        end = services.month_end(period)
        if month == services.month_start(timezone.localdate()): end = period.replace(day=min(timezone.localdate().day, end.day))
        has_data = Entry.objects.filter(household=house, effective_date__range=(period, end)).exists()
        amount = services.ordinary_for_period(house, period, end)
        chart.append({'month': period, 'amount': amount, 'has_data': has_data, 'current': offset == 0})
    ceiling = max([item['amount'] for item in chart] + [1])
    for item in chart: item['height'] = max(item['amount'] * 100 // ceiling, 0)
    # Listefiltre påvirker aldri månedens regnskapsgrunnlag eller andre seksjoner.
    entries = month_entries.select_related('category', 'asset', 'created_by').order_by('-effective_date', '-sequence', '-pk')
    filter_form, page_obj = None, None
    entry_query = ''
    entry_scope_has_rows = False
    if page in ('poster', 'utland'):
        if page == 'utland': entries = entries.filter(Q(kind='remittance') | Q(kind='refund', original__kind='remittance'))
        entry_scope_has_rows = entries.exists()
        filter_form = forms.EntryFilterForm(request.GET, household=house, month=month, remittances_only=page == 'utland')
        if filter_form.is_valid():
            filters = filter_form.cleaned_data
            if filters['q']: entries = entries.filter(Q(description__icontains=filters['q']) | Q(category__name__icontains=filters['q']) | Q(asset__name__icontains=filters['q']) | Q(kind='refund', original__category__name__icontains=filters['q']))
            if filters['kind']: entries = entries.filter(kind=filters['kind'])
            if filters['category']: entries = entries.filter(Q(category=filters['category']) | Q(kind='refund', original__category=filters['category']))
            if filters['creator']: entries = entries.filter(created_by_id=filters['creator'])
            if filters['date_from']: entries = entries.filter(effective_date__gte=filters['date_from'])
            if filters['date_to']: entries = entries.filter(effective_date__lte=filters['date_to'])
            if filters.get('status'): entries = entries.filter(kind='income', received=filters['status'] == 'received')
        else:
            entries = entries.none()
        page_obj = Paginator(entries, 10).get_page(request.GET.get('page'))
        entries = page_obj.object_list
        entry_query = urlencode({**{key: request.GET[key] for key in filter_form.fields if request.GET.get(key)}, 'month': month.strftime('%Y-%m')})
    spent_by_category = dict(month_entries.filter(kind__in=['expense', 'remittance']).values('category_id').annotate(amount=Sum('amount_ore')).values_list('category_id', 'amount'))
    refunds_by_category = dict(month_entries.filter(kind='refund', original__kind__in=['expense', 'remittance']).values('original__category_id').annotate(amount=Sum('amount_ore')).values_list('original__category_id', 'amount'))
    plans_by_category = {plan.category_id: plan for plan in MonthPlan.objects.filter(household=house, month=month, category__isnull=False)}
    categories = []
    for category in Category.objects.filter(household=house).order_by('name', 'id'):
        plan = plans_by_category.get(category.pk)
        spent = spent_by_category.get(category.pk, 0) - refunds_by_category.get(category.pk, 0)
        limit = plan.amount_ore if plan else None
        categories.append({'row': category, 'spent': spent, 'plan': plan, 'limit': limit, 'over': max(spent - limit, 0) if limit is not None else None, 'progress_value': min(max(spent, 0), limit) if limit else 0})
    positive_spending = sum(max(item['spent'], 0) for item in categories)
    for item in categories:
        share = Decimal(max(item['spent'], 0)) * 100 / positive_spending if positive_spending else Decimal(0)
        item.update(share=share, share_width=format(share, '.4f'))
    category_count_total = len(categories)
    category_q = request.GET.get('category_q', '').strip()[:120]
    category_status = request.GET.get('category_status', 'active' if page == 'oversikt' else 'all')
    if category_status not in ('active', 'all', 'archived'): category_status = 'all'
    if category_status == 'active': categories = [item for item in categories if not item['row'].archived or item['spent'] != 0]
    if category_status == 'archived': categories = [item for item in categories if item['row'].archived]
    if category_q: categories = [item for item in categories if category_q.casefold() in item['row'].name.casefold()]
    categories.sort(key=lambda item: (-max(item['spent'], 0), item['row'].archived, item['row'].name.casefold(), str(item['row'].pk)))
    category_matched_count = len(categories)
    category_show_all = request.GET.get('category_all') == '1'
    category_expand_query = urlencode({'month': month.strftime('%Y-%m'), 'category_q': category_q, 'category_status': category_status, 'category_all': '0' if category_show_all else '1'})
    assets = []
    kind_map = {'sparing': 'savings', 'gjeld': 'debt', 'arsutgifter': 'fund', 'utland': 'recipient'}
    all_assets = Asset.objects.filter(household=house)
    if page in kind_map: all_assets = all_assets.filter(kind=kind_map[page])
    for asset in all_assets:
        balance = services.savings_balance(asset, services.month_end(month)) if asset.kind == 'savings' else services.fund_balance(asset, services.month_end(month)) if asset.kind == 'fund' else asset.opening_ore
        plan = services.total(MonthPlan.objects.filter(asset=asset, month=month))
        remaining = max(asset.target_ore - balance, 0)
        months_left = (asset.target_date.year - month.year) * 12 + asset.target_date.month - month.month + 1 if asset.target_date else None
        movements = Entry.objects.filter(household=house, asset=asset, effective_date__range=(month, services.month_end(month)))
        assets.append({'row': asset, 'balance': balance, 'plan': plan, 'remaining': remaining, 'needed': (remaining + months_left - 1) // months_left if months_left and months_left > 0 else None, 'target_overdue': bool(months_left is not None and months_left <= 0 and remaining), 'projected_date': add_calendar_months(month, max((remaining + plan - 1) // plan - 1, 0)) if plan and remaining else None, 'deposits': services.total(movements.filter(kind='deposit')), 'withdrawals': services.total(movements.filter(kind='withdrawal')), 'paid': services.total(movements.filter(kind__in=['debt', 'fund'])), 'percent': min(max(balance * 100 // asset.target_ore, 0), 100) if asset.target_ore else 0})
    bills = BillOccurrence.objects.filter(household=house, due_date__lte=services.month_end(month)).select_related('template', 'asset').order_by('due_date')
    if page in ('oversikt', 'varsler'): bills = services.pending_bills(house, services.month_end(month)).order_by('due_date')
    previous = (month.replace(day=1) - __import__('datetime').timedelta(days=1)).replace(day=1)
    comparison = services.calculate(house, previous) if Entry.objects.filter(household=house, effective_date__range=(previous, services.month_end(previous))).exists() else None
    if comparison and month == services.month_start(timezone.localdate()):
        end_previous = previous.replace(day=min(timezone.localdate().day, services.month_end(previous).day))
        comparison['ordinary'] = services.ordinary_for_period(house, previous, end_previous)
    ctx = {'member': member, 'household': house, 'nav': NAV, 'page': page, 'title': TITLES[page], 'month': month, 'totals': totals, 'entries': entries, 'categories': categories, 'assets': assets, 'bills': bills, 'today': timezone.localdate(), 'comparison': comparison, 'updated': timezone.now(), 'kind_choices': Entry.KINDS, 'chart': chart, 'filter_form': filter_form, 'page_obj': page_obj, 'entry_query': entry_query, 'entry_scope_has_rows': entry_scope_has_rows, 'has_positive_category_spending': positive_spending > 0, 'category_count_total': category_count_total, 'category_matched_count': category_matched_count, 'category_q': category_q, 'category_status': category_status, 'category_show_all': category_show_all, 'category_expand_query': category_expand_query}
    if page == 'oversikt':
        ctx['spending_embedded'] = True
        ctx['spending_boot'] = {'initial_tab': 'spending', 'month': month.strftime('%Y-%m'), 'can_save': member.role == 'admin', 'urls': {'spending': reverse('spending_data'), 'planning': reverse('planning_data'), 'preview': reverse('planning_preview'), 'save': reverse('planning_save')}}
    if page == 'familie':
        ctx.update(members=Membership.objects.filter(household=house).select_related('user'), invitations=Invitation.objects.filter(household=house, accepted=False, revoked=False), invite_form=forms.EmailForm(), email_invitations_enabled=settings.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend' and bool(settings.EMAIL_HOST))
    if page == 'arsoversikt':
        services.prepare_month(house, date(month.year, 12, 1))
        cumulative = 0
        rows = []
        for n in range(1, 13):
            period = date(month.year, n, 1)
            result = services.calculate(house, period)
            has_data = Entry.objects.filter(household=house, effective_date__year=month.year, effective_date__month=n).exists()
            cumulative += result['cash']
            rows.append({'month': period, 'totals': result, 'has_data': has_data, 'cumulative': cumulative, 'budget': services.total(MonthPlan.objects.filter(household=house, month=period, category__isnull=False))})
        ctx['year_rows'] = rows
        year_categories = []
        for category in Category.objects.filter(household=house):
            periods = []
            for n in range(1, 13):
                period = date(month.year, n, 1)
                monthly = Entry.objects.filter(household=house, effective_date__range=(period, services.month_end(period)))
                spent = services.total(monthly.filter(category=category, kind__in=['expense', 'remittance'])) - services.total(monthly.filter(kind='refund', original__category=category, original__kind__in=['expense', 'remittance']))
                budget = services.total(MonthPlan.objects.filter(household=house, category=category, month=period))
                periods.append({'month': period, 'spent': spent, 'budget': budget})
            budget = sum(item['budget'] for item in periods)
            actual = sum(item['spent'] for item in periods)
            year_categories.append({'name': category.name, 'periods': periods, 'budget': budget, 'actual': actual, 'variance': budget - actual, 'ytd': sum(item['spent'] for item in periods if item['month'] <= timezone.localdate())})
        ctx['year_categories'] = year_categories
    if page == 'gjeld':
        debts = list(Asset.objects.filter(household=house, kind='debt', archived=False))
        for debt in debts:
            debt.opening_ore = services.estimated_debt_balance(debt, timezone.localdate())
        strategy = request.GET.get('strategy', 'avalanche')
        try: extra = max(int(Decimal(request.GET.get('extra', '0').replace(',', '.')) * 100), 0)
        except Exception: extra = 0
        if any(debt.opening_ore is None for debt in debts):
            ctx['projection'] = {'error': 'Mangler rente eller gyldig saldodato.'}
        else:
            ctx['projection'] = services.debt_projection(debts, strategy, extra) if debts else None
            baseline = services.debt_projection(debts, strategy, 0) if debts else None
            if ctx['projection'] and baseline and 'interest_ore' in baseline and 'interest_ore' in ctx['projection']:
                ctx['projection']['saved_interest'] = baseline['interest_ore'] - ctx['projection']['interest_ore']
                ctx['projection']['completion'] = add_calendar_months(timezone.localdate(), ctx['projection']['months'])
        ctx['extra'] = Decimal(extra) / 100
        ctx['strategy'] = strategy
        ctx['debt_plan_form'] = forms.DebtPlanForm(initial={'month': month, 'strategy': strategy})
    if page == 'utland':
        ytd_end = min(services.month_end(month), timezone.localdate())
        ytd_rows = Entry.objects.filter(household=house, effective_date__range=(date(month.year, 1, 1), ytd_end))
        ytd_amount = services.total(ytd_rows.filter(kind='remittance')) - services.total(ytd_rows.filter(kind='refund', original__kind='remittance'))
        ytd_income = services.total(ytd_rows.filter(kind='income', received=True))
        ctx.update(remittance_ytd=ytd_amount, remittance_share=round(ytd_amount * 100 / ytd_income, 1) if ytd_income else None, remittance_average=ytd_amount // max(ytd_end.month, 1), recipients=Asset.objects.filter(household=house, kind='recipient'))
    if page == 'import':
        try:
            package, binding = importing.load_private_source()
            importing.owner_membership(request.user, request.session.get('verified_email'), binding, auth_context=request.session)
            for batch in ImportBatch.objects.filter(household=house): importing.reconcile_batch(batch)
            ctx.update(import_batches=ImportBatch.objects.filter(household=house), import_records=ImportRecord.objects.filter(household=house).order_by('source_kind', 'source_id'), source_period=package.get('source_selected_month'), source_counts={name: len(package.get(name, [])) for name in importing.COLLECTIONS})
        except (OSError, ValueError): ctx['import_error'] = 'Privat kilde er ikke montert eller kan ikke leses.'
    if page == 'tilpass': ctx['preference_form'] = forms.PreferenceForm(initial={**house.modules, 'version': house.version})
    return render(request, 'budget/page.html', ctx)


EDIT_TYPES = {'entry': (Entry, forms.EntryForm, False, 'poster'), 'category': (Category, forms.CategoryForm, True, 'budsjett'), 'asset': (Asset, forms.AssetForm, True, 'sparing'), 'plan': (MonthPlan, forms.PlanForm, True, 'budsjett'), 'bill': (BillTemplate, forms.BillForm, False, 'regninger')}


@login_required
def edit_view(request, kind, row_id=None):
    if kind not in EDIT_TYPES: raise Http404
    member = get_member(request)
    if not member: return redirect('family_gate')
    model, form_type, admin, destination = EDIT_TYPES[kind]
    row = get_object_or_404(model, pk=row_id, household=member.household) if row_id else model(household=member.household, created_by=request.user)
    services.authorize(request.user, row if row_id else None, admin)
    kwargs = {'instance': row}
    if issubclass(form_type, forms.RowForm): kwargs['household'] = member.household
    initial = {'version': row.version if row_id else 0}
    if kind == 'asset' and row_id: initial.update(opening=Decimal(row.opening_ore) / 100, target=Decimal(row.target_ore) / 100, plan=Decimal(row.minimum_ore) / 100 if row.kind == 'debt' else None)
    if kind == 'asset':
        try: plan_month = date.fromisoformat(request.GET.get('plan_month', services.month_start(timezone.localdate()).isoformat()))
        except ValueError: raise Http404
        displayed_plan = MonthPlan.objects.filter(asset=row, month=plan_month).first() if row_id else None
        initial.update(plan_month=plan_month, displayed_plan_month=plan_month, plan_version=displayed_plan.version if displayed_plan else 0)
        if displayed_plan: initial['plan'] = Decimal(displayed_plan.amount_ore) / 100
    form = form_type(request.POST or None, initial=initial, **kwargs)
    status = 200
    if request.method == 'POST' and form.is_valid():
        try:
            row = form.save(commit=False)
            with transaction.atomic():
                if kind == 'asset' and form.cleaned_data.get('plan') is not None:
                    type(member.household).objects.select_for_update().get(pk=member.household_id)
                    existing_plan = MonthPlan.objects.select_for_update().filter(household=member.household, asset=row, month=form.cleaned_data['plan_month']).first() if row_id else None
                    if row_id and form.cleaned_data.get('displayed_plan_month') != form.cleaned_data['plan_month']:
                        raise services.Conflict('Last inn oppsettet for valgt planmåned før lagring; feltene dine er beholdt.')
                    if (existing_plan.version if existing_plan else 0) != (form.cleaned_data.get('plan_version') or 0):
                        raise services.Conflict('Månedsplanen er endret siden skjemaet ble åpnet; feltene dine er beholdt.')
                if kind == 'entry': services.save_entry(request.user, row, form.cleaned_data.get('version'))
                else:
                    if kind == 'asset' and row.kind == 'savings': services.validate_savings(row)
                    if kind == 'plan' and row.asset_id and row.asset.kind == 'savings' and row.month < services.month_start(timezone.localdate()):
                        raise ValidationError('Avsluttet spareplan kan ikke endres.')
                    services.save_row(request.user, row, form.cleaned_data.get('version'), admin)
                    if kind == 'asset' and row.kind in ('debt', 'fund', 'recipient'):
                        house = type(member.household).objects.select_for_update().get(pk=member.household_id)
                        house.modules = {**house.modules, {'debt': 'debt', 'fund': 'fund', 'recipient': 'remittance'}[row.kind]: True}
                        house.version += 1
                        house.save(update_fields=['modules', 'version'])
                    if kind == 'asset' and form.cleaned_data.get('plan') is not None:
                        plan = existing_plan or MonthPlan(household=member.household, created_by=request.user, asset=row, month=form.cleaned_data['plan_month'])
                        plan.amount_ore = int(form.cleaned_data['plan'] * 100)
                        services.save_row(request.user, plan, form.cleaned_data.get('plan_version') or 0, True)
            messages.success(request, 'Endringen er lagret.')
            return redirect('page', page=destination)
        except (ValidationError, PermissionDenied) as error:
            form.add_error(None, error_text(error))
            status = 409 if isinstance(error, services.Conflict) else 400
    return render(request, 'budget/form.html', {'form': form, 'title': 'Rediger' if row_id else 'Ny registrering', 'member': member, 'nav': NAV, 'page': destination, 'back': reverse('page', args=[destination])}, status=status)


@login_required
def delete_view(request, row_id):
    member = get_member(request)
    if not member: return redirect('family_gate')
    row = get_object_or_404(Entry, pk=row_id, household=member.household)
    services.authorize(request.user, row)
    error = None
    if request.method == 'POST':
        try:
            services.delete_entry(request.user, row.pk, int(request.POST.get('version', 0)))
            messages.success(request, 'Posten er slettet / betalingen er angret.')
            return redirect('page', page='poster')
        except (ValidationError, ValueError) as exc: error = error_text(exc)
    return render(request, 'budget/confirm.html', {'member': member, 'nav': NAV, 'row': row, 'title': 'Bekreft sletting / angre betaling', 'error': error})


@login_required
def pay_view(request, row_id):
    member = get_member(request)
    if not member: return redirect('family_gate')
    bill = get_object_or_404(BillOccurrence, pk=row_id, household=member.household)
    form = forms.PaymentForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            services.pay_bill(request.user, bill.pk, form.cleaned_data['date'], form.cleaned_data['key'])
            messages.success(request, 'Betalingen er registrert én gang. Appen har ikke flyttet penger.')
            return redirect('page', page='regninger')
        except ValidationError as error: form.add_error(None, error)
    return render(request, 'budget/form.html', {'form': form, 'title': f'Merk {bill.name} som betalt', 'explanation': 'Dette registrerer faktisk betaling i budsjettet. Appen utfører ingen bankbetaling.', 'member': member, 'nav': NAV, 'back': reverse('page', args=['regninger'])})


@login_required
@require_POST
def preferences_view(request):
    member = services.authorize(request.user, admin=True)
    form = forms.PreferenceForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            house = type(member.household).objects.select_for_update().get(pk=member.household_id)
            if house.version != form.cleaned_data['version']: return HttpResponse('Samtidig endring. Last inn på nytt.', status=409)
            house.modules = {k: v for k, v in form.cleaned_data.items() if k not in ('version', 'confirm')}
            house.version += 1
            house.save()
        messages.success(request, 'Familiens visningsvalg er lagret. Forpliktelser og historikk er bevart.')
        return redirect('page', page='tilpass')
    return render(request, 'budget/form.html', {'form': form, 'title': 'Tilpass appen', 'member': member, 'nav': NAV}, status=400)


@login_required
@require_POST
def debt_plan_view(request):
    member = services.authorize(request.user, admin=True)
    form = forms.DebtPlanForm(request.POST)
    if form.is_valid():
        try:
            services.allocate_debt_plan(request.user, form.cleaned_data['month'], form.cleaned_data['strategy'], int((form.cleaned_data['extra'] or 0) * 100))
            messages.success(request, 'Månedsplanens kvoter per gjeld er lagret.')
            return redirect('page', page='gjeld')
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, 'budget/form.html', {'form': form, 'title': 'Fordel gjeldsplan', 'member': member, 'nav': NAV}, status=400)


@login_required
@require_POST
def invite_view(request):
    member = services.authorize(request.user, admin=True)
    form = forms.EmailForm(request.POST)
    if form.is_valid():
        try:
            identity.invite(request.user, form.cleaned_data['email'], request.build_absolute_uri('/').rstrip('/'))
            messages.success(request, 'Invitasjonen er sendt og gjelder i 7 dager.')
        except Exception: messages.error(request, 'Invitasjonen kunne ikke sendes.')
    return redirect('page', page='familie')


@login_required
@require_POST
def revoke_view(request, row_id):
    member = services.authorize(request.user, admin=True)
    row = get_object_or_404(Invitation, pk=row_id, household=member.household)
    row.revoked = True
    row.save(update_fields=['revoked'])
    return redirect('page', page='familie')


@login_required
@require_POST
def import_view(request):
    package, binding = importing.load_private_source()
    try:
        batch = importing.apply_import(request.user, request.session.get('verified_email'), package, binding, auth_context=request.session)
        messages.success(request, f'Kilden er bevart i familien. {batch.reconciliation.get("needs_review", 0)} poster trenger avklaring.')
    except ValidationError as exc: messages.error(request, error_text(exc))
    period = package.get('source_selected_month')
    if isinstance(period, str):
        try:
            date.fromisoformat(period + '-01')
            return redirect(reverse('page', args=['import']) + '?month=' + period)
        except ValueError: pass
    return redirect('page', page='import')


@login_required
def resolve_import(request, row_id):
    member = services.authorize(request.user, admin=True)
    record = get_object_or_404(ImportRecord, pk=row_id, household=member.household)
    package, binding = importing.load_private_source()
    importing.owner_membership(request.user, request.session.get('verified_email'), binding, auth_context=request.session)
    if record.status == 'confirmed': return redirect('page', page='import')
    # Avklaring krever eksplisitt validerte felt; råkilden endres aldri.
    source = record.raw
    raw = source.get('raw', {})
    collection = record.source_kind
    if collection == 'categories':
        row = MonthPlan(household=member.household, created_by=request.user, category_id=record.target_id)
        form = forms.PlanForm(request.POST or None, household=member.household, instance=row, initial={'category': record.target_id, 'amount': source_money(source.get('monthly_budget_ore'))})
    elif collection in ('savings_goals', 'debts', 'annual_funds', 'recipients'):
        row = get_object_or_404(Asset, pk=record.target_id, household=member.household) if record.target_id else Asset(household=member.household, created_by=request.user)
        asset_kind = {'savings_goals': 'savings', 'debts': 'debt', 'annual_funds': 'fund', 'recipients': 'recipient'}[collection]
        form = forms.AssetForm(request.POST or None, instance=row, initial={'name': raw.get('name'), 'kind': asset_kind, 'opening': source_money(source.get('opening_balance_ore', source.get('reference_balance_ore', source.get('opening_allocation_ore')))), 'target': source_money(source.get('target_ore', source.get('annual_amount_ore'))), 'opening_date': source.get('opening_balance_effective_date') or source.get('reference_date') or source.get('opening_allocation_effective_date'), 'target_date': source.get('target_date'), 'plan': source_money(source.get('monthly_plan_ore', source.get('monthly_minimum_ore'))), 'plan_month': None, 'version': row.version if record.target_id else 0})
        if asset_kind != 'recipient': form.fields['opening'].required = True
        if asset_kind in ('savings', 'fund'): form.fields['target'].required = True
        if asset_kind in ('savings', 'debt'): form.fields['plan'].required = True
    elif collection == 'transactions':
        row = Entry(household=member.household, created_by=request.user)
        form = forms.EntryForm(request.POST or None, household=member.household, instance=row, initial={'description': raw.get('description'), 'amount': source_money(abs(source['amount_nok_ore'])) if source.get('amount_nok_ore') is not None else None, 'effective_date': source.get('effective_date')})
    else:
        form = forms.SourceConfirmationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                record = ImportRecord.objects.select_for_update().get(pk=record.pk, household=member.household)
                if record.status == 'confirmed': return redirect('page', page='import')
                if collection == 'transactions':
                    target = services.save_entry(request.user, form.save(commit=False))
                elif collection == 'categories':
                    target = services.save_row(request.user, form.save(commit=False), admin=True)
                elif collection in ('savings_goals', 'debts', 'annual_funds', 'recipients'):
                    target = form.save(commit=False)
                    if target.kind == 'savings': services.validate_savings(target)
                    services.save_row(request.user, target, form.cleaned_data.get('version'), admin=True)
                    if form.cleaned_data.get('plan') is not None:
                        # Historisk plan må velges separat; ingen udatert kildeplan gjøres historisk.
                        plan = MonthPlan(household=member.household, created_by=request.user, month=form.cleaned_data['plan_month'], asset=target, amount_ore=int(form.cleaned_data['plan'] * 100))
                        services.save_row(request.user, plan, admin=True)
                else:
                    target = None
                record.target_id, record.status = target.pk if target else None, 'confirmed'
                if isinstance(target, Entry): record.approved_decision = importing.decision_snapshot(target)
                record.save(update_fields=['target_id', 'status', 'approved_decision'])
                importing.reconcile_batch(record.batch)
            return redirect('page', page='import')
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, 'budget/form.html', {'form': form, 'title': 'Avklar kildepost', 'source_record': record, 'member': member, 'nav': NAV})


def manifest_view(request):
    return JsonResponse({'name': 'Familieblikk', 'short_name': 'Familieblikk', 'lang': 'nb', 'start_url': '/', 'scope': '/', 'display': 'standalone', 'background_color': '#F5F7F4', 'theme_color': '#17644B', 'icons': [{'src': '/static/budget/icon.svg', 'sizes': 'any', 'type': 'image/svg+xml', 'purpose': 'any maskable'}]}, content_type='application/manifest+json')


def worker_view(request):
    from pathlib import Path
    import hashlib
    root = Path(__file__).parent
    public_files = [root / 'static/budget' / name for name in ['app.css', 'app.js', 'icon.svg', 'sw.js']] + [root / 'templates/budget/offline.html']
    version = hashlib.sha256(b''.join(file.read_bytes() for file in public_files)).hexdigest()[:20]
    source = (root / 'static/budget/sw.js').read_text(encoding='utf-8').replace('__PUBLIC_VERSION__', version)
    response = HttpResponse(source, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response


def public_asset(request, name):
    from pathlib import Path
    from django.http import FileResponse
    allowed = {'app.css': 'text/css', 'app.js': 'application/javascript', 'icon.svg': 'image/svg+xml', 'calendar.css': 'text/css', 'calendar.js': 'application/javascript', 'spending.css': 'text/css', 'spending.js': 'application/javascript'}
    if name not in allowed: raise Http404
    response = FileResponse((Path(__file__).parent / 'static/budget' / name).open('rb'), content_type=allowed[name])
    response['Cache-Control'] = 'public, max-age=0, must-revalidate'
    return response


def offline_view(request): return render(request, 'budget/offline.html')


def help_view(request, topic):
    texts = {'personvern': 'Budsjettet er privat for familien. Opplysninger lagres på tjenestens database. Kontakt driftsansvarlig for innsyn, retting og sletting. Ikke legg inn opplysninger du ikke trenger i budsjettet.', 'hjelp': 'Familieblikk registrerer familiens budsjett og flytter ingen penger. Lagring krever nett. Installer via nettleserens meny. På iPhone: Del → Legg til på Hjem-skjerm. Kontakt familiens administrator ved tilgangsproblemer.'}
    if topic not in texts: raise Http404
    return render(request, 'budget/info.html', {'title': 'Personvern' if topic == 'personvern' else 'Hjelp og kontakt', 'text': texts[topic]})


def forbidden_view(request, exception=None):
    return render(request, 'budget/error.html', {'title': 'Begrenset tilgang', 'text': 'Du har ikke rettighet til denne handlingen. Bare oppretteren eller en administrator kan endre posten.'}, status=403)


def not_found_view(request, exception=None):
    return render(request, 'budget/error.html', {'title': 'Fant ikke siden', 'text': 'Posten eller siden finnes ikke, eller er ikke tilgjengelig i familien din.'}, status=404)


def server_error_view(request):
    return render(request, 'budget/error.html', {'title': 'Kunne ikke hente opplysningene', 'text': 'Prøv igjen om litt. Ingen lagring er bekreftet.'}, status=500)
