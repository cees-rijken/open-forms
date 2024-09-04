from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from django.test import TestCase

from openforms.contrib.objects_api.helpers import prepare_data_for_registration
from openforms.registrations.contrib.objects_api.client import get_objects_client
from openforms.registrations.contrib.objects_api.models import ObjectsAPIConfig
from openforms.registrations.contrib.objects_api.tests.factories import (
    ObjectsAPIGroupConfigFactory,
)
from openforms.submissions.tests.factories import SubmissionFactory
from openforms.utils.tests.vcr import OFVCRMixin

from ..plugin import PLUGIN_IDENTIFIER, ObjectsAPIPrefill

VCR_TEST_FILES = Path(__file__).parent / "files"


class ObjectsAPIPrefillPluginTests(OFVCRMixin, TestCase):
    """This test case requires the Objects & Objecttypes API to be running.

    See the relevant Docker compose in the ``docker/`` folder.
    """

    VCR_TEST_FILES = VCR_TEST_FILES

    def setUp(self):
        super().setUp()

        config_patcher = patch(
            "openforms.registrations.contrib.objects_api.models.ObjectsAPIConfig.get_solo",
            return_value=ObjectsAPIConfig(),
        )
        self.mock_get_config = config_patcher.start()
        self.addCleanup(config_patcher.stop)

        self.objects_api_group = ObjectsAPIGroupConfigFactory.create(
            for_test_docker_compose=True
        )

    def test_available_attributes(self):
        plugin = ObjectsAPIPrefill(PLUGIN_IDENTIFIER)

        # Trigger the attributes retrieval flow
        available_attrs = plugin.get_available_attributes(
            reference={
                "objects_api_group": self.objects_api_group,
                "objects_api_objecttype_uuid": "8e46e0a5-b1b4-449b-b9e9-fa3cea655f48",
                "objects_api_objecttype_version": "3",
            }
        )

        self.assertEqual(
            available_attrs,
            [
                ("age", "age (integer)"),
                ("name > last.name", "name > last.name (string)"),
                ("nested > unrelated", "nested > unrelated (string)"),
                (
                    "nested > submission_payment_amount",
                    "nested > submission_payment_amount (number)",
                ),
                ("submission_date", "submission_date (string)"),
                ("submission_csv_url", "submission_csv_url (string)"),
                ("submission_pdf_url", "submission_pdf_url (string)"),
                (
                    "submission_payment_completed",
                    "submission_payment_completed (boolean)",
                ),
            ],
        )

    def test_prefill_variables(self):
        plugin = ObjectsAPIPrefill(PLUGIN_IDENTIFIER)

        # We manually create the objects instance as if it was created upfront by some external party
        with get_objects_client(self.objects_api_group) as client:
            created_obj = client.create_object(
                record_data=prepare_data_for_registration(
                    data={
                        "data": {
                            "name": {"last.name": "zig"},
                            "age": 38,
                            "submission_date": "2024-09-02T10:33:00+00:00",
                        }
                    },
                    objecttype_version=3,
                ),
                objecttype_url="http://objecttypes-web:8000/api/v2/objecttypes/8e46e0a5-b1b4-449b-b9e9-fa3cea655f48",
            )

        submission = SubmissionFactory.from_components(
            [
                {
                    "key": "age",
                    "type": "number",
                },
                {
                    "key": "lastname",
                    "type": "textfield",
                },
                {
                    "key": "location",
                    "type": "map",
                },
            ],
            completed=True,
            submitted_data={
                "age": 20,
                "lastname": "My last name",
                "location": [52.36673378967122, 4.893164274470299],
            },
            initial_data_reference=created_obj["uuid"],
        )
        prefill_options = {
            "prefill_plugin": "objects_api",
            "objects_api_group": self.objects_api_group.pk,
            "objecttype_uuid": UUID("8e46e0a5-b1b4-449b-b9e9-fa3cea655f48"),
            "objecttype_version": 3,
            "variables_mapping": [
                {
                    "variable_key": "age",
                    "target_path": ["age"],
                },
                {
                    "variable_key": "lastname",
                    "target_path": ["name", "last.name"],
                },
                {
                    "variable_key": "now",
                    "target_path": ["submission_date"],
                },
            ],
        }

        results = plugin.get_prefill_values(
            submission=submission, prefill_options=prefill_options
        )

        self.assertEqual(
            results, {"age": 38, "lastname": "zig", "now": "2024-09-02T10:33:00+00:00"}
        )
