from __future__ import annotations

import secrets
import string

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from apps.integrations.models import HollihopCredentialDelivery, HollihopSyncLog

from .normalization import email_is_valid, normalize_email, normalize_phone
from .sms import SmsDeliveryError, send_sms


_PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%&*+-_"


def generate_temporary_password(length: int = 14) -> str:
    length = max(12, int(length))
    while True:
        password = "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "!@#$%&*+-_" for c in password)
        ):
            return password


def _login_identifier(user) -> str:
    email = normalize_email(user.email)
    if email:
        return email
    phone = normalize_phone(getattr(user.profile, "phone_number", ""))
    if phone:
        return phone
    return user.get_username()


def _sms_channel_enabled() -> bool:
    provider = str(getattr(settings, "MAKONBOOK_SMS_PROVIDER", "") or "").strip().lower()
    return provider not in {"", "disabled", "none"}


def can_deliver_temporary_access(user) -> bool:
    """Return True only when at least one delivery channel is currently usable.

    A phone number by itself is not enough while the SMS provider is disabled.
    This lets the profile remain ``pending`` so credentials can be delivered
    later when SMS is enabled, instead of silently rotating to an unreachable
    temporary password.
    """
    email = normalize_email(user.email)
    phone = normalize_phone(getattr(user.profile, "phone_number", ""))
    return email_is_valid(email) or (bool(phone) and _sms_channel_enabled())


def deliver_new_temporary_access(user) -> HollihopCredentialDelivery:
    """Reset to a fresh temporary password and deliver it once.

    The plaintext password exists only in local variables during this function.
    It is never persisted to models or logs.
    """
    profile = user.profile
    email = normalize_email(user.email)
    phone = normalize_phone(profile.phone_number)
    has_email = email_is_valid(email)
    has_phone = bool(phone)
    has_sms = has_phone and _sms_channel_enabled()

    delivery = HollihopCredentialDelivery.objects.create(
        user=user,
        email_status="pending" if has_email else "not_available",
        sms_status="pending" if has_sms else "not_available",
        overall_status="pending" if (has_email or has_sms) else "no_contact",
    )

    if not has_email and not has_sms:
        profile.credentials_delivery_status = "no_contact"
        profile.save(update_fields=["credentials_delivery_status", "updated_at"])
        return delivery

    temporary_password = generate_temporary_password()
    user.set_password(temporary_password)
    user.save(update_fields=["password"])
    profile.must_change_password = True

    login_value = _login_identifier(user)
    sent_count = 0
    failure_count = 0

    if has_email:
        context = {
            "display_name": (user.get_full_name() or user.get_username()).strip(),
            "login": login_value,
            "temporary_password": temporary_password,
            "login_url": f"{settings.SITE_URL.rstrip('/')}/login/",
            "support_email": getattr(settings, "EMAIL_HOST_USER", "") or "support@makonbook.uz",
            "current_year": timezone.localdate().year,
        }
        try:
            text_body = render_to_string("emails/hollihop_credentials.txt", context)
            html_body = render_to_string("emails/hollihop_credentials.html", context)
            message = EmailMultiAlternatives(
                subject="Your MakonBook account is ready",
                body=text_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email],
            )
            message.attach_alternative(html_body, "text/html")
            message.send(fail_silently=False)
            delivery.email_status = "sent"
            sent_count += 1
            HollihopSyncLog.objects.create(
                event_type="credentials_email_sent",
                entity_type="user",
                external_id=str(profile.hollihop_client_id or profile.hollihop_teacher_id or profile.hollihop_employee_id or ""),
                user=user,
                details={"channel": "email"},
            )
        except Exception as exc:  # provider failures must not roll back account creation
            delivery.email_status = "failed"
            delivery.email_error_safe = f"Email provider error ({type(exc).__name__})"[:300]
            failure_count += 1

    if has_sms:
        sms_text = (
            f"MakonBook\nLogin: {login_value}\nTemporary password: {temporary_password}\n"
            f"{settings.SITE_URL.rstrip('/')}/login/"
        )
        try:
            sms_result = send_sms(phone, sms_text)
            delivery.sms_status = "sent"
            sent_count += 1
            HollihopSyncLog.objects.create(
                event_type="credentials_sms_sent",
                entity_type="user",
                external_id=str(profile.hollihop_client_id or profile.hollihop_teacher_id or profile.hollihop_employee_id or ""),
                user=user,
                details={
                    "channel": "sms",
                    "provider": sms_result.provider,
                    "provider_message_id": sms_result.message_id,
                    "provider_status": sms_result.status,
                },
            )
        except SmsDeliveryError as exc:
            delivery.sms_status = "failed"
            delivery.sms_error_safe = str(exc)[:300]
            failure_count += 1
        except Exception as exc:
            delivery.sms_status = "failed"
            delivery.sms_error_safe = f"SMS provider error ({type(exc).__name__})"[:300]
            failure_count += 1

    if sent_count and failure_count:
        delivery.overall_status = "partial"
        profile.credentials_delivery_status = "partial"
    elif sent_count:
        delivery.overall_status = "sent"
        profile.credentials_delivery_status = "sent"
    else:
        delivery.overall_status = "failed"
        profile.credentials_delivery_status = "failed"

    delivery.completed_at = timezone.now()
    delivery.save(update_fields=[
        "email_status", "sms_status", "email_error_safe", "sms_error_safe", "overall_status", "completed_at"
    ])
    profile.credentials_last_sent_at = timezone.now()
    profile.save(update_fields=["must_change_password", "credentials_delivery_status", "credentials_last_sent_at", "updated_at"])
    return delivery
