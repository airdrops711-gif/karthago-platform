"""Core views including health check."""
from django.http import JsonResponse
from django.db import connection


def healthz(request):
    """Kubernetes/OpenShift liveness and readiness probe endpoint."""
    db_ok = True
    try:
        connection.ensure_connection()
    except Exception:
        db_ok = False

    status = "ok" if db_ok else "degraded"
    return JsonResponse({"status": status, "database": db_ok}, status=200 if db_ok else 503)
