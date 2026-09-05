# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-09-05

The first release with a CI gate. Every leg of the matrix (Python 3.10–3.13,
Django 5.2 and 6.1) and the migration check must pass before a release can
reach PyPI.

### ⚠️ Breaking

- **The built-in SSE endpoints are no longer anonymous** (#2). They were
  `csrf_exempt` and open to any caller, which exposed the ORM tools to the
  internet. Callers now need a staff session, a matching `API_PERMISSION`, or
  an explicit `"public"` opt-in, plus a CSRF token on POST. The bundled chat UI
  already sends one. See "Upgrading from 0.1.x" in the README.
- **Threads created before this release have no owner.** Ownership is recorded
  per thread and 0.1.x had no authenticated caller to record, so those rows
  have `user_id = NULL` and are treated as unclaimed. The README documents the
  behaviour under each `API_PERMISSION` setting.

### Fixed

- Model/migration drift: `makemigrations` no longer wants a `0003` inside
  `site-packages` (#5). A `0003_alter_agentconfig_extra_tools` migration ships
  with the package, and CI now fails on any future drift.
- `_summarize_node` deleted the newest `HumanMessage`, so the agent answered a
  question it could no longer see (#4).
- `_serialize_qs` raised on unknown field types (`PhoneNumber`, `UUID`, files),
  which made read tools fail and let the model fabricate data (#7).
- `setup_agent_db` failed on PostgreSQL: `CREATE INDEX CONCURRENTLY` cannot run
  inside a transaction block (#8).
- The admin chat transcript did not auto-scroll to the newest message (#6). The
  root cause was a silent no-op — a `scrollTop` write against a panel that was
  not scrollable — not the `max-height` it looked like. Scrolling now sticks to
  the bottom only while the reader is already there, so it no longer yanks the
  view away mid-read.
- Message bubbles overflowed: `.ai-msg-meta` could not shrink inside
  `.ai-msg-body`'s `max-width` (#10).
- `allowed_models` autocomplete offered models that could never work, including
  `AUTH_USER_MODEL`; the mismatch only surfaced at chat time (#11). The picker
  now lists only resolvable whitelisted models and the form validates the
  selection.
- Streaming errors no longer leak exception text to the client. The detail goes
  to the log; the client gets a generic message.

### Added

- **Upstream provider routing** (#9). `OPENROUTER_PROVIDER`,
  `OPENROUTER_BASE_URL`, `EXTRA_BODY` and `MODEL_KWARGS` settings let you pin
  the OpenRouter route — Gemini no longer silently defaults to the pricier
  Vertex path. Documented under "Choosing the Upstream Model Provider".
- **Tenant scoping for the built-in ORM tools** (#3), and a way to replace the
  built-ins rather than only add to them.
- **Custom tools in the example project** (#1): `check_low_stock`,
  `apply_discount` and `send_order_confirmation`, including the
  human-in-the-loop approval path and `RunnableConfig` access.
- `CHANGELOG.md`, and a CI workflow running the suite, `manage.py check` and
  `makemigrations --check` on pull requests and on `master`.

### Changed

- `langgraph-checkpoint-sqlite` is now a declared runtime dependency. It ships
  as its own distribution and is the default checkpointer for Django's default
  database, so a fresh install previously raised `ModuleNotFoundError` on the
  first chat.
- `django-unfold` is declared in the `test` extra — the example project's
  `INSTALLED_APPS` needs it.
- Classifiers now reflect what CI actually exercises: Python 3.10–3.13,
  Django 4.2 through 6.1.
- Test suite grew from 38 to 147 tests.

## [0.1.3] - 2026-08-08

Earlier releases predate this changelog. See the
[release history](https://github.com/bixat/django-langgraph-agent/releases).

[0.2.0]: https://github.com/bixat/django-langgraph-agent/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/bixat/django-langgraph-agent/releases/tag/v0.1.3
