import os
import django
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "satmakon.settings")
django.setup()

from django.test import Client
from apps.sat.models import Test
from django.contrib.auth.models import User

client = Client(raise_request_exception=True, HTTP_HOST='localhost')
user = User.objects.first()
client.force_login(user)

payload = {
    "test_name": "Day-1",
    "mode": "math_only",
    "multiplier": 1.5,
    "classroom_id": None
}

response = client.post(
    '/sat/api/test/initialize/', 
    data=json.dumps(payload),
    content_type='application/json'
)

print("Status:", response.status_code)
if response.status_code == 200:
    start_url = response.json().get('redirect_url')
    print("Redirect URL:", start_url)
    res2 = client.get(start_url)
    print("Start URL status:", res2.status_code)
