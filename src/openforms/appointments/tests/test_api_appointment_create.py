from datetime import datetime, time
from unittest.mock import patch

from django.utils import timezone
from django.utils.translation import gettext as _

from freezegun import freeze_time
from hypothesis import given
from hypothesis.extra.django import TestCase as HypothesisTestCase
from rest_framework import status
from rest_framework.reverse import reverse, reverse_lazy
from rest_framework.test import APITestCase

from openforms.config.models import GlobalConfiguration
from openforms.forms.constants import SubmissionAllowedChoices
from openforms.submissions.tests.factories import SubmissionFactory
from openforms.submissions.tests.mixins import SubmissionsMixin
from openforms.tests.search_strategies import json_values

from ..models import Appointment, AppointmentsConfig

ENDPOINT = reverse_lazy("api:appointments-create")
TODAY = timezone.localdate()


class ConfigPatchMixin:
    def setUp(self):
        super().setUp()  # type: ignore
        self.config = AppointmentsConfig(plugin="demo", limit_to_location="1")
        paths = [
            "openforms.appointments.utils.AppointmentsConfig.get_solo",
            "openforms.appointments.api.serializers.AppointmentsConfig.get_solo",
        ]
        for path in paths:
            patcher = patch(path, return_value=self.config)
            patcher.start()
            self.addCleanup(patcher.stop)  # type: ignore

        self.global_configuration = GlobalConfiguration(ask_privacy_consent=True)
        global_config_patcher = patch(
            "openforms.forms.models.form.GlobalConfiguration.get_solo",
            return_value=self.global_configuration,
        )
        global_config_patcher.start()
        self.addCleanup(global_config_patcher.stop)  # type: ignore


