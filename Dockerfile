# Stage 1: Build virtual environment
FROM registry.access.redhat.com/ubi9/python-311:latest AS builder
USER 0
WORKDIR /build
RUN dnf install -y --nodocs gcc postgresql-devel libxml2-devel libxslt-devel && \
    dnf clean all
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip wheel && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime Image (OpenShift Arbitrary UID Compliant)
FROM registry.access.redhat.com/ubi9/python-311:latest
USER 0
RUN dnf install -y --nodocs libpq libxml2 libxslt && \
    dnf clean all && \
    rm -rf /var/cache/dnf
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    HOME=/opt/app-root/src
WORKDIR /opt/app-root/src
COPY . .
# Grant write access to GID 0 (root group) across runtime paths
RUN mkdir -p /opt/app-root/src/static \
             /opt/app-root/src/media \
             /opt/app-root/src/logs \
             /opt/app-root/src/run && \
    chown -R 1001:0 /opt/app-root && \
    chmod -R g=u /opt/app-root && \
    chmod -R 775 /opt/app-root/src/static \
                 /opt/app-root/src/media \
                 /opt/app-root/src/logs \
                 /opt/app-root/src/run
USER 1001
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "--error-logfile", "-"]
