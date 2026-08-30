from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.integrations.hollihop.sms import SmsDeliveryError, send_sms, validate_sms_configuration


class Command(BaseCommand):
    help = "Validate MakonBook SMS provider settings and optionally send one explicit test SMS."

    def add_arguments(self, parser):
        parser.add_argument(
            "--send-to",
            dest="send_to",
            default="",
            help="Optional phone number. If supplied, one real test SMS is sent.",
        )
        parser.add_argument(
            "--message",
            default="This is test from Eskiz",
            help="Test message used only together with --send-to.",
        )

    def handle(self, *args, **options):
        ready, detail = validate_sms_configuration()
        if not ready:
            raise CommandError(detail)
        self.stdout.write(self.style.SUCCESS(detail))

        phone = str(options.get("send_to") or "").strip()
        if not phone:
            self.stdout.write("No SMS sent. Add --send-to only when you intentionally want a live provider test.")
            return

        try:
            result = send_sms(phone, str(options.get("message") or ""))
        except SmsDeliveryError as exc:
            raise CommandError(str(exc)) from exc

        extra = f", message_id={result.message_id}" if result.message_id else ""
        self.stdout.write(self.style.SUCCESS(f"SMS accepted by {result.provider}: status={result.status}{extra}"))
