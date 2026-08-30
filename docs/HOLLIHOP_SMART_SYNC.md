# Hollihop → MakonBook smart synchronization

## Final operating model

The integration is read-only toward Hollihop. MakonBook never changes or deletes Hollihop leads, students, teachers, EdUnits or attendance.

### 1. No synchronization on application startup

Starting Django, `runserver`, Celery, migrations, health checks or the autoreloader does **not** start an import.

The first import is explicit from **Manager → Hollihop Integration → Run initial sync**. Periodic reconciliation is blocked in the database until that full import finishes successfully.

This matters for local testing: a local database can use the same Hollihop API credentials without an accidental import merely because the developer starts the app.

### 2. LearningType filter

Only:

- `GROUP`

is allowed.

These are rejected:

- `ONLINE`
- `IV ONLINE`
- `IV OFFLINE`

The filter is applied both to `GetEdUnits.learningTypes` and locally to returned `LearningType` / `EdUnitLearningType` values.

### 3. Five-minute smart cycle

The normal Celery Beat task runs every 5 minutes, but it does **not** perform a full account export.

It uses:

- `GetStudents?lastUpdatedFrom=...` for StudentClient deltas;
- `GetEdUnits?lastUpdatedFrom=...` for EdUnit deltas;
- targeted `GetEdUnitStudents(studentClientId=...)` or `GetEdUnitStudents(edUnitId=...)` with `queryDays=false` when a changed object needs its memberships;
- dependency fetches for a missing EdUnit/Teacher only when a valid GROUP relation requires them.

### 4. Hollihop limitation: membership changes

Hollihop support confirmed that adding/removing a student from an EdUnit does **not** count as an EdUnit `lastUpdated` change. Therefore a pure membership move cannot always be discovered from a 5-minute delta query.

To cover that gap, MakonBook runs one **relation-only** full `GetEdUnitStudents` sweep every 240 minutes by default. It never requests `Days` or payment payloads in that sweep.

This follows Hollihop support's warning that `GetEdUnitStudents` becomes heavy with days/payments and that complete account exports should only happen several times per day.

### 5. Other low-frequency safety checks

Defaults:

- Teachers: every 5 minutes. Only already-linked teachers are updated; unassigned new teachers are imported only when an EdUnit references them.
- Managers: every 15 minutes.
- Existing student profile catalog: every 360 minutes. This catches personal-field changes that Hollihop may not include in `lastUpdatedFrom`.
- Full EdUnit catalog: every 360 minutes. This discovers a new GROUP even if the incremental timestamp behavior misses it.
- Full membership relation sweep: every 240 minutes.

### 6. Webhooks

Supported StudentClient events such as `Created`, `StatusSet` and `PassSet` are still processed immediately. Webhooks are also blocked until the explicit initial import has completed for that database.

A webhook for `PassSet` performs a targeted attendance refresh for that student only.

### 7. API protection

Hollihop support stated a limit of **600 requests per 30 seconds**. MakonBook defaults to at least 0.10 seconds between requests per sync client, retries the documented `Requests limit is exceeded` response with backoff, and uses a database lock so two sync jobs do not run concurrently.

### 8. Eskiz / credentials

Data synchronization is separated from credential delivery.

While Eskiz is in test mode keep:

```env
HOLLIHOP_AUTO_SEND_CREDENTIALS=false
```

The Manager-panel initial/full/smart sync buttons never enable credential sending. A manual CLI pilot can still use `--send-credentials` explicitly when needed.

### 9. First deployment

```powershell
python manage.py migrate
python manage.py sync_hollihop --all --dry-run
```

Review the dry-run, then either use the Manager-panel **Run initial sync** button or:

```powershell
python manage.py sync_hollihop --all --mark-initial
```

After `initial_sync_completed=true`, Celery Beat's 5-minute smart task becomes active.
