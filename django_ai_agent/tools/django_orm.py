"""
django_ai_agent/tools/django_orm.py

Optional built-in Django ORM tools for django-langgraph-agent.

Provides a DjangoORMToolkit that reads model configuration from
DJANGO_AI_AGENT["MODEL_WHITELIST"] and generates safe CRUD tools:

  - get_model_schema          : Describe a model's fields to the LLM
  - query_records             : Filter/paginate model records
  - aggregate_model_records   : Count, sum, average, min, max stats
  - add_record                : Create a new record (approval-gated by default)
  - update_record             : Update a record field-by-field (approval-gated by default)
"""

import json
import logging
from decimal import Decimal
from typing import Any

from django.apps import apps
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from django_ai_agent.conf import agent_settings

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Internal Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _extract_agent_restrictions(config: Any) -> tuple[list | None, list | None]:
    """Extracts allowed_models and blocked_fields from LangGraph runnable config."""
    if not config:
        return None, None
    if isinstance(config, dict):
        configurable = config.get("configurable", {})
    elif hasattr(config, "configurable"):
        configurable = getattr(config, "configurable", {})
    else:
        configurable = {}

    if not isinstance(configurable, dict):
        configurable = {}

    allowed_models = configurable.get("allowed_models")
    blocked_fields = configurable.get("blocked_fields")
    return allowed_models, blocked_fields


def _get_model_config(model_name: str, allowed_models: list | None = None) -> dict:
    """Returns the whitelist config dict for a given model name, with flexible lookup."""
    if allowed_models and isinstance(allowed_models, list) and len(allowed_models) > 0:
        clean_req = model_name.split(".")[-1].lower()
        matched = any(
            a.split(".")[-1].lower() == clean_req or model_name.lower() == a.lower()
            for a in allowed_models
        )
        if not matched:
            raise ValueError(
                f"Model '{model_name}' is not in allowed_models for this agent. "
                f"Allowed models: {allowed_models}"
            )

    whitelist = getattr(agent_settings, "MODEL_WHITELIST", {})
    if whitelist and isinstance(whitelist, dict):
        if model_name in whitelist:
            return whitelist[model_name]

        clean_name = model_name.split(".")[-1].lower()
        for key, conf in whitelist.items():
            key_clean = key.split(".")[-1].lower()
            if key_clean == clean_name or key.lower() == model_name.lower():
                return conf

        allowed = list(whitelist.keys())
        raise ValueError(
            f"Model '{model_name}' is not in MODEL_WHITELIST. "
            f"Allowed models: {allowed}"
        )

    # Dynamic lookup from installed Django models
    try:
        clean_name = model_name.split(".")[-1].lower()
        if "." in model_name:
            app_label, mname = model_name.split(".", 1)
            model_cls = apps.get_model(app_label, mname)
        else:
            model_cls = None
            for m in apps.get_models():
                if m._meta.object_name.lower() == clean_name:
                    model_cls = m
                    break
        if model_cls:
            return {
                "app_label": model_cls._meta.app_label,
                "display_name": model_cls._meta.verbose_name.title(),
                "object_name": model_cls._meta.object_name,
            }
    except Exception:
        pass

    raise ValueError(f"Model '{model_name}' is not accessible.")


def _get_model_class(model_name: str, allowed_models: list | None = None):
    """Resolves a whitelisted model name to its Django model class."""
    conf = _get_model_config(model_name, allowed_models=allowed_models)
    app_label = conf.get("app_label")
    object_name = conf.get("object_name", model_name.split(".")[-1])

    if app_label:
        try:
            return apps.get_model(app_label, object_name)
        except LookupError:
            pass

    for m in apps.get_models():
        if m._meta.object_name.lower() == object_name.lower() or f"{m._meta.app_label}.{m._meta.object_name}".lower() == model_name.lower():
            return m

    raise ValueError(f"Could not resolve Django model class for '{model_name}'.")


