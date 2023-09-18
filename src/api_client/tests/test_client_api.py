from unittest import TestCase

import requests_mock
from hypothesis import given, strategies as st
from requests import Session
from requests.auth import HTTPBasicAuth

from ..client import APIClient


class DirectInstantiationTests(TestCase):
    def test_defaults_from_requests_session(self):
        vanilla_session = Session()

        client = APIClient("https://example.com")

        for attr in Session.__attrs__:
            if attr == "adapters":
                continue
            with self.subTest(attr=attr):
                vanilla_value = getattr(vanilla_session, attr)
                client_value = getattr(client, attr)

                self.assertEqual(client_value, vanilla_value)

    def test_can_override_defaults(self):
        vanilla_session = Session()
        overrides = [
            ("auth", HTTPBasicAuth("superuser", "letmein")),
            ("verify", False),
            ("cert", ("/tmp/cert.pem", "/tmp/key.pem")),
        ]

        for attr, value in overrides:
            # sanity check for test itself
            assert attr in Session.__attrs__

            with self.subTest(attr=attr, value=value):
                client = APIClient("https://example.com", {attr: value})

                vanilla_value = getattr(vanilla_session, attr)
                client_value = getattr(client, attr)

                self.assertNotEqual(client_value, vanilla_value)
                self.assertEqual(client_value, value)


class TestFactory:
    @staticmethod
    def get_client_base_url():
        return "https://from-factory.example.com"

    @staticmethod
    def get_client_session_kwargs():
        return {
            "verify": False,
            "timeout": 20,
            "auth": HTTPBasicAuth("superuser", "letmein"),
        }


class FromFactoryTests(TestCase):
    def test_factory_can_configure_session(self):
        factory = TestFactory()

        client = APIClient.configure_from(factory)

        self.assertFalse(client.verify)
        self.assertIsNotNone(client.auth)
        self.assertFalse(hasattr(client, "timeout"))


class RequestTests(TestCase):
    @requests_mock.Mocker()
    def test_runtime_request_kwargs(self, m):
        m.get(requests_mock.ANY, text="ok")
        factory = TestFactory()

        with APIClient.configure_from(factory) as client:
            client.get("https://from-factory.example.com/foo")

        self.assertEqual(m.last_request.url, "https://from-factory.example.com/foo")
        headers = m.last_request.headers
        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("Basic "))
        self.assertFalse(m.last_request.verify)
        self.assertEqual(m.last_request.timeout, 20.0)

    @requests_mock.Mocker()
    def test_request_kwargs_overrule_defaults(self, m):
        m.get(requests_mock.ANY, text="ok")
        factory = TestFactory()

        with APIClient.configure_from(factory) as client:
            client.get(
                "https://from-factory.example.com/foo",
                timeout=5,
                verify=True,
            )

        self.assertEqual(m.last_request.url, "https://from-factory.example.com/foo")
        headers = m.last_request.headers
        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("Basic "))
        self.assertTrue(m.last_request.verify)
        self.assertEqual(m.last_request.timeout, 5.0)

    @given(
        st.one_of(
            st.just("GET"),
            st.just("OPTIONS"),
            st.just("HEAD"),
            st.just("POST"),
            st.just("PUT"),
            st.just("PATCH"),
            st.just("DELETE"),
        )
    )
    def test_applies_to_any_http_method(self, method):
        with requests_mock.Mocker() as m:
            m.register_uri(requests_mock.ANY, requests_mock.ANY)
            factory = TestFactory()

            with APIClient.configure_from(factory) as client:
                client.request(method, "https://from-factory.example.com/foo")

        self.assertEqual(len(m.request_history), 1)
        self.assertEqual(m.last_request.url, "https://from-factory.example.com/foo")
        self.assertEqual(m.last_request.method, method)
        headers = m.last_request.headers
        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("Basic "))
        self.assertFalse(m.last_request.verify)
        self.assertEqual(m.last_request.timeout, 20.0)
