from django.test import tag

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APIRequestFactory, APITestCase
from testfixtures import LogCapture

from openforms.accounts.tests.factories import SuperUserFactory
from openforms.forms.tests.factories import (
    FormFactory,
    FormLogicFactory,
    FormStepFactory,
)

from ...api.viewsets import SubmissionStepViewSet
from ..factories import SubmissionFactory, SubmissionStepFactory
from ..mixins import SubmissionsMixin


class CheckLogicEndpointTests(SubmissionsMixin, APITestCase):
    def test_update_not_applicable_steps(self):
        form = FormFactory.create()
        step1 = FormStepFactory.create(
            form=form,
            form_definition__configuration={
                "components": [
                    {
                        "type": "select",
                        "key": "pet",
                        "data": {
                            "values": [
                                {"label": "Cat", "value": "cat"},
                                {"label": "Dog", "value": "dog"},
                            ]
                        },
                    }
                ]
            },
        )
        step2 = FormStepFactory.create(
            form=form,
            form_definition__configuration={
                "components": [
                    {
                        "type": "textfield",
                        "key": "step2",
                    }
                ]
            },
        )
        step3 = FormStepFactory.create(
            form=form,
            form_definition__configuration={
                "components": [
                    {
                        "type": "textfield",
                        "key": "step3",
                    }
                ]
            },
        )
        FormLogicFactory.create(
            form=form,
            json_logic_trigger={
                "==": [
                    {"var": "pet"},
                    "cat",
                ]
            },
            actions=[
                {
                    "form_step_uuid": f"{step2.uuid}",
                    "action": {
                        "name": "Step is not applicable",
                        "type": "step-not-applicable",
                    },
                }
            ],
        )
        FormLogicFactory.create(
            form=form,
            json_logic_trigger={
                "==": [
                    {"var": "pet"},
                    "dog",
                ]
            },
            actions=[
                {
                    "form_step_uuid": f"{step3.uuid}",
                    "action": {
                        "name": "Step is not applicable",
                        "type": "step-not-applicable",
                    },
                }
            ],
        )
        submission = SubmissionFactory.create(form=form)

        SubmissionStepFactory.create(
            submission=submission,
            form_step=step1,
            data={"pet": "dog"},  # With this data, step 3 is not applicable
        )

        endpoint = reverse(
            "api:submission-steps-logic-check",
            kwargs={"submission_uuid": submission.uuid, "step_uuid": step1.uuid},
        )
        self._add_submission_to_session(submission)

        # Make a change to the data, which causes step 2 to be not applicable (while step 3 is applicable again)
        response = self.client.post(endpoint, data={"data": {"pet": "cat"}})

        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertFalse(response.data["submission"]["steps"][1]["is_applicable"])
        self.assertTrue(response.data["submission"]["steps"][2]["is_applicable"])

    def test_endpoint_loads_submission_with_auth_info(self):
        submission = SubmissionFactory.create()
        submission_step = SubmissionStepFactory.create(submission=submission)

        request = APIRequestFactory().get("/")
        request.user = SuperUserFactory.create()

        def check_object_permissions(request, submission_step):
            return True

        endpoint = SubmissionStepViewSet()
        endpoint.kwargs = dict(
            submission_uuid=submission.uuid, step_uuid=submission_step.form_step.uuid
        )
        endpoint.request = request
        endpoint.check_object_permissions = check_object_permissions

        object = endpoint.get_object()

        # Check that get_object retrieves also the auth info as part of the select related
        with self.assertNumQueries(0):
            hasattr(object.submission, "auth_info")

    def test_updating_data_marks_step_as_applicable_again(self):
        form = FormFactory.create()
        form_step0 = FormStepFactory.create(form=form)
        form_step1 = FormStepFactory.create(
            form=form,
            form_definition__configuration={
                "components": [
                    {
                        "type": "radio",
                        "key": "radio",
                        "values": [
                            {"label": "A", "value": "a"},
                            {"label": "B", "value": "b"},
                        ],
                    }
                ]
            },
        )
        form_step2 = FormStepFactory.create(form=form)
        FormLogicFactory.create(
            form=form,
            json_logic_trigger={
                "==": [
                    {"var": "radio"},
                    "a",
                ]
            },
            actions=[
                {
                    "form_step_uuid": f"{form_step2.uuid}",
                    "action": {
                        "name": "Step is not applicable",
                        "type": "step-not-applicable",
                    },
                }
            ],
        )
        submission = SubmissionFactory.create(form=form)
        SubmissionStepFactory.create(
            submission=submission, form_step=form_step0, data={"some": "data"}
        )
        SubmissionStepFactory.create(
            submission=submission,
            form_step=form_step1,
            data={"radio": "a"},
        )

        endpoint = reverse(
            "api:submission-steps-logic-check",
            kwargs={"submission_uuid": submission.uuid, "step_uuid": form_step1.uuid},
        )
        self._add_submission_to_session(submission)

        # Make a change to the data, which causes step 2 to be applicable again
        response = self.client.post(endpoint, data={"data": {"radio": "b"}})

        data = response.json()

        self.assertTrue(data["submission"]["steps"][2]["isApplicable"])

    @tag("gh-3647")
    def test_sending_invalid_time_values(self):
        submission = SubmissionFactory.from_components(
            components_list=[
                {"type": "time", "key": "time"},
                {"type": "date", "key": "date"},
                {"type": "datetime", "key": "datetime"},
            ]
        )

        endpoint = reverse(
            "api:submission-steps-logic-check",
            kwargs={
                "submission_uuid": submission.uuid,
                "step_uuid": submission.submissionstep_set.first().form_step.uuid,
            },
        )
        self._add_submission_to_session(submission)

        with (
            self.subTest("Invalid time with good format"),
            LogCapture() as log_capture,
        ):
            self.client.post(endpoint, data={"data": {"time": "25:00"}})

            log_capture.check_present(
                (
                    "openforms.utils.date",
                    "INFO",
                    "Invalid time '25:00', falling back to 'None' instead.",
                )
            )

        with (
            self.subTest("Invalid time with bad format"),
            LogCapture() as log_capture,
        ):
            self.client.post(endpoint, data={"data": {"time": "Invalid"}})

            log_capture.check_present(
                (
                    "openforms.utils.date",
                    "INFO",
                    "Badly formatted time 'Invalid', falling back to 'None' instead.",
                )
            )

        with (self.subTest("Invalid date"), LogCapture() as log_capture):
            self.client.post(endpoint, data={"data": {"date": "2020-13-46"}})

            log_capture.check_present(
                (
                    "openforms.utils.date",
                    "INFO",
                    "Can't format date '2020-13-46', falling back to an empty string.",
                ),
                (
                    "openforms.utils.date",
                    "INFO",
                    "Badly formatted datetime '2020-13-46', falling back to 'None' instead.",
                ),
            )

        with (self.subTest("Invalid datetime"), LogCapture() as log_capture):
            self.client.post(
                endpoint, data={"data": {"datetime": "2022-13-46T00:00:00+02:00"}}
            )

            log_capture.check_present(
                (
                    "openforms.utils.date",
                    "INFO",
                    "Can't parse datetime '2022-13-46T00:00:00+02:00', falling back to 'None' instead.",
                )
            )

    def test_handling_none_values_in_logic(self):
        submission = SubmissionFactory.from_components(
            components_list=[
                {"type": "time", "key": "time"},
                {"type": "date", "key": "date"},
                {"type": "datetime", "key": "datetime"},
                {"type": "string", "key": "result"},
                {"type": "date", "key": "resultDate"},
                {"type": "datetime", "key": "resultDatetime"},
            ]
        )
        FormLogicFactory.create(
            form=submission.form,
            json_logic_trigger={
                "and": [
                    {"==": [None, {"var": "time"}]},
                    {"==": [None, {"var": "date"}]},
                    {"==": [None, {"var": "datetime"}]},
                ]
            },
            actions=[
                {
                    "variable": "result",
                    "action": {
                        "type": "variable",
                        "value": "All the variables were None",
                    },
                }
            ],
        )
        FormLogicFactory.create(
            form=submission.form,
            json_logic_trigger=True,
            actions=[
                {
                    "variable": "resultDate",
                    "action": {
                        "type": "variable",
                        "value": {"+": [{"var": "date"}, {"duration": "P1M"}]},
                    },
                },
                {
                    "variable": "resultDatetime",
                    "action": {
                        "type": "variable",
                        "value": {"+": [{"var": "datetime"}, {"duration": "P1M"}]},
                    },
                },
            ],
        )
        endpoint = reverse(
            "api:submission-steps-logic-check",
            kwargs={
                "submission_uuid": submission.uuid,
                "step_uuid": submission.submissionstep_set.first().form_step.uuid,
            },
        )
        self._add_submission_to_session(submission)

        response = self.client.post(
            endpoint,
            data={
                "data": {
                    "time": "Invalid",
                    "date": "2020-13-46",
                    "datetime": "2022-13-46T00:00:00+02:00",
                }
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()

        self.assertEqual(data["step"]["data"]["result"], "All the variables were None")
        self.assertEqual(data["step"]["data"]["time"], "Invalid")
        self.assertEqual(data["step"]["data"]["date"], "2020-13-46")
        self.assertEqual(data["step"]["data"]["datetime"], "2022-13-46T00:00:00+02:00")
        self.assertNotIn("resultDate", data["step"]["data"])
        self.assertNotIn("resultDatetime", data["step"]["data"])
