FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[dev]"
RUN groupadd --system app && useradd --system --gid app --home-dir /app app
COPY --chown=app:app . .
RUN chmod 0555 docker-entrypoint.sh
USER app
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
