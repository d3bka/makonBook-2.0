import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase

from .auth_rate_limit import check_auth_rate_limit


class AuthRateLimitV43Tests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()

    @patch.dict(os.environ, {"AUTH_FORGOT_IDENTIFIER_MAX": "1", "AUTH_FORGOT_IP_MAX": "100"}, clear=False)
    def test_password_reset_request_is_limited_by_identifier(self):
        request = self.factory.post("/forgot-password/", REMOTE_ADDR="127.0.0.1")
        self.assertTrue(check_auth_rate_limit(request, action="forgot_password", identifier="User@Example.com").allowed)
        blocked = check_auth_rate_limit(request, action="forgot_password", identifier="user@example.com")
        self.assertFalse(blocked.allowed)
        self.assertGreater(blocked.retry_after, 0)

    @patch.dict(os.environ, {"AUTH_TEMP_PASSWORD_USER_MAX": "1", "AUTH_TEMP_PASSWORD_IP_MAX": "100"}, clear=False)
    def test_temporary_password_change_is_limited_by_user(self):
        request = self.factory.post("/change-temporary-password/", REMOTE_ADDR="127.0.0.1")
        self.assertTrue(check_auth_rate_limit(request, action="temporary_password", identifier="42").allowed)
        self.assertFalse(check_auth_rate_limit(request, action="temporary_password", identifier="42").allowed)


class TemporaryPasswordTemplateV43Tests(TestCase):
    def test_template_uses_submit_once_and_makonbook_security_design(self):
        User = get_user_model()
        user = User.objects.create_user(username="temp-user", password="TempPass123!")
        html = render_to_string("base/change_temporary_password.html", {"form": SetPasswordForm(user)})
        self.assertIn("data-submit-once", html)
        self.assertIn("One last security step", html)
        self.assertIn("makon-submit-once.js", html)
