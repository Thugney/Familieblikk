import uuid
from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Asset, BillTemplate, Category, Entry, MonthPlan
from .identity import LOGIN_ERROR, MAX_PASSWORD_LENGTH
from .entry_presentation import ENTRY_LABELS, ASSET_LABELS, BILL_LABELS


class MoneyField(forms.DecimalField):
    def __init__(self, *args, **kwargs):
        kwargs.update(max_digits=14, decimal_places=2, localize=True)
        kwargs.setdefault('min_value', Decimal('0.01'))
        super().__init__(*args, **kwargs)
        self.widget.attrs.update(inputmode='decimal')
    def to_python(self, value):
        if isinstance(value, str): value = value.replace(' ', '').replace('\xa0', '').replace(',', '.')
        return super().to_python(value)


class EmailForm(forms.Form):
    email = forms.EmailField(label='E-post', widget=forms.EmailInput(attrs={'autocomplete': 'email'}))


class EntryFilterForm(forms.Form):
    q = forms.CharField(label='Søk i poster', max_length=120, required=False, widget=forms.TextInput(attrs={'placeholder': 'Beskrivelse, kategori eller mål'}))
    kind = forms.ChoiceField(label='Type', required=False, choices=[('', 'Alle typer')] + list(ENTRY_LABELS.items()))
    category = forms.ModelChoiceField(label='Kategori', required=False, queryset=Category.objects.none(), empty_label='Alle kategorier')
    creator = forms.ChoiceField(label='Registrert av', required=False)
    date_from = forms.DateField(label='Fra dato', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(label='Til dato', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    status = forms.ChoiceField(label='Inntektsstatus', required=False, choices=[('', 'Alle statuser'), ('expected', 'Forventet inntekt'), ('received', 'Mottatt inntekt')])
    def __init__(self, *args, household, month, remittances_only=False, **kwargs):
        from .models import Membership
        from .services import month_end
        super().__init__(*args, **kwargs)
        if remittances_only:
            self.fields['kind'].choices = [('', 'Alle typer')] + [(key, label) for key, label in ENTRY_LABELS.items() if key in ('remittance', 'refund')]
            self.fields.pop('status')
        self.fields['category'].queryset = Category.objects.filter(household=household).order_by('name', 'id')
        self.fields['creator'].choices = [('', 'Alle familiemedlemmer')] + [(str(member.user_id), member.user.get_full_name() or member.user.email) for member in Membership.objects.filter(household=household).select_related('user').order_by('user__email', 'user_id')]
        for key in ('date_from', 'date_to'): self.fields[key].widget.attrs.update(min=month.isoformat(), max=month_end(month).isoformat())
    def clean(self):
        result = super().clean()
        if result.get('date_from') and result.get('date_to') and result['date_from'] > result['date_to']:
            raise ValidationError('Fra dato må være før eller lik til dato.')
        return result

    @property
    def advanced_open(self):
        keys = ('category', 'creator', 'date_from', 'date_to', 'status')
        return bool(self.errors) or any(self.data.get(key) for key in keys)


class CodeForm(EmailForm):
    code = forms.RegexField(r'^[0-9]{6}$', max_length=6, label='Engangskode', widget=forms.TextInput(attrs={'inputmode': 'numeric', 'autocomplete': 'one-time-code', 'maxlength': 6}))


class PasswordLoginForm(EmailForm):
    password = forms.CharField(label='Passord', max_length=MAX_PASSWORD_LENGTH, error_messages={'max_length': LOGIN_ERROR}, strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))


class FinancialPrivacyForm(EmailForm):
    financial_sharing = forms.ChoiceField(label='Tilgang til det nye budsjettet', choices=[('', 'Velg tilgang'), ('private', 'Privat – bare medlemmet'), ('named', 'Navngitte foreldre får lesetilgang')])
    financial_reader_ids = forms.MultipleChoiceField(label='Foreldre med lesetilgang', required=False, widget=forms.CheckboxSelectMultiple)
    def __init__(self, *args, member=None, new_household=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['financial_reader_ids'].choices = [(str(m.pk), m.user.get_full_name() or m.user.email) for m in member.household.membership_set.select_related('user').filter(user__is_active=True)] if member and not new_household else []
        if new_household:
            self.fields['financial_sharing'].choices = [('private', 'Privat – bare den nye familieadministratoren')]
    def clean(self):
        data = super().clean()
        sharing, readers = data.get('financial_sharing'), data.get('financial_reader_ids', [])
        if sharing == 'private' and readers or sharing == 'named' and not readers:
            raise ValidationError('Velg ingen lesere for privat budsjett, eller minst én for navngitt innsyn.')
        return data


class RegisterAccountForm(FinancialPrivacyForm):
    role = forms.ChoiceField(label='Rolle i familien', choices=[('member', 'Medlem'), ('admin', 'Administrator')])
    password1 = forms.CharField(label='Startpassord (minst 12 tegn)', max_length=MAX_PASSWORD_LENGTH, strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))
    password2 = forms.CharField(label='Bekreft startpassord', max_length=MAX_PASSWORD_LENGTH, strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))
    confirm = forms.BooleanField(label='Jeg bekrefter registreringen og deler startpassordet privat med den nye brukeren. Ingen e-post sendes.')
    def clean(self):
        data = super().clean()
        if data.get('password1') != data.get('password2'): raise ValidationError('Passordene må være like.')
        return data


