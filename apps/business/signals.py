import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Product, ProductCapability, ProductIntegration, ProductPricingPlan

logger = logging.getLogger(__name__)


def _sync_prod(product):
    if not product:
        return
    try:
        from apps.knowledge_base.synchronization import KnowledgeSynchronizer
        KnowledgeSynchronizer.sync_product(product)
    except Exception as exc:
        logger.debug("Product vector sync skipped or logged: %s", exc)


@receiver(post_save, sender=Product)
@receiver(post_delete, sender=Product)
def on_product_change(sender, instance, **kwargs):
    _sync_prod(instance)


@receiver(post_save, sender=ProductCapability)
@receiver(post_delete, sender=ProductCapability)
def on_capability_change(sender, instance, **kwargs):
    _sync_prod(getattr(instance, 'product', None))


@receiver(post_save, sender=ProductIntegration)
@receiver(post_delete, sender=ProductIntegration)
def on_integration_change(sender, instance, **kwargs):
    _sync_prod(getattr(instance, 'product', None))


@receiver(post_save, sender=ProductPricingPlan)
@receiver(post_delete, sender=ProductPricingPlan)
def on_pricing_plan_change(sender, instance, **kwargs):
    _sync_prod(getattr(instance, 'product', None))
