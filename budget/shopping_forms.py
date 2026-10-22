from django import forms
from django.utils import timezone
from .document_forms import CommandForm, TargetChoice
from .forms import MoneyField
from .models import Category, Document
from . import access


class ListForm(CommandForm):
    name = forms.CharField(label='Listenavn', max_length=120)


class ItemForm(CommandForm):
    name = forms.CharField(label='Vare', max_length=120)
    quantity = forms.CharField(label='Antall / mengde', max_length=40, initial='1')
    purchased = forms.BooleanField(label='Kjøpt', required=False)
    removed = forms.BooleanField(label='Fjern fra aktiv liste (historikken bevares)', required=False)
    def __init__(self, *args, member, **kwargs):
        super().__init__(*args, **kwargs)


class DocumentChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj): return obj.filename or obj.supplier or f"Skanning {str(obj.pk)[:8]}"


class TripForm(CommandForm):
    store = forms.CharField(label='Butikk – én butikk per tur', max_length=120)
    effective_date = forms.DateField(label='Faktisk kjøpsdato', initial=timezone.localdate, widget=forms.DateInput(attrs={'type': 'date'}))
    amount = MoneyField(label='Faktisk total i NOK')
    category = forms.ModelChoiceField(label='Én hovedkategori', queryset=Category.objects.none())
    receipt = DocumentChoice(label='Valgfri gjennomgått skanning', queryset=Document.objects.none(), required=False)
    acknowledge_duplicate = forms.BooleanField(label='Jeg har kontrollert mulige duplikater og bekrefter at dette er en separat ny tur.', required=False)
    confirmation = forms.BooleanField(label='Jeg bekrefter faktisk total og oppretter én utgift for de avkryssede varene.')
    def __init__(self, *args, member, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = access.category_choices(member, Category.objects.filter(archived=False))
        self.fields['receipt'].queryset = access.safe_rows(member, Document.objects.filter(confirmed=False, cancelled=False))
        if not access.allows(member, 'documents'): self.fields.pop('receipt')


class ReceiptForm(CommandForm):
    receipt = DocumentChoice(label='Kvittering', queryset=Document.objects.none())
    confirmation = forms.BooleanField(label='Koble kvitteringen til turens eksisterende utgift uten ny bokføring.')
    def __init__(self, *args, member, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['receipt'].queryset = access.safe_rows(member, Document.objects.filter(confirmed=False, cancelled=False))
