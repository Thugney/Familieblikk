"""Private, bounded-lived scan spool. Never visits legacy document storage."""
from contextlib import contextmanager
from pathlib import Path
import os
import re
import tempfile
import time
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError

TTL_SECONDS = 15 * 60

def root():
    path = Path(settings.PRIVATE_SCAN_ROOT)
    if path.is_symlink():
        raise ValidationError('Ugyldig skannelager.')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path.resolve()

def path_for(key):
    if not re.fullmatch(r'scan-[0-9a-f]{32}', key):
        raise ValidationError('Ugyldig skannenøkkel.')
    path = root() / key
    if path.is_symlink():
        raise ValidationError('Ugyldig skannefil.')
    return path

def store(data):
    key = 'scan-' + uuid.uuid4().hex
    with path_for(key).open('xb') as output:
        os.chmod(output.name, 0o600)
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    return key

def discard(key):
    path_for(key).unlink(missing_ok=True)

@contextmanager
def scratch():
    # Flat files only; the sweeper never follows links or walks arbitrary trees.
    with tempfile.TemporaryDirectory(prefix='scratch-', dir=root()) as directory:
        yield Path(directory)

def sweep_orphans(referenced, now=None):
    cutoff = (time.time() if now is None else now) - TTL_SECONDS
    for path in root().iterdir():
        if path.is_symlink():
            continue
        if re.fullmatch(r'scan-[0-9a-f]{32}', path.name) and path.name not in referenced:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        elif re.fullmatch(r'scratch-[\w-]+', path.name) and path.is_dir() and path.stat().st_mtime < cutoff:
            # Native adapters only create direct scratch files. Refuse nested/link entries.
            children = list(path.iterdir())
            if any(item.is_symlink() or not item.is_file() for item in children):
                continue
            for item in children:
                item.unlink(missing_ok=True)
            path.rmdir()
