from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings, tag
from django.utils.translation import gettext_lazy as _

from privates.test import temp_private_root
from testfixtures import LogCapture

from openforms.appointments.exceptions import AppointmentRegistrationFailed
from openforms.appointments.tests.utils import setup_jcc
from openforms.authentication.constants import AuthAttribute
from openforms.config.models import GlobalConfiguration
from openforms.emails.tests.factories import ConfirmationEmailTemplateFactory
from openforms.forms.tests.factories import FormDefinitionFactory
from openforms.payments.constants import PaymentStatus
from openforms.payments.tests.factories import SubmissionPaymentFactory

from ..constants import PostSubmissionEvents
from ..models import SubmissionReport
from ..public_references import get_random_reference
from ..tasks import on_post_submission_event
from .factories import SubmissionFactory


@temp_private_root()
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, LANGUAGE_CODE="en")
class TaskOrchestrationPostSubmissionEventTests(TestCase):
    def test_submission_completed_cosign_and_payment_not_needed(self):
        # The registration should happen since we are not waiting on payment/cosign
        submission = SubmissionFactory.from_components(
            components_list=[
                {
                    "key": "email",
                    "type": "email",
                    "label": "Email",
                    "confirmationRecipient": True,
                }
            ],
            form__name="Pretty Form",
            submitted_data={"email": "test@test.nl"},
            completed_not_preregistered=True,
            cosign_complete=False,
            confirmation_email_sent=False,
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            auth_info__attribute=AuthAttribute.bsn,
            auth_info__value="111222333",
            language_code="en",
        )
        ConfirmationEmailTemplateFactory.create(
            form=submission.form,
            subject="Confirmation of your {{ form_name }} submission",
            content="Custom content {% appointment_information %} {% payment_information %} {% cosign_information %}",
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ) as mock_registration,
            patch(
                "openforms.submissions.public_references.get_reference_for_submission",
                return_value="OF-TEST!",
            ),
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.update_payment_status"
            ) as mock_payment_status_update,
        ):
            on_post_submission_event(submission.id, PostSubmissionEvents.on_completion)

        submission.refresh_from_db()

        self.assertEqual(submission.public_registration_reference, "OF-TEST!")
        self.assertTrue(SubmissionReport.objects.filter(submission=submission).exists())
        mock_registration.assert_called()
        mock_payment_status_update.assert_not_called()

        mails = mail.outbox

        self.assertEqual(1, len(mails))  # Confirmation email (registration is mocked)
        self.assertEqual(
            mails[0].subject, "Confirmation of your Pretty Form submission"
        )
        self.assertEqual(mails[0].to, ["test@test.nl"])
        self.assertEqual(mails[0].cc, [])

        submission.refresh_from_db()

        self.assertTrue(submission.confirmation_email_sent)
        self.assertFalse(submission.cosign_request_email_sent)
        self.assertNotEqual(submission.auth_info.value, "111222333")

    def test_submission_completed_cosign_needed(self):
        # The registration should not happen since we are waiting on cosign
        submission = SubmissionFactory.from_components(
            components_list=[
                {
                    "key": "email",
                    "type": "email",
                    "label": "Email",
                    "confirmationRecipient": True,
                },
                {
                    "key": "cosign",
                    "type": "cosign",
                    "label": "Cosign component",
                    "validate": {"required": True},
                },
            ],
            submitted_data={"email": "test@test.nl", "cosign": "cosign@test.nl"},
            completed_not_preregistered=True,
            cosign_complete=False,
            cosign_request_email_sent=False,
            confirmation_email_sent=False,
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            form__name="Pretty Form",
            auth_info__attribute=AuthAttribute.bsn,
            auth_info__value="111222333",
            language_code="en",
        )
        ConfirmationEmailTemplateFactory.create(
            form=submission.form,
            subject="Confirmation of your {{ form_name }} submission",
            content="Custom content {% appointment_information %} {% payment_information %} {% cosign_information %}",
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ) as mock_registration,
            patch(
                "openforms.submissions.public_references.get_reference_for_submission",
                return_value="OF-TEST!",
            ),
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.update_payment_status"
            ) as mock_payment_status_update,
        ):
            on_post_submission_event(submission.id, PostSubmissionEvents.on_completion)

        submission.refresh_from_db()

        self.assertEqual(submission.public_registration_reference, "OF-TEST!")
        self.assertTrue(SubmissionReport.objects.filter(submission=submission).exists())
        mock_registration.assert_not_called()
        mock_payment_status_update.assert_not_called()

        mails = mail.outbox

        self.assertEqual(2, len(mails))
        self.assertEqual(
            mails[0].subject,
            "Co-sign request for {form_name}".format(form_name="Pretty Form"),
        )
        self.assertEqual(mails[0].to, ["cosign@test.nl"])
        self.assertEqual(
            mails[1].subject, "Confirmation of your Pretty Form submission"
        )
        self.assertEqual(mails[1].to, ["test@test.nl"])
        self.assertEqual(mails[1].cc, [])

        cosign_info = "This form will not be processed until it has been co-signed. A co-sign request was sent to cosign@test.nl."

        self.assertIn(cosign_info, mails[1].body.strip("\n"))

        submission.refresh_from_db()

        self.assertTrue(submission.cosign_request_email_sent)
        self.assertTrue(submission.confirmation_email_sent)
        self.assertEqual(submission.auth_info.value, "111222333")

    def test_submission_completed_payment_needed(self):
        # The registration should happen (old payment flow!)
        submission = SubmissionFactory.from_components(
            components_list=[
                {
                    "key": "email",
                    "type": "email",
                    "label": "Email",
                    "confirmationRecipient": True,
                },
            ],
            submitted_data={"email": "test@test.nl"},
            completed_not_preregistered=True,
            cosign_complete=False,
            confirmation_email_sent=False,
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            form__name="Pretty Form",
            form__product__price=10,
            form__payment_backend="demo",
            auth_info__attribute=AuthAttribute.bsn,
            auth_info__value="111222333",
            language_code="en",
        )
        ConfirmationEmailTemplateFactory.create(
            form=submission.form,
            subject="Confirmation of your {{ form_name }} submission",
            content="Custom content {% appointment_information %} {% payment_information %} {% cosign_information %}",
        )
        SubmissionPaymentFactory.create(
            submission=submission, amount=10, status=PaymentStatus.started
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ) as mock_registration,
            patch(
                "openforms.submissions.public_references.get_reference_for_submission",
                return_value="OF-TEST!",
            ),
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.update_payment_status"
            ) as mock_payment_status_update,
            patch(
                "openforms.registrations.tasks.GlobalConfiguration.get_solo",
                return_value=GlobalConfiguration(wait_for_payment_to_register=False),
            ),
        ):
            on_post_submission_event(submission.id, PostSubmissionEvents.on_completion)

        submission.refresh_from_db()

        self.assertEqual(submission.public_registration_reference, "OF-TEST!")
        self.assertTrue(SubmissionReport.objects.filter(submission=submission).exists())
        mock_registration.assert_called()
        mock_payment_status_update.assert_not_called()

        mails = mail.outbox

        self.assertEqual(1, len(mails))
        self.assertEqual(
            mails[0].subject, "Confirmation of your Pretty Form submission"
        )
        self.assertEqual(mails[0].to, ["test@test.nl"])
        self.assertEqual(mails[0].cc, [])

        payment_info = (
            "Payment of EUR 10.00 is required. You can pay using the link below."
        )

        self.assertIn(payment_info, mails[0].body.strip("\n"))

        submission.refresh_from_db()

        self.assertTrue(submission.confirmation_email_sent)
        self.assertFalse(submission.cosign_request_email_sent)
        self.assertNotEqual(submission.auth_info.value, "111222333")

    def test_submission_completed_payment_and_cosign_needed(self):
        submission = SubmissionFactory.from_components(
            components_list=[
                {
                    "key": "email",
                    "type": "email",
                    "label": "Email",
                    "confirmationRecipient": True,
                },
                {
                    "key": "cosign",
                    "type": "cosign",
                    "label": "Cosign component",
                    "validate": {"required": True},
                },
            ],
            submitted_data={"email": "test@test.nl", "cosign": "cosign@test.nl"},
            completed_not_preregistered=True,
            cosign_complete=False,
            cosign_request_email_sent=False,
            confirmation_email_sent=False,
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            form__product__price=10,
            form__payment_backend="demo",
            form__name="Pretty Form",
            auth_info__attribute=AuthAttribute.bsn,
            auth_info__value="111222333",
            language_code="en",
        )
        ConfirmationEmailTemplateFactory.create(
            form=submission.form,
            subject="Confirmation of your {{ form_name }} submission",
            content="Custom content {% appointment_information %} {% payment_information %} {% cosign_information %}",
        )
        SubmissionPaymentFactory.create(
            submission=submission, amount=10, status=PaymentStatus.started
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ) as mock_registration,
            patch(
                "openforms.submissions.public_references.get_reference_for_submission",
                return_value="OF-TEST!",
            ),
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.update_payment_status"
            ) as mock_payment_status_update,
        ):
            on_post_submission_event(submission.id, PostSubmissionEvents.on_completion)

        submission.refresh_from_db()

        self.assertEqual(submission.public_registration_reference, "OF-TEST!")
        self.assertTrue(SubmissionReport.objects.filter(submission=submission).exists())
        mock_registration.assert_not_called()
        mock_payment_status_update.assert_not_called()

        mails = mail.outbox

        self.assertEqual(2, len(mails))
        self.assertEqual(
            mails[0].subject,
            _("Co-sign request for {form_name}").format(form_name="Pretty Form"),
        )
        self.assertEqual(mails[0].to, ["cosign@test.nl"])
        self.assertEqual(
            mails[1].subject, "Confirmation of your Pretty Form submission"
        )
        self.assertEqual(mails[1].to, ["test@test.nl"])
        self.assertEqual(mails[1].cc, [])

        cosign_info = "This form will not be processed until it has been co-signed. A co-sign request was sent to cosign@test.nl."
        payment_info = (
            "Payment of EUR 10.00 is required. You can pay using the link below."
        )

        self.assertIn(cosign_info, mails[1].body.strip("\n"))
        self.assertIn(payment_info, mails[1].body.strip("\n"))

        submission.refresh_from_db()

        self.assertTrue(submission.cosign_request_email_sent)
        self.assertTrue(submission.confirmation_email_sent)
        self.assertEqual(submission.auth_info.value, "111222333")

    def test_cosign_done_payment_not_needed(self):
        submission = SubmissionFactory.from_components(
            components_list=[
                {
                    "key": "email",
                    "type": "email",
                    "label": "Email",
                    "confirmationRecipient": True,
                },
                {
                    "key": "cosign",
                    "type": "cosign",
                    "label": "Cosign component",
                    "validate": {"required": True},
                },
            ],
            submitted_data={"email": "test@test.nl", "cosign": "cosign@test.nl"},
            completed=True,
            cosign_request_email_sent=True,
            cosign_complete=True,
            confirmation_email_sent=True,
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            form__name="Pretty Form",
            auth_info__attribute=AuthAttribute.bsn,
            auth_info__value="111222333",
            language_code="en",
        )
        ConfirmationEmailTemplateFactory.create(
            form=submission.form,
            subject="Confirmation of your {{ form_name }} submission",
            content="Custom content {% appointment_information %} {% payment_information %} {% cosign_information %}",
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ) as mock_registration,
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.update_payment_status"
            ) as mock_payment_status_update,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                on_post_submission_event(
                    submission.id, PostSubmissionEvents.on_completion
                )

        submission.refresh_from_db()

        self.assertTrue(SubmissionReport.objects.filter(submission=submission).exists())
        mock_registration.assert_called()
        mock_payment_status_update.assert_not_called()

        mails = mail.outbox

        self.assertEqual(1, len(mails))
        self.assertEqual(
            mails[0].subject, "Confirmation of your Pretty Form submission"
        )
        self.assertEqual(mails[0].to, ["test@test.nl"])
        self.assertEqual(mails[0].cc, ["cosign@test.nl"])

        cosign_info = "This email is a confirmation that this form has been co-signed by cosign@test.nl and can now be processed."

        self.assertIn(cosign_info, mails[0].body.strip("\n"))

        submission.refresh_from_db()

        self.assertTrue(submission.cosign_confirmation_email_sent)
        self.assertNotEqual(submission.auth_info.value, "111222333")

    def test_cosign_done_payment_needed_not_done(self):
        submission = SubmissionFactory.from_components(
            components_list=[
                {
                    "key": "email",
                    "type": "email",
                    "label": "Email",
                    "confirmationRecipient": True,
                },
                {
                    "key": "cosign",
                    "type": "cosign",
                    "label": "Cosign component",
                    "validate": {"required": True},
                },
            ],
            submitted_data={"email": "test@test.nl", "cosign": "cosign@test.nl"},
            completed=True,
            cosign_request_email_sent=True,
            cosign_complete=True,
            confirmation_email_sent=True,
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            form__name="Pretty Form",
            auth_info__attribute=AuthAttribute.bsn,
            auth_info__value="111222333",
            form__product__price=10,
            form__payment_backend="demo",
            language_code="en",
        )
        SubmissionPaymentFactory.create(
            submission=submission, amount=10, status=PaymentStatus.started
        )
        ConfirmationEmailTemplateFactory.create(
            form=submission.form,
            subject="Confirmation of your {{ form_name }} submission",
            content="Custom content {% appointment_information %} {% payment_information %} {% cosign_information %}",
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ) as mock_registration,
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.update_payment_status"
            ) as mock_payment_status_update,
            patch(
                "openforms.registrations.tasks.GlobalConfiguration.get_solo",
                return_value=GlobalConfiguration(wait_for_payment_to_register=False),
            ),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                on_post_submission_event(
                    submission.id, PostSubmissionEvents.on_completion
                )

        submission.refresh_from_db()

        self.assertTrue(SubmissionReport.objects.filter(submission=submission).exists())
        mock_registration.assert_called()
        mock_payment_status_update.assert_not_called()

        mails = mail.outbox

        self.assertEqual(1, len(mails))
        self.assertEqual(
            mails[0].subject, "Confirmation of your Pretty Form submission"
        )
        self.assertEqual(mails[0].to, ["test@test.nl"])
        self.assertEqual(mails[0].cc, ["cosign@test.nl"])

        cosign_info = "This email is a confirmation that this form has been co-signed by cosign@test.nl and can now be processed."
        payment_info = (
            "Payment of EUR 10.00 is required. You can pay using the link below."
        )

        self.assertIn(cosign_info, mails[0].body.strip("\n"))
        self.assertIn(payment_info, mails[0].body.strip("\n"))

        submission.refresh_from_db()

        self.assertTrue(submission.cosign_confirmation_email_sent)
        self.assertFalse(submission.payment_complete_confirmation_email_sent)
        self.assertNotEqual(submission.auth_info.value, "111222333")

    def test_cosign_done_payment_done(self):
        submission = SubmissionFactory.from_components(
            components_list=[
                {
                    "key": "email",
                    "type": "email",
                    "label": "Email",
                    "confirmationRecipient": True,
                },
                {
                    "key": "cosign",
                    "type": "cosign",
                    "label": "Cosign component",
                    "validate": {"required": True},
                },
            ],
            submitted_data={"email": "test@test.nl", "cosign": "cosign@test.nl"},
            completed=True,
            cosign_request_email_sent=True,
            cosign_complete=True,
            confirmation_email_sent=True,
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            form__name="Pretty Form",
            auth_info__attribute=AuthAttribute.bsn,
            auth_info__value="111222333",
            form__product__price=10,
            form__payment_backend="demo",
            language_code="en",
        )
        SubmissionPaymentFactory.create(
            submission=submission, amount=10, status=PaymentStatus.registered
        )
        ConfirmationEmailTemplateFactory.create(
            form=submission.form,
            subject="Confirmation of your {{ form_name }} submission",
            content="Custom content {% appointment_information %} {% payment_information %} {% cosign_information %}",
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ) as mock_registration,
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.update_payment_status"
            ) as mock_payment_status_update,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                on_post_submission_event(
                    submission.id, PostSubmissionEvents.on_completion
                )

        submission.refresh_from_db()

        self.assertTrue(SubmissionReport.objects.filter(submission=submission).exists())
        mock_registration.assert_called()
        mock_payment_status_update.assert_not_called()

        mails = mail.outbox

        self.assertEqual(1, len(mails))
        self.assertEqual(
            mails[0].subject, "Confirmation of your Pretty Form submission"
        )
        self.assertEqual(mails[0].to, ["test@test.nl"])
        self.assertEqual(mails[0].cc, ["cosign@test.nl"])

        cosign_info = "This email is a confirmation that this form has been co-signed by cosign@test.nl and can now be processed."
        payment_info = (
            "Payment of EUR 10.00 is required. You can pay using the link below."
        )

        self.assertIn(cosign_info, mails[0].body.strip("\n"))
        self.assertNotIn(payment_info, mails[0].body.strip("\n"))

        submission.refresh_from_db()

        self.assertTrue(submission.cosign_confirmation_email_sent)
        self.assertTrue(submission.payment_complete_confirmation_email_sent)
        self.assertNotEqual(submission.auth_info.value, "111222333")

    def test_payment_done_cosign_not_needed(self):
        submission = SubmissionFactory.from_components(
            components_list=[
                {
                    "key": "email",
                    "type": "email",
                    "label": "Email",
                    "confirmationRecipient": True,
                },
            ],
            submitted_data={"email": "test@test.nl"},
            completed=True,
            confirmation_email_sent=True,
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            form__name="Pretty Form",
            auth_info__attribute=AuthAttribute.bsn,
            auth_info__value="111222333",
            language_code="en",
            with_completed_payment=True,
        )
        ConfirmationEmailTemplateFactory.create(
            form=submission.form,
            subject="Confirmation of your {{ form_name }} submission",
            content="Custom content {% appointment_information %} {% payment_information %} {% cosign_information %}",
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ) as mock_registration,
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.update_payment_status"
            ) as mock_payment_status_update,
            patch(
                "openforms.registrations.tasks.GlobalConfiguration.get_solo",
                return_value=GlobalConfiguration(wait_for_payment_to_register=False),
            ),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                on_post_submission_event(
                    submission.id, PostSubmissionEvents.on_completion
                )

        submission.refresh_from_db()

        self.assertTrue(SubmissionReport.objects.filter(submission=submission).exists())
        mock_registration.assert_called()
        mock_payment_status_update.assert_called()

        mails = mail.outbox

        self.assertEqual(1, len(mails))
        self.assertEqual(
            mails[0].subject, "Confirmation of your Pretty Form submission"
        )
        self.assertEqual(mails[0].to, ["test@test.nl"])
        self.assertEqual(mails[0].cc, [])

        cosign_info = "This email is a confirmation that this form has been co-signed by cosign@test.nl and can now be processed."
        payment_info = (
            "Payment of EUR 10.00 is required. You can pay using the link below."
        )

        self.assertNotIn(cosign_info, mails[0].body.strip("\n"))
        self.assertNotIn(payment_info, mails[0].body.strip("\n"))

        submission.refresh_from_db()

        self.assertFalse(submission.cosign_confirmation_email_sent)
        self.assertTrue(submission.payment_complete_confirmation_email_sent)
        self.assertNotEqual(submission.auth_info.value, "111222333")

    def test_payment_done_cosign_needed_not_done(self):
        submission = SubmissionFactory.from_components(
            components_list=[
                {
                    "key": "email",
                    "type": "email",
                    "label": "Email",
                    "confirmationRecipient": True,
                },
                {
                    "key": "cosign",
                    "type": "cosign",
                    "label": "Cosign component",
                    "validate": {"required": True},
                },
            ],
            submitted_data={"email": "test@test.nl", "cosign": "cosign@test.nl"},
            completed=True,
            cosign_request_email_sent=True,
            cosign_complete=False,
            cosign_confirmation_email_sent=False,
            confirmation_email_sent=True,
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            form__name="Pretty Form",
            auth_info__attribute=AuthAttribute.bsn,
            auth_info__value="111222333",
            language_code="en",
            with_completed_payment=True,
        )
        ConfirmationEmailTemplateFactory.create(
            form=submission.form,
            subject="Confirmation of your {{ form_name }} submission",
            content="Custom content {% appointment_information %} {% payment_information %} {% cosign_information %}",
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ) as mock_registration,
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.update_payment_status"
            ) as mock_payment_status_update,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                on_post_submission_event(
                    submission.id, PostSubmissionEvents.on_completion
                )

        submission.refresh_from_db()

        self.assertTrue(SubmissionReport.objects.filter(submission=submission).exists())
        mock_registration.assert_not_called()
        mock_payment_status_update.assert_not_called()

        mails = mail.outbox

        self.assertEqual(1, len(mails))
        self.assertEqual(
            mails[0].subject, "Confirmation of your Pretty Form submission"
        )
        self.assertEqual(mails[0].to, ["test@test.nl"])
        self.assertEqual(mails[0].cc, [])

        cosign_info = "This email is a confirmation that this form has been co-signed by cosign@test.nl and can now be processed."
        payment_info = (
            "Payment of EUR 10.00 is required. You can pay using the link below."
        )

        self.assertNotIn(cosign_info, mails[0].body.strip("\n"))
        self.assertNotIn(payment_info, mails[0].body.strip("\n"))

        submission.refresh_from_db()

        self.assertFalse(submission.cosign_confirmation_email_sent)
        self.assertTrue(submission.payment_complete_confirmation_email_sent)
        self.assertEqual(submission.auth_info.value, "111222333")

    def test_retry_flow(self):
        submission = SubmissionFactory.from_components(
            components_list=[
                {
                    "key": "email",
                    "type": "email",
                    "label": "Email",
                    "confirmationRecipient": True,
                },
                {
                    "key": "cosign",
                    "type": "cosign",
                    "label": "Cosign component",
                    "validate": {"required": True},
                },
            ],
            submitted_data={"email": "test@test.nl", "cosign": "cosign@test.nl"},
            cosign_request_email_sent=True,
            cosign_complete=True,
            cosign_confirmation_email_sent=True,
            payment_complete_confirmation_email_sent=True,
            confirmation_email_sent=True,
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            form__name="Pretty Form",
            auth_info__attribute=AuthAttribute.bsn,
            auth_info__value="111222333",
            needs_on_completion_retry=True,
            registration_failed=True,
            with_completed_payment=True,
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ) as mock_registration,
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.update_payment_status"
            ) as mock_payment_status_update,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                on_post_submission_event(
                    submission.id, PostSubmissionEvents.on_completion
                )

        submission.refresh_from_db()

        mock_registration.assert_called()
        mock_payment_status_update.assert_called()

        mails = mail.outbox

        self.assertEqual(len(mails), 0)
        self.assertNotEqual(submission.auth_info.value, "111222333")

    def test_payment_status_update_retry_flow(self):
        submission = SubmissionFactory.from_components(
            components_list=[
                {
                    "key": "email",
                    "type": "email",
                    "label": "Email",
                    "confirmationRecipient": True,
                },
                {
                    "key": "cosign",
                    "type": "cosign",
                    "label": "Cosign component",
                    "validate": {"required": True},
                },
            ],
            submitted_data={"email": "test@test.nl", "cosign": "cosign@test.nl"},
            registration_success=True,
            cosign_request_email_sent=True,
            cosign_complete=True,
            cosign_confirmation_email_sent=True,
            payment_complete_confirmation_email_sent=True,
            confirmation_email_sent=True,
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            form__name="Pretty Form",
            auth_info__attribute=AuthAttribute.bsn,
            auth_info__value="111222333",
            needs_on_completion_retry=True,
            with_completed_payment=True,
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ) as mock_registration,
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.update_payment_status"
            ) as mock_payment_status_update,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                on_post_submission_event(
                    submission.id, PostSubmissionEvents.on_completion
                )

        submission.refresh_from_db()

        mock_registration.assert_not_called()
        mock_payment_status_update.assert_called()

        mails = mail.outbox

        self.assertEqual(len(mails), 0)
        self.assertNotEqual(submission.auth_info.value, "111222333")

    def test_submission_completed_incomplete_appointment(self):
        setup_jcc()
        components = FormDefinitionFactory.build(is_appointment=True).configuration[
            "components"
        ]
        submission = SubmissionFactory.from_components(
            completed=True,
            form__registration_backend="",
            components_list=components,
            submitted_data={"product": {"identifier": "79", "name": "Paspoort"}},
        )

        with self.assertRaises(AppointmentRegistrationFailed):
            on_post_submission_event(submission.id, PostSubmissionEvents.on_completion)

    def test_cosign_not_required_and_not_filled_in_proceeds_with_registration(self):
        submission = SubmissionFactory.from_components(
            components_list=[
                {
                    "key": "email",
                    "type": "email",
                    "label": "Email",
                    "confirmationRecipient": True,
                },
                {
                    "key": "cosign",
                    "type": "cosign",
                    "label": "Cosign component",
                    "validate": {"required": False},
                },
            ],
            submitted_data={"cosign": "", "email": "test@test.nl"},
            completed=True,
            cosign_complete=False,
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            form__name="Pretty Form",
            auth_info__attribute=AuthAttribute.bsn,
            auth_info__value="111222333",
            language_code="en",
        )
        ConfirmationEmailTemplateFactory.create(
            form=submission.form,
            subject="Confirmation of your {{ form_name }} submission",
            content="Custom content {% appointment_information %} {% payment_information %} {% cosign_information %}",
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ) as mock_registration,
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.update_payment_status"
            ) as mock_payment_status_update,
        ):
            on_post_submission_event(submission.id, PostSubmissionEvents.on_completion)

        mock_registration.assert_called_once()
        mock_payment_status_update.assert_not_called()

        mails = mail.outbox

        self.assertEqual(1, len(mails))  # No cosign request email!
        self.assertEqual(
            mails[0].subject, "Confirmation of your Pretty Form submission"
        )
        self.assertEqual(mails[0].to, ["test@test.nl"])
        self.assertEqual(mails[0].cc, [])

        cosign_info = "This form will not be processed until it has been co-signed. A co-sign request was sent to cosign@test.nl."

        self.assertNotIn(cosign_info, mails[0].body.strip("\n"))

        submission.refresh_from_db()

        self.assertFalse(submission.cosign_request_email_sent)
        self.assertTrue(submission.confirmation_email_sent)
        self.assertNotEqual(submission.auth_info.value, "111222333")

    def test_cosign_not_required_but_filled_in_does_not_proceed_with_registration(self):
        submission = SubmissionFactory.from_components(
            components_list=[
                {
                    "key": "email",
                    "type": "email",
                    "label": "Email",
                    "confirmationRecipient": True,
                },
                {
                    "key": "cosign",
                    "type": "cosign",
                    "label": "Cosign component",
                    "validate": {"required": False},
                },
            ],
            submitted_data={"cosign": "cosign@test.nl", "email": "test@test.nl"},
            completed=True,
            cosign_complete=False,
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            form__name="Pretty Form",
            auth_info__attribute=AuthAttribute.bsn,
            auth_info__value="111222333",
            language_code="en",
        )
        ConfirmationEmailTemplateFactory.create(
            form=submission.form,
            subject="Confirmation of your {{ form_name }} submission",
            content="Custom content {% appointment_information %} {% payment_information %} {% cosign_information %}",
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ) as mock_registration,
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.update_payment_status"
            ) as mock_payment_status_update,
        ):
            on_post_submission_event(submission.id, PostSubmissionEvents.on_completion)

        mock_registration.assert_not_called()
        mock_payment_status_update.assert_not_called()

        mails = mail.outbox

        self.assertEqual(2, len(mails))
        self.assertEqual(
            mails[0].subject,
            _("Co-sign request for {form_name}").format(form_name="Pretty Form"),
        )
        self.assertEqual(mails[0].to, ["cosign@test.nl"])
        self.assertEqual(
            mails[1].subject, "Confirmation of your Pretty Form submission"
        )
        self.assertEqual(mails[1].to, ["test@test.nl"])
        self.assertEqual(mails[1].cc, [])

        cosign_info = "This form will not be processed until it has been co-signed. A co-sign request was sent to cosign@test.nl."

        self.assertIn(cosign_info, mails[1].body.strip("\n"))

        submission.refresh_from_db()

        self.assertTrue(submission.cosign_request_email_sent)
        self.assertTrue(submission.confirmation_email_sent)
        self.assertEqual(submission.auth_info.value, "111222333")

    @tag("gh-3924")
    def test_payment_complete_does_not_set_retry_flag(self):
        submission = SubmissionFactory.create(
            form__payment_backend="demo",
            form__product__price=Decimal("11.35"),
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            form__name="Pretty Form",
            completed=True,
            public_registration_reference=get_random_reference(),
            with_completed_payment=True,
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ),
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.update_payment_status"
            ),
            patch(
                "openforms.registrations.tasks.GlobalConfiguration.get_solo",
                return_value=GlobalConfiguration(wait_for_payment_to_register=True),
            ),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                on_post_submission_event(
                    submission.id, PostSubmissionEvents.on_payment_complete
                )

            submission.refresh_from_db()

            self.assertFalse(submission.needs_on_completion_retry)


