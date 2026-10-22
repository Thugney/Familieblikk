from django import forms
from .models import Membership

class CalendarForm(forms.Form):
    title=forms.CharField(label='Tittel',max_length=160)
    start=forms.DateField(label='Startdato',widget=forms.DateInput(attrs={'type':'date'}))
    end=forms.DateField(label='Sluttdato (inkludert)',widget=forms.DateInput(attrs={'type':'date'}))
    all_day=forms.BooleanField(label='Heldag',required=False)
    start_time=forms.TimeField(label='Fra klokken',required=False,widget=forms.TimeInput(attrs={'type':'time'}))
    end_time=forms.TimeField(label='Til klokken',required=False,widget=forms.TimeInput(attrs={'type':'time'}))
    fold=forms.TypedChoiceField(label='Ved vintertid',choices=[('','Velg ved tvetydig klokkeslett'),('0','Tidligere tidspunkt'),('1','Senere tidspunkt')],coerce=int,empty_value=None,required=False)
    scope=forms.ChoiceField(label='Kalender',choices=[('shared','Felles familieavtale'),('selected','Valgte familiemedlemmer')])
    participants=forms.MultipleChoiceField(label='Deltakere',required=False,widget=forms.CheckboxSelectMultiple)
    recurrence=forms.ChoiceField(label='Gjenta',choices=[('none','Ingen gjentakelse'),('weekly','Ukentlig'),('monthly','Månedlig')])
    until=forms.DateField(label='Siste startdato i serien (valgfritt)',required=False,widget=forms.DateInput(attrs={'type':'date'}))
    place=forms.CharField(label='Sted (valgfritt)',max_length=240,required=False)
    note=forms.CharField(label='Notat (valgfritt)',max_length=4000,required=False,widget=forms.Textarea(attrs={'rows':3}))
    def __init__(self,household,*args,**kwargs):
        super().__init__(*args,**kwargs)
        from .access import calendar_members
        self.fields['participants'].choices=[(str(m.pk),m.user.get_full_name() or m.user.email) for m in calendar_members(household)]