def get_whitelisted_models_summary(allowed_models: list | None = None) -> str:
    """Returns a readable summary of whitelisted models for system prompt injection."""
    lines = []

    if allowed_models and isinstance(allowed_models, list) and len(allowed_models) > 0:
        for item in allowed_models:
            clean_item = item.split(".")[-1]
            try:
                model_cls = _get_model_class(item, allowed_models=allowed_models)
                disp = model_cls._meta.verbose_name.title()
                lines.append(f"- {clean_item} ({disp}) [{item}]")
            except Exception:
                lines.append(f"- {clean_item} [{item}]")
        return "\n".join(lines)

    whitelist = getattr(agent_settings, "MODEL_WHITELIST", {})
    if whitelist and isinstance(whitelist, dict):
        for name, conf in whitelist.items():
            disp = conf.get("display_name", name)
            lines.append(f"- {name} ({disp})")
    else:
        for m in apps.get_models():
            if not m._meta.app_label.startswith("django_ai_agent") and not m._meta.app_label.startswith("admin") and not m._meta.app_label.startswith("sessions"):
                lines.append(f"- {m._meta.object_name} ({m._meta.verbose_name.title()})")

    return "\n".join(lines)


def _get_accessible_fields(model_name: str, model, allowed_models: list | None = None, blocked_fields: list | None = None) -> list[str]:
    """
    Returns the list of field names accessible for this model,
    applying allowlist, blocklist, per-agent blocked fields, and global blocked substrings.
    """
    conf = _get_model_config(model_name, allowed_models=allowed_models)
    global_blocked = set(agent_settings.BLOCKED_FIELD_SUBSTRINGS)
    if blocked_fields:
        global_blocked.update(blocked_fields)

    per_model_excluded = set(conf.get("exclude_fields", []))
    allowlist = conf.get("fields", None)

    all_fields = []
    for field in model._meta.get_fields():
        if not hasattr(field, "column"):
            continue
        fname = field.name

        if allowlist is not None:
            if fname in allowlist:
                if not any(blocked.lower() in fname.lower() for blocked in global_blocked):
                    all_fields.append(fname)
            continue

        if fname in per_model_excluded:
            continue

        fname_lower = fname.lower()
        if any(blocked.lower() in fname_lower for blocked in global_blocked):
            continue

        all_fields.append(fname)

    return all_fields


def _validate_filter_keys(model_name: str, filters: dict, allowed_models: list | None = None, blocked_fields: list | None = None) -> None:
    global_blocked = set(agent_settings.BLOCKED_FIELD_SUBSTRINGS)
    if blocked_fields:
        global_blocked.update(blocked_fields)

    conf = _get_model_config(model_name, allowed_models=allowed_models)
    per_model_excluded = set(conf.get("exclude_fields", []))
    allowlist = conf.get("fields", None)

    for key in filters:
        field_root = key.split("__")[0].lower()

        for blocked in global_blocked:
            if blocked.lower() in field_root:
                raise ValueError(f"Filtering on field '{field_root}' is not allowed.")

        if field_root in per_model_excluded:
            raise ValueError(
                f"Filtering on field '{field_root}' is not allowed for {model_name}."
            )

        if allowlist is not None and field_root not in allowlist:
            raise ValueError(
                f"Filtering on field '{field_root}' is not in the allowed fields for {model_name}."
            )


def _validate_write_keys(model_name: str, data: dict, allowed_models: list | None = None, blocked_fields: list | None = None) -> None:
    global_blocked = set(agent_settings.BLOCKED_FIELD_SUBSTRINGS)
    if blocked_fields:
        global_blocked.update(blocked_fields)

    conf = _get_model_config(model_name, allowed_models=allowed_models)
    per_model_excluded = set(conf.get("exclude_fields", []))
    allowlist = conf.get("fields", None)

    for key in data:
        field_root = key.split("__")[0].lower()

        for blocked in global_blocked:
            if blocked.lower() in field_root:
                raise ValueError(f"Writing to field '{field_root}' is not allowed.")

        if field_root in per_model_excluded:
            raise ValueError(
                f"Writing to field '{field_root}' is not allowed for {model_name}."
            )

        if allowlist is not None and field_root not in allowlist:
            raise ValueError(
                f"Field '{field_root}' is not in the allowed fields for {model_name}."
            )


def _serialize_qs(qs, field_names: list[str]) -> list[dict]:
    results = []
    for obj in qs:
        row = {}
        for fname in field_names:
            try:
                val = getattr(obj, fname)
                if isinstance(val, Decimal):
                    val = str(val)
                elif hasattr(val, "isoformat"):
                    val = val.isoformat()
                elif hasattr(val, "pk"):
                    val = val.pk
                row[fname] = val
            except Exception:
                row[fname] = None
        results.append(row)
    return results


# ──────────────────────────────────────────────────────────────────────────────
# Tool Definitions
# ──────────────────────────────────────────────────────────────────────────────

