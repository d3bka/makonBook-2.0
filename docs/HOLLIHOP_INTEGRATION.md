# Hollihop → MakonBook production integration

This integration keeps **Hollihop as the source of truth for administrative data** and keeps **MakonBook as the source of truth for passwords, SAT tests, attempts, scores, progress, flashcards, booking and learning analytics**.

## 1. Safe first-run configuration

Keep the provider local while you inspect the initial match:

```env
SCHOOL_DATA_PROVIDER=local
HOLLIHOP_ENABLED=true
HOLLIHOP_MODE=users
HOLLIHOP_API_URL=https://YOUR-SUBDOMAIN.t8s.ru/Api/V2
HOLLIHOP_AUTH_KEY=...
HOLLIHOP_WEBHOOK_SECRET=...
```

`HOLLIHOP_MODE` accepts:

- `users` — non-corporative EdUnits/memberships/employees.
- `corporative` — corporative EdUnits/memberships/employees.
- `all` — both.

`holihop` is accepted as an alias for `hollihop` in `SCHOOL_DATA_PROVIDER`.

## 2. Hollihop Admin → MakonBook Manager

Hollihop `GetEmployees` returns employees other than teachers. MakonBook **does not grant Manager to every employee**.

An employee is treated as a Manager only when an explicit role/type/position value matches `HOLLIHOP_MANAGER_TYPES` (or the API returns `IsAdmin=true` / `IsAdministrator=true`). Supported role-like fields include `Type`, `UserType`, `EmployeeType`, `AccountType`, `Role`, `RoleName`, `Position`, and `PositionName`.

Default:

```env
HOLLIHOP_MANAGER_TYPES=Admin,Administrator,Админ,Администратор
```

If your Hollihop tenant uses another exact label, add it to this comma-separated setting.

Rules:

- Hollihop Admin → Django `Manager` group.
- Existing MakonBook password is preserved when an employee is linked.
- Existing roles are preserved. A Teacher who is also Hollihop Admin becomes `Teacher + Manager`.
- Removing/firing the Hollihop admin role removes only the MakonBook `Manager` group; Teacher/Support Teacher/Admin roles are not destroyed.
- Hollihop employee identity is stored in `UserProfile.hollihop_employee_id` and is never matched by full name.

## 3. Migrate first

```bash
python manage.py migrate
```

New nullable external IDs and sync metadata are added to existing models. Existing MakonBook records are preserved.

## 4. Initial dry-run — no DB writes

Keep:

```env
SCHOOL_DATA_PROVIDER=local
```

Then run:

```bash
python manage.py sync_hollihop --all --dry-run
```

You can also isolate stages:

```bash
python manage.py sync_hollihop --managers --dry-run
python manage.py sync_hollihop --teachers --dry-run
python manage.py sync_hollihop --students --dry-run
python manage.py sync_hollihop --classrooms --dry-run
python manage.py sync_hollihop --memberships --dry-run
python manage.py sync_hollihop --attendance --from 2026-01-01 --to 2026-08-22 --dry-run
```

The dry-run reads Hollihop but does not create users, sync logs, conflicts, attendance or memberships.

## 5. Matching policy

Users are matched only by:

1. Existing Hollihop external ID.
2. Exact normalized email.
3. Exact normalized phone.
4. A single unambiguous matching MakonBook user.

Full name is **never** used as a user identity key.

Ambiguous email/phone matches are placed into `HollihopSyncConflict` for Manager review.

## 6. Safe local pilot with one student

Before enabling Hollihop as the global provider, you can perform a **live sync of exactly one student** while keeping:

```env
SCHOOL_DATA_PROVIDER=local
HOLLIHOP_ENABLED=true
```

Dry-run by phone:

```bash
python manage.py sync_hollihop --pilot-student-phone "+998901234567" --dry-run
```

Live pilot for only that student:

```bash
python manage.py sync_hollihop --pilot-student-phone "+998901234567"
```

Or use the exact Hollihop Client ID:

```bash
python manage.py sync_hollihop --pilot-student-id 236 --dry-run
python manage.py sync_hollihop --pilot-student-id 236
```

Pilot mode synchronizes only:

- the target student;
- teachers referenced by that student's current Hollihop EdUnits;
- those EdUnits/Classrooms;
- only that student's memberships;
- only that student's recent attendance.

It does **not** synchronize unrelated students, managers, teachers or classrooms. Pilot mode cannot be combined with `--all` or stage flags.

If multiple Hollihop students share the same normalized phone, phone-based pilot sync refuses to guess and tells you to use `--pilot-student-id`.

Credential delivery remains explicit. To test the complete temporary-password flow for that one account:

```bash
python manage.py sync_hollihop --pilot-student-id 236 --send-credentials
```

Do this only after the pilot account/classroom match has been reviewed.

### Hollihop remains read-only

The MakonBook client used by this integration calls only Hollihop read methods (`GetStudents`, `GetEmployees`, `GetTeachers`, `GetEdUnits`, `GetEdUnitStudents`). It contains no create/update/delete Lead or StudentClient API operation. Running a pilot or a full sync therefore does not delete or modify Hollihop leads.

## 7. Enable live sync

After reviewing dry-run results:

```env
SCHOOL_DATA_PROVIDER=hollihop
HOLLIHOP_ENABLED=true
```

Restart web / Celery services, then run a live sync without credentials first:

