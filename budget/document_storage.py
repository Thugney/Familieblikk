"""Private immutable files. No user-supplied path ever reaches the filesystem."""
import hashlib
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import uuid
import zlib
from django.conf import settings
from django.core.exceptions import ValidationError

from .document_spool import scratch

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 25_000_000


def inspect_content(data, *, image_only=False):
    if not data or len(data) > MAX_BYTES:
        raise ValidationError('Filen må være mellom 1 byte og 10 MiB.')
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        pos, dims, ended, image_data, header = 8, None, False, bytearray(), None
        while pos + 12 <= len(data):
            length = struct.unpack('>I', data[pos:pos+4])[0]
            kind = data[pos+4:pos+8]
            end = pos + 12 + length
            if end > len(data) or zlib.crc32(data[pos+4:end-4]) != struct.unpack('>I', data[end-4:end])[0]:
                raise ValidationError('PNG-filen er skadet.')
            if kind == b'IHDR' and length == 13:
                if pos != 8 or header is not None: raise ValidationError('Ugyldig PNG-header.')
                dims = struct.unpack('>II', data[pos+8:pos+16])
                header = data[pos+8:end-4]
            if kind == b'IDAT': image_data.extend(data[pos+8:end-4])
            if kind == b'IEND':
                ended = end == len(data)
                break
            pos = end
        if not ended or not dims or not image_data:
            raise ValidationError('Ugyldig PNG-fil.')
        mime = 'image/png'
    elif data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9'):
        pos, dims, scan = 2, None, False
        while pos + 4 <= len(data):
            if data[pos] != 255:
                break
            while pos < len(data) and data[pos] == 255:
                pos += 1
            if pos >= len(data): break
            marker = data[pos]
            pos += 1
            if marker in (0xD9, 0xDA):
                if marker == 0xDA:
                    length = int.from_bytes(data[pos:pos+2], 'big')
                    scan = length >= 6 and pos + length < len(data) - 2
                break
            length = int.from_bytes(data[pos:pos+2], 'big')
            if length < 2 or pos + length > len(data):
                break
            if marker in (0xC0, 0xC1, 0xC2) and length >= 8:
                dims = (int.from_bytes(data[pos+5:pos+7], 'big'), int.from_bytes(data[pos+3:pos+5], 'big'))
            pos += length
        if not dims or not scan:
            raise ValidationError('Ugyldig JPEG-fil.')
        mime = 'image/jpeg'
    elif not image_only and data.startswith(b'%PDF-') and b'%%EOF' in data[-1024:]:
        # Poppler parses the real page tree; counting /Page tokens is not safe.
        try:
            with scratch() as tmp:
                source = Path(tmp) / 'input.pdf'
                source.write_bytes(data)
                from .document_ocr import run
                info = run(['pdfinfo', str(source)], timeout=15)
            pages = re.search(r'^Pages:\s+(\d+)', info, re.M)
            if not pages or not 1 <= int(pages[1]) <= 10 or re.search(r'^Encrypted:\s+yes', info, re.M):
                raise ValidationError('PDF må ha 1–10 sider og ikke være passordbeskyttet.')
            return 'application/pdf'
        except (OSError, subprocess.SubprocessError):
            raise ValidationError('PDF-kontroll er ikke tilgjengelig eller filen er skadet. Prøv et bilde; lokal PDF-motor må klargjøres.') from None
    else:
        raise ValidationError('Bare gyldige PDF-, JPEG- og PNG-filer støttes.')
    if not dims[0] or not dims[1] or dims[0] * dims[1] > MAX_PIXELS:
        raise ValidationError('Bildet må være høyst 25 megapiksler.')
    if mime == 'image/png':
        # Validate the whole zlib stream, including empty/truncated IDAT, before
        # invoking native decoding. Bound decompressed bytes to the pixel budget.
        decoder, decoded = zlib.decompressobj(), 0
        try:
            pending = bytes(image_data)
            while pending:
                block = decoder.decompress(pending, 65536)
                decoded += len(block)
                if decoded > MAX_PIXELS * 8 + dims[1] * 8:
                    raise ValidationError('PNG-strømmen overskrider bildegrensen.')
                pending = decoder.unconsumed_tail
            if not decoder.eof or decoder.unused_data or decoded == 0:
                raise ValidationError('PNG-bildestrømmen er tom eller avbrutt.')
            # Non-interlaced PNG exact scan length, also usable without native engines on Windows.
            depth, color, compression, filtering, interlace = header[8:13]
            channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
            if not channels or compression or filtering or interlace not in (0, 1):
                raise ValidationError('Ugyldig PNG-format.')
            if not interlace and decoded != dims[1] * (1 + (dims[0] * channels * depth + 7) // 8):
                raise ValidationError('PNG-bildestrømmen har feil lengde.')
        except zlib.error:
            raise ValidationError('PNG-bildestrømmen er skadet.') from None
    if os.name == 'posix' or mime == 'image/jpeg':
        try:
            from .document_ocr import run
            with scratch() as tmp:
                source = Path(tmp) / 'image'
                source.write_bytes(data)
                run([sys.executable, '-m', 'budget.document_image_probe', str(source)], timeout=15)
        except (OSError, subprocess.SubprocessError):
            raise ValidationError('Bildet er skadet eller lokal bildevalidering mangler. Bruk en gyldig original i Docker-miljøet.') from None
    return mime


def path_for(key):
    if not re.fullmatch(r'[0-9a-f-]{36}/[0-9a-f]{32}', key):
        raise ValidationError('Ugyldig lagringsnøkkel.')
    root = Path(settings.PRIVATE_DOCUMENT_ROOT).resolve()
    path = (root / key).resolve()
    if not path.is_relative_to(root):
        raise ValidationError('Ugyldig dokumentsti.')
    return path


def store(household_id, data):
    key = f'{household_id}/{uuid.uuid4().hex}'
    path = path_for(key)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('xb') as target:
        target.write(data)
        target.flush()
        os.fsync(target.fileno())
    return key


def discard_unregistered_staging(key):
    """Only for the exclusive new key owned by the current upload request.

    Never scan old files. On database uncertainty, retain the file. Callers must
    not invoke this after attempting to insert a reference (commit can be uncertain).
    """
    from django.db import DatabaseError
    from .models import Document
    try:
        if Document.objects.filter(storage_key=key).exists():
            return False
        path_for(key).unlink(missing_ok=True)
        return True
    except (DatabaseError, OSError):
        return False
