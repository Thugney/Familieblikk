"""Bounded local OCR and crash-safe disposal of new camera scans."""
from datetime import datetime, timedelta
from pathlib import Path
import os
import csv
import io
import re
import subprocess
import uuid
from django.db import connection, transaction
from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models import Q
from django.utils import timezone
from .models import DocumentJob, Document, Membership
from .financial_areas import area_scope, current_area
from . import access
from .document_storage import path_for
from . import document_spool


def limits():
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (40, 40))
    resource.setrlimit(resource.RLIMIT_FSIZE, (80 * 1024**2, 80 * 1024**2))


def decoder_environment(directory):
    """Native decoders need locale/executable lookup, never application secrets.

    The image probe and PDF inspection also call run(), sharing this boundary.
    Windows needs SystemRoot to load system libraries; all temporary files stay
    inside the existing per-job scratch directory.
    """
    allowed = ('PATH', 'SYSTEMROOT', 'WINDIR', 'PATHEXT', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ')
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    environment.update(OMP_THREAD_LIMIT='1', TMPDIR=str(directory), TMP=str(directory), TEMP=str(directory))
    return environment


def run(arguments, timeout=45):
    with document_spool.scratch() as directory:
        with (directory / 'output').open('w+b') as output:
            subprocess.run(arguments, check=True, stdout=output, stderr=subprocess.DEVNULL, timeout=timeout,
                env=decoder_environment(directory),
                preexec_fn=limits if os.name == 'posix' else None)
            output.seek(0)
            data = output.read(200_001)
            if len(data) > 200_000:
                raise ValueError('OCR-resultatet overskrider den sikre størrelsesgrensen.')
            return data.decode('utf-8', 'replace')


class LegacyPDFManualReview(ValueError):
    pass


def recognize(document):
    if document.content_type == 'application/pdf':
        raise LegacyPDFManualReview('Automatisk PDF-lesing er deaktivert. Originalen er bevart; fyll inn feltene manuelt.')
    source = document_spool.path_for(document.storage_key) if document.transient else path_for(document.storage_key)
    if document.transient:
        # One uniform-text pass suits receipt blocks. TSV quality signals
        # suppress doubtful lines; they are not calibrated probabilities.
        return readable_lines(run(['tesseract', str(source), 'stdout', '-l', 'nor+eng', '--psm', '6', 'tsv']))
    return run(['tesseract', str(source), 'stdout', '-l', 'nor+eng'])


def readable_lines(tsv):
    """Withhold an entire uncertain line rather than repair guessed digits.

    80 is a conservative engine-quality cutoff, not a claimed accuracy rate.
    A withheld first line stays a non-text sentinel so we never promote a
    later arbitrary item/customer line into the merchant heading.
    """
    lines = {}
    reader = csv.DictReader(io.StringIO(tsv), delimiter='\t')
    required = {'level', 'page_num', 'block_num', 'par_num', 'line_num', 'word_num', 'conf', 'text'}
    if not reader.fieldnames or not required.issubset(reader.fieldnames) or len(set(reader.fieldnames)) != len(reader.fieldnames):
        return ''
    seen_words = set()
    for word in reader:
        if None in word or any(word.get(name) is None for name in required):
            return ''
        if word['level'] not in ('1', '2', '3', '4', '5'):
            return ''
        if word['level'] != '5' or not word['text']:
            continue
        ids = [word[name] for name in ('page_num', 'block_num', 'par_num', 'line_num', 'word_num')]
        if any(not re.fullmatch(r'[1-9][0-9]*', value) for value in ids):
            return ''
        identity = tuple(int(value) for value in ids)
        if identity in seen_words:
            return ''
        seen_words.add(identity)
        key = identity[:-1]
        line = lines.setdefault(key, {'words': [], 'readable': True})
        line['words'].append(word['text'])
        try:
            score = float(word.get('conf', '-1'))
            line['readable'] &= 80 <= score <= 100
        except (ValueError, TypeError):
            line['readable'] = False
    if not any(line['readable'] for line in lines.values()):
        return ''
    output = []
    for line in lines.values():
        value = ' '.join(line['words'])
        if line['readable']:
            output.append(value)
        elif re.match(r'^(?:å betale|a betale|til betaling|beløp å betale|amount due|totalt|total|sum)\b', value, re.I):
            # A doubtful payable total must block weaker totals, not disappear.
            output.append('Å betale: ?')
        elif re.match(r'^(?:forfallsdato|forfall|due date)\b', value, re.I):
            output.append('Forfall: ?')
        elif re.match(r'^(?:fakturadato|kjøpsdato|dato|date)\b', value, re.I):
            output.append('Dato: ?')
        elif re.match(r'^(?:leverandør|butikk|betalingsmottaker|merchant)\b', value, re.I):
            output.append('Butikk: ?')
        else:
            output.append('…')
    return '\n'.join(output)


def money_token(token):
    token = re.sub(r'\s*(?:NOK|kr\.?)\s*$', '', token, flags=re.I).strip()
    token = token.replace('\u00a0', ' ').replace('\u202f', ' ')
    if re.fullmatch(r'(?:\d{1,12}|\d{1,3}(?:\.\d{3})+|\d{1,3}(?: \d{3})+),\d{2}', token):
        return token.replace('.', '').replace(' ', '') if int(re.sub(r'[., ]', '', token)) > 0 else None
    if re.fullmatch(r'\d{1,12}\.\d{2}', token):
        return token.replace('.', ',') if float(token) > 0 else None
    return None


def suggestions(text):
    """Conservative structured candidates; equal-priority conflicts stay unfilled."""
    result, ambiguous = {}, []
    def choose(name, values):
        values = set(filter(None, values))
        if len(values) == 1:
            result[name] = values.pop()
        elif len(values) > 1:
            ambiguous.append(name)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # An unclassifiable doubtful line may itself be a misread payable total
    # or date label. Do not silently fall back to other numeric candidates.
    if '…' in lines:
        ambiguous.extend(('amount', 'document_date', 'due_date'))
    totals = {0: [], 1: []}
    for line in lines:
        match = re.fullmatch(r'(å betale|a betale|til betaling|beløp å betale|amount due|totalt|total|sum)\s*:?\s*(?:NOK\s*)?(.+)', line, re.I)
        if match:
            rank = 0 if match[1].lower() in ('å betale', 'a betale', 'til betaling', 'beløp å betale', 'amount due') else 1
            totals[rank].append(money_token(match[2]))
    chosen_totals = totals[0] if totals[0] else totals[1]
    if None in chosen_totals: ambiguous.append('amount')
    choose('amount', chosen_totals)
    for name, label in [('document_date', r'(?:fakturadato|kjøpsdato|dato|date)'), ('due_date', r'(?:forfallsdato|forfall|due date)')]:
        dates = []
        for line in lines:
            match = re.fullmatch(label + r'\s*:?\s*(\d{2}[./-]\d{2}[./-]\d{4})(?:\s+\d{2}:\d{2}(?::\d{2})?)?', line, re.I)
            if not match and re.match(label + r'\s*:', line, re.I):
                ambiguous.append(name)
            if match:
                try:
                    day = datetime.strptime(re.sub(r'[/-]', '.', match[1]), '%d.%m.%Y')
                    dates.append(day.strftime('%d.%m.%Y'))
                except ValueError:
                    ambiguous.append(name)
        choose(name, dates)
    # A receipt often has one unlabelled transaction timestamp. Never use a
    # labelled due date as a purchase date, or choose between conflicting days.
    if 'document_date' not in result and 'document_date' not in ambiguous:
        dates = []
        for line in lines:
            if re.fullmatch(r'\d{2}[./-]\d{2}[./-]\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?', line):
                try: dates.append(datetime.strptime(re.sub(r'[/-]', '.', line[:10]), '%d.%m.%Y').strftime('%d.%m.%Y'))
                except ValueError: ambiguous.append('document_date')
        choose('document_date', dates)
    suppliers = []
    for line in lines:
        match = re.fullmatch(r'(?:leverandør|butikk|betalingsmottaker|merchant)\s*:\s*(.{1,120})', line, re.I)
        if match: suppliers.append(match[1])
    if '?' in suppliers:
        ambiguous.append('supplier')
    choose('supplier', suppliers)
    if not suppliers and lines:
        header = lines[:3]
        # Only skip standalone document-title lines at the very start. Never
        # search beyond metadata or line items for a merchant-looking phrase.
        while header and re.fullmatch(r'(?:fiktiv\s+)?(?:test)?(?:faktura|kvittering|invoice|receipt)', header[0], re.I):
            header.pop(0)
        first = header[0] if header else ''
        if len(first) <= 120 and re.search(r'[A-Za-zÆØÅæøå]{3}', first) and not re.search(r'\d|kvittering|faktura|receipt|invoice|velkommen|total|subtotal|mva|sum|dato|forfall|kontant|tilbake', first, re.I):
            result['supplier'] = first
            result['merchant_heading'] = True
    if ambiguous:
        for name in set(ambiguous): result.pop(name, None)
        result['ambiguous'] = sorted(set(ambiguous))
    return result


def clean_photo(document_id):
    """Delete only after durable cleanup intent; retry after any interruption."""
    with transaction.atomic():
        row = Document.all_objects.select_for_update().get(pk=document_id)
        if not row.transient or not row.cleanup_pending: return
        try:
            document_spool.discard(row.storage_key)
        except (OSError, ValueError, ValidationError):
            return
        row.cleanup_pending, row.photo_deleted_at = False, timezone.now()
        Document.all_objects.filter(pk=row.pk).update(cleanup_pending=row.cleanup_pending, photo_deleted_at=row.photo_deleted_at)


def sweep():
    now = timezone.now()
    terminal = DocumentJob.objects.filter(status='running', lease_until__lt=now, attempts__gte=3).values_list('document_id', flat=True)
    for pk in list(terminal):
        with transaction.atomic():
            row = Document.all_objects.select_for_update().get(pk=pk)
            job = DocumentJob.objects.select_for_update().get(document=row)
            if job.status != 'running' or job.lease_until is None or job.lease_until >= now: continue
            job.status, job.lease_until, job.generation = 'failed', None, uuid.uuid4()
            job.error = 'Tekstgjenkjenning ble avbrutt flere ganger. Fyll inn manuelt eller ta et nytt bilde.'
            job.save()
            if row.transient:
                row.cleanup_pending = True
                Document.all_objects.filter(pk=row.pk).update(cleanup_pending=True)
    expired = Document.all_objects.filter(transient=True, photo_deleted_at__isnull=True,
        expires_at__lte=now, cleanup_pending=False).values_list('pk', flat=True)
    for pk in list(expired):
        with transaction.atomic():
            row = Document.all_objects.select_for_update().get(pk=pk)
            if row.photo_deleted_at or row.cleanup_pending: continue
            job = DocumentJob.objects.select_for_update().get(document=row)
            job.generation, job.lease_until = uuid.uuid4(), None
            if job.status not in ('ready', 'cancelled'):
                job.status, job.error = 'failed', 'Skannetiden er utløpt. Ta et nytt bilde eller fyll inn manuelt.'
            job.save()
            row.cleanup_pending = True
            Document.all_objects.filter(pk=row.pk).update(cleanup_pending=True)
    for pk in list(Document.all_objects.filter(transient=True, cleanup_pending=True).values_list('pk', flat=True)):
        clean_photo(pk)
    referenced = set(Document.all_objects.filter(transient=True, photo_deleted_at__isnull=True).values_list('storage_key', flat=True))
    document_spool.sweep_orphans(referenced)


def process_one():
    sweep()
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(64712022)')
        if not cursor.fetchone()[0]: return False
    try:
        # Lock document then job everywhere, matching cancellation/confirmation.
        candidate = DocumentJob.objects.filter(attempts__lt=3).filter(
            Q(status='pending') | Q(status='running', lease_until__lt=timezone.now())).order_by('pk').first()
        if not candidate: return False
        raw = Document.all_objects.get(pk=candidate.document_id)
        entered = False
        try:
            member = Membership.objects.get(user_id=raw.created_by_id)
            document_actor = member.user
            scope = area_scope(member, raw.financial_area_id, write=True)
            scope.__enter__()
            entered = True
            access.require(member, {'documents'})
        except (PermissionDenied, Membership.DoesNotExist):
            if entered: scope.__exit__(None, None, None)
            DocumentJob.objects.filter(pk=candidate.pk).update(status='suspended', error='Tilgangen til budsjettet er endret.')
            return False
        try:
            with transaction.atomic():
                member = access.lock_member(document_actor)
                current_area(member, write=True)
                access.require(member, {'documents'})
                document = Document.objects.select_for_update().get(pk=candidate.document_id)
                job = DocumentJob.objects.select_for_update().get(pk=candidate.pk)
                if document.cancelled or job.status not in ('pending', 'running'): return False
                if document.transient and (document.photo_deleted_at or document.cleanup_pending): return False
                job.status, job.error, job.generation = 'running', '', uuid.uuid4()
                job.attempts += 1
                job.lease_until = timezone.now() + timedelta(minutes=8)
                job.save()
                generation = job.generation
            try:
                text = recognize(document)
                if not text.strip(): raise ValueError('Ingen lesbar tekst')
                candidates, error = suggestions(text), ''
            except LegacyPDFManualReview as exc:
                candidates, text, error = document.suggestions, document.ocr_text, str(exc)
            except (OSError, subprocess.SubprocessError, ValueError):
                candidates, text = {}, ''
                error = 'Teksten kunne ikke leses. Ta et nytt bilde i jevnt lys eller fyll inn manuelt.'
            with transaction.atomic():
                member = access.lock_member(document_actor)
                current_area(member, write=True)
                access.require(member, {'documents'})
                row = Document.objects.select_for_update().get(pk=document.pk)
                current = DocumentJob.objects.select_for_update().get(pk=job.pk)
                if current.generation != generation or current.status != 'running' or row.cancelled:
                    return True
                if row.transient and row.expires_at <= timezone.now():
                    candidates, text, error = {}, '', 'Skannetiden er utløpt. Ta et nytt bilde eller fyll inn manuelt.'
                row.suggestions, row.ocr_text = candidates, '' if row.transient else text
                row.cleanup_pending = row.transient
                row.save(update_fields=['suggestions', 'ocr_text', 'cleanup_pending'])
                current.status, current.error, current.lease_until = ('failed' if error else 'ready'), error, None
                current.save()
            if document.transient: clean_photo(document.pk)
            return True
        except PermissionDenied:
            DocumentJob.objects.filter(pk=candidate.pk).update(status='suspended', error='Tilgangen til budsjettet er endret.')
            return False
        finally:
            scope.__exit__(None, None, None)
    finally:
        with connection.cursor() as cursor: cursor.execute('SELECT pg_advisory_unlock(64712022)')