class AppointmentCreateSuccessTests(ConfigPatchMixin, SubmissionsMixin, APITestCase):
    """
    Test the appointment create happy flow.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.submission = SubmissionFactory.create(form__is_appointment_form=True)

    def setUp(self):
        super().setUp()
        self._add_submission_to_session(self.submission)

    def test_appointment_data_is_recorded(self):
        appointment_datetime = timezone.make_aware(
            datetime.combine(TODAY, time(15, 15))
        )
        data = {
            "submission": reverse(
                "api:submission-detail", kwargs={"uuid": self.submission.uuid}
            ),
            "products": [
                {
                    "productId": "2",
                    "amount": 1,
                }
            ],
            "location": "1",
            "date": TODAY.isoformat(),
            "datetime": appointment_datetime.isoformat(),
            "contactDetails": {
                "lastName": "Periwinkle",
            },
            "privacy_policy_accepted": True,
        }

        response = self.client.post(ENDPOINT, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        appointment = Appointment.objects.get()
        self.assertEqual(appointment.submission, self.submission)
        self.assertEqual(appointment.plugin, "demo")
        self.assertEqual(appointment.location, "1")
        self.assertEqual(appointment.datetime, appointment_datetime)
        self.assertEqual(
            appointment.contact_details_meta,
            [
                {
                    "type": "textfield",
                    "key": "lastName",
                    "label": _("Last name"),
                    "validate": {
                        "required": True,
                        "maxLength": 20,
                    },
                }
            ],
        )
        self.assertEqual(appointment.contact_details, {"lastName": "Periwinkle"})
        products = appointment.products.all()
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].product_id, "2")
        self.assertEqual(products[0].amount, 1)

        self.submission.refresh_from_db()
        self.assertTrue(self.submission.privacy_policy_accepted)

    @patch("openforms.submissions.api.mixins.on_completion")
    def test_submission_is_completed(self, mock_on_completion):
        appointment_datetime = timezone.make_aware(
            datetime.combine(TODAY, time(15, 15))
        )
        data = {
            "submission": reverse(
                "api:submission-detail", kwargs={"uuid": self.submission.uuid}
            ),
            "products": [
                {
                    "productId": "2",
                    "amount": 1,
                }
            ],
            "location": "1",
            "date": TODAY,
            "datetime": appointment_datetime.isoformat(),
            "contactDetails": {
                "lastName": "Periwinkle",
            },
            "privacy_policy_accepted": True,
        }

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(ENDPOINT, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.submission.refresh_from_db()
        self.assertTrue(self.submission.is_completed)
        self.assertIn("statusUrl", response.json())

        # assert that the async celery task execution is scheduled
        mock_on_completion.assert_called_once_with(self.submission.id)

    def test_retry_does_not_cause_integrity_error(self):
        # When there are on_completion processing errors, the client will re-post the
        # same state. This must update the existing appointment rather than trying to
        # create a new one.
        appointment_datetime = timezone.make_aware(
            datetime.combine(TODAY, time(15, 15))
        )
        data = {
            "submission": reverse(
                "api:submission-detail", kwargs={"uuid": self.submission.uuid}
            ),
            "products": [{"productId": "2", "amount": 1}],
            "location": "1",
            "date": TODAY,
            "datetime": appointment_datetime.isoformat(),
            "contactDetails": {
                "lastName": "Periwinkle",
            },
            "privacy_policy_accepted": True,
        }
        # first POST
        response = self.client.post(ENDPOINT, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # retry attempt - SubmissionProcessingStatus.ensure_failure_can_be_managed adds
        # the submission ID back to the session
        self._add_submission_to_session(self.submission)
        updated_data = {
            **data,
            "contactDetails": {
                "lastName": "Periwinkle",
                "firstName": "Caro",
            },
        }
        response = self.client.post(ENDPOINT, updated_data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Appointment.objects.count(), 1)
        appointment = Appointment.objects.get()
        self.assertEqual(
            appointment.contact_details,
            {
                "lastName": "Periwinkle",
                "firstName": "Caro",
            },
        )

    def test_privacy_policy_not_required(self):
        self.global_configuration.ask_privacy_consent = False
        appointment_datetime = timezone.make_aware(
            datetime.combine(TODAY, time(15, 15))
        )
        data = {
            "submission": reverse(
                "api:submission-detail", kwargs={"uuid": self.submission.uuid}
            ),
            "products": [
                {
                    "productId": "2",
                    "amount": 1,
                }
            ],
            "location": "1",
            "date": TODAY.isoformat(),
            "datetime": appointment_datetime.isoformat(),
            "contactDetails": {
                "lastName": "Periwinkle",
            },
            "privacy_policy_accepted": False,
        }

        response = self.client.post(ENDPOINT, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class AppointmentCreateInvalidPermissionsTests(
    SubmissionsMixin, APITestCase, HypothesisTestCase
):
    def test_no_submission_in_session(self):
        submission = SubmissionFactory.create(form__is_appointment_form=True)
        submission_url = reverse(
            "api:submission-detail", kwargs={"uuid": submission.uuid}
        )

        response = self.client.post(ENDPOINT, {"submission": submission_url})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_submission_in_request_body(self):
        submission = SubmissionFactory.create(form__is_appointment_form=True)
        self._add_submission_to_session(submission)

        empty_ish_bodies = [
            {},
            {"submission": None},
            {"submission": ""},
        ]
        for data in empty_ish_bodies:
            with self.subTest(json_data=data):
                response = self.client.post(ENDPOINT, data)

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_different_submission_url_in_request_body(self):
        submission1, submission2 = SubmissionFactory.create_batch(
            2, form__is_appointment_form=True
        )
        self._add_submission_to_session(submission1)
        submission2_url = reverse(
            "api:submission-detail", kwargs={"uuid": submission2.uuid}
        )

        response = self.client.post(ENDPOINT, {"submission": submission2_url})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @given(json_values())
    def test_invalid_submission_url_in_request_body(self, submission_url):
        response = self.client.post(ENDPOINT, {"submission": submission_url})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_submission_allowed_on_form(self):
        submission = SubmissionFactory.create(
            form__is_appointment_form=True,
            form__submission_allowed=SubmissionAllowedChoices.no_with_overview,
        )
        self._add_submission_to_session(submission)
        submission_url = reverse(
            "api:submission-detail", kwargs={"uuid": submission.uuid}
        )

        response = self.client.post(ENDPOINT, {"submission": submission_url})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AppointmentCreateValidationErrorTests(
    ConfigPatchMixin, SubmissionsMixin, APITestCase
):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.submission = SubmissionFactory.create(form__is_appointment_form=True)

    def setUp(self):
        super().setUp()
        self._add_submission_to_session(self.submission)

    def test_required_privacy_policy_accept_missing(self):
        valid_data = {
            "submission": reverse(
                "api:submission-detail", kwargs={"uuid": self.submission.uuid}
            ),
            "products": [
                {
                    "productId": "2",
                    "amount": 1,
                }
            ],
            "location": "1",
            "date": TODAY.isoformat(),
            "datetime": f"{TODAY.isoformat()}T13:15:00Z",
            "contactDetails": {
                "lastName": "Periwinkle",
            },
        }

        invalid_privacy_policy_accepted_variants = [
            {"privacy_policy_accepted": None},
            {"privacy_policy_accepted": False},
            {"privacy_policy_accepted": ""},
            {"privacy_policy_accepted": "nope"},
            {},
        ]

        for variant in invalid_privacy_policy_accepted_variants:
            with self.subTest(privacy_policy_accepted=variant):
                data = {**valid_data, **variant}

                response = self.client.post(ENDPOINT, data)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                invalid_params = response.json()["invalidParams"]
                self.assertEqual(len(invalid_params), 1)
                self.assertEqual(invalid_params[0]["name"], "privacyPolicyAccepted")

    def test_invalid_products(self):
        appointment_datetime = timezone.make_aware(
            datetime.combine(TODAY, time(15, 15))
        )
        base = {
            "submission": reverse(
                "api:submission-detail", kwargs={"uuid": self.submission.uuid}
            ),
            "location": "1",
            "date": TODAY.isoformat(),
            "datetime": appointment_datetime.isoformat(),
            "contactDetails": {
                "lastName": "Periwinkle",
            },
            "privacyPolicyAccepted": True,
        }

        with self.subTest("invalid product ID"):
            data = {
                **base,
                "products": [
                    {
                        "productId": "123",
                        "amount": 1,
                    }
                ],
            }

            response = self.client.post(ENDPOINT, data)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            invalid_params = response.json()["invalidParams"]
            self.assertEqual(len(invalid_params), 1)
            self.assertEqual(invalid_params[0]["name"], "products.0.productId")

        with self.subTest("invalid amount"):
            for amount in (0, -2, 4.2, "foo"):
                with self.subTest(amount=amount):
                    data = {
                        **base,
                        "products": [
                            {
                                "productId": "123",
                                "amount": amount,
                            }
                        ],
                    }

                    response = self.client.post(ENDPOINT, data)

                    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                    invalid_params = response.json()["invalidParams"]
                    self.assertEqual(len(invalid_params), 1)
                    self.assertEqual(invalid_params[0]["name"], "products.0.amount")

        with self.subTest("plugin does not support multiple products"):
            data = {
                **base,
                "products": [
                    {
                        "productId": "1",
                        "amount": 1,
                    },
                    {
                        "productId": "2",
                        "amount": 1,
                    },
                ],
            }

            response = self.client.post(ENDPOINT, data)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            invalid_params = response.json()["invalidParams"]
            self.assertEqual(len(invalid_params), 1)
            self.assertEqual(invalid_params[0]["name"], "products")

    def test_invalid_location_with_fixed_location_in_config(self):
        # made up, but you can assume this is valid via the admin validation
        self.config.limit_to_location = "2"
        appointment_datetime = timezone.make_aware(
            datetime.combine(TODAY, time(15, 15))
        )
        data = {
            "submission": reverse(
                "api:submission-detail", kwargs={"uuid": self.submission.uuid}
            ),
            "products": [{"productId": "1", "amount": 1}],
            "location": "1",
            "date": TODAY.isoformat(),
            "datetime": appointment_datetime.isoformat(),
            "contactDetails": {
                "lastName": "Periwinkle",
            },
            "privacyPolicyAccepted": True,
        }

        response = self.client.post(ENDPOINT, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        invalid_params = response.json()["invalidParams"]
        self.assertEqual(len(invalid_params), 1)
        self.assertEqual(invalid_params[0]["name"], "location")

    def test_invalid_location_from_plugins_available_locations(self):
        # made up, but you can assume this is valid via the admin validation
        self.config.limit_to_location = ""
        appointment_datetime = timezone.make_aware(
            datetime.combine(TODAY, time(15, 15))
        )
        data = {
            "submission": reverse(
                "api:submission-detail", kwargs={"uuid": self.submission.uuid}
            ),
            "products": [{"productId": "1", "amount": 1}],
            "location": "123",
            "date": TODAY.isoformat(),
            "datetime": appointment_datetime.isoformat(),
            "contactDetails": {
                "lastName": "Periwinkle",
            },
            "privacyPolicyAccepted": True,
        }

        response = self.client.post(ENDPOINT, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        invalid_params = response.json()["invalidParams"]
        self.assertEqual(len(invalid_params), 1)
        self.assertEqual(invalid_params[0]["name"], "location")

    def test_invalid_date(self):
        appointment_datetime = timezone.make_aware(
            datetime.combine(TODAY, time(15, 15))
        )
        base = {
            "submission": reverse(
                "api:submission-detail", kwargs={"uuid": self.submission.uuid}
            ),
            "products": [{"productId": "1", "amount": 1}],
            "location": "1",
            "datetime": appointment_datetime.isoformat(),
            "contactDetails": {
                "lastName": "Periwinkle",
            },
            "privacyPolicyAccepted": True,
        }

        with self.subTest("not ISO 8601 date"):
            data = {**base, "date": "18/7/2023"}

            response = self.client.post(ENDPOINT, data)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            invalid_params = response.json()["invalidParams"]
            self.assertEqual(len(invalid_params), 1)
            self.assertEqual(invalid_params[0]["name"], "date")

        with self.subTest("date not available in backend"):
            # demo plugin only has 'today' available
            data = {**base, "date": "2021-01-01", "datetime": "2021-01-01T13:15:00Z"}

            response = self.client.post(ENDPOINT, data)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            invalid_params = response.json()["invalidParams"]
            self.assertEqual(len(invalid_params), 1)
            self.assertEqual(invalid_params[0]["name"], "date")

    @freeze_time("2023-07-18T07:42:00Z")  # pin to DST, UTC+2
    def test_invalid_datetime(self):
        today = timezone.localdate()
        base = {
            "submission": reverse(
                "api:submission-detail", kwargs={"uuid": self.submission.uuid}
            ),
            "products": [{"productId": "1", "amount": 1}],
            "location": "1",
            "date": today.isoformat(),
            "contactDetails": {
                "lastName": "Periwinkle",
            },
            "privacyPolicyAccepted": True,
        }

        with self.subTest("not ISO 8601 datetime"):
            data = {**base, "datetime": "12:00"}

            response = self.client.post(ENDPOINT, data)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            invalid_params = response.json()["invalidParams"]
            self.assertEqual(len(invalid_params), 1)
            self.assertEqual(invalid_params[0]["name"], "datetime")

        with self.subTest("different date part than date field"):
            data = {**base, "datetime": "2023-01-01T10:00:00Z"}

            response = self.client.post(ENDPOINT, data)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            invalid_params = response.json()["invalidParams"]
            self.assertEqual(len(invalid_params), 1)
            self.assertEqual(invalid_params[0]["name"], "date")

        with self.subTest("time slot not available in plugin (AMS timezone)"):
            data = {**base, "datetime": f"{today.isoformat()}T09:11:00+02:00"}

            response = self.client.post(ENDPOINT, data)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            invalid_params = response.json()["invalidParams"]
            self.assertEqual(len(invalid_params), 1)
            self.assertEqual(invalid_params[0]["name"], "datetime")

        with self.subTest("time slot not available in plugin (UTC timezone)"):
            data = {**base, "datetime": f"{today.isoformat()}T07:11:00Z"}

            response = self.client.post(ENDPOINT, data)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            invalid_params = response.json()["invalidParams"]
            self.assertEqual(len(invalid_params), 1)
            self.assertEqual(invalid_params[0]["name"], "datetime")

    def test_invalid_contact_details(self):
        appointment_datetime = timezone.make_aware(
            datetime.combine(TODAY, time(15, 15))
        )
        base = {
            "submission": reverse(
                "api:submission-detail", kwargs={"uuid": self.submission.uuid}
            ),
            "products": [{"productId": "1", "amount": 1}],
            "location": "1",
            "date": TODAY.isoformat(),
            "datetime": appointment_datetime.isoformat(),
            "privacyPolicyAccepted": True,
        }

        with self.subTest("missing contact details"):
            response = self.client.post(ENDPOINT, base)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            invalid_params = response.json()["invalidParams"]
            self.assertEqual(len(invalid_params), 1)
            self.assertEqual(invalid_params[0]["name"], "contactDetails")

        with self.subTest("missing required field"):
            data = {**base, "contactDetails": {}}

            response = self.client.post(ENDPOINT, data)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            invalid_params = response.json()["invalidParams"]
            self.assertEqual(len(invalid_params), 1)
            self.assertEqual(invalid_params[0]["name"], "contactDetails.0")
            self.assertEqual(invalid_params[0]["code"], "required")

        with self.subTest("value too long"):
            data = {**base, "contactDetails": {"lastName": "abcd" * 6}}  # 24 > 20

            response = self.client.post(ENDPOINT, data)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            invalid_params = response.json()["invalidParams"]
            self.assertEqual(len(invalid_params), 1)
            self.assertEqual(invalid_params[0]["name"], "contactDetails.0")
            self.assertEqual(invalid_params[0]["code"], "max_length")
