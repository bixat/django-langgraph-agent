"""
example_project/store/tools.py

Custom tools for the store agents — the counterpart to the built-in ORM tools.

Reach for a custom tool when the built-ins cannot express the job:
  * business logic the model should not have to assemble from raw queries
    (`check_low_stock`),
  * a write with rules attached (`apply_discount` clamps the percentage and
    refuses inactive products),
  * a side effect that is not a database row at all (`send_order_confirmation`).

Two decorators, in this order:

    @register_tool   # makes the name selectable in AgentConfig.extra_tools
    @tool            # makes it a LangChain tool

`@tool` builds the tool from the signature and the docstring, so the docstring
IS the prompt the model reads — describe arguments and units there, not in a
comment.

Registration only happens when this module is imported. StoreConfig.ready()
does that, which is why the names show up in the admin without any project
importing them by hand.
"""

import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from django_langgraph_agent import register_tool

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Read-only tool
# ──────────────────────────────────────────────────────────────────────────────

@register_tool
@tool
def check_low_stock(threshold: int = 5, category: str = "") -> str:
    """
    Lists active products whose stock is at or below `threshold`.

    Args:
        threshold: Stock level at or below which a product counts as low. Default 5.
        category:  Optional category to restrict the check to (e.g. "electronics").
    """
    from .models import Product

    qs = Product.objects.filter(is_active=True, stock__lte=threshold)
    if category:
        qs = qs.filter(category__iexact=category)

    rows = list(qs.order_by("stock").values("id", "name", "category", "stock")[:50])
    if not rows:
        scope = f" in category '{category}'" if category else ""
        return f"No active products{scope} are at or below a stock of {threshold}."

    lines = [f"{len(rows)} product(s) at or below a stock of {threshold}:"]
    lines += [f"  #{r['id']} {r['name']} ({r['category']}) — {r['stock']} left" for r in rows]
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Write tool — gated behind approval (see agents.py / AgentConfig.extra_approval_tools)
# ──────────────────────────────────────────────────────────────────────────────

@register_tool
@tool
def apply_discount(product_id: int, percent: float, config: RunnableConfig = None) -> str:
    """
    Reduces a product's price by `percent` and reports the old and new price.

    Args:
        product_id: Primary key of the product to discount.
        percent:    Discount percentage between 0 and 90 (e.g. 15 for 15% off).
    """
    from decimal import Decimal

    from .models import Product

    if not 0 < percent <= 90:
        return f"Error: percent must be between 0 and 90, got {percent}."

    try:
        product = Product.objects.get(pk=product_id, is_active=True)
    except Product.DoesNotExist:
        return f"Error: no active product with id {product_id}."

    old_price = product.price
    factor = Decimal(str(1 - percent / 100))
    product.price = (old_price * factor).quantize(Decimal("0.01"))
    product.save(update_fields=["price"])

    # `config` carries the RunnableConfig the agent was invoked with — the
    # place to read thread_id / user_id for auditing a write.
    actor = (config or {}).get("configurable", {}).get("user_id", "anonymous")
    logger.info("apply_discount: user=%s product=%s %s→%s", actor, product_id, old_price, product.price)

    return f"Applied {percent}% off {product.name}: ${old_price} → ${product.price}."


# ──────────────────────────────────────────────────────────────────────────────
# Side-effecting tool — nothing to do with the ORM
# ──────────────────────────────────────────────────────────────────────────────

@register_tool
@tool
def send_order_confirmation(order_id: int) -> str:
    """
    Sends the customer a confirmation email for an order.

    Args:
        order_id: Primary key of the order to confirm.
    """
    from .models import Order

    try:
        order = Order.objects.only("id", "customer_name", "customer_email", "status").get(pk=order_id)
    except Order.DoesNotExist:
        return f"Error: no order with id {order_id}."

    # A real project would hand off to django.core.mail / Celery here.
    logger.info("send_order_confirmation: order=%s to=%s", order_id, order.customer_email)
    return (
        f"Confirmation for order #{order.pk} ({order.status}) "
        f"queued to {order.customer_name} <{order.customer_email}>."
    )
