"""Kontroller alle hash-låste Python-pakker uten å installere revisjonsverktøy.

Sender bare offentlige pakkenavn/versjoner til OSV og PyPI. Nettverksfeil,
ufullstendig svar eller kjente sårbarheter gir en ikke-null avslutningskode.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen


def locked_packages(path):
    packages = []
    for line in path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or stripped.startswith('--hash=sha256:'):
            continue
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([^\s;\\]+)(?:\s*;[^\\]+)?\s*\\?', stripped)
        if not match:
            raise ValueError('Uventet eller ulåst pakkelinje i requirements.lock')
        name, version = match.groups()
        packages.append({'name': re.sub(r'[-_.]+', '-', name).lower(), 'version': version})
    if not packages or len({p['name'] for p in packages}) != len(packages):
        raise ValueError('Tom eller duplisert pakkeliste')
    return packages


def fetch_json(url, payload=None):
    request = Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                      headers={'Content-Type': 'application/json', 'User-Agent': 'Familieblikk-dependency-audit/1'})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def audit(packages):
    result = fetch_json('https://api.osv.dev/v1/querybatch', {'queries': [
        {'package': {'name': p['name'], 'ecosystem': 'PyPI'}, 'version': p['version']} for p in packages
    ]})
    if not isinstance(result, dict) or not isinstance(result.get('results'), list) or len(result['results']) != len(packages):
        raise ValueError('Ufullstendig OSV-svar')
    checked = []
    for package, entry in zip(packages, result['results']):
        if not isinstance(entry, dict) or not isinstance(entry.get('vulns', []), list):
            raise ValueError('Ugyldig OSV-pakkeresultat')
        osv_ids = []
        for vuln in entry.get('vulns', []):
            if not isinstance(vuln, dict) or not isinstance(vuln.get('id'), str) or not vuln['id']:
                raise ValueError('Ugyldig OSV-varsel')
            osv_ids.append(vuln['id'])
        metadata = fetch_json(f"https://pypi.org/pypi/{package['name']}/{package['version']}/json")
        if not isinstance(metadata, dict) or not isinstance(metadata.get('vulnerabilities'), list):
            raise ValueError('Ufullstendig PyPI-svar')
        if metadata.get('info', {}).get('version') != package['version']:
            raise ValueError('PyPI returnerte feil pakkeversjon')
        pypi_ids = []
        for vuln in metadata['vulnerabilities']:
            if not isinstance(vuln, dict) or not isinstance(vuln.get('id'), str):
                raise ValueError('Ugyldig PyPI-varsel')
            if not vuln.get('withdrawn'):
                pypi_ids.append(vuln['id'])
        checked.append({**package, 'osv': sorted(set(osv_ids)), 'pypi': sorted(set(pypi_ids))})
    return checked


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, default=Path(__file__).resolve().parents[1] / 'requirements.lock')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'sources': ['OSV', 'PyPI'], 'status': 'error'}
    code = 2
    try:
        report['packages'] = audit(locked_packages(args.lock))
        vulnerable = [p for p in report['packages'] if p['osv'] or p['pypi']]
        report['status'] = 'known_vulnerabilities' if vulnerable else 'no_known_vulnerabilities'
        code = 1 if vulnerable else 0
        print(f"Kontrollert {len(report['packages'])} låste pakker; {len(vulnerable)} med kjente sårbarhetsvarsler.")
        for package in vulnerable:
            print(package['name'], package['version'], ', '.join(sorted(set(package['osv'] + package['pypi']))))
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        print('Avhengighetskontrollen kunne ikke fullføres; resultatet er ukjent.', file=sys.stderr)
        print(report['error'], file=sys.stderr)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return code


if __name__ == '__main__':
    sys.exit(main())
