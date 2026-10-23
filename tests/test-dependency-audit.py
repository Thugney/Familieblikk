"""Kontroll av sikkerhetsporten uten nettverkskall."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('dependency_audit', Path(__file__).resolve().parents[1] / 'scripts/audit-dependencies.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class DependencyAuditTests(unittest.TestCase):
    packages = [{'name': 'example', 'version': '1.0'}]

    def test_all_locked_platforms_included(self):
        packages = audit.locked_packages(Path(__file__).resolve().parents[1] / 'requirements.lock')
        self.assertIn('gunicorn', {p['name'] for p in packages})
        self.assertIn('tzdata', {p['name'] for p in packages})

    def test_unpinned_requirement_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'requirements.lock'
            path.write_text('example>=1.0')
            with self.assertRaises(ValueError):
                audit.locked_packages(path)

    def test_complete_clean_results(self):
        with patch.object(audit, 'fetch_json', side_effect=[{'results': [{}]}, {'info': {'version': '1.0'}, 'vulnerabilities': []}]):
            self.assertEqual(audit.audit(self.packages)[0]['osv'], [])

    def test_both_sources_report_advisories(self):
        with patch.object(audit, 'fetch_json', side_effect=[{'results': [{'vulns': [{'id': 'OSV-1'}]}]}, {'info': {'version': '1.0'}, 'vulnerabilities': [{'id': 'PYPI-2', 'withdrawn': None}]}]):
            result = audit.audit(self.packages)[0]
            self.assertEqual(result['osv'], ['OSV-1'])
            self.assertEqual(result['pypi'], ['PYPI-2'])

    def test_partial_osv_response_fails(self):
        with patch.object(audit, 'fetch_json', return_value={'results': []}):
            with self.assertRaises(ValueError):
                audit.audit(self.packages)

    def test_incomplete_pypi_response_fails(self):
        with patch.object(audit, 'fetch_json', side_effect=[{'results': [{}]}, {'info': {'version': '1.0'}}]):
            with self.assertRaises(ValueError):
                audit.audit(self.packages)

    def test_network_failure_exits_nonzero(self):
        with patch.object(audit, 'fetch_json', side_effect=TimeoutError('Synthetic timeout')):
            self.assertEqual(audit.main([]), 2)

    def test_main_exit_code_blocks_either_advisory_source(self):
        for osv, pypi, expected in (([], [], 0), (['OSV-1'], [], 1), ([], ['PYPI-1'], 1)):
            with self.subTest(osv=osv, pypi=pypi), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / 'result.json'
                with patch.object(audit, 'locked_packages', return_value=self.packages), patch.object(
                    audit, 'fetch_json', side_effect=[
                        {'results': [{'vulns': [{'id': value} for value in osv]}]},
                        {'info': {'version': '1.0'}, 'vulnerabilities': [{'id': value} for value in pypi]},
                    ]
                ):
                    self.assertEqual(audit.main(['--output', str(output)]), expected)
                import json
                result = json.loads(output.read_text())
                self.assertEqual(result['status'], 'known_vulnerabilities' if expected else 'no_known_vulnerabilities')


if __name__ == '__main__':
    unittest.main()
