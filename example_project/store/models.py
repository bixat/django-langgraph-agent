"""
example_project/store/models.py

Simple e-commerce models for testing the django-langgraph-agent package.
"""

from django.db import models


class Product(models.Model):
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=100, default="general")
    stock = models.IntegerField(default=0)
    cost_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Internal cost — excluded from AI access via exclude_fields"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "store"

    def __str__(self):
        return self.name


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]

    customer_name = models.CharField(max_length=200)
    customer_email = models.EmailField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    # Internal fields — blocked via exclude_fields in MODEL_WHITELIST
    payment_reference = models.CharField(max_length=200, blank=True)
    internal_notes = models.TextField(blank=True)
    cost_breakdown = models.JSONField(default=dict)

    class Meta:
        app_label = "store"

    def __str__(self):
        return f"Order #{self.pk} — {self.customer_name}"
