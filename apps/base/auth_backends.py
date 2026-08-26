from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from apps.integrations.hollihop.normalization import normalize_email, normalize_phone
from .models import UserProfile


class EmailOrPhoneModelBackend(ModelBackend):
    """Authenticate by username, exact email, or normalized phone.

    Ambiguous legacy emails intentionally fail instead of picking the first user.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        credential = (username or kwargs.get("email") or "").strip()
        if not credential or password is None:
            return None
        User = get_user_model()
        user = None

        # Preserve normal Django username behaviour first.
        try:
            user = User._default_manager.get(username=credential)
        except User.DoesNotExist:
            pass

        if user is None and "@" in credential:
            matches = list(User._default_manager.filter(email__iexact=normalize_email(credential))[:2])
            if len(matches) == 1:
                user = matches[0]

        if user is None:
            phone = normalize_phone(credential)
            if phone:
                profiles = list(UserProfile.objects.select_related("user").filter(phone_number=phone)[:2])
                if len(profiles) == 1:
                    user = profiles[0].user

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
