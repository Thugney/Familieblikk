import uuid
from datetime import date
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, Client
from django.urls import reverse
from budget.models import Household, Membership, CalendarEvent, CalendarException, CalendarResponse
from budget import calendar_services as cal
from budget.services import Conflict

class CalendarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.house=Household.objects.create(name='Testfamilien')
        cls.other_house=Household.objects.create(name='Annen testfamilie')
        cls.users=[];cls.members=[]
        for index,role in enumerate(['member','member','admin','member']):
            user=get_user_model().objects.create_user(username='cal'+str(index),email='cal'+str(index)+'@example.test',password='Temporary-test-password-44')
            cls.users.append(user)
            cls.members.append(Membership.objects.create(user=user,household=cls.house if index<3 else cls.other_house,role=role))
    def payload(self,**changes):
        p=dict(title='Familieavtale',start='2027-01-31',end='2027-01-31',all_day=False,start_time='17:00',end_time='18:00',place='',note='',scope='shared',participants=[],recurrence='monthly',until=None,fold=None)
        return {**p,**changes}
    def create(self,actor=0,**changes):
        result=cal.mutate(self.users[actor],'create',uuid.uuid4(),payload=self.payload(**changes))
        return CalendarEvent.objects.get(pk=result['id'])
    def edit(self,event,original='2027-01-31',actor=0,scope='one',**changes):
        current=cal.occurrence(event,date.fromisoformat(original))
        return cal.mutate(self.users[actor],'edit',uuid.uuid4(),event_id=event.pk,original=original,revision=event.revision,payload={**current,**changes},scope=scope)
    def response(self,event,original='2027-01-31',actor=0,status='yes',version=0):
        return cal.mutate(self.users[actor],'respond',uuid.uuid4(),event_id=event.pk,original=original,revision=event.revision,status=status,response_revision=version)
    def list(self,actor=0,first='2027-01-01',last='2027-03-31',selected='all'):
        return cal.listing(self.users[actor],date.fromisoformat(first),date.fromisoformat(last),selected)
    def test_monthly_anchor_clamps_and_restores(self):
        self.create()
        self.assertEqual([x['start'] for x in self.list()],['2027-01-31','2027-02-28','2027-03-31'])
    def test_visible_grid_neighbors_include_events_but_monthly_agenda_stays_scoped(self):
        for day in ['2026-09-29','2026-10-05','2026-11-01']:
            self.create(title='Synlig '+day,start=day,end=day,recurrence='none',all_day=True,start_time='',end_time='')
        self.create(actor=3,title='Privat naboavtale',start='2026-11-01',end='2026-11-01',recurrence='none',all_day=True,start_time='',end_time='')
        self.client.force_login(self.users[0])
        response=self.client.get('/app/kalender/',{'cal_month':'2026-10'})
        self.assertEqual([event['start'] for event in response.context['events']],['2026-10-05'])
        self.assertEqual({event['start'] for event in response.context['grid_events']},{'2026-09-29','2026-10-05','2026-11-01'})
        for day in [date(2026,9,29),date(2026,11,1)]:
            cell=next(cell for week in response.context['weeks'] for cell in week if cell['date']==day)
            self.assertFalse(cell['current'])
            self.assertEqual(len(cell['events']),1)
        self.assertNotContains(response,'Privat naboavtale')
    def test_monthly_future_metadata_edit_retains_original_anchor_and_series(self):
        event=self.create(); self.edit(event,'2027-02-28',scope='future',title='Nytt navn')
        rows=self.list(); self.assertEqual([x['start'] for x in rows],['2027-01-31','2027-02-28','2027-03-31'])
        self.assertEqual(rows[-1]['canonical_id'].split(':')[0],rows[0]['canonical_id'].split(':')[0])
    def test_leap_year(self):
        self.create(start='2028-01-31',end='2028-01-31')
        self.assertEqual([x['start'] for x in self.list(first='2028-01-01',last='2028-03-31')],['2028-01-31','2028-02-29','2028-03-31'])
    def test_shared_and_selected_union_and_visibility(self):
        event=self.create(scope='selected',participants=[str(self.members[0].pk),str(self.members[1].pk)])
        self.assertEqual(len(self.list(selected='all')),3)
        self.assertEqual(len(self.list(selected='shared')),0)
        self.assertEqual([x['canonical_id'] for x in self.list(selected=str(self.members[0].pk))],[x['canonical_id'] for x in self.list(selected=str(self.members[1].pk))])
        self.assertEqual(len(self.list(actor=1)),3)
        self.assertEqual(self.list(actor=3),[])
    def test_invalid_participant_rolls_back(self):
        with self.assertRaises(ValidationError): self.create(scope='selected',participants=[str(self.members[3].pk)])
        self.assertEqual(CalendarEvent.objects.count(),0)
    def test_creator_admin_and_tenant_policy(self):
        event=self.create()
        with self.assertRaises(PermissionDenied): self.edit(event,actor=1,title='Ulovlig')
        with self.assertRaises(PermissionDenied): self.edit(event,actor=3,title='Ulovlig')
        self.edit(event,actor=2,title='Administrator')
        event.refresh_from_db(); self.assertEqual(cal.occurrence(event,date(2027,1,31))['title'],'Administrator')
    def test_revision_conflict_and_idempotency(self):
        key=uuid.uuid4(); data=self.payload()
        first=cal.mutate(self.users[0],'create',key,payload=data)
        self.assertEqual(cal.mutate(self.users[0],'create',key,payload=data),first)
        self.assertEqual(CalendarEvent.objects.count(),1)
        event=CalendarEvent.objects.get(); self.edit(event,title='Endret')
        with self.assertRaises(Conflict): self.edit(event,title='Gammel side')
        with self.assertRaises(Conflict): cal.mutate(self.users[0],'create',key,payload=self.payload(title='Annen'))
    def test_moved_exception_once_and_overlap(self):
        event=self.create(); self.edit(event,start='2027-02-02',end='2027-02-03')
        rows=self.list(); self.assertEqual([x['start'] for x in rows],['2027-02-02','2027-02-28','2027-03-31'])
        self.assertEqual(rows[0]['original'],'2027-01-31')
        self.assertEqual(len(self.list(first='2027-02-03',last='2027-02-03')),1)
    def test_one_and_future_delete_preserve_history(self):
        event=self.create()
        cal.mutate(self.users[0],'delete',uuid.uuid4(),event_id=event.pk,original='2027-02-28',revision=1)
        self.assertEqual([x['start'] for x in self.list()],['2027-01-31','2027-03-31'])
        event.refresh_from_db()
        cal.mutate(self.users[0],'delete',uuid.uuid4(),event_id=event.pk,original='2027-03-31',revision=event.revision,scope='future')
        self.assertEqual([x['start'] for x in self.list()],['2027-01-31'])
    def test_future_edit_removes_future_exceptions_preserves_past(self):
        event=self.create(); self.edit(event,note='Tidligere unntak'); event.refresh_from_db()
        self.edit(event,'2027-03-31',start='2027-04-01',end='2027-04-01'); event.refresh_from_db()
        self.edit(event,'2027-02-28',scope='future',title='Ny fremtid')
        rows=self.list();self.assertEqual(rows[0]['note'],'Tidligere unntak');self.assertEqual(rows[-1]['start'],'2027-03-31');self.assertEqual(rows[-1]['title'],'Ny fremtid')
    def test_responses_own_and_visible(self):
        event=self.create(); self.response(event,actor=1)
        people=self.list()[0]['people']; self.assertEqual(next(p['status'] for p in people if p['id']==self.members[1].pk),'yes')
        with self.assertRaises(Conflict): self.response(event,actor=1,status='no')
        self.response(event,actor=1,status='no',version=1)
        self.response(event,actor=1,status='none',version=2)
        self.assertEqual(CalendarResponse.objects.get().status,'none')
    def test_nonparticipant_cannot_reply_even_admin(self):
        event=self.create(scope='selected',participants=[str(self.members[1].pk)])
        with self.assertRaises(PermissionDenied): self.response(event,actor=0)
        with self.assertRaises(PermissionDenied): self.response(event,actor=2)
        with self.assertRaises(PermissionDenied): self.response(event,actor=3)
    def test_response_reset_and_metadata_preservation(self):
        event=self.create();self.response(event);self.edit(event,title='Ny tittel');event.refresh_from_db()
        self.assertEqual(CalendarResponse.objects.count(),1)
        self.edit(event,start_time='19:00',end_time='20:00');self.assertEqual(CalendarResponse.objects.count(),0)
    def test_future_metadata_keeps_responses_past_and_future(self):
        event=self.create();self.response(event);self.response(event,'2027-03-31',actor=1)
        self.edit(event,'2027-02-28',scope='future',note='Nytt notat')
        self.assertEqual(CalendarResponse.objects.count(),2)
        self.assertEqual(self.list()[-1]['people'][1]['status'],'yes')
    def test_future_time_reset_does_not_change_past_reply(self):
        event=self.create();self.response(event);self.response(event,'2027-03-31')
        self.edit(event,'2027-02-28',scope='future',start_time='18:00',end_time='19:00')
        self.assertEqual(CalendarResponse.objects.count(),1)
        self.assertEqual(CalendarResponse.objects.get().original_date,date(2027,1,31))
    def test_weekly_local_walltime_across_dst(self):
        self.create(start='2027-03-21',end='2027-03-21',recurrence='weekly')
        rows=self.list(first='2027-03-21',last='2027-04-04')
        self.assertEqual([x['start_time'] for x in rows],['17:00']*3)
        self.assertNotEqual(cal.local_time(date(2027,3,21),'17:00').utcoffset(),cal.local_time(date(2027,3,28),'17:00').utcoffset())
    def test_dst_nonexistent_and_ambiguous_explicit(self):
        with self.assertRaises(ValidationError): self.create(start='2027-03-28',end='2027-03-28',start_time='02:30',end_time='03:30')
        with self.assertRaises(ValidationError): self.create(start='2027-10-31',end='2027-10-31',start_time='02:30',end_time='03:30')
        self.create(start='2027-10-31',end='2027-10-31',start_time='02:30',end_time='03:30',fold=1)
    def test_all_day_and_inclusive_until(self):
        self.create(start='2027-01-30',end='2027-02-02',all_day=True,recurrence='weekly',until='2027-02-06')
        rows=self.list(first='2027-02-01',last='2027-02-28');self.assertEqual([x['start'] for x in rows],['2027-01-30','2027-02-06'])
    def test_bounded_range_and_unknown_member(self):
        with self.assertRaises(ValidationError): self.list(first='2027-01-01',last='2027-12-31')
        with self.assertRaises(ValidationError): self.list(selected=str(self.members[3].pk))
    def test_database_guard_participants_and_responses(self):
        with self.assertRaises(IntegrityError),transaction.atomic(): CalendarEvent.objects.create(household=self.house,created_by=self.users[0],payload=self.payload(scope='selected',participants=[str(self.members[3].pk)]))
        event=self.create()
        with self.assertRaises(IntegrityError),transaction.atomic(): CalendarResponse.objects.create(event=event,original_date='2027-01-31',member=self.members[3],status='yes')
    def test_api_csrf_and_no_impersonation(self):
        event=self.create(); client=Client(enforce_csrf_checks=True);client.force_login(self.users[0])
        result=client.post(reverse('calendar_api'),data={'action':'respond'},content_type='application/json');self.assertEqual(result.status_code,403)
        page=client.get(reverse('calendar'));self.assertEqual(page.status_code,200)
        token=client.cookies['csrftoken'].value
        result=client.post(reverse('calendar_api'),data={'action':'respond','key':str(uuid.uuid4()),'event_id':str(event.pk),'original':'2027-01-31','revision':1,'status':'yes','response_revision':0,'member_id':self.members[1].pk},content_type='application/json',HTTP_X_CSRFTOKEN=token)
        self.assertEqual(result.status_code,400);self.assertEqual(CalendarResponse.objects.count(),0)
    def test_bad_api_payloads_and_months_are_not_server_errors(self):
        self.client.force_login(self.users[0])
        for payload in [None,[],{'title':'bad'},self.payload(all_day='false'),self.payload(participants='no')]:
            response=self.client.post(reverse('calendar_api'),data={'action':'create','key':str(uuid.uuid4()),'payload':payload},content_type='application/json');self.assertEqual(response.status_code,400)
        for month in ['0001-01','9999-12','nonsense']:
            self.assertEqual(self.client.get(reverse('calendar'),{'cal_month':month}).status_code,200)
    def test_unauthenticated_calendar_requires_session(self):
        self.assertEqual(self.client.get(reverse('calendar')).status_code,302)

    def test_bounded_series_occurrence_can_move_beyond_until(self):
        event=self.create(until='2027-01-31')
        self.edit(event,start='2027-02-04',end='2027-02-04')
        rows=self.list()
        self.assertEqual([x['start'] for x in rows],['2027-02-04'])
        self.assertEqual(rows[0]['original'],'2027-01-31')
    def test_edit_and_response_duplicate_post_is_idempotent(self):
        event=self.create();key=uuid.uuid4();payload=self.payload(title='Once')
        args=dict(event_id=event.pk,original='2027-01-31',revision=1,payload=payload)
        first=cal.mutate(self.users[0],'edit',key,**args)
        self.assertEqual(cal.mutate(self.users[0],'edit',key,**args),first)
        self.assertEqual(CalendarException.objects.count(),1)
        key=uuid.uuid4();args=dict(event_id=event.pk,original='2027-01-31',revision=2,status='yes',response_revision=0)
        first=cal.mutate(self.users[0],'respond',key,**args)
        self.assertEqual(cal.mutate(self.users[0],'respond',key,**args),first)
        self.assertEqual(CalendarResponse.objects.count(),1)
    def test_new_shared_member_starts_without_response(self):
        event=self.create();self.response(event)
        user=get_user_model().objects.create_user(username='newcalendar',email='newcalendar@example.test')
        member=Membership.objects.create(user=user,household=self.house,role='member')
        people=self.list()[0]['people'];self.assertEqual(next(p['status'] for p in people if p['id']==member.pk),'none')
    def test_participant_scope_change_resets_and_removes_right_to_reply(self):
        event=self.create();self.response(event,actor=1)
        current=cal.occurrence(event,date(2027,1,31))
        cal.mutate(self.users[0],'edit',uuid.uuid4(),event_id=event.pk,original='2027-01-31',revision=1,payload={**current,'scope':'selected','participants':[str(self.members[0].pk)]})
        self.assertEqual(CalendarResponse.objects.count(),0);event.refresh_from_db()
        with self.assertRaises(PermissionDenied):self.response(event,actor=1)

    def test_authenticated_account_without_family_is_forbidden(self):
        user=get_user_model().objects.create_user(username='nomembership',email='nomembership@example.test')
        self.client.force_login(user)
        self.assertRedirects(self.client.get(reverse('calendar')),reverse('family_gate'),fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse('calendar_data'),{'start':'2027-01-01','end':'2027-01-31'}).status_code,403)
        self.assertEqual(self.client.post(reverse('calendar_api'),data={'action':'create','key':str(uuid.uuid4()),'payload':self.payload()},content_type='application/json').status_code,403)
    def test_time_with_external_timezone_rejected(self):
        with self.assertRaises(ValidationError): self.create(start_time='17:00+03:00')

    def test_midnight_end_is_exclusive_but_all_day_end_inclusive(self):
        self.create(start='2027-01-31',end='2027-02-01',start_time='23:00',end_time='00:00',recurrence='none')
        self.assertEqual(self.list(first='2027-02-01',last='2027-02-01'),[])
        timed=self.list(first='2027-01-31',last='2027-01-31')[0]
        self.assertEqual(timed['end'],'2027-02-01');self.assertEqual(timed['display_end'],'2027-01-31')
        self.create(start='2027-01-31',end='2027-02-01',all_day=True,recurrence='none')
        self.assertEqual(len(self.list(first='2027-02-01',last='2027-02-01')),1)
    def test_midnight_grid_excludes_ending_day(self):
        self.create(start='2027-01-30',end='2027-01-31',start_time='23:00',end_time='00:00',recurrence='none')
        self.client.force_login(self.users[0])
        response=self.client.get(reverse('calendar'),{'cal_month':'2027-01'})
        day=next(d for w in response.context['weeks'] for d in w if d['date']==date(2027,1,31))
        self.assertEqual(day['events'],[])

    def test_future_metadata_discards_reply_to_replaced_moved_exception(self):
        event=self.create()
        self.edit(event,'2027-03-31',start='2027-04-01',end='2027-04-01');event.refresh_from_db()
        self.response(event,'2027-03-31')
        self.response(event,'2027-01-31')
        self.edit(event,'2027-02-28',scope='future',title='New title')
        self.assertEqual(CalendarResponse.objects.count(),1)
        self.assertEqual(CalendarResponse.objects.get().original_date,date(2027,1,31))
        self.assertEqual(self.list()[-1]['people'][0]['status'],'none')
    def test_future_metadata_discards_reply_when_exception_participants_replaced(self):
        event=self.create(scope='selected',participants=[str(self.members[0].pk)])
        current=cal.occurrence(event,date(2027,3,31))
        cal.mutate(self.users[0],'edit',uuid.uuid4(),event_id=event.pk,original='2027-03-31',revision=1,payload={**current,'participants':[str(self.members[1].pk)]})
        event.refresh_from_db();self.response(event,'2027-03-31',actor=1)
        self.edit(event,'2027-02-28',scope='future',title='New title')
        self.assertEqual(CalendarResponse.objects.count(),0)
        self.assertEqual(self.list()[-1]['participants'],[str(self.members[0].pk)])

    def test_future_segment_cannot_move_before_original_cutoff(self):
        event=self.create()
        with self.assertRaises(ValidationError):
            self.edit(event,'2027-02-28',scope='future',start='2027-01-31',end='2027-01-31')
        rows=self.list();identities=[row['canonical_id'] for row in rows]
        self.assertEqual(len(identities),len(set(identities)))
        self.assertEqual([row['start'] for row in rows],['2027-01-31','2027-02-28','2027-03-31'])
        # A single-occurrence exception can still move backwards without changing identity.
        self.edit(event,'2027-02-28',start='2027-01-31',end='2027-01-31')
        identities=[row['canonical_id'] for row in self.list()]
        self.assertEqual(len(identities),len(set(identities)))
    def test_single_editor_always_has_reset_policy_and_draft_guard(self):
        self.client.force_login(self.users[0]); response=self.client.get(reverse('calendar'))
        self.assertContains(response,'id="calendar-edit-policy"')
        self.assertContains(response,'data-calendar-form data-dirty-warning')
