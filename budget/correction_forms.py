import uuid
from django import forms
from django.utils import timezone
from .forms import MoneyField
from .models import Category
from . import access


class CorrectionForm(forms.Form):
    version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    key = forms.UUIDField(initial=uuid.uuid4, widget=forms.HiddenInput)
    operation = forms.ChoiceField(label='Handling', choices=[])
    reason = forms.CharField(label='Begrunnelse', max_length=500, required=False, widget=forms.Textarea(attrs={'rows': 2}))
    event = forms.IntegerField(required=False, widget=forms.HiddenInput)
    name = forms.CharField(label='Navn', max_length=120, required=False)
    amount = MoneyField(label='Beløp NOK', required=False)
    due_date = forms.DateField(label='Forfall', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    category = forms.ModelChoiceField(label='Kategori', required=False, queryset=Category.objects.none())
    start = forms.DateField(label='Virkningsdato (fra og med)', required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, member, row, kind, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = access.category_choices(member, Category.objects.filter(household=member.household))
        if kind == 'bill':
            choices = [('correct', 'Rett denne regningen'), ('cancel', 'Avbryt feilført regning'), ('restore', 'Gjenopprett / angre endring')]
            self.fields.pop('start')
        elif kind == 'series':
            choices = [('revise', 'Endre fremtidig serie'), ('archive', 'Arkiver serie'), ('resume', 'Gjenoppta serie')]
            self.fields.pop('due_date'); self.fields.pop('event')
        else:
            choices = [('reverse', 'Angre feilregistrert betaling' if row.occurrence_id else 'Slett feilført post (bevar historikk)'), ('restore', 'Gjenopprett / angre endring')]
            for field in ('name', 'amount', 'due_date', 'category', 'start'): self.fields.pop(field)
        self.fields['operation'].choices = choices
        self.kind = kind

    def clean(self):
        data = super().clean()
        operation = data.get('operation')
        if operation in ('correct', 'revise'):
            for field in ('name', 'amount'):
                if not data.get(field): self.add_error(field, 'Fyll ut feltet før bekreftelse.')
            if operation == 'correct' and not data.get('due_date'): self.add_error('due_date', 'Velg forfall.')
        if self.kind == 'series' and not data.get('start'): self.add_error('start', 'Velg virkningsdato.')
        if operation == 'restore' and not data.get('event'): self.add_error(None, 'Velg hendelsen i historikken først.')
        if operation in ('cancel', 'reverse') and not data.get('reason'): self.add_error('reason', 'Beskriv feilregistreringen.')
        return data


class ExportForm(forms.Form):
    date_from = forms.DateField(label='Fra dato', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(label='Til dato', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    category = forms.ModelChoiceField(label='Kategori', required=False, queryset=Category.objects.none())
    status = forms.ChoiceField(label='Status', required=False)

    def __init__(self, *args, member, kind, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = access.category_choices(member, Category.objects.filter(household=member.household))
        self.fields['status'].choices = [('', 'Alle')] + ([('unpaid', 'Ubetalt'), ('paid', 'Betalt'), ('cancelled', 'Avbrutt')] if kind == 'bill' else [('active', 'Aktiv'), ('reversed', 'Reversert')])

    def clean(self):
        data = super().clean()
        if data.get('date_from') and data.get('date_to') and data['date_from'] > data['date_to']:
            raise forms.ValidationError('Fra dato må være før til dato.')
        return data
