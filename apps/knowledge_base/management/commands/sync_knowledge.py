from django.core.management.base import BaseCommand
from apps.knowledge_base.synchronization import KnowledgeSynchronizer
from apps.knowledge_base.vector_store import ChromaVectorStore

class Command(BaseCommand):
    help = "Synchronize all active PostgreSQL services, FAQs, and documents into ChromaDB."

    def add_arguments(self, parser):
        parser.add_argument(
            '--rebuild',
            action='store_true',
            help='Reset vector store and rebuild all embeddings from scratch'
        )

    def handle(self, *args, **options):
        if options['rebuild']:
            self.stdout.write(self.style.WARNING("Resetting ChromaDB collection..."))
            ChromaVectorStore.get_instance().reset()

        self.stdout.write(self.style.NOTICE("Synchronizing knowledge base records with ChromaDB..."))
        stats = KnowledgeSynchronizer.sync_all()

        self.stdout.write(self.style.SUCCESS(
            f"Sync complete!\n"
            f"  Services:  {stats['services']}\n"
            f"  Products:  {stats.get('products', 0)}\n"
            f"  FAQs:      {stats['faqs']}\n"
            f"  Documents: {stats['documents']}\n"
            f"  Business:  {stats['business']}\n"
            f"  Errors:    {stats['errors']}\n"
            f"  Total in ChromaDB: {ChromaVectorStore.get_instance().count()}"
        ))
