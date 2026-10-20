FROM python:3.12.15-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r requirements.lock && useradd --create-home --uid 10001 familieblikk
COPY manage.py /app/
COPY familieblikk /app/familieblikk
COPY budget /app/budget
RUN DJANGO_SECRET_KEY=static-collection-only python manage.py collectstatic --noinput && chown -R familieblikk:familieblikk /app
USER familieblikk
EXPOSE 8000
CMD ["gunicorn", "familieblikk.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--no-control-socket", "--access-logfile", "-", "--access-logformat", "%(s)s %(L)s", "--error-logfile", "-"]
