from unittest.mock import patch

from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from openforms.submissions.tests.factories import SubmissionFactory
from openforms.submissions.tests.mixins import SubmissionsMixin

from ..models import AppointmentsConfig


class ProductListTests(SubmissionsMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.submission = SubmissionFactory.create()
        cls.endpoint = reverse("api:appointments-products-list")

    @patch("openforms.appointments.api.views.get_plugin")
    def test_list_products_with_fixed_location_in_config(self, mock_get_plugin):
        mock_plugin = mock_get_plugin.return_value
        config_patcher = patch(
            "openforms.appointments.utils.AppointmentsConfig.get_solo",
            return_value=AppointmentsConfig(
                plugin="demo",
                limit_to_location="some-location-id",
            ),
        )
        config_patcher.start()
        self.addCleanup(config_patcher.stop)
        self._add_submission_to_session(self.submission)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 200)
        mock_plugin.get_available_products.assert_called_once_with(
            location_id="some-location-id"
        )
