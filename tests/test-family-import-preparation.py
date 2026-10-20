"""Private-source preparation tests, not application/profile acceptance tests."""
import importlib.util
import unittest
from pathlib import Path
from datetime import datetime
from decimal import Decimal
import json
import subprocess
import threading
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

imp = load('family_import', 'scripts/prepare-family-import.py')
preview = load('family_preview', 'scripts/serve-design-preview.py')

class ValueRules(unittest.TestCase):
    def test_money_including_zero_and_negative_preserved(self):
        self.assertEqual(imp.money_ore(0), 0)
        self.assertEqual(imp.money_ore(Decimal('123.45')), 12345)
        self.assertEqual(imp.money_ore(-15.2), -1520)
        self.assertIsNone(imp.money_ore(None))

    def test_no_rounding_or_cast_guess_for_inputs(self):
        for bad in ['1,50', '150.00', Decimal('1.005'), Decimal('NaN')]:
            with self.subTest(value=bad):
                with self.assertRaises((ValueError, ArithmeticError)):
                    imp.money_ore(bad)

    def test_dates_do_not_assume_numeric_or_ambiguous_strings(self):
        self.assertEqual(imp.calendar_date(datetime(2026, 9, 21)), '2026-09-21')
        self.assertIsNone(imp.calendar_date(None))
        self.assertIsNone(imp.calendar_date('09/10/26'))
        self.assertIsNone(imp.calendar_date(46000))
        with self.assertRaises(ValueError):
            imp.calendar_date(datetime(2026, 9, 21, 9, 30))

    def test_stable_source_identity_is_not_amount_or_revision_dependent(self):
        self.assertEqual(imp.stable_id('Transactions', 5), imp.stable_id('Transactions', 5))
        self.assertNotEqual(imp.stable_id('Transactions', 5), imp.stable_id('Transactions', 6))
        self.assertNotEqual(imp.stable_id('Transactions', 5), imp.stable_id('Debts', 5))

    def test_eligibility_blocks_module_issues_and_missing_runtime(self):
        self.assertFalse(imp.staging_eligibility([])['safe_to_apply_as_confirmed_ledger'])
        result = imp.staging_eligibility([{'severity': 'review', 'code': 'opening_balance_date_not_in_source'}])
        self.assertFalse(result['all_financial_records_resolved'])
        self.assertIn('unresolved_source_data', result['blockers'])
        self.assertFalse(result['owner_verified'])

class RealWorkbookPreservation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not imp.SOURCE.exists():
            raise unittest.SkipTest('Private workbook unavailable; cannot verify real-data preservation.')
        cls.before = imp.digest(imp.SOURCE)
        cls.extractor = imp.Extractor()
        cls.package = cls.extractor.extract()

    def test_original_and_copy_identical(self):
        self.assertEqual(imp.digest(Path('E:/Family_Budget_Expandable.xlsx')), self.before)
        self.assertEqual(self.package['source']['sha256'], self.before)

    def test_current_source_records_not_demo(self):
        for key, expected in {'categories':32, 'transactions':23, 'debts':7, 'savings_goals':2,
                              'annual_funds':0, 'recipients':1, 'fx_rate_settings':6}.items():
            self.assertEqual(len(self.package[key]), expected, key)
        self.assertEqual(self.package['source_selected_month'], '2026-09')
        self.assertFalse(self.package['target']['global_seed_for_new_families'])
        self.assertIsNone(self.package['target']['household_id'])

    def test_all_source_transaction_rows_retained_exactly_once(self):
        rows = [r['source']['row'] for r in self.package['transactions']]
        self.assertEqual(rows, list(range(5, 28)))
        self.assertEqual(len({r['source_id'] for r in self.package['transactions']}), len(rows))
        for rec in self.package['transactions']:
            for field, cell in rec['cells'].items():
                self.assertEqual(rec['raw'][field], imp.serial(self.extractor.book['Transactions'][cell].value))

    def test_undated_rows_stay_unconfirmed_and_visible(self):
        rows = {r['source']['row']:r for r in self.package['transactions']}
        for r in [26, 27]:
            self.assertIsNone(rows[r]['effective_date'])
            self.assertIsNotNone(rows[r]['original_amount_minor_if_2dp'])
            self.assertEqual(rows[r]['review_state'], 'needs_review')

    def test_expense_debt_ambiguity_not_silently_reclassified(self):
        rows = {r['source']['row']:r for r in self.package['transactions']}
        for r in [9, 25, 26]:
            self.assertEqual(rows[r]['source_accounting_class'], 'expense')
            self.assertIn('expense_has_module_link_classification_review', rows[r]['issue_codes'])

    def test_source_zero_currency_and_uncertain_dates_not_fabricated(self):
        row = next(r for r in self.package['transactions'] if r['source']['row'] == 6)
        self.assertIsNone(row['raw']['currency'])
        self.assertEqual(row['currency'], 'NOK')
        self.assertEqual(row['currency_provenance'], 'workbook_blank_means_base_currency')
        self.assertEqual(sum(r['confirmed_for_conversion'] for r in self.package['fx_rate_settings']), 1)
        for goal in self.package['savings_goals']:
            self.assertIsNone(goal['opening_balance_effective_date'])

    def test_snapshot_preserves_every_nonempty_cell_and_cache(self):
        snap = self.extractor.snapshot()
        by_name = {s['name']:s for s in snap['sheets']}
        for ws in self.extractor.book:
            values = {c.coordinate:c for row in ws.iter_rows() for c in row if c.value is not None}
            cells = {c['cell']:c for c in by_name[ws.title]['cells']}
            self.assertEqual(set(values), set(cells), ws.title)
            for coordinate, cell in values.items():
                self.assertEqual(cells[coordinate]['value'], imp.serial(cell.value))
                if cell.data_type == 'f':
                    self.assertEqual(cells[coordinate]['cached_value'], imp.serial(self.extractor.cache[ws.title][coordinate].value))

    def test_no_source_mutation_or_fake_owner(self):
        self.assertEqual(imp.digest(imp.SOURCE), self.before)
        self.assertFalse(self.package['app_profile_populated'])
        self.assertIsNone(self.package['target']['owner_user_id'])
        target = json.loads((imp.PRIVATE/'profile-target.json').read_text(encoding='utf-8'))
        self.assertFalse(target['owner_email_verified'])
        self.assertFalse(target['send_email_automatically'])

    def test_private_tree_is_gitignored(self):
        result = subprocess.run(['git','check-ignore','--','private-data/family-budget/source/family-budget-expandable.xlsx',
                                 'private-data/family-budget/import/import-package.json','private-data/family-budget/profile-target.json'],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(result.stdout.splitlines()), 3)

