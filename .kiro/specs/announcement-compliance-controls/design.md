# Announcement Compliance Controls Technical Design

## Overview

Announcement Compliance Controls extends the existing announcement module with five additive capabilities: a five-second participant acknowledgement delay, durable acknowledgement audit rows, a 24-hour Critical-announcement watchdog, an acknowledgement-logs API and admin display, and a live participant deadline display. The implementation remains inside the existing Python 3.10, FastAPI, SQLite, Jinja2, HTML5, Tailwind-class, and Vanilla JavaScript architecture.

The implementation boundary is absolute: application changes are limited to `app/services/announcement_service.py`, `app/routers/announcements.py`, `app/main.py`, `templates/announcements.html`, and `templates/admin_announcements.html`. No application, test, configuration, migration, frontend, or backend file is added or modified. Existing routes, startup handler order, sample data, template includes, CRUD behavior, participant tracking, and teammate code remain in place unless an approved requirement explicitly adds behavior.

### Design Goals

- Record exactly one durable audit row when an acknowledgement first transitions to acknowledged.
- Detect tracked, unacknowledged Critical recipients after the strict 24-hour deadline and emit the required warning.
- Keep each browser countdown independent, deterministic, and isolated to its rendered control.
- Expose logs through the exact `/api/v1/announcements/{announcement_id}/logs` contract and render untrusted values safely.
- Preserve every existing behavior and keep all integration local to the five approved files.

### Non-Goals and Constraints

This design does not add authentication, server-enforced reading delays, distributed watchdog coordination, durable escalation delivery, schema migration tooling, new dependencies, or production audit certification. The existing client-supplied identity, one-process watchdog, warning-log escalation, and SQLite deployment model remain unchanged. The production-hardening concerns in `requirements.md` therefore remain applicable.

### Research Findings

- FastAPI startup handlers execute before request handling; although current FastAPI guidance favors lifespan handlers for new applications, replacing this application's registered `@app.on_event("startup")` handlers would violate preservation requirements. The design extends the existing announcement startup handler instead ([FastAPI lifespan events](https://fastapi.tiangolo.com/advanced/events/)).
- `asyncio.create_task()` schedules a coroutine on the running loop. Keeping the returned task on `app.state` avoids relying only on a weak task reference while retaining the exact required creation call ([Python coroutine and task documentation](https://docs.python.org/3.10/library/asyncio-task.html)).
- Python's `sqlite3` connection transaction behavior supports committing the recipient transition and audit insert together; both statements are issued before the existing `commit()`, with connection closure on failure preventing a partial commit ([Python 3.10 sqlite3 documentation](https://docs.python.org/3.10/library/sqlite3.html)).
- Hypothesis integrates with pytest and is appropriate for generated timestamp, identity, and state-transition inputs. Because repository changes outside the five implementation files are prohibited, Hypothesis tests must run from an ephemeral external harness rather than being committed ([Hypothesis documentation](https://hypothesis.readthedocs.io/en/latest/)).

Content from the linked documentation was rephrased for compliance with licensing restrictions.
