"""
rebuild_embeddings - precompute semantic embeddings for the knowledge base.

Used by Mr Caluu's semantic RAG (Phase B). After adding/editing knowledge
documents, run this so retrieval can use real vector search:

    python manage.py rebuild_embeddings
    python manage.py rebuild_embeddings --university 3
    python manage.py rebuild_embeddings --flush
"""
from django.core.management.base import BaseCommand

from chatbot.vector_service import VectorSearchService


class Command(BaseCommand):
    help = 'Precompute and store semantic embeddings for knowledge documents.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--university', type=int, default=None,
            help='Only rebuild embeddings for this university id (global docs still included).',
        )
        parser.add_argument(
            '--flush', action='store_true',
            help='Clear all stored embeddings first, then rebuild.',
        )

    def handle(self, *args, **options):
        from chatbot.models import KnowledgeDocument

        if options['flush']:
            cleared = KnowledgeDocument.objects.update(embedding=None)
            self.stdout.write(self.style.WARNING(f'Cleared embeddings for {cleared} documents.'))

        service = VectorSearchService()
        if service.model is None:
            self.stderr.write(self.style.ERROR(
                'Sentence-transformers model not available. Install '
                'sentence-transformers + faiss-cpu, then retry.'
            ))
            return

        ok = service.build_index(university_id=options['university'])
        total = KnowledgeDocument.objects.filter(is_active=True).count()
        embedded = KnowledgeDocument.objects.filter(is_active=True).exclude(embedding=None).count()
        self.stdout.write(self.style.SUCCESS(
            f'Index build {"succeeded" if ok else "finished"} — {embedded}/{total} active documents embedded.'
        ))
