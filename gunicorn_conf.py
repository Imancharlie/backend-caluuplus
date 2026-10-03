"""Gunicorn config for the Caluu+ backend.

Why ``preload_app = True``
--------------------------
The chatbot loads a sentence-transformers model in
``VectorSearchService._load_model``. That import costs ~13-17s (plus a
Hugging Face metadata call) and used to happen lazily, inside whichever worker
happened to serve the first chatbot message -- so that unlucky request sat for
17s before the user saw anything, and every fresh worker paid it again.

With ``preload_app`` the master imports the app once and then forks. The workers
share those pages copy-on-write, so:

  * the 13-17s load happens once at boot, not inside a user request
  * the ~90MB of model weights are shared, not duplicated per worker
  * no per-worker lazy load to race on

Measured on this box: two independently-warmed workers reached ~633MB + ~445MB
RSS (over 1GB just for this app). Preloaded, the same two workers share the
model pages instead.

Keep the warmup inside the master explicit rather than relying on lazy import
order, so a failure is logged at boot instead of surfacing as a slow first
request.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "academic_backend.production")

# The model is already in the local sentence-transformers cache. Without this
# every boot makes a blocking call to huggingface.co just to read metadata, which
# adds latency and makes the service fail to start when that host is
# unreachable. HF_HUB_OFFLINE=1 is set in the unit's EnvironmentFile too; this
# is the belt-and-braces version for local/manual runs.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def when_ready(server):
    """Pay the model-loading cost once, in the master, before forking."""
    server.log.info("Preloading app and warming chatbot services...")
    try:
        import django

        django.setup()
        from chatbot.views import get_enhanced_service, get_vector_service

        get_enhanced_service()
        vector = get_vector_service()
        loaded = getattr(vector, "model", None) is not None
        server.log.info("Warmup finished (embedding model loaded: %s)", loaded)
    except Exception as exc:  # noqa: BLE001 - never block startup on warmup
        server.log.warning("Chatbot warmup failed (continuing): %s", exc)


bind = "127.0.0.1:8006"
workers = 2
timeout = 120
graceful_timeout = 30
accesslog = "-"
errorlog = "-"

preload_app = True