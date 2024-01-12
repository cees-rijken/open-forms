from contextlib import contextmanager
from unittest.mock import patch

from django.test import TestCase, tag

import requests_mock
from requests import RequestException

from openforms.plugins.exceptions import InvalidPluginConfiguration
from openforms.prefill.constants import IdentifierRoles
from openforms.submissions.models import Submission
from openforms.submissions.tests.factories import SubmissionFactory
from stuf.stuf_bg.constants import FieldChoices
from stuf.stuf_bg.models import StufBGConfig
from stuf.tests.factories import StufServiceFactory

from ..plugin import (
    StufBgPrefill,
    is_empty_wrapped_response,
    is_object_not_found_response,
)
from .utils import get_mock_response_content, get_mock_xml, mock_stufbg_client


@contextmanager
def mock_stufbg_make_request(template: str):
    content = get_mock_response_content(template)
    with requests_mock.Mocker() as m:
        m.register_uri(requests_mock.ANY, requests_mock.ANY, content=content)
        yield


class StufBgPrefillTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.stuf_bg_service = StufServiceFactory.create()
        cls.submission: Submission = SubmissionFactory.create(
            auth_info__value="999992314"
        )

    def setUp(self) -> None:
        super().setUp()

        self.plugin = StufBgPrefill("test-plugin")

        # mock out django-solo interface (we don't have to deal with caches then)
        stufbg_config_patcher = patch(
            "openforms.prefill.contrib.stufbg.plugin.StufBGConfig.get_solo",
            return_value=StufBGConfig(service=self.stuf_bg_service),
        )
        stufbg_config_patcher.start()
        self.addCleanup(stufbg_config_patcher.stop)

    def test_getting_available_attributes(self):
        attributes = self.plugin.get_available_attributes()
        self.assertIsInstance(attributes, list)

        for entry in attributes:
            with self.subTest(entry=entry):
                self.assertIsInstance(entry, tuple)
                self.assertEqual(len(entry), 2)
                value, label = entry
                self.assertEqual(value, str(value))
                self.assertEqual(label, str(label))

    def test_get_available_attributes_returns_correct_attributes(self):
        client_patcher = mock_stufbg_client("StufBgResponse.xml")
        self.addCleanup(client_patcher.stop)
        attributes = [c.value for c in FieldChoices]

        values = self.plugin.get_prefill_values(self.submission, attributes)

        self.assertEqual(values["bsn"], "999992314")
        self.assertEqual(values["voornamen"], "Media")
        self.assertEqual(values["voorletters"], "M")
        self.assertEqual(values["geslachtsnaam"], "Maykin")
        self.assertEqual(values["straatnaam"], "Keizersgracht")
        self.assertEqual(values["huisnummer"], "117")
        self.assertEqual(values["huisletter"], "A")
        self.assertEqual(values["huisnummertoevoeging"], "B")
        self.assertEqual(values["postcode"], "1015 CJ")
        self.assertEqual(values["woonplaatsNaam"], "Amsterdam")

    def test_response_external_municipality_returns_correct_attributes(self):
        client_patcher = mock_stufbg_client("StufBgResponseGemeenteVanInschrijving.xml")
        self.addCleanup(client_patcher.stop)
        attributes = [c.value for c in FieldChoices]

        values = self.plugin.get_prefill_values(self.submission, attributes)

        self.assertEqual(values["bsn"], "999992314")
        self.assertEqual(values["voornamen"], "Media")
        self.assertEqual(values["geslachtsnaam"], "Maykin")
        self.assertEqual(values["straatnaam"], "Keizersgracht")
        self.assertEqual(values["huisnummer"], "117")
        self.assertEqual(values["huisletter"], "A")
        self.assertEqual(values["huisnummertoevoeging"], "B")
        self.assertEqual(values["postcode"], "1015 CJ")
        self.assertEqual(values["gemeenteVanInschrijving"], "Amsterdam")

    def test_get_available_attributes_when_some_attributes_are_not_returned(self):
        client_patcher = mock_stufbg_client("StufBgResponseMissingSomeData.xml")
        self.addCleanup(client_patcher.stop)
        attributes = [c.value for c in FieldChoices]

        values = self.plugin.get_prefill_values(self.submission, attributes)

        self.assertEqual(values["bsn"], "999992314")
        self.assertEqual(values["voornamen"], "Media")
        self.assertEqual(values["geslachtsnaam"], "Maykin")
        self.assertEqual(values["straatnaam"], "Keizersgracht")
        self.assertEqual(values["huisnummer"], "117")
        self.assertEqual(values["postcode"], "1015 CJ")
        self.assertEqual(values["woonplaatsNaam"], "Amsterdam")
        self.assertNotIn("huisnummertoevoeging", values)
        self.assertNotIn("huisletter", values)

    def test_voorvoegsel_is_parsed(self):
        client_patcher = mock_stufbg_client("StufBgResponseWithVoorvoegsel.xml")
        self.addCleanup(client_patcher.stop)
        attributes = [c.value for c in FieldChoices]

        values = self.plugin.get_prefill_values(self.submission, attributes)

        self.assertEqual(values["bsn"], "999992314")
        self.assertEqual(values["voornamen"], "Media")
        self.assertEqual(values["voorvoegselGeslachtsnaam"], "van")
        self.assertEqual(values["geslachtsnaam"], "Maykin")
        self.assertEqual(values["straatnaam"], "Keizersgracht")
        self.assertEqual(values["huisnummer"], "117")
        self.assertEqual(values["huisletter"], "A")
        self.assertEqual(values["huisnummertoevoeging"], "B")
        self.assertEqual(values["postcode"], "1015 CJ")
        self.assertEqual(values["woonplaatsNaam"], "Amsterdam")

    def test_get_available_attributes_when_error_occurs(self):
        client_patcher = mock_stufbg_client("StufBgErrorResponse.xml")
        self.addCleanup(client_patcher.stop)

        attributes = [c.value for c in FieldChoices]

        with self.assertLogs() as logs:
            with self.assertRaises(ValueError):
                self.plugin.get_prefill_values(self.submission, attributes)

            self.assertEqual(logs.records[0].fault["faultcode"], "soapenv:Server")
            self.assertEqual(logs.records[0].fault["faultstring"], "Policy Falsified")
            self.assertEqual(
                logs.records[0].fault["detail"][
                    "http://www.layer7tech.com/ws/policy/fault:policyResult"
                ]["@status"],
                "Error in Assertion Processing",
            )

    def test_get_available_attributes_when_no_answer_is_returned(self):
        client_patcher = mock_stufbg_client("StufBgNoAnswerResponse.xml")
        self.addCleanup(client_patcher.stop)
        attributes = [c.value for c in FieldChoices]

        try:
            values = self.plugin.get_prefill_values(self.submission, attributes)
        except ValueError:
            # empty responses should be handled graciously
            self.fail("No fault/error expected.")

        self.assertEqual(values, {})

    def test_get_available_attributes_when_object_not_found_reponse_is_returned(self):
        client_patcher = mock_stufbg_client("StufBgNotFoundResponse.xml")
        self.addCleanup(client_patcher.stop)
        attributes = [c.value for c in FieldChoices]

        with self.assertLogs() as logs:
            with self.assertRaises(ValueError):
                self.plugin.get_prefill_values(self.submission, attributes)

            self.assertEqual(
                logs.records[0].fault, {"faultstring": "Object niet gevonden"}
            )

    def test_get_available_attributes_when_empty_reponse_is_returned(self):
        client_patcher = mock_stufbg_client("StufBgNoObjectResponse.xml")
        self.addCleanup(client_patcher.stop)
        attributes = [c.value for c in FieldChoices]

        try:
            values = self.plugin.get_prefill_values(self.submission, attributes)
        except ValueError:
            # empty responses should be handled graciously
            self.fail("No fault/error expected.")

        self.assertEqual(values, {})

    @tag("gh-1617")
    def test_onvolledige_datum(self):
        """
        Regression test for StUF-onvolledigeDatum responses.

        See issue #1617 on Github.
        """
        client_patcher = mock_stufbg_client("StufBgResponseOnvolledigeDatum.xml")
        self.addCleanup(client_patcher.stop)

        values = self.plugin.get_prefill_values(self.submission, ["geboortedatum"])

        self.assertEqual(values["geboortedatum"], "19600701")

    def test_prefill_values_not_authenticated(self):
        client_patcher = mock_stufbg_client("StufBgResponse.xml")
        self.addCleanup(client_patcher.stop)
        attributes = [c.value for c in FieldChoices]
        submission = SubmissionFactory.create()

        assert not submission.is_authenticated

        values = self.plugin.get_prefill_values(submission, attributes)

        self.assertEqual(values, {})

    def test_get_available_attributes_for_gemachtigde(self):
        client_patcher = mock_stufbg_client("StufBgResponse.xml")
        self.addCleanup(client_patcher.stop)
        attributes = [c.value for c in FieldChoices]
        submission = SubmissionFactory.create(
            auth_info__value="111111111",
            auth_info__machtigen={"identifier_value": "999992314"},
        )

        values = self.plugin.get_prefill_values(
            submission, attributes, IdentifierRoles.authorised_person
        )

        self.assertEqual(values["bsn"], "999992314")
        self.assertEqual(values["voornamen"], "Media")
        self.assertEqual(values["geslachtsnaam"], "Maykin")
        self.assertEqual(values["straatnaam"], "Keizersgracht")
        self.assertEqual(values["huisnummer"], "117")
        self.assertEqual(values["huisletter"], "A")
        self.assertEqual(values["huisnummertoevoeging"], "B")
        self.assertEqual(values["postcode"], "1015 CJ")
        self.assertEqual(values["woonplaatsNaam"], "Amsterdam")


class StufBgCheckTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stuf_bg_service = StufServiceFactory.create()

    def setUp(self) -> None:
        super().setUp()

        self.plugin = StufBgPrefill("test-plugin")

        # mock out django-solo interface (we don't have to deal with caches then)
        self.config = StufBGConfig(service=self.stuf_bg_service)
        stufbg_config_patcher = patch(
            "openforms.prefill.contrib.stufbg.plugin.StufBGConfig.get_solo",
            return_value=self.config,
        )
        stufbg_config_patcher.start()
        self.addCleanup(stufbg_config_patcher.stop)

    def test_no_service_configured(self):
        self.config.service = None

        with self.assertRaises(InvalidPluginConfiguration):
            self.plugin.check_config()

    def test_check_config_exception(self):
        with patch(
            "stuf.stuf_bg.client.Client.get_values_for_attributes",
            side_effect=RequestException(),
        ):
            with self.assertRaises(InvalidPluginConfiguration):
                self.plugin.check_config()

    @requests_mock.Mocker()
    def test_check_config_invalid_xml_returned(self, m):
        m.register_uri(requests_mock.ANY, requests_mock.ANY, json={"not": "xml"})

        with self.assertRaises(InvalidPluginConfiguration):
            self.plugin.check_config()

    def test_check_config_ok_not_found(self):
        try:
            with mock_stufbg_make_request("StufBgNotFoundResponse.xml"):
                self.plugin.check_config()
        except InvalidPluginConfiguration as exc:
            raise self.failureException("Config should have passed checks") from exc

    def test_check_config_ok_no_object(self):
        try:
            with mock_stufbg_make_request("StufBgNoObjectResponse.xml"):
                self.plugin.check_config()
        except InvalidPluginConfiguration as exc:
            raise self.failureException("Config should have passed checks") from exc

    def test_check_config_other_error(self):
        with self.assertRaises(InvalidPluginConfiguration):
            with mock_stufbg_make_request("StufBgErrorResponse.xml"):
                self.plugin.check_config()

    def test_check_config_some_unexpected_random_result(self):
        with self.assertRaises(InvalidPluginConfiguration):
            with mock_stufbg_make_request("StufBgResponseWithVoorvoegsel.xml"):
                self.plugin.check_config()


class StufBGHelpersTests(TestCase):
    def test_helper_is_object_not_found_response(self):
        with self.subTest("found"):
            xml = get_mock_xml("StufBgResponse.xml")
            self.assertFalse(is_object_not_found_response(xml))

        with self.subTest("not found"):
            xml = get_mock_xml("StufBgNotFoundResponse.xml")
            self.assertTrue(is_object_not_found_response(xml))

        with self.subTest("other error"):
            xml = get_mock_xml("StufBgErrorResponse.xml")
            self.assertFalse(is_object_not_found_response(xml))

    def test_helper_is_empty_wrapped_response(self):
        with self.subTest("empty"):
            xml = get_mock_xml("StufBgNoObjectResponse.xml")
            self.assertTrue(is_empty_wrapped_response(xml))

        with self.subTest("not empty"):
            xml = get_mock_xml("StufBgResponse.xml")
            self.assertFalse(is_empty_wrapped_response(xml))

        with self.subTest("other error"):
            xml = get_mock_xml("StufBgErrorResponse.xml")
            self.assertFalse(is_empty_wrapped_response(xml))
