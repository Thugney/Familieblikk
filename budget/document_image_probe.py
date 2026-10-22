"""Decode an image in a bounded subprocess using Tesseract's approved Leptonica."""
import ctypes
import ctypes.util
import os
import sys
import tempfile


def main(path):
    library = ctypes.util.find_library('leptonica') or ctypes.util.find_library('lept')
    if not library: return 2
    lept = ctypes.CDLL(library)
    lept.pixRead.argtypes = [ctypes.c_char_p]
    lept.pixRead.restype = ctypes.c_void_p
    lept.pixDestroy.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    # Native decoders can return partial pixels after warning about truncation.
    # Treat diagnostic output as rejection, rather than accepting such a partial image.
    with tempfile.TemporaryFile() as diagnostics:
        saved = os.dup(2)
        try:
            os.dup2(diagnostics.fileno(), 2)
            image = ctypes.c_void_p(lept.pixRead(os.fsencode(path)))
        finally:
            os.dup2(saved, 2)
            os.close(saved)
        diagnostics.seek(0)
        warning = bool(diagnostics.read(8192))
    success = bool(image.value) and not warning
    if image.value: lept.pixDestroy(ctypes.byref(image))
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1]))