@temp_private_root()
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class PaymentFlowTests(TestCase):
    def test_payment_required_and_not_should_wait_for_registration(self):
        """
        The payment is required and has not been completed, and the general configuration says to NOT skip registration if
        the payment has not been completed.
        """
        submission = SubmissionFactory.from_components(
            components_list=[
                {
                    "key": "email",
                    "type": "email",
                    "label": "Email",
                    "confirmationRecipient": True,
                }
            ],
            completed=True,
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            form__product__price=10,
            form__payment_backend="demo",
        )
        SubmissionPaymentFactory.create(
            submission=submission, amount=10, status=PaymentStatus.started
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ) as mock_registration,
            patch(
                "openforms.registrations.tasks.GlobalConfiguration.get_solo",
                return_value=GlobalConfiguration(wait_for_payment_to_register=True),
            ),
            LogCapture() as logs,
        ):
            on_post_submission_event(submission.id, PostSubmissionEvents.on_completion)

        mock_registration.assert_not_called()
        logs.check_present(
            (
                "openforms.registrations.tasks",
                "DEBUG",
                f"Skipping registration for submission '{submission}' as the payment hasn't been received yet.",
            )
        )

    def test_payment_done_and_should_wait_for_payment(
        self,
    ):
        """
        The payment is required and has been completed, so registration should not be skipped regardless of the general
        configuration setting.
        """
        submission = SubmissionFactory.from_components(
            components_list=[
                {
                    "key": "email",
                    "type": "email",
                    "label": "Email",
                    "confirmationRecipient": True,
                }
            ],
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            form__product__price=10,
            form__payment_backend="demo",
            completed=True,
            with_completed_payment=True,
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ) as mock_registration,
            patch(
                "openforms.registrations.tasks.GlobalConfiguration.get_solo",
                return_value=GlobalConfiguration(wait_for_payment_to_register=True),
            ),
            patch(
                "openforms.payments.tasks.update_submission_payment_registration"
            ) as mock_update_payment_status,
        ):
            on_post_submission_event(submission.id, PostSubmissionEvents.on_completion)

        mock_registration.assert_called_once()
        mock_update_payment_status.assert_not_called()

    def test_payment_done_and_not_should_wait_for_payment(
        self,
    ):
        """
        The payment is required and has been completed, so registration should not be skipped regardless of the general
        configuration setting.
        """

        submission = SubmissionFactory.create(
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            form__product__price=10,
            form__payment_backend="demo",
            completed=True,
            with_completed_payment=True,
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ) as mock_registration,
            patch(
                "openforms.registrations.tasks.GlobalConfiguration.get_solo",
                return_value=GlobalConfiguration(wait_for_payment_to_register=False),
            ),
        ):
            on_post_submission_event(submission.id, PostSubmissionEvents.on_completion)

        mock_registration.assert_called_once()

    def test_payment_not_required_and_should_wait_for_payment(
        self,
    ):
        """
        The payment is NOT required, so registration should not be skipped regardless of the general
        configuration setting.
        """
        submission = SubmissionFactory.create(
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            completed=True,
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ) as mock_registration,
            patch(
                "openforms.registrations.tasks.GlobalConfiguration.get_solo",
                return_value=GlobalConfiguration(wait_for_payment_to_register=True),
            ),
        ):
            on_post_submission_event(submission.id, PostSubmissionEvents.on_completion)

        mock_registration.assert_called_once()

    def test_payment_not_required_and_not_should_wait_for_payment(
        self,
    ):
        """
        The payment is NOT required, so registration should not be skipped regardless of the general
        configuration setting.
        """
        submission = SubmissionFactory.create(
            form__registration_backend="email",
            form__registration_backend_options={"to_emails": ["test@registration.nl"]},
            completed=True,
        )

        with (
            patch(
                "openforms.registrations.contrib.email.plugin.EmailRegistration.register_submission"
            ) as mock_registration,
            patch(
                "openforms.registrations.tasks.GlobalConfiguration.get_solo",
                return_value=GlobalConfiguration(wait_for_payment_to_register=False),
            ),
        ):
            on_post_submission_event(submission.id, PostSubmissionEvents.on_completion)

        mock_registration.assert_called_once()