class RegisterHouseholdForm(RegisterAccountForm):
    family_name = forms.CharField(label='Navn på den nye familien', max_length=120)


class FamilyForm(forms.Form):
    name = forms.CharField(label='Familiens navn', max_length=120)


class MemberAccessForm(forms.Form):
    version = forms.IntegerField(widget=forms.HiddenInput, min_value=1)
    modules = forms.MultipleChoiceField(label='Tillatte moduler', required=False,
                                       widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, member, **kwargs):
        from .access import MODULES, allows
        super().__init__(*args, **kwargs)
        self.fields['modules'].choices = list(MODULES.items())
        if not self.is_bound:
            self.initial.update(version=member.access_version,
                                modules=[key for key in MODULES if allows(member, key)])


class MemberChangeForm(forms.Form):
    version = forms.IntegerField(widget=forms.HiddenInput, min_value=1)
    action = forms.ChoiceField(widget=forms.HiddenInput, choices=[])
    confirm = forms.BooleanField(label='Jeg bekrefter endringen.')

    def __init__(self, *args, **kwargs):
        from .identity import MEMBER_ACTIONS
        super().__init__(*args, **kwargs)
        self.fields['action'].choices = list(MEMBER_ACTIONS.items())


class RowForm(forms.ModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput, initial=0, required=False)
    amount = MoneyField(label='Beløp i NOK')
    def __init__(self, *args, household, **kwargs):
        super().__init__(*args, **kwargs)
        self.household = household
        self.instance.household = household
        if self.instance.pk and not self.instance._state.adding:
            self.initial['version'] = self.instance.version
            if hasattr(self.instance, 'amount_ore'): self.initial['amount'] = Decimal(self.instance.amount_ore) / 100
        for name, field in self.fields.items():
            if isinstance(field, forms.ModelChoiceField): field.queryset = field.queryset.model.objects.filter(household=household)
            if isinstance(field, forms.DateField): field.widget = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')
        if 'kind' in self.fields and isinstance(self.instance, Entry):
            self.fields['kind'].choices = list(ENTRY_LABELS.items())
        if 'accounting_class' in self.fields:
            self.fields['accounting_class'].choices = list(BILL_LABELS.items())
            self.fields['accounting_class'].help_text = 'For lån og kredittkort: velg Gjeldsbetaling og koble til riktig gjeld. Da inngår regningen i gjeldsbeløpet én gang. En høyere månedsplan for gjelden reserverer også det planlagte ekstrabeløpet.'
            self.fields['category'].help_text = 'En regning er penger ut. Kategorien endrer ikke dette. Lønn og andre penger inn registreres som Inntekt under Ny post.'
    def clean(self):
        result = super().clean()
        if result.get('amount') is not None: self.instance.amount_ore = int(result['amount'] * 100)
        return result


