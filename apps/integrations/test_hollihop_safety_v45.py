from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.integrations.hollihop.client import HollihopAPIError, HollihopClient
from apps.integrations.hollihop.sync import hollihop_bool


class HollihopClientPaginationSafetyTests(SimpleTestCase):
    def _client(self):
        return HollihopClient(api_url="https://example.t8s.ru/Api/V2", auth_key="test")

    @override_settings(HOLLIHOP_PAGE_SIZE=2, HOLLIHOP_MAX_PAGES=10)
    def test_repeated_full_page_aborts_instead_of_looping_forever(self):
        client = self._client()
        page = {"Students": [{"ClientId": 1}, {"ClientId": 2}]}
        with patch.object(client, "_request", return_value=page) as request_mock:
            with self.assertRaises(HollihopAPIError):
                client.get_students()
        self.assertEqual(request_mock.call_count, 2)

    @override_settings(HOLLIHOP_PAGE_SIZE=2, HOLLIHOP_MAX_PAGES=3)
    def test_max_page_guard_aborts_unbounded_unique_pages(self):
        client = self._client()
        pages = [
            {"Students": [{"ClientId": 1}, {"ClientId": 2}]},
            {"Students": [{"ClientId": 3}, {"ClientId": 4}]},
            {"Students": [{"ClientId": 5}, {"ClientId": 6}]},
        ]
        with patch.object(client, "_request", side_effect=pages):
            with self.assertRaises(HollihopAPIError):
                client.get_students()

    def test_hollihop_boolean_strings_are_parsed_safely(self):
        self.assertFalse(hollihop_bool("false"))
        self.assertFalse(hollihop_bool("0"))
        self.assertTrue(hollihop_bool("true"))
        self.assertTrue(hollihop_bool("1"))
