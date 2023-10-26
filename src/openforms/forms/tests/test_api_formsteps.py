import uuid
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.test import override_settings, tag
from django.urls import reverse
from django.utils.translation import gettext as _

from rest_framework import status
from rest_framework.test import APITestCase

from openforms.accounts.tests.factories import (
    StaffUserFactory,
    TokenFactory,
    UserFactory,
)
from openforms.submissions.tests.factories import SubmissionFactory
from openforms.translations.tests.utils import make_translated

from ..models import FormStep
from .factories import FormDefinitionFactory, FormFactory, FormStepFactory


def assign_change_form_permissions(user) -> None:
    user.user_permissions.add(Permission.objects.get(codename="change_form"))
    user.is_staff = True
    user.save()


class FormsStepsAPITests(APITestCase):
    def setUp(self):
        super().setUp()

        self.user = UserFactory.create()
        self.step = FormStepFactory.create()
        self.other_form_definition = FormDefinitionFactory.create()

        self.client.force_authenticate(user=self.user)

    def test_steps_list(self):
        url = reverse(
            "api:form-steps-list", kwargs={"form_uuid_or_slug": self.step.form.uuid}
        )
        response = self.client.get(url, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_form_step_successful(self):
        assign_change_form_permissions(self.user)
        url = reverse(
            "api:form-steps-list", kwargs={"form_uuid_or_slug": self.step.form.uuid}
        )
        form_detail_url = reverse(
            "api:formdefinition-detail",
            kwargs={"uuid": self.other_form_definition.uuid},
        )
        data = {"formDefinition": f"http://testserver{form_detail_url}", "index": 0}
        response = self.client.post(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            FormStep.objects.filter(form_definition=self.other_form_definition).count(),
            1,
        )

    def test_create_form_step_successful_with_custom_button_text(self):
        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()
        url = reverse(
            "api:form-steps-list", kwargs={"form_uuid_or_slug": self.step.form.uuid}
        )
        form_detail_url = reverse(
            "api:formdefinition-detail",
            kwargs={"uuid": self.other_form_definition.uuid},
        )
        data = {
            "formDefinition": f"http://testserver{form_detail_url}",
            "index": 0,
            "literals": {
                "previousText": {"value": "Different Previous Text"},
                "saveText": {"value": "Different Save Text"},
                "nextText": {"value": "Different Next Text"},
            },
        }
        response = self.client.post(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            FormStep.objects.filter(form_definition=self.other_form_definition).count(),
            1,
        )
        form_step = FormStep.objects.get(form_definition=self.other_form_definition)
        self.assertEqual(form_step.previous_text, "Different Previous Text")
        self.assertEqual(form_step.save_text, "Different Save Text")
        self.assertEqual(form_step.next_text, "Different Next Text")

    @patch(
        "openforms.api.exception_handling.uuid.uuid4",
        return_value="95a55a81-d316-44e8-b090-0519dd21be5f",
    )
    def test_create_form_step_unsuccessful_with_bad_data(self, _mock):
        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()
        url = reverse(
            "api:form-steps-list", kwargs={"form_uuid_or_slug": self.step.form.uuid}
        )
        data = {
            "bad": "data",
        }
        response = self.client.post(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(FormStep.objects.count(), 1)
        self.assertEqual(
            response.json(),
            {
                "type": "http://testserver/fouten/ValidationError/",
                "code": "invalid",
                "title": _("Invalid input."),
                "status": 400,
                "detail": "",
                "instance": "urn:uuid:95a55a81-d316-44e8-b090-0519dd21be5f",
                "invalidParams": [
                    {
                        "name": "index",
                        "code": "required",
                        "reason": _("This field is required."),
                    },
                    {
                        "name": "formDefinition",
                        "code": "required",
                        "reason": _("This field is required."),
                    },
                ],
            },
        )

    def test_create_form_step_unsuccessful_when_form_is_not_found(self):
        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()
        url = reverse("api:form-steps-list", kwargs={"form_uuid_or_slug": uuid.uuid4()})
        form_detail_url = reverse(
            "api:formdefinition-detail", kwargs={"uuid": self.step.form_definition.uuid}
        )
        data = {"formDefinition": f"http://testserver{form_detail_url}"}
        response = self.client.post(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(FormStep.objects.count(), 1)

    def test_create_form_step_unsuccessful_without_authorization(self):
        url = reverse(
            "api:form-steps-list", kwargs={"form_uuid_or_slug": self.step.form.uuid}
        )
        form_detail_url = reverse(
            "api:formdefinition-detail", kwargs={"uuid": self.step.form_definition.uuid}
        )
        data = {"formDefinition": f"http://testserver{form_detail_url}"}
        response = self.client.post(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(FormStep.objects.count(), 1)

    def test_complete_form_step_update_successful(self):
        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()
        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.step.form.uuid, "uuid": self.step.uuid},
        )
        form_detail_url = reverse(
            "api:formdefinition-detail",
            kwargs={"uuid": self.other_form_definition.uuid},
        )
        data = {"formDefinition": f"http://testserver{form_detail_url}", "index": 0}
        response = self.client.put(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            FormStep.objects.filter(form_definition=self.other_form_definition).count(),
            1,
        )

    def test_complete_form_step_update_with_custom_texts_successful(self):
        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()
        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.step.form.uuid, "uuid": self.step.uuid},
        )
        form_detail_url = reverse(
            "api:formdefinition-detail",
            kwargs={"uuid": self.other_form_definition.uuid},
        )
        data = {
            "formDefinition": f"http://testserver{form_detail_url}",
            "index": 0,
            "literals": {
                "previousText": {"value": "Different Previous Text"},
                "saveText": {"value": "Different Save Text"},
                "nextText": {"value": "Different Next Text"},
            },
        }
        response = self.client.put(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            FormStep.objects.filter(form_definition=self.other_form_definition).count(),
            1,
        )
        form_step = FormStep.objects.get(form_definition=self.other_form_definition)
        self.assertEqual(form_step.previous_text, "Different Previous Text")
        self.assertEqual(form_step.save_text, "Different Save Text")
        self.assertEqual(form_step.next_text, "Different Next Text")

    def test_complete_form_step_update_unsuccessful_when_form_step_not_found(self):
        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()
        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.step.form.uuid, "uuid": uuid.uuid4()},
        )
        form_detail_url = reverse(
            "api:formdefinition-detail",
            kwargs={"uuid": self.other_form_definition.uuid},
        )
        data = {"formDefinition": f"http://testserver{form_detail_url}"}
        response = self.client.put(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(
            FormStep.objects.filter(form_definition=self.other_form_definition).exists()
        )

    @patch(
        "openforms.api.exception_handling.uuid.uuid4",
        return_value="95a55a81-d316-44e8-b090-0519dd21be5f",
    )
    def test_complete_form_step_update_unsuccessful_with_non_existant_form_definition(
        self, _mock
    ):
        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()
        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.step.form.uuid, "uuid": self.step.uuid},
        )
        form_detail_url = reverse(
            "api:formdefinition-detail",
            kwargs={"uuid": uuid.uuid4()},
        )
        data = {"formDefinition": f"http://testserver{form_detail_url}", "index": 0}
        response = self.client.put(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            FormStep.objects.filter(form_definition=self.other_form_definition).exists()
        )
        self.assertEqual(
            response.json(),
            {
                "type": "http://testserver/fouten/ValidationError/",
                "code": "invalid",
                "title": _("Invalid input."),
                "status": 400,
                "detail": "",
                "instance": "urn:uuid:95a55a81-d316-44e8-b090-0519dd21be5f",
                "invalidParams": [
                    {
                        "name": "formDefinition",
                        "code": "does_not_exist",
                        "reason": _("Invalid hyperlink - Object does not exist."),
                    }
                ],
            },
        )

    @patch(
        "openforms.api.exception_handling.uuid.uuid4",
        return_value="95a55a81-d316-44e8-b090-0519dd21be5f",
    )
    def test_complete_form_step_update_unsuccessful_with_bad_data(self, _mock):
        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()
        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.step.form.uuid, "uuid": self.step.uuid},
        )
        data = {
            "bad": "data",
        }
        response = self.client.put(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(FormStep.objects.count(), 1)
        self.assertEqual(
            response.json(),
            {
                "type": "http://testserver/fouten/ValidationError/",
                "code": "invalid",
                "title": _("Invalid input."),
                "status": 400,
                "detail": "",
                "instance": "urn:uuid:95a55a81-d316-44e8-b090-0519dd21be5f",
                "invalidParams": [
                    {
                        "name": "index",
                        "code": "required",
                        "reason": _("This field is required."),
                    },
                    {
                        "name": "formDefinition",
                        "code": "required",
                        "reason": _("This field is required."),
                    },
                ],
            },
        )

    def test_complete_form_step_update_unsuccessful_without_authorization(self):
        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.step.form.uuid, "uuid": self.step.uuid},
        )
        form_detail_url = reverse(
            "api:formdefinition-detail", kwargs={"uuid": self.step.form_definition.uuid}
        )
        data = {"formDefinition": f"http://testserver{form_detail_url}"}
        response = self.client.put(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            FormStep.objects.filter(form_definition=self.other_form_definition).exists()
        )

    def test_partial_form_step_update_successful(self):
        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()
        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.step.form.uuid, "uuid": self.step.uuid},
        )
        form_detail_url = reverse(
            "api:formdefinition-detail",
            kwargs={"uuid": self.other_form_definition.uuid},
        )
        data = {"formDefinition": f"http://testserver{form_detail_url}"}
        response = self.client.patch(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            FormStep.objects.filter(form_definition=self.other_form_definition).count(),
            1,
        )

    def test_partial_form_step_update_with_texts_successful(self):
        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()
        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.step.form.uuid, "uuid": self.step.uuid},
        )
        form_detail_url = reverse(
            "api:formdefinition-detail",
            kwargs={"uuid": self.other_form_definition.uuid},
        )
        data = {
            "formDefinition": f"http://testserver{form_detail_url}",
            "literals": {
                "previousText": {"value": "Different Previous Text"},
                "saveText": {"value": "Different Save Text"},
                "nextText": {"value": "Different Next Text"},
            },
        }
        response = self.client.patch(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            FormStep.objects.filter(form_definition=self.other_form_definition).count(),
            1,
        )
        form_step = FormStep.objects.get(form_definition=self.other_form_definition)
        self.assertEqual(form_step.previous_text, "Different Previous Text")
        self.assertEqual(form_step.save_text, "Different Save Text")
        self.assertEqual(form_step.next_text, "Different Next Text")

    def test_partial_form_step_update_with_of_single_text_successful(self):
        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()
        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.step.form.uuid, "uuid": self.step.uuid},
        )
        form_detail_url = reverse(
            "api:formdefinition-detail",
            kwargs={"uuid": self.other_form_definition.uuid},
        )
        data = {
            "formDefinition": f"http://testserver{form_detail_url}",
            "literals": {
                "previousText": {"value": "Different Previous Text"},
            },
        }
        response = self.client.patch(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            FormStep.objects.filter(form_definition=self.other_form_definition).count(),
            1,
        )
        form_step = FormStep.objects.get(form_definition=self.other_form_definition)
        self.assertEqual(form_step.previous_text, "Different Previous Text")

    def test_partial_form_step_update_unsuccessful_when_form_step_not_found(self):
        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()
        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.step.form.uuid, "uuid": uuid.uuid4()},
        )
        form_detail_url = reverse(
            "api:formdefinition-detail", kwargs={"uuid": uuid.uuid4()}
        )
        data = {"formDefinition": f"http://testserver{form_detail_url}"}
        response = self.client.patch(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(
            FormStep.objects.filter(form_definition=self.other_form_definition).exists()
        )

    @patch(
        "openforms.api.exception_handling.uuid.uuid4",
        return_value="95a55a81-d316-44e8-b090-0519dd21be5f",
    )
    def test_partial_form_step_update_unsuccessful_when_form_definition_not_found(
        self, _mock
    ):
        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()
        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.step.form.uuid, "uuid": self.step.uuid},
        )
        form_detail_url = reverse(
            "api:formdefinition-detail", kwargs={"uuid": uuid.uuid4()}
        )
        data = {"formDefinition": f"http://testserver{form_detail_url}"}
        response = self.client.patch(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            FormStep.objects.filter(form_definition=self.other_form_definition).exists()
        )
        self.assertEqual(
            response.json(),
            {
                "type": "http://testserver/fouten/ValidationError/",
                "code": "invalid",
                "title": _("Invalid input."),
                "status": 400,
                "detail": "",
                "instance": "urn:uuid:95a55a81-d316-44e8-b090-0519dd21be5f",
                "invalidParams": [
                    {
                        "name": "formDefinition",
                        "code": "does_not_exist",
                        "reason": _("Invalid hyperlink - Object does not exist."),
                    }
                ],
            },
        )

    def test_partial_form_step_update_unsuccessful_without_authorization(self):
        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.step.form.uuid, "uuid": self.step.uuid},
        )
        form_detail_url = reverse(
            "api:formdefinition-detail", kwargs={"uuid": self.step.form_definition.uuid}
        )
        data = {"formDefinition": f"http://testserver{form_detail_url}"}
        response = self.client.patch(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            FormStep.objects.filter(form_definition=self.other_form_definition).exists()
        )

    def test_delete_form_step_successful(self):
        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()
        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.step.form.uuid, "uuid": self.step.uuid},
        )
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(FormStep.objects.exists())

    def test_delete_form_step_unsuccessful_when_form_not_found(self):
        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()
        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.step.form.uuid, "uuid": uuid.uuid4()},
        )
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(FormStep.objects.count(), 1)

    def test_delete_form_step_unsuccessful_when_not_authorized(self):
        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.step.form.uuid, "uuid": self.step.uuid},
        )
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(FormStep.objects.count(), 1)

    def test_form_delete(self):
        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()
        token = TokenFactory(user=self.user)

        form = FormFactory.create()
        submission = SubmissionFactory.create(form=form)

        response = self.client.delete(
            reverse("api:form-detail", kwargs={"uuid_or_slug": form.uuid}),
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        form.refresh_from_db()
        self.assertTrue(form._is_deleted)

        response_retrieve = self.client.get(
            reverse("api:form-detail", kwargs={"uuid_or_slug": form.uuid}),
        )
        response_list = self.client.get(reverse("api:form-list"))

        # The form is still visible for staff users from the retrieve endpoint but not from the list endpoint
        self.assertEqual(response_retrieve.status_code, status.HTTP_200_OK)
        self.assertEqual(response_list.status_code, status.HTTP_200_OK)

        forms = response_list.json()
        for item in forms:
            self.assertNotEqual(form.uuid, item["uuid"])

        form.refresh_from_db()
        self.assertTrue(form._is_deleted)

        # Submission still exists
        submission.refresh_from_db()
        self.assertEqual(submission.form, form)

    def test_form_delete_staff_required(self):
        token = TokenFactory(user=self.user)

        form = FormFactory.create()

        response = self.client.delete(
            reverse("api:form-detail", kwargs={"uuid_or_slug": form.uuid}),
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        form.refresh_from_db()
        self.assertFalse(form._is_deleted)

        response = self.client.get(
            reverse("api:form-detail", kwargs={"uuid_or_slug": form.uuid}),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_form_delete_token_required(self):
        form = FormFactory.create()

        response = self.client.delete(
            reverse("api:form-detail", kwargs={"uuid_or_slug": form.uuid}),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        form.refresh_from_db()
        self.assertFalse(form._is_deleted)

        response = self.client.get(
            reverse("api:form-detail", kwargs={"uuid_or_slug": form.uuid}),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @override_settings(LANGUAGE_CODE="en")
    def test_create_duplicate_keys_in_different_form_steps(self):
        form_definition1 = FormDefinitionFactory.create(
            name="Form Def 1",
            configuration={
                "components": [
                    {"key": "duplicate", "label": "Duplicate", "type": "textfield"}
                ]
            },
        )
        form_definition2 = FormDefinitionFactory.create(
            name="Form Def 2",
            configuration={
                "components": [
                    {
                        "key": "repeatingGroup",
                        "label": "Repeating Group",
                        "type": "editgrid",
                        "components": [
                            {
                                "key": "duplicate",
                                "label": "Duplicate",
                                "type": "textfield",
                            },
                            {
                                "key": "notDuplicate",
                                "label": "Not Duplicate",
                                "type": "textfield",
                            },
                        ],
                    }
                ]
            },
        )
        form = FormFactory.create()
        FormStepFactory.create(form=form, form_definition=form_definition1)

        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()

        form_definition2_url = reverse(
            "api:formdefinition-detail",
            kwargs={"uuid": form_definition2.uuid},
        )
        data = {
            "formDefinition": f"http://testserver{form_definition2_url}",
            "index": 1,
        }

        response = self.client.post(
            reverse("api:form-steps-list", kwargs={"form_uuid_or_slug": form.uuid}),
            data=data,
        )

        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)

        data = response.json()

        self.assertEqual(
            data["invalidParams"][0]["reason"],
            'Detected duplicate keys in configuration: "duplicate" (in '
            "Form Def 2 > Repeating Group > Duplicate, Form Def 1 > Duplicate)",
        )

    @override_settings(LANGUAGE_CODE="en")
    def test_update_duplicate_keys_in_different_form_steps(self):
        form_definition1 = FormDefinitionFactory.create(
            name="Form Def 1",
            configuration={
                "components": [
                    {"key": "duplicate", "label": "Duplicate", "type": "textfield"}
                ]
            },
        )
        form_definition2 = FormDefinitionFactory.create(
            name="Form Def 2",
            configuration={
                "components": [
                    {
                        "key": "repeatingGroup",
                        "label": "Repeating Group",
                        "type": "editgrid",
                        "components": [
                            {
                                "key": "duplicate",
                                "label": "Duplicate",
                                "type": "textfield",
                            },
                            {
                                "key": "notDuplicate",
                                "label": "Not Duplicate",
                                "type": "textfield",
                            },
                        ],
                    }
                ]
            },
        )
        form = FormFactory.create()
        FormStepFactory.create(form=form, form_definition=form_definition1)
        form_step2 = FormStepFactory.create(form=form, form_definition=form_definition2)

        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()

        form_definition2_url = reverse(
            "api:formdefinition-detail",
            kwargs={"uuid": form_definition2.uuid},
        )
        data = {
            "formDefinition": f"http://testserver{form_definition2_url}",
            "index": 1,
        }

        response = self.client.put(
            reverse(
                "api:form-steps-detail",
                kwargs={"form_uuid_or_slug": form.uuid, "uuid": form_step2.uuid},
            ),
            data=data,
        )

        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)

        data = response.json()

        self.assertEqual(
            data["invalidParams"][0]["reason"],
            'Detected duplicate keys in configuration: "duplicate" (in '
            "Form Def 2 > Repeating Group > Duplicate, Form Def 1 > Duplicate)",
        )

    def test_duplicate_keys_all_in_other_steps(self):
        form_definition1 = FormDefinitionFactory.create(
            name="Form Def 1",
            configuration={
                "components": [
                    {"key": "duplicate", "label": "Duplicate", "type": "textfield"}
                ]
            },
        )
        form_definition2 = FormDefinitionFactory.create(
            name="Form Def 2",
            configuration={
                "components": [
                    {
                        "key": "repeatingGroup",
                        "label": "Repeating Group",
                        "type": "editgrid",
                        "components": [
                            {
                                "key": "duplicate",
                                "label": "Duplicate",
                                "type": "textfield",
                            },
                        ],
                    }
                ]
            },
        )
        form_definition3 = FormDefinitionFactory.create(
            name="Form Def 3",
            configuration={
                "components": [
                    {
                        "key": "notDuplicate",
                        "label": "Not Duplicate",
                        "type": "textfield",
                    }
                ]
            },
        )
        form = FormFactory.create()
        FormStepFactory.create(form=form, form_definition=form_definition1)
        FormStepFactory.create(form=form, form_definition=form_definition2)

        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()

        form_definition2_url = reverse(
            "api:formdefinition-detail",
            kwargs={"uuid": form_definition3.uuid},
        )
        data = {
            "formDefinition": f"http://testserver{form_definition2_url}",
            "index": 1,
        }

        response = self.client.post(
            reverse("api:form-steps-list", kwargs={"form_uuid_or_slug": form.uuid}),
            data=data,
        )

        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

    @tag("gh-2017")
    def test_deprecated_form_definition_slug(self):
        """
        Assert that the form definition slug is still functional.

        Open Forms 2.3.0 deprecates the slug on the form definition in favour of the
        slug on the form step. However, to stay backwards compatible, if no or an
        empty form step slug is provided, the step should take the slug from the
        form definition.
        """
        assign_change_form_permissions(self.user)
        form = FormFactory.create()
        fd_with_slug = FormDefinitionFactory.create(slug="fd-with-slug")
        url = reverse("api:form-steps-list", kwargs={"form_uuid_or_slug": form.uuid})
        fd_url = reverse(
            "api:formdefinition-detail", kwargs={"uuid": fd_with_slug.uuid}
        )
        data = {"formDefinition": f"http://testserver{fd_url}", "index": 0}

        response = self.client.post(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        form_step = FormStep.objects.get(form=form)
        self.assertEqual(form_step.slug, "fd-with-slug")

    @tag("gh-2017")
    def test_with_non_unique_fd_slugs(self):
        # when inferring the form step slug from the form definition, these slugs
        # must still be unique for the same form.
        assign_change_form_permissions(self.user)
        form = FormFactory.create()
        url = reverse("api:form-steps-list", kwargs={"form_uuid_or_slug": form.uuid})
        fd_with_slug, fd_with_identical_slug = FormDefinitionFactory.create_batch(
            2, slug="duplicated-slug"
        )

        for fd in fd_with_slug, fd_with_identical_slug:
            fd_url = reverse("api:formdefinition-detail", kwargs={"uuid": fd.uuid})
            data = {"formDefinition": f"http://testserver{fd_url}", "index": 0}
            response = self.client.post(url, data=data)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        form_steps = FormStep.objects.filter(form=form)
        self.assertEqual(len(form_steps), 2)
        slugs = {form_step.slug for form_step in form_steps}
        self.assertEqual(len(slugs), 2)  # we expect two unique slugs


class FormStepsAPITranslationTests(APITestCase):
    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.form = FormFactory.create()

        cls.form_definition = FormDefinitionFactory.create()

        TranslatedFormStepFactory = make_translated(FormStepFactory)
        cls.form_step = TranslatedFormStepFactory.create(
            _language="en",
            form_definition__name="FormDef 001",
            form=cls.form,
            next_text="Next",
            previous_text="Previous",
            save_text="Save",
        )

        cls.user = StaffUserFactory.create(user_permissions=["change_form"])

    def test_detail_staff_show_translations(self):
        """
        Translations for all available languages should be returned for staff users, because they are relevant for the form design UI
        """
        self.client.force_authenticate(user=self.user)

        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.form.uuid, "uuid": self.form_step.uuid},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["translations"],
            {
                "en": {
                    "next_text": "Next",
                    "previous_text": "Previous",
                    "save_text": "Save",
                },
                "nl": {
                    "next_text": "",
                    "previous_text": "",
                    "save_text": "",
                },
            },
        )

    def test_detail_non_staff_no_translations(self):
        """
        Translations for different languages than the active language should not be returned for non-staff users
        """
        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.form.uuid, "uuid": self.form_step.uuid},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("translations", response.data)

    def test_create_with_translations(self):
        self.client.force_authenticate(user=self.user)

        url = reverse(
            "api:form-steps-list", kwargs={"form_uuid_or_slug": self.form.uuid}
        )
        form_detail_url = reverse(
            "api:formdefinition-detail",
            kwargs={"uuid": self.form_definition.uuid},
        )
        data = {
            "formDefinition": f"http://testserver{form_detail_url}",
            "index": 0,
            # ignored
            "literals": {
                "previousText": {"value": "Different Previous Text"},
                "saveText": {"value": "Different Save Text"},
                "nextText": {"value": "Different Next Text"},
            },
            "translations": {
                "nl": {
                    "next_text": "Volgende",
                    "previous_text": "Vorige",
                    "save_text": "Opslaan",
                },
                "en": {
                    "next_text": "Next",
                    "previous_text": "Previous",
                    "save_text": "Save",
                },
            },
        }

        response = self.client.post(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        qs = FormStep.objects.filter(form_definition=self.form_definition)
        self.assertEqual(qs.count(), 1)

        form_step = qs.get()

        self.assertEqual(form_step.previous_text_en, "Previous")
        self.assertEqual(form_step.save_text_en, "Save")
        self.assertEqual(form_step.next_text_en, "Next")

        self.assertEqual(form_step.previous_text_nl, "Vorige")
        self.assertEqual(form_step.save_text_nl, "Opslaan")
        self.assertEqual(form_step.next_text_nl, "Volgende")

    def test_update_with_translations(self):
        self.client.force_authenticate(user=self.user)

        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.form.uuid, "uuid": self.form_step.uuid},
        )
        response = self.client.patch(
            url,
            data={
                # ignored
                "literals": {
                    "previousText": {"value": "Different Previous Text"},
                    "saveText": {"value": "Different Save Text"},
                    "nextText": {"value": "Different Next Text"},
                },
                "translations": {
                    "nl": {
                        "name": "Dutch",
                        "next_text": "Volgende",
                        "previous_text": "Vorige",
                        "save_text": "Opslaan",
                    },
                    "en": {
                        "name": "English",
                        "next_text": "Next",
                        "previous_text": "Previous",
                        "save_text": "Save",
                    },
                },
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.form_step.refresh_from_db()

        self.assertEqual(self.form_step.previous_text_en, "Previous")
        self.assertEqual(self.form_step.save_text_en, "Save")
        self.assertEqual(self.form_step.next_text_en, "Next")

        self.assertEqual(self.form_step.previous_text_nl, "Vorige")
        self.assertEqual(self.form_step.save_text_nl, "Opslaan")
        self.assertEqual(self.form_step.next_text_nl, "Volgende")

        # The FormDefinition translations on this endpoint are read only
        self.assertEqual(self.form_step.form_definition.name_en, None)
        self.assertEqual(self.form_step.form_definition.name_nl, "FormDef 001")

    @patch(
        "openforms.api.exception_handling.uuid.uuid4",
        return_value="95a55a81-d316-44e8-b090-0519dd21be5f",
    )
    def test_update_with_translations_validate_literals(self, _mock):
        self.client.force_authenticate(user=self.user)

        url = reverse(
            "api:form-steps-detail",
            kwargs={"form_uuid_or_slug": self.form.uuid, "uuid": self.form_step.uuid},
        )
        response = self.client.patch(
            url,
            data={
                "literals": {
                    "previousText": {"value": "Different Previous Text"},
                    "saveText": {"value": "Different Save Text"},
                    "nextText": {"value": "Different Next Text"},
                },
                "translations": {
                    "en": {
                        "nextText": {"value": "Next"},
                        "previousText": {"value": "Previous"},
                        "saveText": {"value": "Save"},
                    },
                    "nl": {
                        "nextText": {"value": "Volgende"},
                        "previousText": {"value": "Vorige"},
                        "saveText": {"value": "Opslaan"},
                    },
                },
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_params = response.json()["invalidParams"]
        expected = [
            {
                "name": "translations.nl.previousText",
                "code": "invalid",
                "reason": _("Not a valid string."),
            },
            {
                "name": "translations.nl.saveText",
                "code": "invalid",
                "reason": _("Not a valid string."),
            },
            {
                "name": "translations.nl.nextText",
                "code": "invalid",
                "reason": _("Not a valid string."),
            },
            {
                "name": "translations.en.previousText",
                "code": "invalid",
                "reason": _("Not a valid string."),
            },
            {
                "name": "translations.en.saveText",
                "code": "invalid",
                "reason": _("Not a valid string."),
            },
            {
                "name": "translations.en.nextText",
                "code": "invalid",
                "reason": _("Not a valid string."),
            },
        ]
        for error in expected:
            with self.subTest(field=error["name"], code=error["code"]):
                self.assertIn(error, invalid_params)


class FormStepsAPIApplicabilityTests(APITestCase):
    def setUp(self):
        super().setUp()

        self.user = UserFactory.create()
        self.form = FormFactory.create()
        self.form_definition = FormDefinitionFactory.create()
        self.client.force_authenticate(user=self.user)

    def test_create_form_step_not_applicable_as_first_unsucessful(self):
        self.user.user_permissions.add(Permission.objects.get(codename="change_form"))
        self.user.is_staff = True
        self.user.save()
        url = reverse(
            "api:form-steps-list", kwargs={"form_uuid_or_slug": self.form.uuid}
        )

        form_detail_url = reverse(
            "api:formdefinition-detail",
            kwargs={"uuid": self.form_definition.uuid},
        )
        data = {
            "formDefinition": f"http://testserver{form_detail_url}",
            "index": 0,
            "isApplicable": False,
        }
        response = self.client.post(url, data=data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()["invalidParams"][0],
            {
                "name": "isApplicable",
                "code": "invalid",
                "reason": "First form step must be applicable.",
            },
        )
