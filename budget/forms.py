import uuid
from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Asset, BillTemplate, Category, Entry, MonthPlan


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


class CodeForm(EmailForm):
    code = forms.RegexField(r'^\d{6}$', label='Engangskode', widget=forms.TextInput(attrs={'inputmode': 'numeric', 'autocomplete': 'one-time-code', 'maxlength': 6}))


class PasswordLoginForm(EmailForm):
    password = forms.CharField(label='Passord', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))


class RegisterAccountForm(EmailForm):
    role = forms.ChoiceField(label='Rolle i familien', choices=[('member', 'Medlem'), ('admin', 'Administrator')])
    password1 = forms.CharField(label='Startpassord (minst 12 tegn)', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))
    password2 = forms.CharField(label='Bekreft startpassord', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))
    confirm = forms.BooleanField(label='Jeg bekrefter registreringen og deler startpassordet privat med den nye brukeren. Ingen e-post sendes.')
    def clean(self):
        data = super().clean()
        if data.get('password1') != data.get('password2'): raise ValidationError('Passordene må være like.')
        return data


class RegisterHouseholdForm(RegisterAccountForm):
    family_name = forms.CharField(label='Navn på den nye familien', max_length=120)


class FamilyForm(forms.Form):
    name = forms.CharField(label='Familiens navn', max_length=120)


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
            if isinstance(field, forms.ModelChoiceField): field.queryset = field.queryset.filter(household=household)
            if isinstance(field, forms.DateField): field.widget = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')
    def clean(self):
        result = super().clean()
        if result.get('amount') is not None: self.instance.amount_ore = int(result['amount'] * 100)
        return result


class EntryForm(RowForm):
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    class Meta:
        model = Entry
        fields = ['kind', 'description', 'effective_date', 'category', 'asset', 'received', 'income_attribution', 'original', 'original_amount', 'currency', 'exchange_rate', 'fee_ore']
        labels = {'kind': 'Type', 'description': 'Beskrivelse', 'effective_date': 'Dato', 'category': 'Kategori', 'asset': 'Mål / gjeld / fond / mottaker', 'received': 'Inntekten er mottatt', 'income_attribution': 'Inntekten tilhører (frivillig tekst)', 'original': 'Opprinnelig betaling ved refusjon', 'original_amount': 'Opprinnelig valutabeløp', 'currency': 'ISO-valuta, f.eks. EUR', 'exchange_rate': 'Bekreftet NOK per valutaenhet (tom ved faktisk NOK)', 'fee_ore': 'Separat gebyr i øre'}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['original'].queryset = self.fields['original'].queryset.filter(kind__in=['expense', 'debt', 'fund', 'remittance'])
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
    opening = MoneyField(label='Åpningssaldo / referansesaldo NOK', required=False, min_value=Decimal('0'))
    target = MoneyField(label='Målbeløp / årsbeløp NOK', required=False, min_value=Decimal('0'))
    plan = MoneyField(label='Månedsplan / minimum NOK', required=False, min_value=Decimal('0'))
    plan_month = forms.DateField(label='Planen gjelder fra måned (første dag)', required=False, initial=lambda: timezone.localdate().replace(day=1), widget=forms.DateInput(attrs={'type': 'date'}))
    plan_version = forms.IntegerField(widget=forms.HiddenInput, required=False, initial=0)
    displayed_plan_month = forms.DateField(widget=forms.HiddenInput, required=False)
    class Meta:
        model = Asset
        fields = ['kind', 'name', 'opening_date', 'target_date', 'annual_rate', 'country', 'archived']
        labels = {'kind': 'Type', 'name': 'Navn', 'opening_date': 'Dato for dokumentert åpning / saldo', 'target_date': 'Måldato / forfall', 'annual_rate': 'Årlig rente i prosent', 'country': 'Land / notat', 'archived': 'Arkiver fra neste måned'}
        widgets = {'opening_date': forms.DateInput(attrs={'type': 'date'}), 'target_date': forms.DateInput(attrs={'type': 'date'})}
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
        labels = {'month': 'Måned (første dag)', 'category': 'Kategori', 'asset': 'Mål / gjeld / fond'}
    def clean_month(self):
        day = self.cleaned_data['month']
        if day.day != 1: raise ValidationError('Velg første dag i måneden.')
        return day


class BillForm(RowForm):
    class Meta:
        model = BillTemplate
        fields = ['name', 'first_due', 'monthly', 'category', 'accounting_class', 'asset', 'archived']
        labels = {'name': 'Navn', 'first_due': 'Første forfall', 'monthly': 'Gjenta månedlig', 'category': 'Kategori', 'accounting_class': 'Regnskapsklasse', 'asset': 'Koblet gjeld / årsfond', 'archived': 'Stopp nye forekomster'}
    def clean(self):
        data = super().clean()
        kind, asset = data.get('accounting_class'), data.get('asset')
        if kind == 'ordinary' and not data.get('category'): raise ValidationError('Vanlig regning krever kategori.')
        if kind in ('debt', 'fund') and (not asset or asset.kind != kind): raise ValidationError('Velg samme type gjeld eller fond.')
        if kind == 'ordinary' and asset: raise ValidationError('Vanlig regning kan ikke kobles til gjeld eller fond.')
        return data


class PaymentForm(forms.Form):
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
