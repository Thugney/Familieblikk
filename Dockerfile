FROM python:3.12.15-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Apply Debian fixes to packages inherited from the pinned base image as well.
# apt-get upgrade never removes packages or installs new dependency packages.
RUN apt-get update && apt-get upgrade -y --no-install-recommends && apt-get install -y --no-install-recommends tesseract-ocr=5.5.0-1+b1 tesseract-ocr-nor=1:4.1.0-2 tesseract-ocr-eng=1:4.1.0-2 poppler-utils=25.03.0-5+deb13u4 && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r requirements.lock && useradd --create-home --uid 10001 familieblikk
COPY manage.py /app/
COPY familieblikk /app/familieblikk
COPY budget /app/budget
RUN DJANGO_SECRET_KEY=static-collection-only python manage.py collectstatic --noinput && chown -R familieblikk:familieblikk /app && mkdir -p /private-documents /private-scans && chown familieblikk:familieblikk /private-documents /private-scans
USER familieblikk
EXPOSE 6451
CMD ["gunicorn", "familieblikk.wsgi:application", "--bind", "0.0.0.0:6451", "--workers", "2", "--no-control-socket", "--access-logfile", "-", "--access-logformat", "%(s)s %(L)s", "--error-logfile", "-"]
