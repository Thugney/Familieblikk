"""Member visibility policy. Household accounting never uses these selections.

An absent key preserves legacy access. Explicit False revokes access. Writers and
push delivery lock Household first, then reload Membership, so a committed change
also applies to existing sessions and idempotent requests.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from .models import (Asset, Audit, BillOccurrence, BillTemplate, Category, Entry,
                     FundTopUp, Household, Membership, MonthPlan)

MODULES = {
    'budget': 'Budsjett og poster', 'bills': 'Regninger', 'savings': 'Sparing',
    'debt': 'Gjeld og strategi', 'fund': 'Årsfond', 'remittance': 'Utenlandsregistreringer',
    'annual': 'Årsoversikt', 'calendar': 'Kalender', 'documents': 'Skann kvittering', 'shopping': 'Handlelister',
}
FINANCE = frozenset(MODULES) - {'annual', 'calendar', 'documents', 'shopping'}
ASSETS = {'savings': 'savings', 'debt': 'debt', 'fund': 'fund', 'recipient': 'remittance'}
KINDS = {'income': 'budget', 'expense': 'budget', 'deposit': 'savings',
         'withdrawal': 'savings', 'debt': 'debt', 'fund': 'fund', 'remittance': 'remittance'}
PAGES = {'poster': {'budget'}, 'budsjett': {'budget'}, 'kategorier': {'budget'},
         'dokumenter': {'documents'}, 'handlelister': {'shopping'},
         'regninger': {'bills'}, 'sparing': {'savings'}, 'gjeld': {'debt'},
         'arsutgifter': {'fund'}, 'utland': {'remittance'}, 'kalender': {'calendar'},
         'varsler': {'calendar'}, 'arsoversikt': {'annual', 'budget'}}
PAGE_PREFERENCES = {'gjeld': ('debt', False), 'arsutgifter': ('fund', False),
                    'utland': ('remittance', False), 'arsoversikt': ('annual_navigation', True)}


def validate_permissions(value):
    if not isinstance(value, dict) or set(value) - MODULES.keys() or any(type(v) is not bool for v in value.values()):
        raise ValidationError('Velg bare kjente moduler med av/på-verdier.')


def allows(member, module):
    return module in MODULES and (member.role == 'admin' or member.module_access.get(module, True) is True)


def require(member, modules):
    if any(not allows(member, module) for module in modules):
        raise PermissionDenied('Administrator har begrenset modultilgangen din. Be administrator om tilgang.')
    return member


def complete_finance(member):
    return all(allows(member, module) for module in FINANCE)


def can_page(member, page):
    return all(allows(member, module) for module in PAGES.get(page, set()))


def visible_page(member, page):
    preference, default = PAGE_PREFERENCES.get(page, (None, True))
    return can_page(member, page) and (preference is None or member.household.modules.get(preference, default))


def require_page(member, page, matrix=False):
    require(member, PAGES.get(page, set()))
    if matrix:
        require(member, FINANCE)


def lock_member(actor):
    # Call only inside transaction.atomic. This is the shared lock order.
    try:
        initial = Membership.objects.only('household_id').get(user=actor)
    except Membership.DoesNotExist:
        raise PermissionDenied('Bli med i en familie først.') from None
    Household.objects.select_for_update().get(pk=initial.household_id)
    member = Membership.objects.select_related('household').get(user=actor)
    if member.household_id != initial.household_id:
        raise PermissionDenied('Medlemskapet er endret. Last inn på nytt.')
    return member


def row_modules(row, household_id, seen=None):
    from .models import Document, ShoppingList, ShoppingItem, ShoppingTrip
    if row.household_id != household_id:
        raise PermissionDenied('Ingen tilgang til denne familien.')
    seen = set() if seen is None else seen
    identity = (type(row), row.pk)
    if identity in seen:
        raise PermissionDenied('Ugyldig kobling mellom poster.')
    seen.add(identity)
    required = set()
    if isinstance(row, Document):
        required.add('documents')
        if row.entry_id:
            required.update(row_modules(row.entry, household_id, seen.copy()))
        if row.bill_id:
            required.update(row_modules(row.bill, household_id, seen.copy()))
    elif isinstance(row, (ShoppingList, ShoppingItem, ShoppingTrip)):
        required.add('shopping')
    elif isinstance(row, Category):
        required.add('budget')
    elif isinstance(row, Asset):
        required.add(ASSETS.get(row.kind, 'unknown'))
    elif isinstance(row, Entry):
        if row.kind == 'refund':
            if not row.original_id:
                raise PermissionDenied('Refusjonen må ha en tillatt originalpost.')
            required.update(row_modules(row.original, household_id, seen.copy()))
        elif not row.occurrence_id:
            required.add(KINDS.get(row.kind, 'unknown'))
        if row.occurrence_id:
            required.update(row_modules(row.occurrence, household_id, seen.copy()))
            expected = {'ordinary': 'expense', 'debt': 'debt', 'fund': 'fund'}.get(row.occurrence.accounting_class)
            if row.kind != expected and row.kind != 'refund':
                required.add(KINDS.get(row.kind, 'unknown'))
    elif isinstance(row, (BillTemplate, BillOccurrence)):
        required.add('bills')
        if row.accounting_class in ('debt', 'fund'):
            required.add(row.accounting_class)
        elif row.accounting_class != 'ordinary':
            required.add('unknown')
    elif isinstance(row, MonthPlan):
        if row.category_id:
            required.add('budget')
    elif isinstance(row, FundTopUp):
        required.update(row_modules(row.occurrence, household_id, seen.copy()))
    else:
        required.add('unknown')
    if getattr(row, 'asset_id', None):
        required.update(row_modules(row.asset, household_id, seen.copy()))
    # Categories may also classify a permitted bill/remittance. Always check its
    # tenant, without granting access to the separate budget module.
    if getattr(row, 'category_id', None) and row.category.household_id != household_id:
        raise PermissionDenied('Ingen tilgang til denne familien.')
    return required


def require_row(member, row):
    return require(member, row_modules(row, member.household_id))


def require_write_row(member, row):
    required = row_modules(row, member.household_id)
    # Fund mutations validate against balances containing bill payments. Both
    # the amount in an error and acceptance of a guessed amount reveal them.
    if isinstance(row, Entry) and 'fund' in required:
        required.add('bills')
    return require(member, required)


def lock_relations(member, row, seen=None):
    """Replace ModelForm caches with current relations under the household lock."""
    seen = set() if seen is None else seen
    identity = (type(row), row.pk)
    if identity in seen:
        raise PermissionDenied('Ugyldig kobling mellom poster.')
    seen.add(identity)
    for field in row._meta.fields:
        if not field.is_relation or field.name in ('household', 'created_by'):
            continue
        related_id = getattr(row, field.attname)
        if related_id is None or not hasattr(field.related_model, 'household_id'):
            continue
        try:
            fresh = field.related_model.objects.select_for_update().get(pk=related_id, household_id=member.household_id)
        except field.related_model.DoesNotExist:
            raise ValidationError({field.name: 'Koblingen må tilhøre samme familie.'}) from None
        lock_relations(member, fresh, seen.copy())
        setattr(row, field.name, fresh)
    return row


def _asset_predicate(member, prefix):
    kinds = [kind for kind, module in ASSETS.items() if allows(member, module)]
    return Q(**{prefix + 'asset__isnull': True}) | Q(**{
        prefix + 'asset__household_id': member.household_id,
        prefix + 'asset__kind__in': kinds,
    })


def _category_tenant(member, prefix):
    return Q(**{prefix + 'category__isnull': True}) | Q(**{
        prefix + 'category__household_id': member.household_id})


def _bill_predicate(member, prefix):
    classes = (['ordinary'] + [kind for kind in ('debt', 'fund') if allows(member, kind)]) if allows(member, 'bills') else []
    return Q(**{prefix + 'household_id': member.household_id,
                prefix + 'accounting_class__in': classes}) & _asset_predicate(member, prefix) & _category_tenant(member, prefix)


def _entry_predicate(member, prefix='', refunds=True):
    """Classify current rows and relations in SQL, including delayed evaluation.

    The validated payment originals of refunds are never refunds themselves.
    Reject invalid nested originals rather than following an unbounded chain.
    """
    kinds = [kind for kind, module in KINDS.items() if allows(member, module)]
    own_kind = Q(**{prefix + 'kind__in': kinds})
    linked_kind = own_kind
    for accounting_class, kind in (('ordinary', 'expense'), ('debt', 'debt'), ('fund', 'fund')):
        linked_kind |= Q(**{prefix + 'occurrence__accounting_class': accounting_class, prefix + 'kind': kind})
    if refunds:
        original = Q(**{prefix + 'kind': 'refund'}) & _entry_predicate(member, prefix + 'original__', refunds=False)
        linked_kind |= original
        standalone_kind = own_kind | original
    else:
        standalone_kind = own_kind
    classification = (Q(**{prefix + 'occurrence__isnull': True}) & standalone_kind) | (
        Q(**{prefix + 'occurrence__isnull': False}) & _bill_predicate(member, prefix + 'occurrence__') & linked_kind)
    return Q(**{prefix + 'household_id': member.household_id}) & classification & _asset_predicate(member, prefix) & _category_tenant(member, prefix)


def safe_rows(member, queryset):
    """Lazy SQL policy: no earlier Python-approved IDs or relation snapshots."""
    queryset = queryset.filter(household_id=member.household_id)
    from .models import Document, ShoppingList, ShoppingItem, ShoppingTrip, WorkflowCommand
    if queryset.model is Document:
        if not allows(member, 'documents'):
            return queryset.none()
        return queryset.filter(_category_tenant(member, '') & (Q(entry__isnull=True) | Q(entry_id__in=safe_rows(member, Entry.objects.all()).values('pk'))) &
                               (Q(bill__isnull=True) | Q(bill_id__in=safe_rows(member, BillOccurrence.objects.all()).values('pk'))))
    if queryset.model in (ShoppingList, ShoppingItem, ShoppingTrip):
        return queryset if allows(member, 'shopping') else queryset.none()
    if queryset.model is WorkflowCommand:
        return queryset.none()
    if member.role == 'admin' or complete_finance(member):
        return queryset
    model = queryset.model
    if model is Entry:
        predicate = _entry_predicate(member)
    elif model is Asset:
        predicate = Q(kind__in=[kind for kind, module in ASSETS.items() if allows(member, module)])
    elif model in (BillTemplate, BillOccurrence):
        predicate = _bill_predicate(member, '')
    elif model is MonthPlan:
        predicate = _asset_predicate(member, '') & _category_tenant(member, '')
        if not allows(member, 'budget'):
            predicate &= Q(category__isnull=True)
    elif model is FundTopUp:
        predicate = _bill_predicate(member, 'occurrence__')
    elif model is Category and allows(member, 'budget'):
        return queryset
    else:
        return queryset.none()
    return queryset.filter(predicate)


def category_choices(member, queryset):
    """Without budget visibility only expose labels on permitted records."""
    queryset = queryset.filter(household_id=member.household_id)
    if allows(member, 'budget'):
        return queryset
    predicate = Q(pk__in=safe_rows(member, Entry.objects.all()).values('category_id'))
    for model in (BillTemplate, BillOccurrence):
        predicate |= Q(pk__in=safe_rows(member, model.objects.all()).values('category_id'))
    return queryset.filter(predicate)


def calendar_members(household):
    return [m for m in Membership.objects.filter(household=household).select_related('user') if allows(m, 'calendar')]


def restrict_form(member, form):
    from django import forms
    for field in form.fields.values():
        if isinstance(field, forms.ModelChoiceField):
            if field.queryset.model is Category:
                field.queryset = category_choices(member, field.queryset)
            elif field.queryset.model in (Asset, Entry, BillTemplate, BillOccurrence, MonthPlan):
                field.queryset = safe_rows(member, field.queryset)
                if isinstance(form.instance, Entry) and not allows(member, 'bills'):
                    if field.queryset.model is Asset:
                        field.queryset = field.queryset.exclude(kind='fund')
                    elif field.queryset.model is Entry:
                        field.queryset = field.queryset.exclude(Q(kind='fund') | Q(asset__kind='fund'))
    if 'kind' in form.fields:
        mapping = ASSETS if isinstance(form.instance, Asset) else KINDS
        form.fields['kind'].choices = [(key, label) for key, label in form.fields['kind'].choices
                                      if allows(member, mapping.get(key, 'unknown')) or key == 'refund' and
                                      any(allows(member, m) for m in ('budget', 'bills', 'debt', 'fund', 'remittance'))]
        if isinstance(form.instance, Entry) and not allows(member, 'bills'):
            form.fields['kind'].choices = [(key, label) for key, label in form.fields['kind'].choices if key != 'fund']
        if (isinstance(form.instance, Entry) and allows(member, 'remittance') and not allows(member, 'budget')
                and not form.fields['category'].queryset.exists()):
            form.fields['category'].help_text = ('Familieadministratoren må registrere den første faktiske overføringen '
                                                'med riktig kategori, eller gi deg tilgang til Budsjett og poster.')
    if 'accounting_class' in form.fields:
        form.fields['accounting_class'].choices = [(key, label) for key, label in form.fields['accounting_class'].choices
                                                  if key == 'ordinary' or allows(member, key)]
    return form


def entry_page(member, row):
    if can_page(member, 'poster'): return 'poster'
    if row.kind == 'refund' and row.original_id: return entry_page(member, row.original)
    if row.occurrence_id and can_page(member, 'regninger'): return 'regninger'
    page = {'deposit': 'sparing', 'withdrawal': 'sparing', 'debt': 'gjeld',
            'fund': 'arsutgifter', 'remittance': 'utland'}.get(row.kind, 'oversikt')
    return page if can_page(member, page) else 'oversikt'


def update_member_access(actor, target_id, permissions, version):
    from django.db import transaction
    from .services import Conflict
    validate_permissions(permissions)
    with transaction.atomic():
        actor_member = lock_member(actor)
        if actor_member.role != 'admin':
            raise PermissionDenied('Bare administrator kan endre modultilgang.')
        target = Membership.objects.select_for_update().get(pk=target_id, household_id=actor_member.household_id)
        if target.role == 'admin':
            raise PermissionDenied('Administratorer har alltid full tilgang.')
        if type(version) is not int or version != target.access_version:
            raise Conflict('Modultilgangen er endret. Nyeste valg vises; kontroller dem før du lagrer igjen.')
        before = dict(target.module_access)
        target.module_access = dict(permissions)
        target.access_version += 1
        target.full_clean()
        target.save(update_fields=['module_access', 'access_version'])
        Audit.objects.create(household_id=target.household_id, actor=actor,
                             object_id=target.household_id, operation='modultilgang',
                             changes={'membership_id': target.pk, 'before': before, 'after': permissions})
        return target
