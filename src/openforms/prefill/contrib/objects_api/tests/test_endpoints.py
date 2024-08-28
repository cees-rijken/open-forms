from pathlib import Path
from unittest.mock import patch

from rest_framework import status
from rest_framework.reverse import reverse_lazy
from rest_framework.test import APITestCase

from openforms.accounts.tests.factories import StaffUserFactory
from openforms.registrations.contrib.objects_api.models import ObjectsAPIConfig
from openforms.registrations.contrib.objects_api.tests.factories import (
    ObjectsAPIGroupConfigFactory,
)
from openforms.utils.tests.vcr import OFVCRMixin

VCR_TEST_FILES = Path(__file__).parent / "files"


class ObjectsAPIPrefillPluginEndpointTests(OFVCRMixin, APITestCase):
    """This test case requires the Objects & Objecttypes API to be running.
    See the relevant Docker compose in the ``docker/`` folder.
    """

    VCR_TEST_FILES = VCR_TEST_FILES
    endpoints = {
        "objecttype_list": reverse_lazy(
            "api:prefill-objects-api-objecttype-list",
        ),
        "objecttype_versions_list": reverse_lazy(
            "api:prefill-objects-api-objecttype-version-list",
            kwargs={
                "objects_api_objecttype_uuid": "3edfdaf7-f469-470b-a391-bb7ea015bd6f",
            },
        ),
        "attribute_list": reverse_lazy(
            "api:prefill-objects-api-objecttype-attribute-list",
            kwargs={
                "objects_api_objecttype_uuid": "3edfdaf7-f469-470b-a391-bb7ea015bd6f",
                "objects_api_objecttype_version": 1,
            },
        ),
    }

    def setUp(self):
        super().setUp()

        config_patcher = patch(
            "openforms.registrations.contrib.objects_api.models.ObjectsAPIConfig.get_solo",
            return_value=ObjectsAPIConfig(),
        )
        attributes_patcher = patch(
            "openforms.prefill.contrib.objects_api.plugin.ObjectsAPIPrefill.get_available_attributes",
            return_value=[
                ("value one", "value one (string)"),
                ("another value", "another value (string)"),
            ],
        )
        self.mock_get_config = config_patcher.start()
        self.mock_attributes = attributes_patcher.start()
        self.addCleanup(config_patcher.stop)
        self.addCleanup(attributes_patcher.stop)

        self.objects_api_group = ObjectsAPIGroupConfigFactory.create(
            for_test_docker_compose=True
        )

    def test_auth_required(self):
        for endpoint in self.endpoints.values():
            with self.subTest(endpoint=endpoint):
                response = self.client.get(
                    endpoint, {"objects_api_group": self.objects_api_group.pk}
                )

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_endpoints_missing_api_group(self):
        staff_user = StaffUserFactory.create()
        self.client.force_authenticate(user=staff_user)

        for endpoint in self.endpoints.values():
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_objecttypes(self):
        staff_user = StaffUserFactory.create()
        self.client.force_authenticate(user=staff_user)

        response = self.client.get(
            self.endpoints["objecttype_list"],
            {"objects_api_group": self.objects_api_group.pk},
        )

        tree_objecttype = next(obj for obj in response.json() if obj["name"] == "Tree")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            tree_objecttype,
            {
                "dataClassification": "confidential",
                "name": "Tree",
                "namePlural": "Trees",
                "url": "http://objecttypes-web:8000/api/v2/objecttypes/3edfdaf7-f469-470b-a391-bb7ea015bd6f",
                "uuid": "3edfdaf7-f469-470b-a391-bb7ea015bd6f",
            },
        )

    def test_list_objecttypes_versions(self):
        staff_user = StaffUserFactory.create()
        self.client.force_authenticate(user=staff_user)

        response = self.client.get(
            self.endpoints["objecttype_versions_list"],
            {"objects_api_group": self.objects_api_group.pk},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            [{"version": 1, "status": "published"}],
        )

    def test_list_available_attributes(self):
        staff_user = StaffUserFactory.create()
        self.client.force_authenticate(user=staff_user)

        response = self.client.get(
            self.endpoints["attribute_list"],
            {"objects_api_group": self.objects_api_group.pk},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            [
                {"id": "value one", "label": "value one (string)"},
                {"id": "another value", "label": "another value (string)"},
            ],
        )