@tool
def get_model_schema(model_name: str, config: RunnableConfig = None) -> str:
    """
    Returns the accessible fields and their types for a given model.
    Use this before querying or modifying records to understand the schema.

    Args:
        model_name: The model name (e.g. 'Order', 'Product').
    """
    try:
        allowed_models, blocked_fields = _extract_agent_restrictions(config)
        model = _get_model_class(model_name, allowed_models=allowed_models)
        accessible = _get_accessible_fields(model_name, model, allowed_models=allowed_models, blocked_fields=blocked_fields)
        conf = _get_model_config(model_name, allowed_models=allowed_models)
        display_name = conf.get("display_name", model_name)

        fields_info = []
        for field in model._meta.get_fields():
            if not hasattr(field, "column"):
                continue
            if field.name not in accessible:
                continue
            field_type = type(field).__name__.replace("Field", "")
            null_info = "nullable" if getattr(field, "null", False) else "required"
            fields_info.append(f"  - {field.name} ({field_type}, {null_info})")

        return (
            f"Model: {display_name} [{model_name}]\n"
            f"Accessible fields ({len(fields_info)}):\n"
            + "\n".join(fields_info)
        )
    except Exception as exc:
        return f"Error: {exc}"


@tool
def query_records(
    model_name: str,
    filters_json: str = "{}",
    order_by: str = "-id",
    limit: int = 20,
    offset: int = 0,
    config: RunnableConfig = None,
) -> str:
    """
    Query records from an allowed model (e.g. 'Order', 'Product') with filters, ordering, and pagination.

    Args:
        model_name:   Model name (e.g. 'Order', 'Product').
        filters_json: JSON string of Django ORM filter kwargs.
                      e.g. '{"status": "pending"}' or '{}' for all records.
        order_by:     Field to order by (prefix with - for descending). Default: "-id".
        limit:        Max records to return (max 100). Default: 20.
        offset:       Pagination offset. Default: 0.
    """
    try:
        allowed_models, blocked_fields = _extract_agent_restrictions(config)
        model = _get_model_class(model_name, allowed_models=allowed_models)
        filters = json.loads(filters_json) if filters_json else {}
        _validate_filter_keys(model_name, filters, allowed_models=allowed_models, blocked_fields=blocked_fields)

        accessible_fields = _get_accessible_fields(model_name, model, allowed_models=allowed_models, blocked_fields=blocked_fields)
        qs = model.objects.filter(**filters)

        try:
            qs = qs.order_by(order_by)
        except Exception:
            pass

        total_count = qs.count()
        sliced = list(qs[offset : offset + limit])
        records = _serialize_qs(sliced, accessible_fields)

        return json.dumps(
            {
                "model": model_name,
                "total": total_count,
                "returned": len(records),
                "offset": offset,
                "limit": limit,
                "results": records,
            },
            indent=2,
            ensure_ascii=False,
        )

    except Exception as exc:
        logger.warning("query_records error for model '%s': %s", model_name, exc)
        return f"Error: {exc}"


@tool
def aggregate_model_records(
    model_name: str,
    filters_json: str = "{}",
    aggregations_json: str = "[]",
    config: RunnableConfig = None,
) -> str:
    """
    Compute aggregate statistics (Count, Sum, Avg, Min, Max) on a set of records.
    Use this instead of query_records when you just need summary metrics (count, totals, averages), to save tokens.

    Args:
        model_name:        Model name (e.g. 'Order', 'Product').
        filters_json:      JSON string of filter conditions (e.g. '{"status": "delivered"}').
        aggregations_json: JSON list of aggregations. Each must have "type" and "field".
                           Valid types: "count", "sum", "avg", "min", "max".
                           Example: '[{"type": "count", "field": "id"}, {"type": "avg", "field": "total_amount"}]'
    """
    try:
        from django.db.models import Count, Sum, Avg, Min, Max

        allowed_models, blocked_fields = _extract_agent_restrictions(config)
        model = _get_model_class(model_name, allowed_models=allowed_models)
        filters = json.loads(filters_json) if filters_json else {}
        aggregations = json.loads(aggregations_json) if aggregations_json else []

        _validate_filter_keys(model_name, filters, allowed_models=allowed_models, blocked_fields=blocked_fields)

        qs = model.objects.filter(**filters)

        if not aggregations:
            return f"Total matching records for {model_name}: {qs.count()}"

        global_blocked = set(agent_settings.BLOCKED_FIELD_SUBSTRINGS)
        if blocked_fields:
            global_blocked.update(blocked_fields)

        agg_dict = {}
        for agg in aggregations:
            agg_type = str(agg.get("type", "")).lower()
            field_name = agg.get("field")
            if not field_name:
                continue

            field_root = field_name.split("__")[0].lower()
            if any(b.lower() in field_root for b in global_blocked):
                raise ValueError(f"Aggregation on field '{field_name}' is not allowed.")

            agg_key = f"{field_name}_{agg_type}"
            if agg_type == "count":
                agg_dict[agg_key] = Count(field_name)
            elif agg_type == "sum":
                agg_dict[agg_key] = Sum(field_name)
            elif agg_type == "avg":
                agg_dict[agg_key] = Avg(field_name)
            elif agg_type == "min":
                agg_dict[agg_key] = Min(field_name)
            elif agg_type == "max":
                agg_dict[agg_key] = Max(field_name)
            else:
                return f"Error: Unknown aggregation type '{agg_type}'."

        raw_result = qs.aggregate(**agg_dict)
        serialized_result = {}
        for k, v in raw_result.items():
            if isinstance(v, Decimal):
                serialized_result[k] = str(v)
            elif hasattr(v, "isoformat"):
                serialized_result[k] = v.isoformat()
            else:
                serialized_result[k] = v

        return f"Aggregation Results for {model_name}:\n{json.dumps(serialized_result, indent=2, ensure_ascii=False)}"
    except Exception as exc:
        logger.warning("aggregate_model_records error for model '%s': %s", model_name, exc)
        return f"Error: {exc}"


