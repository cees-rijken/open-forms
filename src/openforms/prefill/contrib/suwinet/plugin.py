import logging

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from openforms.authentication.service import AuthAttribute
from openforms.forms.api.typing import _BasePrefillOptions
from openforms.plugins.exceptions import InvalidPluginConfiguration
from openforms.submissions.models import Submission
from openforms.typing import JSONEncodable, JSONObject
from suwinet.client import NoServiceConfigured, SuwinetClient, get_client
from suwinet.constants import SERVICES
from suwinet.models import SuwinetConfig

from ...base import BasePlugin
from ...constants import IdentifierRoles
from ...registry import register

logger = logging.getLogger(__name__)


def _get_client() -> SuwinetClient | None:
    try:
        return get_client()
    except NoServiceConfigured:
        logger.warning("No service defined for Suwinet.")
    return None


@register("suwinet")
class SuwinetPrefill(BasePlugin):
    requires_auth = AuthAttribute.bsn
    verbose_name = _("Suwinet")
    for_components = ()

    @staticmethod
    def get_available_attributes():
        if not (client := _get_client()):
            return []
        with client:
            return [
                (f"{service_name}.{operation}", f"{service_name} > {operation}")
                for service_name in client
                for operation in SERVICES[service_name].operations
            ]

    @classmethod
    def get_prefill_values(
        cls,
        submission: Submission,
        attributes: list[str],
        prefill_options: _BasePrefillOptions,
        identifier_role: IdentifierRoles = IdentifierRoles.main,
    ) -> dict[str, JSONEncodable]:
        if not (
            (client := _get_client())
            and (bsn := cls.get_identifier_value(submission, identifier_role))
        ):
            return {}

        def get_value(attr: str) -> JSONObject | None:
            service_name, operation = attr.split(".")
            service = getattr(client, service_name)
            perform_soap_call = getattr(service, operation)
            try:
                return perform_soap_call(bsn)
            except Exception:
                logger.exception(
                    "Suwinet operation '%s' on service '%s' failed.",
                    operation,
                    service_name,
                    extra={"service": service_name, "operation": operation},
                )
                return None

        with client:
            # these are independent requests and should be performed async
            return {attr: value for attr in attributes if (value := get_value(attr))}

    def check_config(self):
        try:
            client = get_client()
            # Testing configured endpoints with test bsns might not be allowed in
            # production. Check "Grondslag" before proceeding.
        except NoServiceConfigured as e:
            raise InvalidPluginConfiguration(
                _("Configuration error: {exception}").format(exception=e)
            )
        if not len(client):  # pragma: nocover
            # enforced by SuwinetConfig.clean, here for completeness sake
            # of the confugaration overview; it shouldn't show a green
            # checkmark if of whatever reason the config is corrupt.
            raise InvalidPluginConfiguration(
                _("No services found. Check the binding addresses.")
            )

    def get_config_actions(self):
        return [
            (
                _("Configuration"),
                reverse(
                    "admin:suwinet_suwinetconfig_change",
                    args=(SuwinetConfig.singleton_instance_id,),
                ),
            )
        ]
