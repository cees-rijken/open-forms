import json
import os
from unittest.mock import patch

from django.template import Context, Template
from django.test import TestCase

import requests_mock

from openforms.authentication.constants import AuthAttribute
from openforms.contrib.brp.models import BRPConfig
from openforms.formio.service import get_dynamic_configuration
from openforms.prefill.contrib.haalcentraal.tests.test_plugin import load_binary_mock
from openforms.registrations.contrib.zgw_apis.tests.factories import ServiceFactory
from openforms.submissions.tests.factories import SubmissionFactory
from stuf.constants import EndpointType
from stuf.stuf_bg.models import StufBGConfig
from stuf.tests.factories import StufServiceFactory

from ..constants import FamilyMembersDataAPIChoices
from ..handlers.haal_centraal import get_np_children_haal_centraal
from ..handlers.stuf_bg import get_np_children_stuf_bg
from ..models import FamilyMembersTypeConfig


class FamilyMembersCustomFieldTypeTest(TestCase):
    @patch("openforms.formio.components.custom.NPFamilyMembers._get_handler")
    def test_get_values_for_custom_field(self, mock_get_handler):
        mock_get_handler.return_value.return_value = [
            ("222333444", "Billy Doe"),
            ("333444555", "Jane Doe"),
        ]
        submission = SubmissionFactory.from_components(
            [
                {
                    "key": "npFamilyMembers",
                    "type": "npFamilyMembers",
                    "label": "FamilyMembers",
                    "values": [{"label": "", "value": ""}],
                },
            ],
            auth_info__attribute=AuthAttribute.bsn,
            auth_info__value="111222333",
        )
        config = FamilyMembersTypeConfig.get_solo()
        config.data_api = FamilyMembersDataAPIChoices.haal_centraal
        config.save()
        formio_wrapper = (
            submission.submissionstep_set.get().form_step.form_definition.configuration_wrapper
        )

        updated_config_wrapper = get_dynamic_configuration(
            formio_wrapper,
            request=None,
            submission=submission,
        )

        rewritten_component = updated_config_wrapper["npFamilyMembers"]
        self.assertEqual("selectboxes", rewritten_component["type"])
        self.assertFalse(rewritten_component["fieldSet"])
        self.assertFalse(rewritten_component["inline"])
        self.assertEqual("checkbox", rewritten_component["inputType"])
        self.assertEqual(2, len(rewritten_component["values"]))
        self.assertEqual(
            rewritten_component["values"][0],
            {"value": "222333444", "label": "Billy Doe"},
        )
        self.assertEqual(
            rewritten_component["values"][1],
            {"value": "333444555", "label": "Jane Doe"},
        )

    def test_get_children_haal_centraal(self):
        test_files = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "responses"
        )

        response_file = open(os.path.join(test_files, "op_2_children.json"), "r")
        json_response = json.load(response_file)
        response_file.close()

        config = BRPConfig.get_solo()
        haal_centraal_service = ServiceFactory(
            api_root="https://personen/api/",
            oas="https://personen/api/schema/openapi.yaml",
        )
        config.brp_service = haal_centraal_service
        config.save()

        with requests_mock.Mocker() as m:
            m.get(
                "https://personen/api/schema/openapi.yaml?v=3",
                status_code=200,
                content=load_binary_mock("personen.yaml"),
            )
            m.get(
                "https://personen/api/ingeschrevenpersonen/111222333/kinderen",
                status_code=200,
                json=json_response,
            )

            kids_choices = get_np_children_haal_centraal(bsn="111222333")

            self.assertEqual(2, len(kids_choices))
            self.assertEqual(("456789123", "Bolly van Doe"), kids_choices[0])
            self.assertEqual(("789123456", "Billy van Doe"), kids_choices[1])

    def test_get_children_stuf_bg(self):
        test_files = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "responses"
        )

        soap_response_template_file = open(
            os.path.join(test_files, "stuf_bg_2_children.xml"), "r"
        )
        soap_response_template = soap_response_template_file.read()
        soap_response_template_file.close()

        stuf_bg_service = StufServiceFactory.create()
        config = StufBGConfig.get_solo()
        config.service = stuf_bg_service
        config.save()

        with requests_mock.Mocker() as m:
            m.post(
                stuf_bg_service.get_endpoint(type=EndpointType.vrije_berichten),
                content=Template(soap_response_template)
                .render(Context({}))
                .encode("utf-8"),
            )

            kids_choices = get_np_children_stuf_bg(bsn="111222333")

            self.assertEqual(2, len(kids_choices))
            self.assertEqual(("456789123", "Bolly van Doe"), kids_choices[0])
            self.assertEqual(("789123456", "Billy van Doe"), kids_choices[1])