```bash
python manage.py sync_hollihop --all
```

Review the Manager Panel → **Hollihop Integration** page and resolve conflicts.

## 8. Send credentials explicitly

Only after the imported accounts are reviewed:

```bash
python manage.py sync_hollihop --all --send-credentials
```

Credentials are sent only to genuinely Hollihop-created MakonBook users whose delivery state is still `pending`.

Existing MakonBook users that were merely linked:

- keep their current password;
- do not receive a password reset;
- do not receive credentials on later syncs.

Temporary passwords are generated with `secrets`, passed to `user.set_password()`, delivered, and never stored in plaintext in the database/logs.

## 9. First login

A Hollihop-created account that received a temporary password has:

```text
must_change_password = true
```

Server-side middleware forces `/change-temporary-password/` before normal authenticated pages. URL manipulation cannot bypass this check.

Login accepts:

- username;
- email;
- normalized phone;
- existing Google OAuth remains configured separately.

## 10. SMS

SMS remains isolated behind `send_sms(phone, message)`. The safe default is still:

```env
MAKONBOOK_SMS_PROVIDER=disabled
```

MakonBook now supports both the legacy `generic_http` adapter and a native Eskiz.uz adapter. Eskiz configuration:

```env
MAKONBOOK_SMS_PROVIDER=eskiz
ESKIZ_API_BASE_URL=https://notify.eskiz.uz/api
ESKIZ_EMAIL=...
ESKIZ_PASSWORD=...
ESKIZ_SENDER=4546
ESKIZ_CALLBACK_URL=
ESKIZ_TOKEN_CACHE_SECONDS=21600
```

`ESKIZ_SENDER` must be the sender/originator approved for the Eskiz account. Do not enable bulk credential delivery until the service SMS template is approved by Eskiz/operators.

Validate configuration without sending:

```bash
python manage.py check_sms_provider
```

After provider/template approval, one intentional live test can be sent with:

```bash
python manage.py check_sms_provider --send-to "+998901234567" --message "YOUR APPROVED TEST TEXT"
```

Eskiz bearer tokens are cached through Django cache (Redis in production) and refreshed once automatically after HTTP 401. Provider tokens/passwords are never persisted in MakonBook audit logs. See `docs/ESKIZ_SMS_INTEGRATION.md` for the rollout checklist.

## 11. Attendance

Recent reconciliation defaults to 30 days and is requested in 30-day chunks:

```env
HOLLIHOP_RECENT_ATTENDANCE_DAYS=30
HOLLIHOP_ATTENDANCE_CHUNK_DAYS=30
```

Historical import example:

```bash
python manage.py sync_hollihop --attendance --from 2026-01-01 --to 2026-08-22
```

Attendance keys include student, EdUnit, date and Hollihop schedule-item IDs where present, so repeated sync updates an existing record rather than creating duplicates.

## 12. Webhook

Endpoint:

```text
https://makonbook.uz/integrations/hollihop/webhook/
```

Configure the same shared key in Hollihop and:

```env
HOLLIHOP_WEBHOOK_SECRET=...
```

The endpoint validates the key, rate-limits requests and returns safe errors. Nginx access logging is disabled only for this exact endpoint so the webhook key cannot land in the normal access log.

Hollihop's documented CRM webhook object types cover `StudentClient` and `Lead`; therefore employee/teacher/classroom reconciliation remains periodic/manual rather than pretending unsupported employee webhooks exist.

## 13. Periodic reconciliation

`celery-beat` is included in both Docker Compose definitions. Default interval:

```env
HOLLIHOP_RECONCILE_MINUTES=60
```

Reconciliation is a safety net for missed student webhooks and also refreshes managers, teachers, classrooms and memberships.

## 14. Manager Panel

Managers can open:

```text
Manager Panel → Hollihop Integration
```

It shows:

- connection/provider/mode;
- synced Students / Teachers / Managers / Classrooms;
- attendance count;
- pending conflicts;
- recent sync log;
- credential-delivery failures;
- reset & resend action.

`Reset & resend` always creates a **new** temporary password. The previous temporary password is not stored and cannot be resent.

## 15. Disable / rollback operationally

To stop Hollihop from changing data without removing imported history:

```env
SCHOOL_DATA_PROVIDER=local
HOLLIHOP_ENABLED=false
```

Restart services. MakonBook authentication, SAT tests, dashboards and existing imported data continue to exist.

## 16. Production Docker deployment

Typical flow:

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d web redis celery-worker celery-beat

docker compose -f docker-compose.prod.yml exec web python manage.py migrate
docker compose -f docker-compose.prod.yml exec web python manage.py sync_hollihop --all --dry-run
```

After review, change `SCHOOL_DATA_PROVIDER=hollihop`, restart services and run the live import.

## 17. Validation performed for this patch

The isolated Django integration suite was run against an in-memory SQLite test database with production models/migrations loaded:

```text
34 tests
System check: 0 issues
34 / 34: OK
makemigrations --check --dry-run: No changes detected
```

Covered scenarios include duplicate sync, existing-user password preservation, same-name users, Manager+Teacher multi-role, admin employee mapping, employee role revocation, corporate filtering, deactivation/reactivation, classroom transfers, attendance update without duplication, missing contacts, email/SMS failures, first-login gate, email/phone authentication, webhook authorization/replay and management-command dry-run.
