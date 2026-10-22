from .financial_test_helpers import install_area
from .financial_areas import area_scope, create_area
import uuid
from concurrent.futures import ThreadPoolExecutor
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from .tests_documents import DocumentTests
from .models import Entry, ShoppingTrip, Household, Membership, Category, CorrectionEvent
from . import shopping_services as shop, document_services as docs, correction_services, services


class ShoppingTests(DocumentTests):
    # Inherits document contracts, exercised alongside shopping links.
    def listing(self):
        listing = shop.save_list(self.user, 'Felles', uuid.uuid4())
        item = shop.save_item(self.user, listing.pk, listing.version, uuid.uuid4(), name='Melk', quantity='2', purchased=True)
        listing.refresh_from_db()
        return listing, item

    def test_shared_edits_conflicts_and_no_posting(self):
        listing, item = self.listing()
        other = get_user_model().objects.create_user(username='shopping-other')
        Membership.objects.create(user=other, household=self.house, role='member')
        shop.save_item(other, listing.pk, listing.version, uuid.uuid4(), item.pk, name='Havremelk', purchased=False)
        self.assertFalse(Entry.objects.exists())
        with self.assertRaises(services.Conflict): shop.save_item(self.user, listing.pk, listing.version, uuid.uuid4(), item.pk, purchased=True)
        item.refresh_from_db()
        self.assertEqual(item.name, 'Havremelk')

    def test_complete_retry_late_receipt_reverse_restore_keep_one_entry(self):
        listing, _ = self.listing()
        key, version = uuid.uuid4(), listing.version
        trip = shop.complete_trip(self.user, listing.pk, version, key, 'Butikk', self.today, 125000, self.category.pk)
        again = shop.complete_trip(self.user, listing.pk, version, key, 'Butikk', self.today, 125000, self.category.pk)
        self.assertEqual(trip.pk, again.pk)
        doc = self.draft()
        shop.attach_receipt(self.user, trip.pk, doc.pk, trip.version, uuid.uuid4())
        correction_services.entry_state(self.user, trip.entry_id, 'reverse', trip.entry.version, uuid.uuid4(), 'Test')
        event = CorrectionEvent.objects.filter(object_id=trip.entry_id).latest('id')
        trip.entry.refresh_from_db()
        correction_services.entry_state(self.user, trip.entry_id, 'restore', trip.entry.version, uuid.uuid4(), event_id=event.pk)
        trip.refresh_from_db()
        doc.refresh_from_db()
        self.assertEqual(Entry.objects.count(), 1)
        self.assertEqual(doc.entry_id, trip.entry_id)
        self.assertEqual(trip.receipt_id, doc.pk)

    def test_list_only_leaks_no_financial_or_document_data(self):
        listing, _ = self.listing()
        doc = self.draft()
        trip = shop.complete_trip(self.user, listing.pk, listing.version, uuid.uuid4(), 'Butikk', self.today, 125000, self.category.pk, doc.pk)
        self.member.role, self.member.module_access = 'member', {'budget': False, 'documents': False}
        self.member.save()
        result = self.client.get(reverse('shopping_detail', args=[listing.pk]))
        self.assertEqual(result.status_code, 200)
        for hidden in (str(trip.entry_id), str(doc.pk), 'test.png', '1250', '1 250'):
            self.assertNotContains(result, hidden)
        self.assertEqual(self.client.get(reverse('shopping_complete', args=[listing.pk])).status_code, 403)
        with self.assertRaises(PermissionDenied): shop.complete_trip(self.user, listing.pk, 1, uuid.uuid4(), 'Butikk', self.today, 125000, self.category.pk)

    def test_late_receipt_mismatch_does_not_change_expense(self):
        listing, _ = self.listing()
        trip = shop.complete_trip(self.user, listing.pk, listing.version, uuid.uuid4(), 'Butikk', self.today, 120000, self.category.pk)
        doc = self.draft()
        with self.assertRaises(ValidationError): shop.attach_receipt(self.user, trip.pk, doc.pk, trip.version, uuid.uuid4())
        self.assertEqual(Entry.objects.get().amount_ore, 120000)
        self.assertEqual(Entry.objects.count(), 1)

    def test_linked_trip_cannot_be_reclassified_as_income(self):
        listing, _ = self.listing()
        trip = shop.complete_trip(self.user, listing.pk, listing.version, uuid.uuid4(), 'Butikk', self.today, 120000, self.category.pk)
        entry = trip.entry
        entry.kind = 'income'
        with self.assertRaises(ValidationError):
            services.save_entry(self.user, entry, entry.version, uuid.uuid4())
        entry.refresh_from_db()
        self.assertEqual(entry.kind, 'expense')

    def completion_payload(self, listing, receipt=None):
        return dict(key=str(uuid.uuid4()),version=listing.version,store='Butikk',effective_date=self.today.isoformat(),
            amount='1250,00',category=str(self.category.pk),receipt=str(receipt.pk) if receipt else '',confirmation='on')

    def test_http_receipt_completion_retry_is_exact_and_new_choices_stay_unconfirmed(self):
        listing, _ = self.listing()
        receipt = self.draft()
        payload = self.completion_payload(listing,receipt)
        url = reverse('shopping_complete',args=[listing.pk])
        self.assertEqual(self.client.post(url,payload).status_code,302)
        self.assertEqual(self.client.post(url,payload).status_code,302)
        self.assertEqual(Entry.objects.count(),1)
        # A new key or changed content cannot reuse the now-confirmed document.
        self.assertEqual(self.client.post(url,{**payload,'key':str(uuid.uuid4())}).status_code,200)
        self.assertEqual(self.client.post(url,{**payload,'amount':'1251,00'}).status_code,200)
        fresh = self.client.get(url)
        self.assertFalse(fresh.context['form'].fields['receipt'].queryset.filter(pk=receipt.pk).exists())
        self.member.role,self.member.module_access='member',{'documents':False}
        self.member.save()
        result=self.client.post(url,payload)
        self.assertEqual(result.status_code,200)
        self.assertNotContains(result, f'value="{receipt.pk}"')
        self.assertEqual(Entry.objects.count(),1)

    def test_http_late_receipt_retry_and_revocation(self):
        listing,_=self.listing()
        trip=shop.complete_trip(self.user,listing.pk,listing.version,uuid.uuid4(),'Butikk',self.today,125000,self.category.pk)
        doc=self.draft()
        payload=dict(key=str(uuid.uuid4()),version=trip.version,receipt=str(doc.pk),confirmation='on')
        url=reverse('shopping_receipt',args=[trip.pk])
        self.assertEqual(self.client.post(url,payload).status_code,302)
        self.assertEqual(self.client.post(url,payload).status_code,302)
        self.assertEqual(self.client.post(url,{**payload,'key':str(uuid.uuid4())}).status_code,200)
        self.member.role,self.member.module_access='member',{'documents':False}
        self.member.save()
        self.assertEqual(self.client.post(url,payload).status_code,403)
        self.assertEqual(Entry.objects.count(),1)

    def test_completed_and_removed_items_remain_discoverable_without_financial_leaks(self):
        listing,item=self.listing()
        shop.save_item(self.user,listing.pk,listing.version,uuid.uuid4(),item.pk,removed=True)
        listing.refresh_from_db()
        result=self.client.get(reverse('shopping_detail',args=[listing.pk]))
        self.assertContains(result,'Gjennomgå og gjenopprett vare')
        self.assertContains(result,reverse('shopping_item',args=[item.pk]))
        result=self.client.post(reverse('shopping_item',args=[item.pk]),dict(key=uuid.uuid4(),version=listing.version,
            name=item.name,quantity='2',purchased='on',price='12,50',category=self.category.pk))
        self.assertEqual(result.status_code,302)
        item.refresh_from_db(); listing.refresh_from_db()
        self.assertFalse(item.removed)
        trip=shop.complete_trip(self.user,listing.pk,listing.version,uuid.uuid4(),'Butikk',self.today,125000,self.category.pk)
        self.member.role,self.member.module_access='member',{'budget':False,'documents':False}
        self.member.save()
        result=self.client.get(reverse('shopping_detail',args=[listing.pk]))
        self.assertContains(result,'Varer i denne turen')
        self.assertContains(result,item.name)
        self.assertNotContains(result,str(trip.entry_id))
        self.assertNotContains(result,'12,50')

    def test_http_recovered_list_and_trip_drafts_preserve_fields_and_require_reconfirmation(self):
        listing,_=self.listing()
        url=reverse('shopping_detail',args=[listing.pk])
        payload=dict(key=str(uuid.uuid4()),version=1,name='Behold meg',quantity='3',price='10,50')
        stale=self.client.post(url,payload)
        self.assertContains(stale,'Behold meg')
        recovered=self.client.post(url,{**payload,'refresh_version':'1'})
        self.assertContains(recovered,'data-preserved-draft="true"')
        self.assertEqual(recovered.context['form']['name'].value(),'Behold meg')
        self.assertNotEqual(recovered.context['form']['key'].value(),payload['key'])
        self.assertFalse(Entry.objects.exists())
        complete=reverse('shopping_complete',args=[listing.pk])
        trip_payload={**self.completion_payload(listing),'version':1}
        stale=self.client.post(complete,trip_payload)
        self.assertContains(stale,'Endret av et annet familiemedlem')
        recovered=self.client.post(complete,{**trip_payload,'refresh_version':'1'})
        form=recovered.context['form']
        self.assertEqual(form['amount'].value(),'1250,00')
        self.assertFalse(form['confirmation'].value())
        self.assertFalse(Entry.objects.exists())
        self.assertEqual(self.client.post(complete,{**trip_payload,'version':form['version'].value(),
            'key':form['key'].value(),'confirmation':'on'}).status_code,302)
        self.assertEqual(Entry.objects.count(),1)

    def test_duplicate_warning_links_only_authorized_candidates(self):
        listing,_=self.listing()
        known=services.save_entry(self.user,Entry(kind='expense',amount_ore=125000,effective_date=self.today,
            description='Butikk',category=self.category,idempotency_key=uuid.uuid4()))
        other=Household.objects.create(name='Other isolated')
        other_user=get_user_model().objects.create_user(username='duplicate-foreign')
        other_member=Membership.objects.create(user=other_user,household=other)
        other_area=create_area(other_member)
        with area_scope(other_member,other_area.pk):
            hidden=Entry.objects.create(household=other,created_by=other_user,kind='expense',amount_ore=125000,
                effective_date=self.today,description='Butikk',sequence=1)
        response=self.client.post(reverse('shopping_complete',args=[listing.pk]),self.completion_payload(listing))
        self.assertContains(response,'Mulige duplikater')
        self.assertContains(response,reverse('correction_history',args=['entry',known.pk]))
        self.assertNotContains(response,str(hidden.pk))
        self.assertEqual(Entry.objects.filter(household=self.house).count(),1)

    def test_form_flows_and_safe_refresh(self):
        listing, item = self.listing()
        for url in (reverse('shopping_lists'), reverse('shopping_detail', args=[listing.pk]), reverse('shopping_item', args=[item.pk]), reverse('shopping_complete', args=[listing.pk])):
            self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(reverse('shopping_revision', args=[listing.pk])).json(), {'version': listing.version})
        result = self.client.post(reverse('shopping_item', args=[item.pk]), dict(key=uuid.uuid4(), version=listing.version,
            name='Brød', quantity='3', purchased='on', price='25,50', category=self.category.pk))
        self.assertEqual(result.status_code, 302)
        item.refresh_from_db()
        # Shared list edits cannot publish private price/category metadata.
        self.assertIsNone(item.price_ore)
        self.assertIsNone(item.category_id)
        self.assertEqual(item.name, 'Brød')
        self.assertFalse(Entry.objects.exists())


class ConcurrentShoppingTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='concurrent-shop')
        house = Household.objects.create(name='Synthetic concurrent')
        self.member = Membership.objects.create(user=self.user, household=house, role='admin')
        install_area(self, self.member)
        self.category = Category.objects.create(household=house, created_by=self.user, name='Test')
        self.listing = shop.save_list(self.user, 'Concurrent', uuid.uuid4())
        shop.save_item(self.user, self.listing.pk, 1, uuid.uuid4(), name='Item', quantity='1', purchased=True)
        self.listing.refresh_from_db()

    def complete(self, key):
        close_old_connections()
        try:
            with area_scope(self.member, self.area.pk):
                return shop.complete_trip(self.user, self.listing.pk, self.listing.version, key, 'Test', timezone.localdate(), 10000, self.category.pk).pk
        finally: close_old_connections()

    def test_simultaneous_retry_returns_same_trip(self):
        key = uuid.uuid4()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.complete, [key, key]))
        self.assertEqual(results[0], results[1])
        self.assertEqual(Entry.objects.count(), 1)
        self.assertEqual(ShoppingTrip.objects.count(), 1)

    def test_simultaneous_distinct_confirmation_conflicts(self):
        def attempt(key):
            try: return self.complete(key)
            except services.Conflict: return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, [uuid.uuid4(), uuid.uuid4()]))
        self.assertEqual(results.count('conflict'), 1)
        self.assertEqual(Entry.objects.count(), 1)

