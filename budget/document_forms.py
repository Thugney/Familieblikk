import uuid
from django import forms
from .forms import MoneyField
from . import access
from .models import Category, Entry, BillOccurrence


class CommandForm(forms.Form):
    key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    version = forms.IntegerField(min_value=1, widget=forms.HiddenInput, initial=1)


class UploadForm(forms.Form):
    key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    file = forms.FileField(label='Ta bilde eller velg et bilde', widget=forms.ClearableFileInput(attrs={'accept': 'image/jpeg,image/png', 'capture': 'environment'}))


class DraftForm(CommandForm):
    supplier = forms.CharField(label='Leverandør / butikk', max_length=120, required=False)
    amount = MoneyField(label='Beløp i NOK', required=False)
    document_date = forms.DateField(label='Dokumentdato', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    due_date = forms.DateField(label='Forfallsdato (faktura)', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    category = forms.ModelChoiceField(label='Hovedkategori', queryset=Category.objects.none(), required=False)
    def __init__(self, *args, member, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = access.category_choices(member, Category.objects.filter(archived=False))


class TargetChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        name = getattr(obj, 'description', getattr(obj, 'name', ''))
        day = getattr(obj, 'effective_date', getattr(obj, 'due_date', ''))
        return f'{name} · {day} · {obj.amount_ore / 100:.2f} NOK'


class ConfirmForm(CommandForm):
    action = forms.ChoiceField(label='Hva vil du bekrefte?', choices=[('expense', 'Opprett én utgift'), ('bill', 'Opprett én ubetalt engangsregning'), ('link_entry', 'Koble til eksisterende utgift/betaling'), ('link_bill', 'Koble til eksisterende regning')])
    entry = TargetChoice(label='Eksisterende utgift / betaling', queryset=Entry.objects.none(), required=False)
    bill = TargetChoice(label='Eksisterende regning', queryset=BillOccurrence.objects.none(), required=False)
    acknowledge_duplicate = forms.BooleanField(label='Jeg har kontrollert mulige duplikater og bekrefter at dette er en separat ny post.', required=False)
    confirmation = forms.BooleanField(label='Jeg bekrefter beløp, dato og kobling. En ny post opprettes bare for valgt opprett-handling.')
    def __init__(self, *args, member, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['entry'].queryset = access.safe_rows(member, Entry.objects.filter(kind__in=['expense', 'debt', 'fund', 'remittance']))
        self.fields['bill'].queryset = access.safe_rows(member, BillOccurrence.objects.all())
        self.fields['action'].choices = [(key, label) for key, label in self.fields['action'].choices
            if key not in ('expense', 'bill') or access.allows(member, 'budget' if key == 'expense' else 'bills')]
    def clean(self):
        data = super().clean()
        if data.get('action') == 'link_entry' and not data.get('entry'): self.add_error('entry', 'Velg eksisterende betaling.')
        if data.get('action') == 'link_bill' and not data.get('bill'): self.add_error('bill', 'Velg eksisterende regning.')
        return data
