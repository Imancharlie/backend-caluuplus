"""
Auto-invalidate RAG cache when content changes.

When a new article or opportunity is published/updated, the RAG search cache
may contain stale results. This invalidates the cached searches so the next
query reflects the new content — no manual re-index step required (Phase 4).
"""
import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver([post_save, post_delete], sender='api.Article')
@receiver([post_save, post_delete], sender='resources_opps.Opportunity')
def invalidate_rag_cache(sender, **kwargs):
    """Clear RAG search cache when articles/opportunities change."""
    try:
        from django.core.cache import cache

        # Best-effort invalidation. With a Redis cache backend this wipes all
        # RAG search keys; with LocMemCache it is a no-op (each worker is
        # independent anyway).
        try:
            cache.clear()
        except Exception:
            pass

        logger.debug(f"RAG cache invalidated after {sender.__name__} change")
    except Exception as e:
        logger.debug(f"RAG cache invalidation skipped: {e}")
