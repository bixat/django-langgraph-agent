"""
example_project/store/admin.py

Admin configuration for example Product and Order models using Unfold.
"""

from django.contrib import admin

try:
    from unfold.admin import ModelAdmin
except ImportError:
    from django.contrib.admin import ModelAdmin

from .models import Order, Product


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ("name", "price", "category", "stock", "cost_price", "is_active", "created_at")
    list_filter = ("category", "is_active")
    search_fields = ("name", "category")
    list_editable = ("price", "stock", "is_active")


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = ("id", "customer_name", "customer_email", "status", "total_amount", "created_at")
    list_filter = ("status",)
    search_fields = ("customer_name", "customer_email", "payment_reference")
