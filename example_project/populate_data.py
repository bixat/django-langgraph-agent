"""
example_project/populate_data.py

Populate script for creating sample data, superuser, and AgentConfig objects.
Usage:
    PYTHONPATH=. python3 example_project/populate_data.py
"""

import os
import sys

import django

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example_project.settings")
django.setup()

from django.contrib.auth import get_user_model
from django_langgraph_agent.models import AgentConfig
from example_project.store.models import Order, Product


def populate():
    print("🚀 Populating example project data...")

    # 1. Create Superuser
    User = get_user_model()
    if not User.objects.filter(username="admin").exists():
        User.objects.create_superuser("admin", "admin@example.com", "admin123")
        print("✅ Superuser created: admin / admin123")
    else:
        print("ℹ️ Superuser 'admin' already exists.")

    # 2. Create Products
    products_data = [
        {"name": "Wireless Noise-Canceling Earbuds", "price": 89.99, "category": "electronics", "stock": 150, "cost_price": 45.00},
        {"name": "Ergonomic Aluminum Laptop Stand", "price": 34.99, "category": "accessories", "stock": 60, "cost_price": 12.50},
        {"name": "7-in-1 USB-C Multiport Hub", "price": 42.50, "category": "electronics", "stock": 90, "cost_price": 18.00},
        {"name": "Mechanical Gaming Keyboard RGB", "price": 119.99, "category": "electronics", "stock": 40, "cost_price": 65.00},
        {"name": "Ultra-Wide Curved Monitor 34-inch", "price": 499.99, "category": "monitors", "stock": 15, "cost_price": 310.00},
        {"name": "Eco-Friendly Cork Desk Pad", "price": 19.99, "category": "accessories", "stock": 200, "cost_price": 6.00},
    ]

    for p in products_data:
        obj, created = Product.objects.get_or_create(
            name=p["name"],
            defaults=p,
        )
        if created:
            print(f"  + Product: {obj.name} (${obj.price})")

    # 3. Create Orders
    orders_data = [
        {"customer_name": "Alice Smith", "customer_email": "alice@example.com", "status": "pending", "total_amount": 89.99, "payment_reference": "PAY-88123", "internal_notes": "First time buyer, priority shipping."},
        {"customer_name": "Bob Johnson", "customer_email": "bob@example.com", "status": "shipped", "total_amount": 162.49, "payment_reference": "PAY-99312", "internal_notes": "Gift wrap requested."},
        {"customer_name": "Charlie Brown", "customer_email": "charlie@example.com", "status": "delivered", "total_amount": 499.99, "payment_reference": "PAY-10023", "internal_notes": "Verified corporate invoice."},
    ]

    for o in orders_data:
        obj, created = Order.objects.get_or_create(
            payment_reference=o["payment_reference"],
            defaults=o,
        )
        if created:
            print(f"  + Order: #{obj.pk} for {obj.customer_name} (${obj.total_amount})")

    # 4. Create AgentConfig objects for Admin UI
    agent1, created1 = AgentConfig.objects.get_or_create(
        name="store",
        defaults={
            "display_name": "Customer Support Agent",
            "model_name": "google/gemini-3.5-flash-lite",
            "system_prompt": (
                "You are a warm, helpful customer support agent for our online tech store.\n"
                "You can search products, check stock, and assist customers.\n"
                "Be polite, concise, and structure responses with bullet points where appropriate.\n"
                "Today's date is {date}."
            ),
            "is_active": True,
        },
    )
    if created1:
        print(f"  + AgentConfig: {agent1.display_name} [{agent1.name}]")

    agent2, created2 = AgentConfig.objects.get_or_create(
        name="store_admin",
        defaults={
            "display_name": "Store Operations Admin Agent",
            "model_name": "google/gemini-3.5-flash-lite",
            "system_prompt": (
                "You are the senior store operations AI manager.\n"
                "You have full CRUD access to Products and Orders.\n"
                "⚠️ Always summarize what changes you are about to make before creating or updating records.\n"
                "Current date: {date}."
            ),
            "extra_approval_tools": ["add_record", "update_record"],
            "is_active": True,
        },
    )
    if created2:
        print(f"  + AgentConfig: {agent2.display_name} [{agent2.name}]")

    print("\n✨ Populate complete! You can now log into /admin with admin/admin123")


if __name__ == "__main__":
    populate()