class TwoMemberConcurrentShoppingTests(TransactionTestCase):
    def setUp(self):
        self.house = Household.objects.create(name='Synthetic two-member shopping')
        self.users = [get_user_model().objects.create_user(username=f'shop-member-{i}') for i in range(2)]
        members = [Membership.objects.create(user=user, household=self.house, role='member') for user in self.users]
        install_area(self, members[0], members[1:])
        self.category = Category.objects.create(household=self.house, created_by=self.users[0], name='Test')
        self.listing = shop.save_list(self.users[0], 'Shared list', uuid.uuid4())
        self.item = shop.save_item(self.users[0], self.listing.pk, 1, uuid.uuid4(), name='Item', quantity='1', purchased=True)
        self.listing.refresh_from_db()

    def race(self, same_key):
        from threading import Barrier
        from django.db import connection
        from .models import WorkflowCommand, ShoppingItem
        self.assertEqual(connection.vendor, 'postgresql')
        barrier = Barrier(2)
        keys = [uuid.uuid4(), uuid.uuid4()]
        if same_key: keys[1] = keys[0]
        def attempt(index):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    pid = cursor.fetchone()[0]
                barrier.wait(timeout=10)
                try:
                    with area_scope(Membership.objects.get(user=self.users[index]), self.area.pk):
                        result = shop.complete_trip(self.users[index], self.listing.pk, self.listing.version,
                            keys[index], 'Test', timezone.localdate(), 10000, self.category.pk).pk
                except services.Conflict:
                    result = 'conflict'
                return pid, result
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, range(2)))
        self.assertEqual(len({pid for pid, _ in outcomes}), 2)
        results = [result for _, result in outcomes]
        # Workflow keys are bound to the actor as well as the area.
        self.assertEqual(results.count('conflict'), 1)
        trip = ShoppingTrip.objects.get()
        self.assertEqual(set(results) - {'conflict'}, {trip.pk})
        entry = Entry.objects.get()
        self.assertEqual(trip.entry_id, entry.pk)
        self.assertEqual(entry.amount_ore, 10000)
        self.assertIn(entry.created_by_id, [user.pk for user in self.users])
        self.assertEqual(ShoppingItem.objects.get().trip_id, trip.pk)
        old_version = self.listing.version
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.version, old_version + 1)
        self.assertEqual(WorkflowCommand.objects.filter(operation='shopping_complete').count(), 1)

    def test_two_members_replay_same_completion(self): self.race(True)
    def test_two_members_distinct_completion_commands_conflict(self): self.race(False)
