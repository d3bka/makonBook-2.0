import json
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "satmakon.settings")
django.setup()
from apps.sat.views import _get_or_create_regular_test_stage
from apps.sat.models import Test
from django.contrib.auth.models import User
user = User.objects.first()
test = Test.objects.first()
print("Calling with None")
try:
    _get_or_create_regular_test_stage(user, test, stage=1, classroom=None, mode='math_only', time_multiplier=1.5)
except Exception as e:
    print(e)
