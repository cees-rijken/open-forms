from typing import TypedDict

from django.test import override_settings, tag
from django.urls import reverse

from asgiref.sync import async_to_sync
from furl import furl
from playwright.async_api import Page, expect
from rest_framework import status
from typing_extensions import NotRequired, Unpack

from openforms.formio.typing import Component
from openforms.forms.models import Form
from openforms.forms.tests.factories import (
    FormDefinitionFactory,
    FormFactory,
    FormStepFactory,
)
from openforms.submissions.tests.factories import SubmissionFactory
from openforms.submissions.tests.mixins import SubmissionsMixin
from openforms.typing import JSONValue

from .base import E2ETestCase, browser_page


def create_form(component: Component) -> Form:
    _test_name = f"{component['type']} - {component['label']}"[:50]
    form_definition = FormDefinitionFactory.create(
        name=_test_name,
        configuration={"components": [component]},
    )
    form = FormFactory.create(
        name=_test_name,
        product=None,
        category=None,
        registration_backend=None,
        translation_enabled=False,  # force Dutch
        ask_privacy_consent=False,
        ask_statement_of_truth=False,
    )
    FormStepFactory.create(
        form=form, form_definition=form_definition, next_text="Volgende"
    )
    return form


class ValidationKwargs(TypedDict):
    api_value: NotRequired[JSONValue]


@tag("e2e-validation")
# allow all origins, since we don't know exactly the generated live server port number
@override_settings(CORS_ALLOW_ALL_ORIGINS=True)
class ValidationsTestCase(SubmissionsMixin, E2ETestCase):

    def assertValidationIsAligned(
        self,
        component: Component,
        ui_input: str | int | float,
        expected_ui_error: str,
        **kwargs: Unpack[ValidationKwargs],
    ):
        """
        Check a component and ensure frontend and backend validation are aligned.

        When the frontend validation rejects a user input, the backend must do so
        accordingly. This does not necessarily apply the other way around - the frontend
        cannot handle array/null datatypes etc. so the backend may be stricter to some
        extent.

        :arg component: Given the component definition, create a form instance and use
          this for both the end-to-end test with playwright and the django test client
          assertions to check for validation issues.
        :arg ui_input: Input to enter in the field with playwright.
        :arg expected_ui_error: Content of the validation error to be expected in the
          playwright test.
        """
        form = create_form(component)

        with self.subTest("frontend validation"):
            self._assertFrontendValidation(
                form, component["label"], str(ui_input), expected_ui_error
            )

        with self.subTest("backend validation"):
            api_value = kwargs.pop("api_value", ui_input)
            self._assertBackendValidation(form, component["key"], api_value)

    def _locate_input(self, page: Page, label: str):
        return page.get_by_label(label, exact=True)

    async def apply_ui_input(self, page: Page, label: str, ui_input: str | int | float):
        await self._locate_input(page, label).fill(ui_input)

    @async_to_sync()
    async def _assertFrontendValidation(
        self,
        form: Form,
        label: str,
        ui_input: str,
        expected_ui_error: str,
    ):
        frontend_path = reverse("forms:form-detail", kwargs={"slug": form.slug})
        url = str(furl(self.live_server_url) / frontend_path)

        async with browser_page() as page:
            await page.goto(url)
            await page.get_by_role("button", name="Formulier starten").click()

            await self.apply_ui_input(page, label, ui_input)

            # try to submit the step which should be invalid, so we expect this to
            # render the error message.
            await page.get_by_role("button", name="Volgende").click()

            await expect(page.get_by_text(expected_ui_error)).to_be_visible()

    def _assertBackendValidation(self, form: Form, key: str, value: JSONValue):
        submission = SubmissionFactory.create(form=form)
        step = form.formstep_set.get()
        self._add_submission_to_session(submission)

        step_endpoint = reverse(
            "api:submission-steps-detail",
            kwargs={
                "submission_uuid": submission.uuid,
                "step_uuid": step.uuid,
            },
        )
        body = {"data": {key: value}}
        response = self.client.put(step_endpoint, body, content_type="application/json")
        assert response.status_code in [201, 200]

        # try to complete the submission, this is expected to fail
        endpoint = reverse("api:submission-complete", kwargs={"uuid": submission.uuid})

        response = self.client.post(
            endpoint,
            data={"privacyPolicyAccepted": True},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_params = response.json()["invalidParams"]
        expected_name = f"steps.0.data.{key}"
        names = [param["name"] for param in invalid_params]
        self.assertIn(expected_name, names)
