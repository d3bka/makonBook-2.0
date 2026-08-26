from __future__ import annotations

from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.integrations.hollihop.sms import (
    SmsDeliveryError,
    _SmsHttpError,
    _eskiz_authenticate,
    send_sms,
    validate_sms_configuration,
)


ESKIZ_SETTINGS = dict(
    MAKONBOOK_SMS_PROVIDER="eskiz",
    MAKONBOOK_SMS_TIMEOUT_SECONDS=5,
    ESKIZ_AUTH_URL="https://notify.eskiz.uz/api/auth/login",
    ESKIZ_SEND_URL="https://notify.eskiz.uz/api/message/sms/send",
    ESKIZ_EMAIL="sms@example.com",
    ESKIZ_PASSWORD="secret",
    ESKIZ_SENDER="4546",
    ESKIZ_TOKEN_CACHE_SECONDS=3600,
)


class EskizSmsAdapterTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @override_settings(**ESKIZ_SETTINGS)
    def test_configuration_is_ready_without_network_call(self):
        ready, detail = validate_sms_configuration()
        self.assertTrue(ready)
        self.assertIn("ready", detail)

    @override_settings(**{**ESKIZ_SETTINGS, "ESKIZ_SENDER": ""})
    def test_configuration_requires_sender(self):
        ready, detail = validate_sms_configuration()
        self.assertFalse(ready)
        self.assertIn("ESKIZ_SENDER", detail)

    @override_settings(**ESKIZ_SETTINGS)
    @patch("apps.integrations.hollihop.sms._post_form")
    def test_eskiz_login_token_is_cached(self, post_form):
        post_form.return_value = {"data": {"token": "token-1"}}
        self.assertEqual(_eskiz_authenticate(), "token-1")
        self.assertEqual(_eskiz_authenticate(), "token-1")
        self.assertEqual(post_form.call_count, 1)

    @override_settings(**ESKIZ_SETTINGS)
    @patch("apps.integrations.hollihop.sms._post_form")
    def test_eskiz_send_uses_expected_payload_and_normalized_phone(self, post_form):
        post_form.side_effect = [
            {"data": {"token": "token-1"}},
            {"id": "sms-123", "status": "waiting", "message": "Waiting for SMS provider"},
        ]

        result = send_sms("+998 90 123 45 67", "MakonBook test")

        self.assertEqual(result.provider, "eskiz")
        self.assertEqual(result.message_id, "sms-123")
        self.assertEqual(result.status, "waiting")
        self.assertEqual(post_form.call_count, 2)
        _, send_kwargs = post_form.call_args_list[1]
        self.assertEqual(send_kwargs["headers"]["Authorization"], "Bearer token-1")
        send_payload = post_form.call_args_list[1].args[1]
        self.assertEqual(send_payload["mobile_phone"], "998901234567")
        self.assertEqual(send_payload["from"], "4546")

    @override_settings(**ESKIZ_SETTINGS)
    @patch("apps.integrations.hollihop.sms._post_form")
    def test_eskiz_reauthenticates_once_after_401(self, post_form):
        post_form.side_effect = [
            {"data": {"token": "old-token"}},
            _SmsHttpError(401),
            {"data": {"token": "new-token"}},
            {"id": "sms-2", "status": "waiting"},
        ]

        result = send_sms("998901234567", "MakonBook test")

        self.assertEqual(result.message_id, "sms-2")
        self.assertEqual(post_form.call_count, 4)
        self.assertEqual(post_form.call_args_list[3].kwargs["headers"]["Authorization"], "Bearer new-token")

    @override_settings(**ESKIZ_SETTINGS)
    @patch("apps.integrations.hollihop.sms._post_form", side_effect=_SmsHttpError(422))
    def test_eskiz_auth_failure_is_safe(self, _post_form):
        with self.assertRaisesMessage(SmsDeliveryError, "authentication was rejected"):
            send_sms("+998901234567", "MakonBook test")