class EntryForm(RowForm):
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    command_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    class Meta:
        model = Entry
        fields = ['kind', 'description', 'effective_date', 'category', 'asset', 'received', 'income_attribution', 'original', 'original_amount', 'currency', 'exchange_rate', 'fee_ore']
        labels = {'kind': 'Type', 'description': 'Beskrivelse', 'effective_date': 'Dato', 'category': 'Kategori', 'asset': 'Sparemål / gjeld / årsutgift / mottaker', 'received': 'Inntekten er mottatt', 'income_attribution': 'Inntekten tilhører (frivillig tekst)', 'original': 'Hvilken betaling fikk du penger tilbake for?', 'original_amount': 'Opprinnelig valutabeløp', 'currency': 'ISO-valuta, f.eks. EUR', 'exchange_rate': 'Bekreftet NOK per valutaenhet (tom ved faktisk NOK)', 'fee_ore': 'Separat gebyr i øre'}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['command_key'].required = not self.instance._state.adding
        self.initial['command_key'] = uuid.uuid4()
        self.fields['original'].queryset = self.fields['original'].queryset.filter(active=True, kind__in=['expense', 'debt', 'fund', 'remittance'])
        self.fields['effective_date'].initial = timezone.localdate
        self.fields['currency'].required = False
    def clean(self):
        data = super().clean()
        if data.get('idempotency_key'): self.instance.idempotency_key = data['idempotency_key']
        return data


class CategoryForm(forms.ModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput, required=False, initial=0)
    class Meta:
        model = Category
        fields = ['name', 'color', 'archived']
        labels = {'name': 'Navn', 'color': 'Kategorifarge', 'archived': 'Arkivert'}
        widgets = {'color': forms.TextInput(attrs={'type': 'color'})}


class AssetForm(forms.ModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput, required=False, initial=0)
    opening = MoneyField(label='Beløp ved start i NOK', required=False, min_value=Decimal('0'))
    target = MoneyField(label='Målbeløp / årsbeløp NOK', required=False, min_value=Decimal('0'))
    plan = MoneyField(label='Månedsplan / minimum NOK', required=False, min_value=Decimal('0'))
    plan_month = forms.DateField(label='Planen gjelder fra måned (første dag)', required=False, initial=lambda: timezone.localdate().replace(day=1), widget=forms.DateInput(attrs={'type': 'date'}))
    plan_version = forms.IntegerField(widget=forms.HiddenInput, required=False, initial=0)
    displayed_plan_month = forms.DateField(widget=forms.HiddenInput, required=False)
    class Meta:
        model = Asset
        fields = ['kind', 'name', 'opening_date', 'target_date', 'annual_rate', 'country', 'archived']
        labels = {'kind': 'Type', 'name': 'Navn', 'opening_date': 'Dato for beløpet ved start', 'target_date': 'Måldato / forfall', 'annual_rate': 'Årlig rente i prosent', 'country': 'Land / notat', 'archived': 'Arkiver fra neste måned'}
        widgets = {'opening_date': forms.DateInput(attrs={'type': 'date'}), 'target_date': forms.DateInput(attrs={'type': 'date'})}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kind'].choices = list(ASSET_LABELS.items())
        self.fields['opening'].help_text = 'Beløpet som allerede var spart, satt av eller skyldig på startdatoen.'
        self.fields['plan'].help_text = 'Beløpet du planlegger å sette av eller betale hver måned.'
    def clean(self):
        data = super().clean()
        self.instance.opening_ore = int((data.get('opening') or 0) * 100)
        self.instance.target_ore = int((data.get('target') or 0) * 100)
        if data.get('kind') == 'debt' and data.get('plan') is not None: self.instance.minimum_ore = int(data['plan'] * 100)
        if data.get('opening_date') and data['opening_date'] > timezone.localdate(): raise ValidationError('Åpningsdato kan ikke være i fremtiden.')
        if data.get('annual_rate') is not None and data['annual_rate'] < 0: raise ValidationError('Renten kan ikke være negativ.')
        if data.get('plan') is not None:
            if not data.get('plan_month') or data['plan_month'].day != 1: raise ValidationError('Velg uttrykkelig planmånedens første dag.')
            if data.get('kind') == 'savings' and data['plan_month'] < timezone.localdate().replace(day=1): raise ValidationError('Avsluttede spareplaner kan ikke endres.')
        return data


