FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt && useradd --create-home app
COPY --chown=app:app . .
RUN mkdir -p /app/staticfiles /app/chroma_data && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["sh", "-c", "python manage.py collectstatic --noinput && exec waitress-serve --listen=0.0.0.0:8000 --threads=8 --channel-timeout=180 --no-clear-untrusted-proxy-headers config.wsgi:application"]
