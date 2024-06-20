import logging
import traceback

from django.db import transaction
from django.utils import timezone

from celery_once import QueueOnce
from glom import assign
from rest_framework.exceptions import ValidationError

from openforms.celery import app
from openforms.config.models import GlobalConfiguration
from openforms.logging import logevent
from openforms.submissions.constants import PostSubmissionEvents, RegistrationStatuses
from openforms.submissions.models import Submission
from openforms.submissions.public_references import set_submission_reference

from .exceptions import RegistrationFailed
from .service import get_registration_plugin

logger = logging.getLogger(__name__)


@app.task()
def pre_registration(submission_id: int, event: PostSubmissionEvents) -> None:
    submission = Submission.objects.get(id=submission_id)
    if not submission.completed_on:
        # This should never happen. Pre-registration shouldn't be attempted for a submission that is not complete.
        logger.error(
            "Trying to pre-register submission '%s' which is not completed.", submission
        )
        return

    if submission.pre_registration_completed:
        return

    config = GlobalConfiguration.get_solo()
    if submission.registration_attempts >= config.registration_attempt_limit:
        logger.debug(
            "Skipping pre-registration for submission '%s' because it retried and failed too many times.",
            submission,
        )
        return

    with transaction.atomic():
        registration_plugin = get_registration_plugin(submission)
        if not registration_plugin:
            set_submission_reference(submission)
            submission.pre_registration_completed = True
            submission.save()
            return

        options_serializer = registration_plugin.configuration_options(
            data=submission.registration_backend.options
        )

        try:
            options_serializer.is_valid(raise_exception=True)
        except ValidationError as exc:
            set_submission_reference(submission)
            submission.save_registration_status(
                RegistrationStatuses.failed, {"traceback": traceback.format_exc()}
            )
            if event == PostSubmissionEvents.on_retry:
                raise exc
            return

        # If we are retrying, then an internal registration reference has been set. We keep track of it.
        if event == PostSubmissionEvents.on_retry:
            if not submission.registration_result:
                submission.registration_result = {}

            assign(
                submission.registration_result,
                "temporary_internal_reference",
                submission.public_registration_reference,
                missing=dict,
            )
            submission.save()

    try:
        result = registration_plugin.pre_register_submission(
            submission, options_serializer.validated_data
        )
    except Exception as exc:
        logger.exception("Pre-registration raised %s", exc)
        submission.save_registration_status(
            RegistrationStatuses.failed, {"traceback": traceback.format_exc()}
        )
        set_submission_reference(submission)
        if event == PostSubmissionEvents.on_retry:
            raise exc
        return

    if not result.reference:
        set_submission_reference(submission)
    else:
        submission.public_registration_reference = result.reference

    if not submission.registration_result:
        submission.registration_result = {}

    if "traceback" in submission.registration_result:
        del submission.registration_result["traceback"]

    if result.data is not None:
        submission.registration_result.update(result.data)

    submission.pre_registration_completed = True
    submission.save()


