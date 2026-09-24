from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from apps.sat.models import Test, TestStage
import json

class InitializeTestEndpointTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.test_obj = Test.objects.create(name='Day-1', is_available=True)
        self.url = '/sat/api/test/initialize/'

    def test_unauthenticated(self):
        response = self.client.post(self.url, data={}, content_type='application/json')
        # login_required redirects to login page with 302
        self.assertEqual(response.status_code, 302)

    def test_successful_initialization(self):
        self.client.login(username='testuser', password='password123')
        payload = {
            'test_name': 'Day-1',
            'mode': 'rw_only',
            'multiplier': 1.5
        }
        response = self.client.post(self.url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('/sat/practise/Day-1/start', data['redirect_url'])

        # Verify TestStage was created/updated
        stage = TestStage.objects.get(user=self.user, test=self.test_obj)
        self.assertEqual(stage.mode, 'rw_only')
        self.assertEqual(stage.time_multiplier, 1.5)

    def test_invalid_multiplier(self):
        self.client.login(username='testuser', password='password123')
        payload = {
            'test_name': 'Day-1',
            'mode': 'full_test',
            'multiplier': 3.0 # Invalid
        }
        response = self.client.post(self.url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    def test_invalid_mode(self):
        self.client.login(username='testuser', password='password123')
        payload = {
            'test_name': 'Day-1',
            'mode': 'invalid_mode',
            'multiplier': 1.0
        }
        response = self.client.post(self.url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())
        
    def test_invalid_json(self):
        self.client.login(username='testuser', password='password123')
        response = self.client.post(self.url, data="not json", content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Invalid JSON')

