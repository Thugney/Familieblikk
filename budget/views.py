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
from . import access, forms, identity, importing, services
from .models import Asset, BillOccurrence, BillTemplate, Category, Entry, ImportBatch, ImportRecord, Invitation, Membership, MonthPlan


NAV = [('oversikt', 'Oversikt'), ('poster', 'Poster'), ('budsjett', 'Budsjett'), ('sparing', 'Sparing'), ('kalender', 'Kalender'), ('mer', 'Mer')]
TITLES = dict(NAV + [('dokumenter', 'Skann kvittering'), ('handlelister', 'Handlelister'), ('kategorier', 'Kategorier og rammer'), ('regninger', 'Regninger'), ('gjeld', 'Gjeld'), ('arsutgifter', 'Årsutgifter'), ('utland', 'Sendt utenlands'), ('arsoversikt', 'Årsoversikt'), ('familie', 'Familie og innstillinger'), ('tilpass', 'Tilpass appen'), ('import', 'Familiens kildeimport'), ('varsler', 'Varsler')])


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
    from .push_services import disable_session
    disable_session(request)
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
    member = get_member(request)
    if not member: return redirect('family_gate')
    access.require_page(member, page, matrix=page == 'arsoversikt' and request.GET.get('view') == 'matrix')
    if page == 'oversikt' and not access.complete_finance(member):
        return render(request, 'budget/restricted_home.html', {
            'member': member, 'household': member.household, 'nav': NAV, 'page': page,
            'title': 'Din startside', 'month': selected_month(request),
            'available_pages': [(key, TITLES[key]) for key in access.PAGES if access.visible_page(member, key)],
        })
    if page == 'budsjett' or page == 'arsoversikt' and request.GET.get('view') != 'matrix':
        from .spending_views import render_shell
        return render_shell(request, 'annual' if page == 'arsoversikt' else 'spending')
    if page not in TITLES: raise Http404
    member = get_member(request)
    if not member: return redirect('family_gate')
    month = selected_month(request)
    # The explicit annual matrix is a read-only report, including future months.
    if page != 'arsoversikt': services.prepare_month(member.household, month)
    house = member.household
    full_finance = access.complete_finance(member)
    totals = services.calculate(house, month) if full_finance else {}
    month_entries = access.safe_rows(member, Entry.objects.filter(active=True, household=house, effective_date__range=(month, services.month_end(month))))
    if full_finance:
        totals['gross_deposits'] = services.total(month_entries.filter(kind='deposit'))
        totals['planned_savings'] = services.total(MonthPlan.objects.filter(household=house, month=month, asset__kind='savings'))
    chart = []
    for offset in ([-2, -1, 0] if full_finance else []):
        period = add_calendar_months(month, offset)
        if period is None: continue
        end = services.month_end(period)
        if month == services.month_start(timezone.localdate()): end = period.replace(day=min(timezone.localdate().day, end.day))
        has_data = Entry.objects.filter(active=True, household=house, effective_date__range=(period, end)).exists()
        amount = services.ordinary_for_period(house, period, end)
        chart.append({'month': period, 'amount': amount, 'has_data': has_data, 'current': offset == 0})
    ceiling = max([item['amount'] for item in chart] + [1])
    for item in chart: item['height'] = max(item['amount'] * 100 // ceiling, 0)
    # Listefiltre påvirker aldri månedens regnskapsgrunnlag eller andre seksjoner.
    entries = month_entries.select_related('category', 'asset', 'created_by').order_by('-effective_date', '-sequence', '-pk')
    filter_form, page_obj = None, None
    entry_query = ''
    entry_scope_has_rows = False
    history_kinds = {'sparing': ('deposit', 'withdrawal'), 'gjeld': ('debt',), 'arsutgifter': ('fund',)}
    module_history = not access.allows(member, 'budget') and page in (*history_kinds, 'regninger')
    if page in ('poster', 'utland') or module_history:
        if page == 'utland': entries = entries.filter(Q(kind='remittance') | Q(kind='refund', original__kind='remittance'))
        if page in history_kinds:
            entries = entries.filter(Q(kind__in=history_kinds[page]) | Q(kind='refund', original__kind__in=history_kinds[page]))
        if page == 'regninger':
            entries = entries.filter(Q(occurrence__isnull=False) | Q(kind='refund', original__occurrence__isnull=False))
        entry_scope_has_rows = entries.exists()
        filter_form = forms.EntryFilterForm(request.GET, household=house, month=month, remittances_only=page == 'utland')
        filter_form.fields['category'].queryset = access.category_choices(member, filter_form.fields['category'].queryset)
        if module_history:
            # Choices describe this module's permitted history only.
            filter_form.fields['category'].queryset = filter_form.fields['category'].queryset.filter(
                Q(pk__in=entries.values('category_id')) | Q(pk__in=entries.values('original__category_id')))
            filter_form.fields.pop('status', None)
            if page in history_kinds:
                filter_form.fields['kind'].choices = [(key, label) for key, label in filter_form.fields['kind'].choices
                                                     if not key or key == 'refund' or key in history_kinds[page]]
        filter_form.fields['kind'].choices = [(key, label) for key, label in filter_form.fields['kind'].choices
                                             if not key or key == 'refund' or access.allows(member, access.KINDS.get(key))
                                             or module_history and page == 'regninger' and key == 'expense']
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
    plans_by_category = {plan.category_id: plan for plan in access.safe_rows(member, MonthPlan.objects.filter(household=house, month=month, category__isnull=False))}
    categories = []
    for category in (Category.objects.filter(household=house).order_by('name', 'id') if access.allows(member, 'budget') else []):
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
    all_assets = access.safe_rows(member, Asset.objects.filter(household=house))
    if page in kind_map: all_assets = all_assets.filter(kind=kind_map[page])
    for asset in all_assets:
        composite_hidden = asset.kind == 'fund' and not access.allows(member, 'bills')
        balance = None if composite_hidden else services.savings_balance(asset, services.month_end(month)) if asset.kind == 'savings' else services.fund_balance(asset, services.month_end(month)) if asset.kind == 'fund' else asset.opening_ore
        plan = services.total(MonthPlan.objects.filter(asset=asset, month=month))
        remaining = max(asset.target_ore - balance, 0) if balance is not None else None
        months_left = (asset.target_date.year - month.year) * 12 + asset.target_date.month - month.month + 1 if asset.target_date else None
        movements = access.safe_rows(member, Entry.objects.filter(active=True, household=house, asset=asset, effective_date__range=(month, services.month_end(month))))
        assets.append({'row': asset, 'balance': balance, 'composite_hidden': composite_hidden, 'plan': plan, 'remaining': remaining, 'needed': (remaining + months_left - 1) // months_left if remaining is not None and months_left and months_left > 0 else None, 'target_overdue': bool(months_left is not None and months_left <= 0 and remaining), 'projected_date': add_calendar_months(month, max((remaining + plan - 1) // plan - 1, 0)) if plan and remaining else None, 'deposits': services.total(movements.filter(kind='deposit')), 'withdrawals': services.total(movements.filter(kind='withdrawal')), 'paid': services.total(movements.filter(kind__in=['debt', 'fund'])), 'percent': min(max(balance * 100 // asset.target_ore, 0), 100) if balance is not None and asset.target_ore else 0})
    bills = BillOccurrence.objects.filter(household=house, due_date__lte=services.month_end(month)).select_related('template', 'asset').order_by('due_date')
    if page in ('oversikt', 'varsler'): bills = services.pending_bills(house, services.month_end(month)).order_by('due_date')
    bills = access.safe_rows(member, bills)
    previous = (month.replace(day=1) - __import__('datetime').timedelta(days=1)).replace(day=1)
    comparison = services.calculate(house, previous) if full_finance and Entry.objects.filter(active=True, household=house, effective_date__range=(previous, services.month_end(previous))).exists() else None
    if comparison and month == services.month_start(timezone.localdate()):
        end_previous = previous.replace(day=min(timezone.localdate().day, services.month_end(previous).day))
        comparison['ordinary'] = services.ordinary_for_period(house, previous, end_previous)
    ctx = {'member': member, 'household': house, 'nav': NAV, 'page': page, 'title': TITLES[page], 'month': month, 'totals': totals, 'entries': entries, 'categories': categories, 'assets': assets, 'bills': bills, 'today': timezone.localdate(), 'comparison': comparison, 'updated': timezone.now(), 'kind_choices': Entry.KINDS, 'chart': chart, 'filter_form': filter_form, 'page_obj': page_obj, 'entry_query': entry_query, 'entry_scope_has_rows': entry_scope_has_rows, 'has_positive_category_spending': positive_spending > 0, 'category_count_total': category_count_total, 'category_matched_count': category_matched_count, 'category_q': category_q, 'category_status': category_status, 'category_show_all': category_show_all, 'category_expand_query': category_expand_query}
    if page == 'oversikt':
        ctx['spending_embedded'] = True
        ctx['spending_boot'] = {'initial_tab': 'spending', 'month': month.strftime('%Y-%m'), 'can_save': member.role == 'admin', 'urls': {'spending': reverse('spending_data'), 'planning': reverse('planning_data'), 'preview': reverse('planning_preview'), 'save': reverse('planning_save')}}
    if page == 'familie':
        ctx.update(members=Membership.objects.filter(household=house).select_related('user'), invitations=Invitation.objects.filter(household=house, accepted=False, revoked=False), invite_form=forms.EmailForm(), email_invitations_enabled=settings.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend' and bool(settings.EMAIL_HOST))
    if page == 'varsler':
        from .models import CalendarNotification
        ctx['calendar_notifications'] = CalendarNotification.objects.filter(household=house, recipient=request.user).order_by('-created_at')[:100]
    if page == 'arsoversikt':
        # Project existing anchors without materializing future plans or bills.
        year_entries = list(Entry.objects.filter(active=True, household=house, effective_date__year=month.year).select_related('original'))
        year_plans = list(MonthPlan.objects.filter(household=house).order_by('month'))
        year_category_rows = list(Category.objects.filter(household=house))
        year_asset_rows = list(Asset.objects.filter(household=house))
        plan_groups = {}
        for plan in year_plans: plan_groups.setdefault((plan.category_id, plan.asset_id), []).append(plan)
        # prepare_month supplies this annual anchor when no explicit fund plan exists.
        # Project it in memory only, including December's remainder.
        for asset in year_asset_rows:
            group = plan_groups.setdefault((None, asset.pk), [])
            if asset.kind == 'fund' and asset.target_ore and not any(not p.derived for p in group):
                effective = services.month_start(asset.opening_date)
                amount = asset.target_ore // 12 + (asset.target_ore % 12 if effective.month == 12 else 0)
                group.append(MonthPlan(asset_id=asset.pk, month=effective, amount_ore=amount, annual_total_ore=asset.target_ore))
                group.sort(key=lambda p: p.month)
        archived_targets = {(c.pk, None) for c in year_category_rows if c.archived} | {(None, a.pk) for a in year_asset_rows if a.archived}
        def effective_amount(period, category_id=None, asset_id=None):
            applicable = [p for p in plan_groups.get((category_id, asset_id), []) if p.month <= period]
            exact = next((p for p in applicable if p.month == period), None)
            if not exact and (category_id, asset_id) in archived_targets and period > services.month_start(timezone.localdate()): return 0
            if exact and (not exact.derived or period < services.month_start(timezone.localdate())): return exact.amount_ore
            anchors = [p for p in applicable if not p.derived]
            return services.plan_amount(anchors[-1], period) if anchors else exact.amount_ore if exact else 0
        category_spent, category_ytd = {}, {}
        for entry in year_entries:
            category_id, amount = entry.category_id, entry.amount_ore
            if entry.kind == 'refund' and entry.original and entry.original.kind in ('expense', 'remittance'):
                category_id, amount = entry.original.category_id, -amount
            elif entry.kind not in ('expense', 'remittance'): continue
            key = (category_id, entry.effective_date.month)
            category_spent[key] = category_spent.get(key, 0) + amount
            if entry.effective_date <= timezone.localdate(): category_ytd[category_id] = category_ytd.get(category_id, 0) + amount
        asset_ids = {a.pk for a in year_asset_rows}
        cumulative, rows = 0, []
        for n in range(1, 13):
            period = date(month.year, n, 1)
            projected = {asset_id: effective_amount(period, asset_id=asset_id) for asset_id in asset_ids}
            result = services.calculate(house, period, projected_asset_plans=projected)
            budget = sum(effective_amount(period, category_id=c.pk) for c in year_category_rows)
            has_data = any(entry.effective_date.month == n for entry in year_entries)
            has_values = has_data or budget != 0 or any(result[key] != 0 for key in ('bills', 'savings', 'debt', 'funds'))
            cumulative += result['cash']
            rows.append({'month': period, 'totals': result, 'has_data': has_data, 'has_values': has_values, 'cumulative': cumulative, 'budget': budget})
        ctx['year_rows'] = rows
        year_categories = []
        for category in year_category_rows:
            periods = []
            for n in range(1, 13):
                period = date(month.year, n, 1)
                periods.append({'month': period, 'spent': category_spent.get((category.pk, n), 0), 'budget': effective_amount(period, category_id=category.pk)})
            budget, actual = sum(item['budget'] for item in periods), sum(item['spent'] for item in periods)
            year_categories.append({'name': category.name, 'periods': periods, 'budget': budget, 'actual': actual, 'variance': budget - actual, 'ytd': category_ytd.get(category.pk, 0)})
        ctx['year_categories'] = year_categories
    if page == 'gjeld':
        debts = list(Asset.objects.filter(household=house, kind='debt', archived=False))
        for debt in debts:
            debt.opening_ore = services.estimated_debt_balance(debt, timezone.localdate()) if access.allows(member, 'bills') else None
        strategy = request.GET.get('strategy', 'avalanche')
        if strategy not in ('avalanche', 'snowball'): strategy = 'avalanche'
        try: extra = max(int(Decimal(request.GET.get('extra', '0').replace(',', '.')) * 100), 0)
        except Exception: extra = 0
        if not access.allows(member, 'bills'):
            ctx['projection'] = {'error': 'Nedbetalingsanslag krever også regningstilgang. Skjulte betalinger og summer er utelatt.'}
        elif any(debt.opening_ore is None for debt in debts):
            ctx['projection'] = {'error': 'Mangler rente eller gyldig saldodato.'}
        else:
            ctx['projection'] = services.debt_projection(debts, strategy, extra) if debts else None
            baseline = services.debt_projection(debts, strategy, 0) if debts else None
            if ctx['projection'] and baseline and 'interest_ore' in baseline and 'interest_ore' in ctx['projection']:
                ctx['projection']['saved_interest'] = baseline['interest_ore'] - ctx['projection']['interest_ore']
                ctx['projection']['completion'] = add_calendar_months(timezone.localdate(), ctx['projection']['months'])
        ctx['extra'] = Decimal(extra) / 100
        ctx['strategy'] = strategy
        ctx['debt_plan_form'] = forms.DebtPlanForm(initial={'month': month, 'strategy': strategy, 'extra': Decimal(extra) / 100})
    if page == 'utland':
        ytd_end = min(services.month_end(month), timezone.localdate())
        ytd_rows = access.safe_rows(member, Entry.objects.filter(active=True, household=house, effective_date__range=(date(month.year, 1, 1), ytd_end)))
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
    ctx['restricted_selection'] = not full_finance
    ctx['module_history'] = module_history
    ctx['history_entry_kind'] = {'sparing': 'deposit', 'gjeld': 'debt', 'arsutgifter': 'fund', 'utland': 'remittance'}.get(page, '')
    ctx['history_can_create'] = page != 'regninger' and (page != 'arsutgifter' or access.allows(member, 'bills'))
    ctx['restricted_bills_selection'] = not (access.allows(member, 'debt') and access.allows(member, 'fund'))
    ctx['kind_choices'] = [(key, label) for key, label in Entry.KINDS if key == 'refund' or access.allows(member, access.KINDS.get(key))]
    if ctx.get('spending_boot'):
        ctx['spending_boot'].update(can_plan=full_finance, can_annual=access.allows(member, 'annual'))
    return render(request, 'budget/page.html', ctx)


EDIT_TYPES = {'entry': (Entry, forms.EntryForm, False, 'poster'), 'category': (Category, forms.CategoryForm, True, 'budsjett'), 'asset': (Asset, forms.AssetForm, True, 'sparing'), 'plan': (MonthPlan, forms.PlanForm, True, 'budsjett'), 'bill': (BillTemplate, forms.BillForm, False, 'regninger')}
ASSET_PAGES = {'savings': 'sparing', 'debt': 'gjeld', 'fund': 'arsutgifter', 'recipient': 'utland'}


def debt_context(query):
    strategy = query.get('strategy')
    if strategy not in ('avalanche', 'snowball'): return {}
    try:
        extra = Decimal(query.get('extra', '0').replace(',', '.'))
        if not extra.is_finite() or extra < 0 or extra > Decimal('999999999999.99'): return {'strategy': strategy}
        return {'strategy': strategy, 'extra': format(extra, '.2f')}
    except (ValueError, ArithmeticError, AttributeError): return {'strategy': strategy}


def module_url(page, month, query=None):
    return reverse('page', args=[page]) + '?' + urlencode({'month': month.strftime('%Y-%m'), **(debt_context(query) if page == 'gjeld' and query is not None else {})})


@login_required
def edit_view(request, kind, row_id=None):
    if kind == 'bill' and row_id:
        return redirect('correction', kind='series', row_id=row_id)
    if kind not in EDIT_TYPES: raise Http404
    member = get_member(request)
    if not member: return redirect('family_gate')
    model, form_type, admin, destination = EDIT_TYPES[kind]
    month = selected_month(request)
    allowed_returns = {'entry': ('oversikt', 'poster', 'sparing', 'gjeld', 'arsutgifter', 'utland', 'regninger'), 'asset': tuple(ASSET_PAGES.values()), 'bill': ('regninger', 'arsutgifter', 'gjeld'), 'plan': ('budsjett', 'kategorier', 'sparing', 'gjeld', 'arsutgifter'), 'category': ('budsjett', 'kategorier')}
    requested_return = request.GET.get('return_to')
    if requested_return in allowed_returns[kind]: destination = requested_return
    row = get_object_or_404(model, pk=row_id, household=member.household) if row_id else model(household=member.household, created_by=request.user)
    services.authorize(request.user, row if row_id else None, admin)
    if kind == 'bill': access.require(member, {'bills'})
    if kind == 'category': access.require(member, {'budget'})
    if kind == 'entry' and not any(access.allows(member, module) for module in access.FINANCE):
        access.require(member, {'budget'})
    if request.method == 'POST':
        posted_kind = request.POST.get('kind')
        if kind == 'entry' and posted_kind in access.KINDS:
            access.require(member, {access.KINDS[posted_kind]})
            if posted_kind == 'fund': access.require(member, {'bills'})
        if kind == 'asset' and posted_kind in access.ASSETS:
            access.require(member, {access.ASSETS[posted_kind]})
        if kind == 'bill' and request.POST.get('accounting_class') in ('debt', 'fund'):
            access.require(member, {request.POST['accounting_class']})
        for field, related_model in (('asset', Asset), ('original', Entry)):
            if kind in ('entry', 'bill', 'plan') and request.POST.get(field):
                try: related_id = uuid.UUID(request.POST[field])
                except (ValueError, TypeError): raise Http404
                related = get_object_or_404(related_model, pk=related_id, household=member.household)
                access.require_row(member, related)
                if kind == 'entry':
                    access.require_write_row(member, related)
                    if isinstance(related, Asset) and related.kind == 'fund': access.require(member, {'bills'})
    kwargs = {'instance': row}
    if issubclass(form_type, forms.RowForm): kwargs['household'] = member.household
    initial = {'version': row.version if row_id else 0}
    if not row_id:
        # URL hints supply GET defaults only; submitted values use normal validation.
        if kind == 'entry' and request.GET.get('entry_kind') in dict(Entry.KINDS): initial['kind'] = request.GET['entry_kind']
        if kind == 'entry' and request.GET.get('original'):
            try: original_id = uuid.UUID(request.GET['original'])
            except ValueError: raise Http404
            original = get_object_or_404(Entry, pk=original_id, household=member.household, active=True, kind__in=['expense', 'debt', 'fund', 'remittance'])
            access.require_write_row(member, original)
            initial.update(kind='refund', original=original)
        if kind == 'asset' and request.GET.get('asset_kind') in ASSET_PAGES: initial['kind'] = request.GET['asset_kind']
        if kind == 'bill' and request.GET.get('accounting_class') in ('ordinary', 'debt', 'fund'): initial['accounting_class'] = request.GET['accounting_class']
        if kind == 'bill' and request.GET.get('once') == '1': initial['monthly'] = False
        if kind in ('entry', 'bill', 'plan') and request.GET.get('asset'):
            try: asset_id = uuid.UUID(request.GET['asset'])
            except ValueError: raise Http404
            initial['asset'] = get_object_or_404(Asset, household=member.household, pk=asset_id)
            access.require_row(member, initial['asset'])
            if kind == 'entry' and initial['asset'].kind == 'fund': access.require(member, {'bills'})
        if 'month' in request.GET:
            if kind == 'entry': initial['effective_date'] = month
            if kind == 'plan': initial['month'] = month
            if kind == 'bill': initial['first_due'] = month
    if kind == 'asset' and row_id: initial.update(opening=Decimal(row.opening_ore) / 100, target=Decimal(row.target_ore) / 100, plan=Decimal(row.minimum_ore) / 100 if row.kind == 'debt' else None)
    if kind == 'asset':
        if row_id: destination = ASSET_PAGES[row.kind]
        elif initial.get('kind'): destination = ASSET_PAGES[initial['kind']]
        try: plan_month = date.fromisoformat(request.GET.get('plan_month', month.isoformat()))
        except ValueError: raise Http404
        if plan_month.day != 1: raise Http404
        displayed_plan = MonthPlan.objects.filter(asset=row, month=plan_month).first() if row_id else None
        initial.update(plan_month=plan_month, displayed_plan_month=plan_month, plan_version=displayed_plan.version if displayed_plan else 0)
        if displayed_plan: initial['plan'] = Decimal(displayed_plan.amount_ore) / 100
    recovering = kind == 'entry' and row_id and request.method == 'POST' and request.POST.get('refresh_version') == '1'
    submitted = request.POST.copy() if request.method == 'POST' else None
    if recovering:
        submitted['version'], submitted['command_key'] = str(row.version), str(uuid.uuid4())
        submitted.pop('confirmation', None)
    form = form_type(submitted, initial=initial, **kwargs)
    access.restrict_form(member, form)
    if kind == 'entry' and not row_id:
        if initial.get('kind'):
            if initial['kind'] != 'refund': access.require(member, {access.KINDS.get(initial['kind'])})
            if initial['kind'] == 'fund': access.require(member, {'bills'})
        elif not access.allows(member, 'budget'):
            form.initial['kind'] = next((key for key, _ in form.fields['kind'].choices if key != 'refund'), 'refund')
    if kind == 'asset' and not row_id and initial.get('kind'):
        access.require(member, {access.ASSETS[initial['kind']]})
    if kind == 'bill' and not row_id and initial.get('accounting_class') in ('debt', 'fund'):
        access.require(member, {initial['accounting_class']})
    if not access.can_page(member, destination):
        if kind == 'entry':
            probe = row if row_id else Entry(kind=form.initial.get('kind', 'income'))
            destination = access.entry_page(member, probe)
        else: destination = 'oversikt'
    status = 200
    if request.method == 'POST' and form.is_valid() and request.POST.get('edit_draft') != '1' and not recovering:
        try:
            row = form.save(commit=False)
            if kind == 'entry' and row_id:
                from .correction_views import entry_edit_preview
                preview = entry_edit_preview(request, member, form, row)
                if preview is not None:
                    return render(request, 'budget/entry_confirmation.html', {'form': form, 'preview': preview, 'title': 'Bekreft postretting', 'member': member, 'nav': NAV, 'back': module_url(destination, month, request.GET)})
            with transaction.atomic():
                if kind == 'asset' and form.cleaned_data.get('plan') is not None:
                    type(member.household).objects.select_for_update().get(pk=member.household_id)
                    existing_plan = MonthPlan.objects.select_for_update().filter(household=member.household, asset=row, month=form.cleaned_data['plan_month']).first() if row_id else None
                    if row_id and form.cleaned_data.get('displayed_plan_month') != form.cleaned_data['plan_month']:
                        raise services.Conflict('Last inn oppsettet for valgt planmåned før lagring; feltene dine er beholdt.')
                    if (existing_plan.version if existing_plan else 0) != (form.cleaned_data.get('plan_version') or 0):
                        raise services.Conflict('Månedsplanen er endret siden skjemaet ble åpnet; feltene dine er beholdt.')
                if kind == 'entry': services.save_entry(request.user, row, form.cleaned_data.get('version'), command_key=form.cleaned_data.get('command_key'))
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
                        # Saving a fund can itself create/update its annual anchor.
                        # The displayed version was checked above under the same lock.
                        plan = MonthPlan.objects.filter(household=member.household, asset=row, month=form.cleaned_data['plan_month']).first()
                        plan_version = plan.version if plan else 0
                        plan = plan or MonthPlan(household=member.household, created_by=request.user, asset=row, month=form.cleaned_data['plan_month'])
                        plan.amount_ore = int(form.cleaned_data['plan'] * 100)
                        services.save_row(request.user, plan, plan_version, True)
            messages.success(request, 'Endringen er lagret.')
            if kind == 'asset': destination = ASSET_PAGES[row.kind]
            if kind == 'entry' and not access.can_page(member, destination): destination = access.entry_page(member, row)
            if kind == 'entry' and destination == 'oversikt' and not access.allows(member, 'budget'): destination = access.entry_page(member, row)
            return redirect(module_url(destination, month, request.GET)) if 'month' in request.GET else redirect('page', page=destination)
        except ValidationError as error:
            form.add_error(None, error_text(error))
            status = 409 if isinstance(error, services.Conflict) else 400
    return render(request, 'budget/form.html', {'form': form, 'title': 'Rediger' if row_id else 'Ny registrering', 'recoverable':kind == 'entry' and status == 409, 'recovered':recovering, 'member': member, 'nav': NAV, 'month': month, 'page': destination, 'back': module_url(destination, month, request.GET)}, status=status)


@login_required
def delete_view(request, row_id):
    from .correction_views import correction_view
    return correction_view(request, 'entry', row_id)



@login_required
def pay_view(request, row_id):
    member = get_member(request)
    if not member: return redirect('family_gate')
    month = selected_month(request)
    destination = request.GET.get('return_to') if request.GET.get('return_to') in ('gjeld', 'arsutgifter') else 'regninger'
    bill = get_object_or_404(BillOccurrence, pk=row_id, household=member.household)
    access.require_row(member, bill)
    if not access.can_page(member, destination): destination = 'regninger'
    form = forms.PaymentForm(request.POST or None, initial={'version': bill.version})
    if request.method == 'POST' and form.is_valid():
        try:
            services.pay_bill(request.user, bill.pk, form.cleaned_data['date'], form.cleaned_data['key'], form.cleaned_data['version'])
            messages.success(request, 'Betalingen er registrert én gang. Appen har ikke flyttet penger.')
            return redirect(module_url(destination, month, request.GET)) if 'month' in request.GET else redirect('page', page=destination)
        except ValidationError as error: form.add_error(None, error)
    return render(request, 'budget/form.html', {'form': form, 'title': f'Merk {bill.name} som betalt', 'explanation': 'Dette registrerer faktisk betaling i budsjettet. Appen utfører ingen bankbetaling.', 'member': member, 'nav': NAV, 'month': month, 'page': destination, 'back': module_url(destination, month, request.GET)})


@login_required
def member_access_view(request, member_id):
    actor = services.authorize(request.user, admin=True)
    target = get_object_or_404(Membership.objects.select_related('user'), pk=member_id, household=actor.household)
    if target.role == 'admin': raise PermissionDenied('Administratorer har alltid full tilgang.')
    form = forms.MemberAccessForm(request.POST if request.method == 'POST' else None, member=target)
    status = 200
    if request.method == 'POST' and form.is_valid():
        try:
            allowed = set(form.cleaned_data['modules'])
            access.update_member_access(request.user, target.pk, {key: key in allowed for key in access.MODULES}, form.cleaned_data['version'])
            messages.success(request, 'Modultilgangen er lagret. Valgene gjelder også i medlemmets åpne økter.')
            return redirect('page', page='familie')
        except services.Conflict as exc:
            target.refresh_from_db()
            latest = {'version': target.access_version, 'modules': [key for key in access.MODULES if access.allows(target, key)]}
            form = forms.MemberAccessForm(latest, member=target, initial=latest)
            form.is_valid()
            form.add_error(None, exc)
            status = 409
    elif request.method == 'POST': status = 400
    return render(request, 'budget/member_access.html', {
        'form': form, 'title': 'Modultilgang', 'member': actor, 'nav': NAV,
        'target': target,
        'explanation': f'Velg hva {target.user.get_full_name() or target.user.email} kan bruke. Skjulte moduler skjuler også opplysninger og summer. Konto, passord, utlogging og startside er alltid tilgjengelige.',
        'back': reverse('page', args=['familie']),
    }, status=status)


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
        return redirect(module_url('tilpass', selected_month(request))) if 'month' in request.GET else redirect('page', page='tilpass')
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
            return redirect(module_url('gjeld', form.cleaned_data['month']) + '&' + urlencode({'strategy': form.cleaned_data['strategy'], 'extra': form.cleaned_data['extra'] or 0}))
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
    public_files = [root / 'static/budget' / name for name in ['app.css', 'app.js', 'icon.svg', 'sw.js', 'calendar.css', 'calendar.js', 'spending.css', 'spending.js', 'push.js', 'loader.css', 'loader.js', 'loader-logo.png', 'loader-icon.png', 'ui-refresh.css', 'ui-refresh.js', 'figtree-latin.woff2']] + [root / 'templates/budget/offline.html']
    version = hashlib.sha256(b''.join(file.read_bytes() for file in public_files)).hexdigest()[:20]
    source = (root / 'static/budget/sw.js').read_text(encoding='utf-8').replace('__PUBLIC_VERSION__', version)
    response = HttpResponse(source, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response


def public_asset(request, name):
    from pathlib import Path
    from django.http import FileResponse
    allowed = {'camera-scan.js': 'application/javascript', 'document-draft.js': 'application/javascript', 'shopping.js': 'application/javascript', 'ui-refresh.css': 'text/css', 'ui-refresh.js': 'application/javascript', 'figtree-latin.woff2': 'font/woff2', 'app.css': 'text/css', 'app.js': 'application/javascript', 'push.js': 'application/javascript', 'loader.css': 'text/css', 'loader.js': 'application/javascript', 'loader-logo.png': 'image/png', 'loader-icon.png': 'image/png', 'icon.svg': 'image/svg+xml', 'calendar.css': 'text/css', 'calendar.js': 'application/javascript', 'spending.css': 'text/css', 'spending.js': 'application/javascript'}
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
