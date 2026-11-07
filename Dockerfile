FROM python:3.12-slim AS runtime
ARG TARGETARCH
ARG HARVESTOPS_VERSION=0.1.0
ARG HARVESTOPS_COMMIT=unknown
ARG HARVESTOPS_BUILD_TIMESTAMP=unknown
ARG HARVESTOPS_ENVIRONMENT=container
ARG HARVESTOPS_IMAGE_DIGEST=unknown
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HARVESTOPS_VERSION=$HARVESTOPS_VERSION \
    HARVESTOPS_COMMIT=$HARVESTOPS_COMMIT \
    HARVESTOPS_BUILD_TIMESTAMP=$HARVESTOPS_BUILD_TIMESTAMP \
    HARVESTOPS_ENVIRONMENT=$HARVESTOPS_ENVIRONMENT \
    HARVESTOPS_IMAGE_DIGEST=$HARVESTOPS_IMAGE_DIGEST
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl gnupg ca-certificates unixodbc \
 && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
 && apt-get update \
 && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN useradd --create-home --uid 10001 appuser
COPY pyproject.toml ./
COPY requirements.lock ./
COPY harvestops ./harvestops
COPY db ./db
COPY knowledge ./knowledge
COPY data ./data
COPY docs ./docs
COPY evidence ./evidence
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --require-hashes -r requirements.lock \
 && pip install --no-cache-dir --no-deps . \
 && pip uninstall -y pip
COPY harvestops/assets ./assets
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8050
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8050/healthz')"
CMD ["gunicorn", "--bind", "0.0.0.0:8050", "--workers", "2", "--timeout", "60", "harvestops.web:server"]
