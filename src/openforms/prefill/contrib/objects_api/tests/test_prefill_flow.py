from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from openforms.registrations.contrib.objects_api.models import ObjectsAPIConfig
from openforms.registrations.contrib.objects_api.tests.factories import (
    ObjectsAPIGroupConfigFactory,
)
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
