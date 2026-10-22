"""Reject oversized file streams before Django's temporary-file handler writes them."""
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.files.uploadhandler import FileUploadHandler, StopUpload, StopFutureHandlers
from .document_storage import MAX_BYTES


class DocumentUploadLimitHandler(FileUploadHandler):
    chunk_size = 64 * 1024

    def __init__(self, request=None):
        super().__init__(request)
        self.received = 0

    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.buffer = BytesIO()
        raise StopFutureHandlers()

    def receive_data_chunk(self, raw_data, start):
        # One document per request. Aggregate file bytes also bounds multi-file abuse.
        self.received += len(raw_data)
        if self.received > MAX_BYTES:
            self.request.document_upload_error = 'Opplastingen er stoppet: maks. 10 MiB per forespørsel.'
            raise StopUpload(connection_reset=True)
        self.buffer.write(raw_data)
        return None

    def file_complete(self, file_size):
        self.buffer.seek(0)
        return InMemoryUploadedFile(self.buffer, self.field_name, self.file_name,
                                   self.content_type, file_size, self.charset)

    def upload_interrupted(self):
        if hasattr(self, 'buffer'):
            self.buffer.close()