class PlanForm(RowForm):
    amount = MoneyField(label='Månedsramme NOK', required=True, min_value=Decimal('0'))
    class Meta:
        model = MonthPlan
        fields = ['month', 'category', 'asset']
        labels = {'month': 'Måned (første dag)', 'category': 'Kategori', 'asset': 'Sparemål / gjeld / årsutgift'}
    def clean_month(self):
        day = self.cleaned_data['month']
        if day.day != 1: raise ValidationError('Velg første dag i måneden.')
        return day


class BillForm(RowForm):
    class Meta:
        model = BillTemplate
        fields = ['name', 'first_due', 'monthly', 'category', 'accounting_class', 'asset', 'archived']
        labels = {'name': 'Navn', 'first_due': 'Første forfall', 'monthly': 'Gjenta månedlig', 'category': 'Kategori', 'accounting_class': 'Hva gjelder regningen?', 'asset': 'Koblet gjeld / penger til årsutgifter', 'archived': 'Stopp nye forekomster'}
    def clean(self):
        data = super().clean()
        kind, asset = data.get('accounting_class'), data.get('asset')
        if kind == 'ordinary' and not data.get('category'): raise ValidationError('Vanlig regning krever kategori.')
        if kind in ('debt', 'fund') and (not asset or asset.kind != kind): raise ValidationError('Velg samme type gjeld eller fond.')
        if kind == 'ordinary' and asset: raise ValidationError('Vanlig regning kan ikke kobles til gjeld eller fond.')
        return data


class PaymentForm(forms.Form):
    version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    date = forms.DateField(label='Faktisk betalingsdato', initial=timezone.localdate, widget=forms.DateInput(attrs={'type': 'date'}))
    key = forms.UUIDField(initial=uuid.uuid4, widget=forms.HiddenInput)


class PreferenceForm(forms.Form):
    version = forms.IntegerField(widget=forms.HiddenInput)
    debt = forms.BooleanField(label='Gjeld', required=False)
    fund = forms.BooleanField(label='Årsutgifter', required=False)
    remittance = forms.BooleanField(label='Utland', required=False)
    savings_dashboard = forms.BooleanField(label='Sparemål i oversikten', required=False)
    annual_navigation = forms.BooleanField(label='Årsoversikt i Mer', required=False)
    confirm = forms.BooleanField(label='Jeg forstår at skjuling bevarer eksisterende forpliktelser og historikk.')


class SourceConfirmationForm(forms.Form):
    confirm = forms.BooleanField(label='Jeg har gjennomgått disse kildeinnstillingene. Dette bekrefter bevaring, ikke at kildekurser er gjeldende eller bokført.')


class DebtPlanForm(forms.Form):
    month = forms.DateField(label='Planmåned (første dag)', widget=forms.DateInput(attrs={'type': 'date'}))
    strategy = forms.ChoiceField(label='Strategi', choices=[('avalanche', 'Høyeste rente først'), ('snowball', 'Laveste saldo først')])
    extra = MoneyField(label='Ekstra månedsbeløp NOK', required=False, min_value=Decimal('0'))
    confirm = forms.BooleanField(label='Lagre fordelte beløp i denne måneden. Historiske planer endres ikke av senere strategivalg.')
