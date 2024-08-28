import logging
from typing import Any, Iterable

from django.utils.translation import gettext_lazy as _

from openforms.authentication.service import AuthAttribute
from openforms.submissions.models import Submission
from openforms.typing import JSONEncodable

from ...base import BasePlugin
from ...constants import IdentifierRoles
from ...registry import register

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
        pass

    @classmethod
    def get_prefill_values(
        cls,
        submission: Submission,
        attributes: list[str],
        identifier_role: IdentifierRoles = IdentifierRoles.main,
    ) -> dict[str, JSONEncodable]:
        pass

    @classmethod
    def get_co_sign_values(
        cls, submission: Submission, identifier: str
    ) -> tuple[dict[str, Any], str]:
        pass