@app.task(
    base=QueueOnce,
    ignore_result=False,
    once={"graceful": True},  # do not spam error monitoring
)
def register_submission(submission_id: int, event: PostSubmissionEvents | str) -> None:
    """
    Attempt to register the submission with the configured backend.

    Note that there are different triggers that can kick off this task:

    * form submission :func:`openforms.submissions.tasks.on_completion` flow
    * celery beat retry flow
    * admin action to retry the submission

    We should only allow a single registration attempt to run at a given time for a
    given submission. This is achieved through the :class:`QueueOnce` task base class
    from celery-once. While the task is already scheduled, subsequent schedule requests
    will not schedule the task _again_ to celery.

    Submission registration is only executed for "completed" forms, and is delegated
    to the underlying registration backend (if set).
    """
    submission = Submission.objects.select_related("auth_info", "form").get(
        id=submission_id
    )
    logger.debug("Register submission '%s'", submission)

    if submission.registration_status == RegistrationStatuses.success:
        # if it's already successfully registered, do not overwrite that.
        return

    if not submission.completed_on:
        # This should never happen. Registration shouldn't be attempted for a submission that is not complete.
        logger.error(
            "Trying to register submission '%s' which is not completed.", submission
        )
        return

    if not submission.pre_registration_completed:
        logger.debug(
            "Skipping registration for submission '%s' because it hasn't been pre-registered yet.",
            submission,
        )
        return

    if submission.waiting_on_cosign:
        logger.debug(
            "Skipping registration for submission '%s' as it hasn't been co-signed yet.",
            submission,
        )
        logevent.skipped_registration_cosign_required(submission)
        return

    config = GlobalConfiguration.get_solo()
    if (
        config.wait_for_payment_to_register
        and submission.payment_required
        and not submission.payment_user_has_paid
    ):
        logger.debug(
            "Skipping registration for submission '%s' as the payment hasn't been received yet.",
            submission,
        )
        logevent.registration_skipped_not_yet_paid(submission)
        return

    if submission.registration_attempts >= config.registration_attempt_limit:
        # if it fails after this many attempts we give up
        logevent.registration_attempts_limited(submission)
        logger.debug(
            "Skipping registration for submission '%s' because it retried and failed too many times.",
            submission,
        )
        return

    logevent.registration_start(submission)

    submission.last_register_date = timezone.now()
    submission.registration_status = RegistrationStatuses.in_progress
    submission.registration_attempts += 1
    submission.save(
        update_fields=[
            "last_register_date",
            "registration_status",
            "registration_attempts",
        ]
    )

    # figure out which registry and backend to use from the model field used
    form = submission.form
    backend_config = submission.registration_backend

    if not backend_config or not backend_config.backend:
        logger.info("Form %s has no registration plugin configured, aborting", form)
        submission.save_registration_status(RegistrationStatuses.success, None)
        logevent.registration_skip(submission)
        return

    registry = backend_config._meta.get_field("backend").registry
    backend = backend_config.backend

    logger.debug("Looking up plugin with unique identifier '%s'", backend)
    plugin = registry[backend]

    if not plugin.is_enabled:
        logger.debug("Plugin '%s' is not enabled", backend)
        exc = RegistrationFailed("Registration plugin is not enabled")
        submission.save_registration_status(
            RegistrationStatuses.failed,
            {"traceback": "".join(traceback.format_exception(exc))},
        )
        logevent.registration_failure(submission, exc)
        if event == PostSubmissionEvents.on_retry:
            raise exc
        return

    logger.debug("De-serializing the plugin configuration options")
    options_serializer = plugin.configuration_options(data=backend_config.options)

    try:
        options_serializer.is_valid(raise_exception=True)
    except ValidationError as exc:
        logevent.registration_failure(submission, exc, plugin)
        logger.warning(
            "Registration using plugin '%r' for submission '%s' failed",
            plugin,
            submission,
            exc_info=exc,
        )
        submission.save_registration_status(
            RegistrationStatuses.failed, {"traceback": traceback.format_exc()}
        )
        if event == PostSubmissionEvents.on_retry:
            raise exc
        return

    logger.debug("Invoking the '%r' plugin callback", plugin)

    try:
        result = plugin.register_submission(
            submission, options_serializer.validated_data
        )
    except RegistrationFailed as exc:
        logger.warning(
            "Registration using plugin '%r' for submission '%s' failed",
            plugin,
            submission,
            exc_info=exc,
        )
        submission.save_registration_status(
            RegistrationStatuses.failed, {"traceback": traceback.format_exc()}
        )
        logevent.registration_failure(submission, exc, plugin)
        submission.save_registration_status(
            RegistrationStatuses.failed, {"traceback": traceback.format_exc()}
        )
        if event == PostSubmissionEvents.on_retry:
            raise exc
        return
    except Exception as exc:
        logger.error(
            "Registration using plugin '%r' for submission '%s' unexpectedly errored",
            plugin,
            submission,
            exc_info=True,
        )
        submission.save_registration_status(
            RegistrationStatuses.failed, {"traceback": traceback.format_exc()}
        )
        logevent.registration_failure(submission, exc, plugin)
        if event == PostSubmissionEvents.on_retry:
            raise exc
        return

    logger.info(
        "Registration using plugin '%r' for submission '%s' succeeded",
        plugin,
        submission,
    )

    if (
        config.wait_for_payment_to_register
        and event == PostSubmissionEvents.on_payment_complete
    ):
        submission.payments.mark_registered()

    submission.save_registration_status(RegistrationStatuses.success, result or {})
    logevent.registration_success(submission, plugin)
