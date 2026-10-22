import uuid
from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.urls import reverse
from django.utils import timezone
from .models import Household, Membership, Category, BillTemplate, BillOccurrence, Entry, CorrectionEvent, CorrectionCommand
from . import services, correction_services as corrections


class BillCorrectionsTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.month = self.today.replace(day=1)
        self.user = get_user_model().objects.create_user('correction-user', email='synthetic@example.invalid', password='synthetic-password')
        self.house = Household.objects.create(name='Synthetic correction household')
        self.member = Membership.objects.create(user=self.user, household=self.house, role='admin')
        self.category = Category.objects.create(household=self.house, created_by=self.user, name='Test')
        self.template = BillTemplate.objects.create(household=self.house, created_by=self.user, name='Regning', amount_ore=100000, first_due=self.month, category=self.category)
        services.materialize_template(self.template, self.month)
        self.bill = BillOccurrence.objects.get(template=self.template)

    def command(self, op, changes=None, reason='Test', event_id=None, key=None):
        self.bill.refresh_from_db()
        return corrections.correct_occurrence(self.user, self.bill.pk, op, self.bill.version, key or uuid.uuid4(), changes, reason, event_id)

    def test_correct_and_moved_slot_not_regenerated(self):
        following = services.next_month(self.month)
        self.command('correct', {'amount_ore': 90000, 'due_date': following})
        services.materialize_template(self.template, following)
        services.materialize_template(self.template, following)
        self.bill.refresh_from_db()
        self.assertEqual(BillOccurrence.objects.count(), 2)
        self.assertEqual(self.bill.recurrence_slot, self.month)
        self.assertEqual(self.bill.amount_ore, 90000)
        self.assertEqual(CorrectionEvent.objects.get().before['amount_ore'], 100000)

    def test_cancel_restore_and_repeat(self):
        key = uuid.uuid4()
        self.command('cancel', key=key)
        count = CorrectionEvent.objects.count()
        corrections.correct_occurrence(self.user, self.bill.pk, 'cancel', 1, key, reason='Test')
        self.assertEqual(CorrectionEvent.objects.count(), count)
        self.assertFalse(services.pending_bills(self.house, self.today).exists())
        services.materialize_template(self.template, self.month)
        self.assertEqual(BillOccurrence.objects.count(), 1)
        event = CorrectionEvent.objects.latest('id')
        self.command('restore', event_id=event.pk)
        self.assertEqual(services.total(services.pending_bills(self.house, self.today)), 100000)

    def test_reverse_correct_repay_preserves_original(self):
        payment = services.pay_bill(self.user, self.bill.pk, self.today, uuid.uuid4(), self.bill.version)
        corrections.entry_state(self.user, payment.pk, 'reverse', payment.version, uuid.uuid4(), 'Feilregistrering')
        event = CorrectionEvent.objects.filter(object_id=payment.pk).latest('id')
        self.command('correct', {'amount_ore': 90000})
        self.bill.refresh_from_db()
        services.pay_bill(self.user, self.bill.pk, self.today, uuid.uuid4(), self.bill.version)
        payment.refresh_from_db()
        self.assertFalse(payment.active)
        self.assertEqual(Entry.objects.filter(active=True).get().amount_ore, 90000)
        self.assertEqual(services.calculate(self.house, self.month)['ordinary'], 90000)
        with self.assertRaises(ValidationError):
            corrections.entry_state(self.user, payment.pk, 'restore', payment.version, uuid.uuid4(), event_id=event.pk)
        self.assertEqual(Entry.objects.count(), 2)

    def test_restore_same_payment_and_refund_guard(self):
        payment = services.pay_bill(self.user, self.bill.pk, self.today, uuid.uuid4(), self.bill.version)
        corrections.entry_state(self.user, payment.pk, 'reverse', payment.version, uuid.uuid4())
        event = CorrectionEvent.objects.filter(object_id=payment.pk).latest('id')
        payment.refresh_from_db()
        corrections.entry_state(self.user, payment.pk, 'restore', payment.version, uuid.uuid4(), event_id=event.pk)
        refund = Entry(household=self.house, created_by=self.user, kind='refund', original=payment, amount_ore=20000, effective_date=self.today, description='Refusjon')
        payment.refresh_from_db(); refund.original=payment
        services.save_entry(self.user, refund)
        with self.assertRaises(ValidationError): corrections.entry_state(self.user, payment.pk, 'reverse', payment.version, uuid.uuid4())
        self.assertEqual(services.calculate(self.house, self.month)['ordinary'], 80000)

    def test_conflict_payload_and_revoked_replay(self):
        key = uuid.uuid4()
        self.command('correct', {'amount_ore': 90000}, key=key)
        with self.assertRaises(services.Conflict): corrections.correct_occurrence(self.user, self.bill.pk, 'correct', 1, key, {'amount_ore': 80000}, 'Test')
        with self.assertRaises(services.Conflict): corrections.correct_occurrence(self.user, self.bill.pk, 'cancel', 1, uuid.uuid4(), reason='Test')
        self.member.role='member'; self.member.module_access={'bills':False}; self.member.save()
        with self.assertRaises(PermissionDenied): corrections.correct_occurrence(self.user, self.bill.pk, 'correct', 1, key, {'amount_ore':90000}, 'Test')
        self.assertEqual(CorrectionEvent.objects.count(), 1)

    def test_archive_resume_does_not_backfill_gap_or_remove_obligation(self):
        stop = services.next_month(self.month)
        restart = services.next_month(services.next_month(stop))
        corrections.revise_series(self.user, self.template.pk, 'archive', 1, uuid.uuid4(), stop, confirmed=[])
        self.template.refresh_from_db()
        services.materialize_template(self.template, services.next_month(stop))
        self.assertEqual(BillOccurrence.objects.count(), 1)
        self.assertEqual(services.total(services.pending_bills(self.house,self.today)),100000)
        corrections.revise_series(self.user,self.template.pk,'resume',self.template.version,uuid.uuid4(),restart,confirmed=[])
        self.template.refresh_from_db(); services.materialize_template(self.template,restart)
        self.assertEqual(set(BillOccurrence.objects.values_list('recurrence_slot',flat=True)),{self.month,restart})

    def test_csv_full_filter_safe_text_and_tenant(self):
        self.client.force_login(self.user)
        for i in range(52):
            Entry.objects.create(household=self.house,created_by=self.user,kind='expense',category=self.category,amount_ore=100,effective_date=self.today,description='=1+1')
        response=self.client.get(reverse('correction_export',args=['entry']),{'download':'1','status':'active'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.content.decode('utf-8-sig').count("'=1+1"),52)
        self.assertIn('no-store',response['Cache-Control'])

    def test_confirmation_required_and_draft_preserved_on_conflict(self):
        self.client.force_login(self.user)
        url=reverse('correction',args=['bill',self.bill.pk])
        data={'version':1,'key':str(uuid.uuid4()),'operation':'correct','name':'Rettet','amount':'900','due_date':self.today.isoformat(),'category':str(self.category.pk),'reason':'test'}
        response=self.client.post(url,data)
        self.assertContains(response,'Bekreft endring')
        self.bill.refresh_from_db(); self.assertEqual(self.bill.amount_ore,100000)
        self.command('correct',{'amount_ore':95000})
        response=self.client.post(url,data)
        self.assertEqual(response.status_code,409)
        self.assertContains(response,'Rettet',status_code=409)

    def test_payment_undo_redo_uses_same_identity(self):
        payment = services.pay_bill(self.user,self.bill.pk,self.today,uuid.uuid4(),1)
        identity, sequence = payment.pk, payment.sequence
        for operation in ('reverse','restore','restore','restore'):
            payment.refresh_from_db()
            event = CorrectionEvent.objects.filter(object_id=payment.pk).latest('id')
            corrections.entry_state(self.user,payment.pk,operation,payment.version,uuid.uuid4(),event_id=event.pk if operation=='restore' else None)
        payment.refresh_from_db()
        self.assertTrue(payment.active)
        self.assertEqual((payment.pk,payment.sequence),(identity,sequence))
        self.assertEqual(Entry.objects.count(),1)

    def test_savings_future_withdrawal_blocks_reverse_and_restore_redo(self):
        from .models import Asset
        goal = Asset.objects.create(household=self.house,created_by=self.user,name='Syntetisk mål',kind='savings',opening_date=self.month)
        deposit = services.save_entry(self.user,Entry(household=self.house,created_by=self.user,kind='deposit',amount_ore=10000,effective_date=self.month,description='Innskudd',asset=goal))
        withdrawal = services.save_entry(self.user,Entry(household=self.house,created_by=self.user,kind='withdrawal',amount_ore=10000,effective_date=self.today,description='Uttak',asset=goal))
        with self.assertRaises(ValidationError): corrections.entry_state(self.user,deposit.pk,'reverse',1,uuid.uuid4())
        self.assertEqual(services.savings_balance(goal),0)
        corrections.entry_state(self.user,withdrawal.pk,'reverse',1,uuid.uuid4())
        withdrawal.refresh_from_db()
        event=CorrectionEvent.objects.filter(object_id=withdrawal.pk).latest('id')
        corrections.entry_state(self.user,withdrawal.pk,'restore',withdrawal.version,uuid.uuid4(),event_id=event.pk)
        self.assertEqual(services.savings_balance(goal),0)

    def test_fund_reverse_and_cancel_reconciles_topup(self):
        from .models import Asset, FundTopUp
        fund = Asset.objects.create(household=self.house,created_by=self.user,name='Syntetisk fond',kind='fund',opening_date=self.month,opening_ore=10000)
        template=BillTemplate.objects.create(household=self.house,created_by=self.user,name='Fondsregning',first_due=self.month,monthly=False,accounting_class='fund',asset=fund,amount_ore=30000)
        services.materialize_template(template,self.month); bill=BillOccurrence.objects.get(template=template)
        payment=services.pay_bill(self.user,bill.pk,self.today,uuid.uuid4(),1)
        self.assertEqual(FundTopUp.objects.get(occurrence=bill).amount_ore,20000)
        corrections.entry_state(self.user,payment.pk,'reverse',1,uuid.uuid4())
        bill.refresh_from_db()
        corrections.correct_occurrence(self.user,bill.pk,'cancel',bill.version,uuid.uuid4(),reason='Feil')
        self.assertEqual(FundTopUp.objects.get(occurrence=bill).amount_ore,0)
        self.assertEqual(services.fund_balance(fund,self.today),10000)

    def test_history_rechecks_hidden_old_relation(self):
        from .models import Asset
        debt=Asset.objects.create(household=self.house,created_by=self.user,name='Skjult gjeld',kind='debt',opening_date=self.month)
        entry=services.save_entry(self.user,Entry(household=self.house,created_by=self.user,kind='debt',amount_ore=100,effective_date=self.today,description='Gammel kobling',asset=debt))
        entry.kind='expense'; entry.asset=None; entry.category=self.category; entry.idempotency_key=uuid.uuid4()
        services.save_entry(self.user,entry,entry.version)
        self.member.role='member';self.member.module_access={'debt':False};self.member.save()
        self.assertEqual(corrections.visible_history(self.member,entry),[])
        event=CorrectionEvent.objects.filter(object_id=entry.pk).latest('id')
        with self.assertRaises(PermissionDenied): corrections.entry_state(self.user,entry.pk,'restore',entry.version,uuid.uuid4(),event_id=event.pk)

    def test_series_manifest_and_individual_override(self):
        future=services.next_month(self.month)
        services.materialize_template(self.template,services.next_month(future))
        individual=BillOccurrence.objects.get(template=self.template,recurrence_slot=future)
        corrections.correct_occurrence(self.user,individual.pk,'correct',1,uuid.uuid4(),{'amount_ore':70000})
        targets=corrections.affected(self.template,future)
        manifest=[[str(row.pk),row.version] for row in targets]
        with self.assertRaises(services.Conflict): corrections.revise_series(self.user,self.template.pk,'revise',1,uuid.uuid4(),future,{'amount_ore':80000},[])
        corrections.revise_series(self.user,self.template.pk,'revise',1,uuid.uuid4(),future,{'amount_ore':80000},manifest)
        individual.refresh_from_db();self.assertEqual(individual.amount_ore,70000)
        self.assertEqual(BillOccurrence.objects.get(pk=targets[0].pk).amount_ore,80000)

    def test_foreign_get_and_csv_no_metadata(self):
        other=get_user_model().objects.create_user('foreign-correction')
        foreign=Household.objects.create(name='Foreign')
        Membership.objects.create(user=other,household=foreign,role='admin')
        self.client.force_login(other)
        for name in ('correction','correction_history'):
            self.assertEqual(self.client.get(reverse(name,args=['bill',self.bill.pk])).status_code,404)
        response=self.client.get(reverse('correction_export',args=['bill']),{'download':1})
        self.assertNotIn(str(self.bill.pk),response.content.decode())

    def test_edit_entry_undo_redo_and_changed_payload(self):
        entry=services.save_entry(self.user,Entry(household=self.house,created_by=self.user,kind='expense',amount_ore=100,effective_date=self.today,description='Før',category=self.category))
        entry.description='Etter';entry.amount_ore=200;entry.idempotency_key=uuid.uuid4()
        services.save_entry(self.user,entry,1)
        event=CorrectionEvent.objects.filter(object_id=entry.pk).latest('id')
        corrections.entry_state(self.user,entry.pk,'restore',2,uuid.uuid4(),event_id=event.pk)
        entry.refresh_from_db();self.assertEqual(entry.amount_ore,100)
        event=CorrectionEvent.objects.filter(object_id=entry.pk).latest('id')
        corrections.entry_state(self.user,entry.pk,'restore',entry.version,uuid.uuid4(),event_id=event.pk)
        entry.refresh_from_db();self.assertEqual(entry.amount_ore,200)
 

    def test_dated_series_before_first_due_out_of_order_and_stopped_revision(self):
        start = services.next_month(self.month)
        december = services.next_month(services.next_month(start))
        template = BillTemplate.objects.create(household=self.house, created_by=self.user, name='Future', amount_ore=10000, first_due=start.replace(day=20), category=self.category)
        corrections.revise_series(self.user,template.pk,'revise',1,uuid.uuid4(),start,{'amount_ore':20000},[])
        template.refresh_from_db(); services.materialize_template(template,december)
        first=BillOccurrence.objects.get(template=template,recurrence_slot=start)
        self.assertEqual(first.amount_ore,20000)
        manifest=[[str(x.pk),x.version] for x in corrections.affected(template,december)]
        corrections.revise_series(self.user,template.pk,'revise',template.version,uuid.uuid4(),december,{'amount_ore':40000},manifest)
        template.refresh_from_db()
        middle=services.next_month(start)
        manifest=[[str(x.pk),x.version] for x in corrections.affected(template,middle)]
        corrections.revise_series(self.user,template.pk,'revise',template.version,uuid.uuid4(),middle,{'amount_ore':30000},manifest)
        self.assertEqual(BillOccurrence.objects.get(template=template,recurrence_slot=december).amount_ore,40000)
        self.assertEqual(corrections.series_state(template,december)[1]['amount_ore'],40000)
        template.refresh_from_db()
        corrections.revise_series(self.user,template.pk,'archive',template.version,uuid.uuid4(),start,confirmed=[])
        template.refresh_from_db()
        manifest=[[str(x.pk),x.version] for x in corrections.affected(template,start)]
        corrections.revise_series(self.user,template.pk,'revise',template.version,uuid.uuid4(),start,{'amount_ore':25000},manifest)
        template.refresh_from_db(); self.assertFalse(corrections.series_state(template,start)[0])
        self.assertFalse(corrections.series_state(template,december)[0])
        with self.assertRaises(ValidationError): corrections.revise_series(self.user,template.pk,'revise',template.version,uuid.uuid4(),start,{'category_id':None},[[str(x.pk),x.version] for x in corrections.affected(template,start)])

    def test_series_http_confirmation_retry_uses_original_manifest(self):
        future=services.next_month(self.month)
        services.materialize_template(self.template,future)
        self.client.force_login(self.user)
        url=reverse('correction',args=['series',self.template.pk])
        data={'version':1,'key':str(uuid.uuid4()),'operation':'revise','start':future.isoformat(),'name':'Changed','amount':'850','category':str(self.category.pk),'reason':'Test'}
        preview=self.client.post(url,data)
        self.assertEqual(preview.status_code,200)
        data['confirmation']=preview.context['confirmation']
        self.assertEqual(self.client.post(url,data).status_code,302)
        count=CorrectionEvent.objects.count()
        self.assertEqual(self.client.post(url,data).status_code,302)
        self.assertEqual(CorrectionEvent.objects.count(),count)
        data['amount']='851'
        self.assertEqual(self.client.post(url,data).status_code,409)

    def test_entry_edit_http_confirm_retry_and_no_preview_writes(self):
        entry=services.save_entry(self.user,Entry(household=self.house,created_by=self.user,kind='expense',category=self.category,amount_ore=10000,effective_date=self.today,description='Before'))
        self.client.force_login(self.user); url=reverse('edit',args=['entry',entry.pk])
        form=self.client.get(url).context['form']
        draft_key=str(form['command_key'].value())
        self.assertNotEqual(draft_key,str(entry.idempotency_key))
        data={'version':entry.version,'command_key':draft_key,'idempotency_key':str(entry.idempotency_key),'kind':'expense','description':'After','effective_date':self.today.isoformat(),'category':str(self.category.pk),'amount':'200','fee_ore':0,'received':'on'}
        counts=(Entry.objects.count(),CorrectionEvent.objects.count(),CorrectionCommand.objects.count())
        self.house.refresh_from_db(); seq=self.house.entry_sequence
        preview=self.client.post(url,data)
        self.assertContains(preview,'Bekreft endring')
        self.assertContains(preview,'type="hidden" name="description"')
        draft=self.client.post(url,{**data,'edit_draft':'1','confirmation':preview.context['preview']['confirmation']})
        self.assertEqual(draft.context['form']['description'].value(),'After')
        self.assertEqual(str(draft.context['form']['command_key'].value()),draft_key)
        self.assertEqual((Entry.objects.count(),CorrectionEvent.objects.count(),CorrectionCommand.objects.count()),counts)
        self.house.refresh_from_db();self.assertEqual(self.house.entry_sequence,seq)
        entry.refresh_from_db();self.assertEqual(entry.amount_ore,10000)
        data['confirmation']=preview.context['preview']['confirmation']
        self.assertEqual(self.client.post(url,data).status_code,302)
        saved_count=CorrectionEvent.objects.count()
        self.assertEqual(self.client.post(url,data).status_code,302)
        self.assertEqual(CorrectionEvent.objects.count(),saved_count)
        entry.refresh_from_db();self.assertEqual(entry.amount_ore,20000)

    def test_economic_preview_debt_max_fund_and_move_months(self):
        from .models import Asset, MonthPlan, FundTopUp
        debt=Asset.objects.create(household=self.house,created_by=self.user,name='Debt preview',kind='debt',opening_date=self.month,opening_ore=100000)
        MonthPlan.objects.create(household=self.house,created_by=self.user,month=self.month,asset=debt,amount_ore=200000)
        template=BillTemplate.objects.create(household=self.house,created_by=self.user,name='Debt',amount_ore=100000,first_due=self.month,monthly=False,asset=debt,accounting_class='debt')
        services.materialize_template(template,self.month);bill=BillOccurrence.objects.get(template=template)
        before=(CorrectionEvent.objects.count(),CorrectionCommand.objects.count(),FundTopUp.objects.count(),BillOccurrence.objects.count())
        effects=corrections.economic_preview(self.user,lambda:corrections.correct_occurrence(self.user,bill.pk,'correct',1,uuid.uuid4(),{'amount_ore':90000}),[self.month])
        self.assertEqual(effects[0]['delta'],0)
        self.assertEqual((CorrectionEvent.objects.count(),CorrectionCommand.objects.count(),FundTopUp.objects.count(),BillOccurrence.objects.count()),before)
        bill.refresh_from_db();self.assertEqual(bill.amount_ore,100000)
        future=services.next_month(self.month)
        effects=corrections.economic_preview(self.user,lambda:corrections.correct_occurrence(self.user,self.bill.pk,'correct',1,uuid.uuid4(),{'due_date':future}),[self.month,future])
        self.assertEqual(effects[0]['delta'],100000)
        self.assertEqual({e['month'] for e in effects},{self.month,future})
        fund=Asset.objects.create(household=self.house,created_by=self.user,name='Fund preview',kind='fund',opening_date=self.month,opening_ore=500000)
        template=BillTemplate.objects.create(household=self.house,created_by=self.user,name='Fund',amount_ore=100000,first_due=self.month,monthly=False,asset=fund,accounting_class='fund')
        services.materialize_template(template,self.month);fb=BillOccurrence.objects.get(template=template)
        topup_count=FundTopUp.objects.count()
        effects=corrections.economic_preview(self.user,lambda:corrections.correct_occurrence(self.user,fb.pk,'correct',1,uuid.uuid4(),{'amount_ore':90000}),[self.month])
        self.assertEqual(effects[0]['delta'],0)
        self.assertEqual(FundTopUp.objects.count(),topup_count)

    def test_bill_history_includes_payment_reversal_and_refund_hint(self):
        payment=services.pay_bill(self.user,self.bill.pk,self.today,uuid.uuid4(),1)
        corrections.entry_state(self.user,payment.pk,'reverse',1,uuid.uuid4())
        events=corrections.visible_history(self.member,self.bill)
        self.assertTrue(any(event.object_id==payment.pk and event.operation=='reverse' for event in events))
        payment.refresh_from_db();event=CorrectionEvent.objects.filter(object_id=payment.pk).latest('id')
        corrections.entry_state(self.user,payment.pk,'restore',payment.version,uuid.uuid4(),event_id=event.pk)
        self.client.force_login(self.user)
        page=self.client.get(reverse('page',args=['regninger']))
        self.assertContains(page,f'original={payment.pk}')
        refund=self.client.get(reverse('create',args=['entry']),{'entry_kind':'refund','original':str(payment.pk)})
        self.assertEqual(str(refund.context['form']['original'].value()),str(payment.pk))

    def test_exact_export_filters_and_hidden_rows(self):
        import csv,io
        from .models import Asset
        second=Category.objects.create(household=self.house,created_by=self.user,name='Other')
        debt=Asset.objects.create(household=self.house,created_by=self.user,name='Hidden debt',kind='debt',opening_date=self.month)
        def entry(**changes):
            data=dict(household=self.house,created_by=self.user,kind='expense',category=self.category,amount_ore=100,effective_date=self.today,description='Filter')
            data.update(changes);return Entry.objects.create(**data)
        wanted=[entry(description=f'=wanted {i}') for i in range(52)]
        excluded=[entry(category=second),entry(active=False),entry(effective_date=self.month-timedelta(days=1)),entry(kind='debt',asset=debt,category=self.category)]
        other=get_user_model().objects.create_user('filter-foreign');foreign=Household.objects.create(name='Foreign filter')
        excluded.append(entry(household=foreign,created_by=other,category=None))
        self.member.role='member';self.member.module_access={'debt':False};self.member.save()
        self.client.force_login(self.user)
        query={'date_from':self.today.isoformat(),'date_to':self.today.isoformat(),'category':str(self.category.pk),'status':'active'}
        url=reverse('correction_export',args=['entry'])
        html=self.client.get(url,query)
        self.assertEqual({row.pk for row in html.context['rows']},{row.pk for row in wanted})
        csv_response=self.client.get(url,{**query,'download':'1'})
        records=list(csv.reader(io.StringIO(csv_response.content.decode('utf-8-sig')),delimiter=';'))[1:]
        self.assertEqual({record[-1] for record in records},{str(row.pk) for row in wanted})
        for row in excluded: self.assertNotContains(html,str(row.pk))
        self.assertTrue(all(record[2].startswith("'=wanted") for record in records))

    def test_exact_bill_export_status_category_period_and_hidden_class(self):
        import csv,io
        from .models import Asset
        other_category=Category.objects.create(household=self.house,created_by=self.user,name='Excluded category')
        hidden=Asset.objects.create(household=self.house,created_by=self.user,name='Hidden bill debt',kind='debt',opening_date=self.month)
        def bill(**changes):
            data=dict(household=self.house,created_by=self.user,name='Export bill',amount_ore=1000,first_due=self.today,category=self.category,monthly=False)
            cancelled=changes.pop('cancelled',False)
            data.update(changes)
            template=BillTemplate.objects.create(**data)
            services.materialize_template(template,services.month_start(data['first_due']))
            result=BillOccurrence.objects.get(template=template)
            if cancelled:
                result.cancelled=True;result.save()
            return result
        wanted=bill()
        paid=bill();services.pay_bill(self.user,paid.pk,self.today,uuid.uuid4(),1)
        excluded=[paid,bill(cancelled=True),bill(category=other_category),bill(first_due=self.month-timedelta(days=1)),bill(asset=hidden,accounting_class='debt')]
        # Existing setup bill falls inside the period only if today is day one; cancel it explicitly.
        self.bill.cancelled=True;self.bill.save()
        self.member.role='member';self.member.module_access={'debt':False};self.member.save()
        self.client.force_login(self.user)
        query={'date_from':self.today.isoformat(),'date_to':self.today.isoformat(),'category':str(self.category.pk),'status':'unpaid'}
        url=reverse('correction_export',args=['bill'])
        html=self.client.get(url,query)
        self.assertEqual({row.pk for row in html.context['rows']},{wanted.pk})
        response=self.client.get(url,{**query,'download':1})
        records=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig')),delimiter=';'))[1:]
        self.assertEqual({record[-1] for record in records},{str(wanted.pk)})
        for row in excluded:self.assertNotContains(html,str(row.pk))


    def test_history_explains_all_changed_financial_fields(self):
        from decimal import Decimal
        from .models import Asset
        recipient=Asset.objects.create(household=self.house,created_by=self.user,kind='recipient',name='Original recipient',opening_date=self.month)
        changed=Asset.objects.create(household=self.house,created_by=self.user,kind='recipient',name='New recipient',opening_date=self.month)
        entry=services.save_entry(self.user,Entry(household=self.house,created_by=self.user,kind='remittance',amount_ore=100000,effective_date=self.today,description='Transfer',category=self.category,asset=recipient,currency='EUR',original_amount=Decimal('100'),exchange_rate=Decimal('10')))
        entry.asset=changed;entry.currency='USD';entry.original_amount=Decimal('50');entry.exchange_rate=Decimal('11');entry.fee_ore=100
        services.save_entry(self.user,entry,1,command_key=uuid.uuid4())
        self.client.force_login(self.user)
        response=self.client.get(reverse('correction_history',args=['entry',entry.pk]))
        for label in ('Opprinnelig valutabeløp','NOK per valutaenhet','Gebyr NOK','Valuta','New recipient','Original recipient'):
            self.assertContains(response,label)
        self.assertNotContains(response,'asset_id')
        income=services.save_entry(self.user,Entry(household=self.house,created_by=self.user,kind='income',amount_ore=10000,effective_date=self.today,description='Income',received=False,income_attribution='Before'))
        income.received=True;income.income_attribution='After'
        services.save_entry(self.user,income,1,command_key=uuid.uuid4())
        response=self.client.get(reverse('correction_history',args=['entry',income.pk]))
        for label in ('Inntektsstatus','Forventet','Mottatt','Inntekten tilhører'):
            self.assertContains(response,label)


    def test_http_validation_failure_shows_reason_without_confirm(self):
        from .models import Asset
        payment=services.pay_bill(self.user,self.bill.pk,self.today,uuid.uuid4(),1)
        services.save_entry(self.user,Entry(household=self.house,created_by=self.user,kind='refund',original=payment,amount_ore=100,effective_date=self.today,description='Actual refund'))
        self.client.force_login(self.user)
        data={'operation':'reverse','version':1,'key':str(uuid.uuid4()),'reason':'Feil'}
        response=self.client.post(reverse('correction',args=['entry',payment.pk]),data)
        self.assertContains(response,'aktive refusjoner',status_code=400)
        self.assertNotContains(response,'Bekreft endring',status_code=400)
        self.assertIsNone(response.context['preview'])
        goal=Asset.objects.create(household=self.house,created_by=self.user,kind='savings',name='Goal',opening_date=self.month)
        deposit=services.save_entry(self.user,Entry(household=self.house,created_by=self.user,kind='deposit',asset=goal,amount_ore=1000,effective_date=self.month,description='Deposit'))
        services.save_entry(self.user,Entry(household=self.house,created_by=self.user,kind='withdrawal',asset=goal,amount_ore=1000,effective_date=self.today,description='Withdrawal'))
        data['key']=str(uuid.uuid4())
        response=self.client.post(reverse('correction',args=['entry',deposit.pk]),data)
        self.assertContains(response,'negativ målbeholdning',status_code=400)
        self.assertNotContains(response,'Bekreft endring',status_code=400)

    def test_stale_draft_recovery_preserves_fields_and_requires_new_confirmation(self):
        self.client.force_login(self.user)
        url=reverse('correction',args=['bill',self.bill.pk])
        data={'operation':'correct','version':1,'key':str(uuid.uuid4()),'name':'Kept draft','amount':'800','due_date':self.today.isoformat(),'category':str(self.category.pk),'reason':'Fix'}
        preview=self.client.post(url,data)
        data['confirmation']=preview.context['confirmation']
        self.command('correct',{'amount_ore':90000})
        self.assertEqual(self.client.post(url,data).status_code,409)
        recovered=self.client.post(url,{**data,'refresh_version':'1'})
        form=recovered.context['form']
        self.assertEqual(form['name'].value(),'Kept draft')
        self.assertEqual(int(form['version'].value()),2)
        self.assertNotEqual(str(form['key'].value()),data['key'])
        self.assertNotIn('confirmation',form.data)
        self.assertIsNone(recovered.context['preview'])
        self.bill.refresh_from_db();self.assertEqual(self.bill.amount_ore,90000)
        new_data={field.name:field.value() if field.value() is not None else '' for field in form}
        fresh=self.client.post(url,new_data)
        self.assertContains(fresh,'Bekreft endring')
        self.bill.refresh_from_db();self.assertEqual(self.bill.amount_ore,90000)
        new_data['confirmation']=fresh.context['confirmation']
        self.assertEqual(self.client.post(url,new_data).status_code,302)
        self.bill.refresh_from_db();self.assertEqual(self.bill.amount_ore,80000)
        entry=services.save_entry(self.user,Entry(household=self.house,created_by=self.user,kind='income',amount_ore=10000,effective_date=self.today,description='Original'))
        url=reverse('edit',args=['entry',entry.pk])
        data={'kind':'income','amount':'200','description':'Kept entry draft','effective_date':self.today.isoformat(),'received':'on','fee_ore':0,'version':1,'command_key':str(uuid.uuid4()),'idempotency_key':str(entry.idempotency_key)}
        entry.description='Newer';services.save_entry(self.user,entry,1,command_key=uuid.uuid4())
        self.assertEqual(self.client.post(url,data).status_code,409)
        recovered=self.client.post(url,{**data,'refresh_version':'1','confirmation':'discard-old'})
        form=recovered.context['form']
        self.assertEqual(form['description'].value(),'Kept entry draft')
        self.assertEqual(int(form['version'].value()),2)
        self.assertNotEqual(str(form['command_key'].value()),data['command_key'])
        self.assertNotIn('confirmation',form.data)
        entry.refresh_from_db();self.assertEqual(entry.description,'Newer')
        new_data={field.name:field.value() if field.value() is not None else '' for field in form}
        fresh=self.client.post(url,new_data)
        self.assertContains(fresh,'Bekreft endring')
        new_data['confirmation']=fresh.context['preview']['confirmation']
        self.assertEqual(self.client.post(url,new_data).status_code,302)
        entry.refresh_from_db();self.assertEqual(entry.description,'Kept entry draft')

    def test_extreme_preview_dates_reject_before_month_loop(self):
        from unittest.mock import Mock,patch
        mutate=Mock()
        counts=(CorrectionCommand.objects.count(),CorrectionEvent.objects.count(),BillOccurrence.objects.count())
        with patch('budget.services.next_month',side_effect=AssertionError('Month loop entered')):
            for extreme in (date(1,1,1),date(9999,12,31)):
                with self.assertRaisesRegex(ValidationError,'120 måneder'):
                    corrections.economic_preview(self.user,mutate,[extreme])
        mutate.assert_not_called()
        self.assertEqual((CorrectionCommand.objects.count(),CorrectionEvent.objects.count(),BillOccurrence.objects.count()),counts)

    def test_preview_shows_in_plan_savings_and_funded_fund_balances(self):
        from .models import Asset,MonthPlan
        goal=Asset.objects.create(household=self.house,created_by=self.user,kind='savings',name='Planned goal',opening_date=self.month)
        MonthPlan.objects.create(household=self.house,created_by=self.user,month=self.month,asset=goal,amount_ore=20000)
        deposit=services.save_entry(self.user,Entry(household=self.house,created_by=self.user,kind='deposit',asset=goal,amount_ore=10000,effective_date=self.today,description='Deposit'))
        effects=corrections.economic_preview(self.user,lambda:corrections.entry_state(self.user,deposit.pk,'reverse',1,uuid.uuid4()),[self.today])
        self.assertEqual(effects[0]['delta'],0)
        self.assertEqual(effects[0]['balances'],[{'name':'Planned goal','kind':'savings','before':10000,'after':0}])
        fund=Asset.objects.create(household=self.house,created_by=self.user,kind='fund',name='Funded fund',opening_date=self.month,opening_ore=50000)
        template=BillTemplate.objects.create(household=self.house,created_by=self.user,first_due=self.today,name='Fund bill',amount_ore=10000,asset=fund,accounting_class='fund',monthly=False)
        services.materialize_template(template,self.month);bill=BillOccurrence.objects.get(template=template)
        payment=services.pay_bill(self.user,bill.pk,self.today,uuid.uuid4(),1)
        effects=corrections.economic_preview(self.user,lambda:corrections.entry_state(self.user,payment.pk,'reverse',1,uuid.uuid4()),[self.today])
        self.assertEqual(effects[0]['delta'],0)
        self.assertIn({'name':'Funded fund','kind':'fund','before':40000,'after':50000},effects[0]['balances'])

    def test_restore_confirmation_fields_and_known_payment_conflict_history(self):
        from .models import Asset
        goal=Asset.objects.create(household=self.house,created_by=self.user,kind='savings',name='Restore goal',opening_date=self.month)
        entry=services.save_entry(self.user,Entry(household=self.house,created_by=self.user,kind='deposit',asset=goal,amount_ore=10000,effective_date=self.today,description='Saved'))
        entry.kind='income';entry.asset=None;entry.received=False
        services.save_entry(self.user,entry,1,command_key=uuid.uuid4())
        event=CorrectionEvent.objects.filter(object_id=entry.pk).latest('id')
        self.client.force_login(self.user)
        response=self.client.post(reverse('correction',args=['entry',entry.pk]),{'operation':'restore','version':entry.version,'key':str(uuid.uuid4()),'event':event.pk})
        for label in ('Posttype','Spareinnskudd','Restore goal','Inntektsstatus'):
            self.assertContains(response,label)
        payment=services.pay_bill(self.user,self.bill.pk,self.today,uuid.uuid4(),1)
        corrections.entry_state(self.user,payment.pk,'reverse',1,uuid.uuid4())
        event=CorrectionEvent.objects.filter(object_id=payment.pk).latest('id')
        self.command('correct',{'amount_ore':95000})
        history=self.client.get(reverse('correction_history',args=['entry',payment.pk]))
        self.assertNotContains(history,f'operation=restore&amp;event={event.pk}')
        self.assertContains(history,'nyere betaling')
        self.assertContains(history,'Økonomisk virkningsdato')


from django.test import TransactionTestCase
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class CorrectionMigrationTests(TransactionTestCase):
    old = ('budget', '0013_membership_module_access')
    new = ('budget', '0014_correctioncommand_correctionevent_seriesrevision_and_more')

    def tearDown(self):
        # Restore current schema before TransactionTestCase flush and later tests.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_upgrade_preserves_source_identity_and_collision_is_atomic(self):
        executor=MigrationExecutor(connection)
        executor.migrate([self.old])
        apps=executor.loader.project_state([self.old]).apps
        User=apps.get_model('auth','User'); House=apps.get_model('budget','Household')
        CategoryOld=apps.get_model('budget','Category'); Template=apps.get_model('budget','BillTemplate')
        Bill=apps.get_model('budget','BillOccurrence'); OldEntry=apps.get_model('budget','Entry')
        user=User.objects.create(username='synthetic-migration')
        house=House.objects.create(name='Synthetic upgrade',entry_sequence=1)
        category=CategoryOld.objects.create(household=house,created_by=user,name='Preserved')
        template=Template.objects.create(household=house,created_by=user,name='Existing',first_due=date(2026,9,1),amount_ore=12345,category=category)
        bill=Bill.objects.create(household=house,created_by=user,template=template,name='Existing',due_date=date(2026,9,1),amount_ore=12345,category=category,accounting_class='ordinary')
        duplicate=Bill.objects.create(household=house,created_by=user,template=template,name='Collision',due_date=date(2026,9,2),amount_ore=678,category=category,accounting_class='ordinary')
        entry=OldEntry.objects.create(household=house,created_by=user,kind='expense',amount_ore=12345,effective_date=date(2026,9,1),description='Preserved entry',category=category,occurrence=bill,sequence=1)
        Batch=apps.get_model('budget','ImportBatch'); Record=apps.get_model('budget','ImportRecord')
        batch=Batch.objects.create(household=house,created_by=user,series='synthetic-only',sha256='a'*64)
        source=Record.objects.create(household=house,created_by=user,batch=batch,source_id='synthetic-row',source_kind='expense',raw={'amount':'123.45'},target_id=entry.pk)
        try:
            with self.assertRaisesRegex(RuntimeError,'Recurrence slot collision'):
                MigrationExecutor(connection).migrate([self.new])
            self.assertEqual(OldEntry.objects.get(pk=entry.pk).amount_ore,12345)
            self.assertEqual(Bill.objects.count(),2)
        finally:
            Bill.objects.filter(pk=duplicate.pk).update(due_date=date(2026,10,1))
            MigrationExecutor(connection).migrate([self.new])
        preserved=Entry.objects.get(pk=entry.pk)
        self.assertEqual((preserved.amount_ore,preserved.effective_date,preserved.sequence,preserved.occurrence_id),(12345,date(2026,9,1),1,bill.pk))
        self.assertTrue(preserved.active)
        self.assertEqual(BillOccurrence.objects.get(pk=bill.pk).recurrence_slot,date(2026,9,1))
        from .models import ImportRecord
        self.assertEqual(ImportRecord.objects.get(pk=source.pk).target_id,entry.pk)

class ConcurrentCorrectionTests(TransactionTestCase):
    def test_reverse_restore_retry_and_competing_versions(self):
        from concurrent.futures import ThreadPoolExecutor
        from django.db import close_old_connections
        self.assertEqual(connection.vendor,'postgresql')
        user=get_user_model().objects.create_user('concurrent-correction')
        house=Household.objects.create(name='Concurrent synthetic')
        Membership.objects.create(user=user,household=house,role='admin')
        category=Category.objects.create(household=house,created_by=user,name='Synthetic')
        today=timezone.localdate()
        template=BillTemplate.objects.create(household=house,created_by=user,name='Concurrent',amount_ore=10000,first_due=today,category=category)
        services.materialize_template(template,today.replace(day=1));bill=BillOccurrence.objects.get(template=template)
        payment=services.pay_bill(user,bill.pk,today,uuid.uuid4(),1)
        def run(operation,version,keys,event_id=None):
            def command(key):
                close_old_connections()
                try:
                    actor=get_user_model().objects.get(pk=user.pk)
                    return str(corrections.entry_state(actor,payment.pk,operation,version,key,event_id=event_id).pk)
                except services.Conflict:
                    return 'conflict'
                finally: close_old_connections()
            with ThreadPoolExecutor(max_workers=2) as pool: return list(pool.map(command,keys))
        key=uuid.uuid4();before=CorrectionEvent.objects.count()
        self.assertEqual(run('reverse',1,[key,key]),[str(payment.pk)]*2)
        self.assertEqual(CorrectionEvent.objects.count(),before+1)
        event=CorrectionEvent.objects.filter(object_id=payment.pk).latest('id')
        key=uuid.uuid4();before=CorrectionEvent.objects.count()
        self.assertEqual(run('restore',2,[key,key],event.pk),[str(payment.pk)]*2)
        self.assertEqual(CorrectionEvent.objects.count(),before+1)
        self.assertEqual(Entry.objects.filter(occurrence=bill,active=True).count(),1)
        results=run('reverse',3,[uuid.uuid4(),uuid.uuid4()])
        self.assertEqual(results.count('conflict'),1)
        self.assertEqual(Entry.objects.filter(occurrence=bill,active=True).count(),0)