class PreviewProtection(unittest.TestCase):
    def test_public_fictional_mock_can_be_served(self):
        self.assertIsNotNone(preview.preview_file('/.project-init/familieblikk-mockup.html'))

    def test_private_and_arbitrary_files_not_served(self):
        for target in ['/private-data/family-budget/source/family-budget-expandable.xlsx',
                       '/private-data/family-budget/profile-target.json', '/.git/config', '/work/workbook-structure.json',
                       '/scripts/prepare-family-import.py', '/.project-init/../private-data/family-budget/import/import-package.json',
                       '/.project-init/%2e%2e/private-data/family-budget/profile-target.json',
                       '/.project-init\\..\\private-data\\family-budget\\profile-target.json', '/', '/.project-init/']:
            with self.subTest(target=target):
                self.assertIsNone(preview.preview_file(target))

class PreviewHTTPProtection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = preview.PreviewServer(('127.0.0.1',0),preview.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self,path,host=None):
        req=urllib.request.Request(f'http://127.0.0.1:{self.port}{path}',headers={'Host':host} if host else {})
        try:
            r=urllib.request.urlopen(req,timeout=5)
            return r.status,r.read()
        except urllib.error.HTTPError as e:
            return e.code,e.read()

    def test_live_handler_public_mock_and_no_owner_address(self):
        status,body=self.request('/.project-init/familieblikk-mockup.html')
        self.assertEqual(status,200)
        owner=json.loads((imp.PRIVATE/'profile-target.json').read_text(encoding='utf-8'))['owner_email']
        self.assertTrue(not owner or owner.encode() not in body,'Owner address must not occur in public mock.')

    def test_live_handler_rejects_all_private_assets(self):
        for target in ['/private-data/family-budget/source/family-budget-expandable.xlsx',
                       '/private-data/family-budget/import/import-package.json',
                       '/private-data/family-budget/profile-target.json',
                       '/work/workbook-structure.json','/.git/config',
                       '/.project-init/%2e%2e/private-data/family-budget/profile-target.json']:
            with self.subTest(target=target):
                status,_=self.request(target)
                self.assertEqual(status,404)

    def test_untrusted_host_rejected(self):
        status,_=self.request('/.project-init/familieblikk-mockup.html','untrusted.invalid')
        self.assertEqual(status,403)

    def test_a_second_server_cannot_shadow_existing_listener(self):
        with self.assertRaises(OSError):
            duplicate=preview.PreviewServer(('127.0.0.1',self.port),preview.Handler)
            duplicate.server_close()

if __name__ == '__main__':
    unittest.main(verbosity=2)
