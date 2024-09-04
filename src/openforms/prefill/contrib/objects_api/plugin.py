import logging
from typing import Any, Iterable

from django.utils.translation import gettext_lazy as _

from glom import GlomError, Path, glom

from openforms.authentication.service import AuthAttribute
from openforms.forms.api.typing import ObjectsAPIPrefillOptions
from openforms.registrations.contrib.objects_api.client import get_objects_client
from openforms.registrations.contrib.objects_api.models import ObjectsAPIGroupConfig
from openforms.submissions.models import Submission
from openforms.typing import JSONEncodable

from ...base import BasePlugin
from ...constants import IdentifierRoles
from ...registry import register
from .utils import retrieve_properties

logger = logging.getLogger(__name__)

PLUGIN_IDENTIFIER = "objects_api"


@register(PLUGIN_IDENTIFIER)
class ObjectsAPIPrefill(BasePlugin):
    verbose_name = _("Objects API")
    requires_auth = AuthAttribute.bsn

    @staticmethod
    def get_available_attributes(
        reference: dict[str, Any] | None = None,
    ) -> Iterable[tuple[str, str]]:
        assert reference is not None
        return retrieve_properties(reference)

    @classmethod
    def get_prefill_values(
        cls,
        submission: Submission,
        prefill_options: ObjectsAPIPrefillOptions,
        identifier_role: IdentifierRoles = IdentifierRoles.main,
    ) -> dict[str, JSONEncodable]:
        assert prefill_options is not None

        config = ObjectsAPIGroupConfig.objects.get(
            id=prefill_options["objects_api_group"]
        )
        with get_objects_client(config) as client:
            if not (data := client.get_object(submission.initial_data_reference)):
                # if not (data := client.get_object("20e61048-887f-402d-9566-74fdb15e65f3")):
                return {}

            try:
                # TODO
                # Take into account the general data as well (what's in record and not only record.data.data)
                record_data = glom(data, "record.data.data")
            except GlomError as exc:
                logger.warning(
                    "missing expected data in backend response",
                    exc_info=exc,
                )

            values = dict()
            for element in prefill_options["variables_mapping"]:
                try:
                    values[element["variable_key"]] = glom(
                        record_data, Path(*element["target_path"])
                    )
                except GlomError as exc:
                    logger.warning(
                        "missing expected attribute in backend response",
                        exc_info=exc,
                    )

        return values