@tool
def add_record(model_name: str, data_json: str, config: RunnableConfig = None) -> str:
    """
    Create a new record for an allowed model.

    Args:
        model_name: Model name (e.g. 'Product', 'Order').
        data_json:  JSON string of field-value pairs to set on the new record.
    """
    try:
        allowed_models, blocked_fields = _extract_agent_restrictions(config)
        model = _get_model_class(model_name, allowed_models=allowed_models)
        data = json.loads(data_json)
        _validate_write_keys(model_name, data, allowed_models=allowed_models, blocked_fields=blocked_fields)

        obj = model.objects.create(**data)
        accessible_fields = _get_accessible_fields(model_name, model, allowed_models=allowed_models, blocked_fields=blocked_fields)
        serialized = _serialize_qs([obj], accessible_fields)[0]

        return f"✅ Created {model_name} #{obj.pk}:\n{json.dumps(serialized, indent=2, ensure_ascii=False)}"

    except Exception as exc:
        logger.warning("add_record error for model '%s': %s", model_name, exc)
        return f"Error: {exc}"


@tool
def update_record(model_name: str, record_id: Any = None, data_json: str = "{}", pk: Any = None, config: RunnableConfig = None) -> str:
    """
    Update an existing record by primary key.

    Args:
        model_name: Model name (e.g. 'Product', 'Order').
        record_id:  Primary key of the record to update.
        data_json:  JSON string of fields to update.
        pk:         Alias for record_id.
    """
    target_pk = record_id if record_id is not None else pk
    try:
        allowed_models, blocked_fields = _extract_agent_restrictions(config)
        model = _get_model_class(model_name, allowed_models=allowed_models)
        data = json.loads(data_json)
        _validate_write_keys(model_name, data, allowed_models=allowed_models, blocked_fields=blocked_fields)

        obj = model.objects.get(pk=target_pk)
        for key, val in data.items():
            setattr(obj, key, val)
        obj.save(update_fields=list(data.keys()))

        accessible_fields = _get_accessible_fields(model_name, model, allowed_models=allowed_models, blocked_fields=blocked_fields)
        serialized = _serialize_qs([obj], accessible_fields)[0]

        return f"✅ Updated {model_name} #{obj.pk}:\n{json.dumps(serialized, indent=2, ensure_ascii=False)}"

    except Exception as exc:
        logger.warning("update_record error for model '%s', pk '%s': %s", model_name, target_pk, exc)
        return f"Error: {exc}"


class DjangoORMToolkit:
    """
    Toolkit that creates configured ORM tools for an agent.
    """
    def __init__(self, include_read: bool = True, include_write: bool = True, *args, **kwargs):
        self.include_read = include_read
        self.include_write = include_write

    @property
    def tools(self) -> list:
        return self.get_tools()

    @property
    def approval_tools(self) -> set:
        return {"add_record", "update_record"} if self.include_write else set()

    def get_tools(self) -> list:
        tools_list = []
        if self.include_read:
            tools_list.extend([get_model_schema, query_records, aggregate_model_records])
        if self.include_write:
            tools_list.extend([add_record, update_record])
        return tools_list
