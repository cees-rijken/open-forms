import logging
from typing import Any

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

import requests
from glom import T as Target, glom
from lxml import etree

from openforms.authentication.constants import AuthAttribute
from openforms.plugins.exceptions import InvalidPluginConfiguration
from openforms.submissions.models import Submission
from openforms.utils.xml import fromstring
from stuf.stuf_bg.client import NoServiceConfigured, get_client
from stuf.stuf_bg.constants import FieldChoices
from stuf.stuf_bg.models import StufBGConfig

from ...base import BasePlugin
from ...constants import IdentifierRoles
from ...registry import register

logger = logging.getLogger(__name__)


"""
    # original
    Bsn
    Voornamen
    VoorvoegselGeslachtsnaam
    Geslachtsnaam
    Straatnaam
    Huisnummer
    Huisletter
    HuisnummerToevoeging
    Postcode
    Woonplaatsnaam

    # added
    Geboorteplaats
    Geslachtsaanduiding
    Geboortedatum
    Geboorteland
    DatumOverlijden

    # not in bg0310
    # AanduidingBijHuisnummer


    LandAdresBuitenland
    Regel1AdresBuitenland
    Regel2AdresBuitenland
    Regel3AdresBuitenland

"""

"""
plenty of examples for responses can be found in open-personen:
https://github.com/maykinmedia/open-personen/tree/master/src/openpersonen/templates/response
"""

ATTRIBUTES_TO_STUF_BG_MAPPING = {
    FieldChoices.bsn: Target["inp.bsn"],
    FieldChoices.voornamen: Target["voornamen"],
    FieldChoices.voorletters: Target["voorletters"],
    FieldChoices.geslachtsnaam: Target["geslachtsnaam"],
    FieldChoices.voorvoegselGeslachtsnaam: Target["voorvoegselGeslachtsnaam"],
    FieldChoices.geboorteplaats: Target["inp.geboorteplaats"],
    FieldChoices.geslachtsaanduiding: Target["geslachtsaanduiding"],
    FieldChoices.geboortedatum: Target["geboortedatum"],
    FieldChoices.geboorteland: Target["inp.geboorteLand"],
    FieldChoices.overlijdensdatum: Target["overlijdensdatum"],
    FieldChoices.straatnaam: Target["verblijfsadres"]["gor.straatnaam"],
    FieldChoices.huisnummer: Target["verblijfsadres"]["aoa.huisnummer"],
    FieldChoices.huisletter: Target["verblijfsadres"]["aoa.huisletter"],
    FieldChoices.huisnummertoevoeging: Target["verblijfsadres"][
        "aoa.huisnummertoevoeging"
    ],
    FieldChoices.postcode: Target["verblijfsadres"]["aoa.postcode"],
    FieldChoices.woonplaatsNaam: Target["verblijfsadres"]["wpl.woonplaatsNaam"],
    FieldChoices.gemeenteVanInschrijving: Target["inp.gemeenteVanInschrijving"],
    FieldChoices.landAdresBuitenland: Target["sub.verblijfBuitenland"]["lnd.landnaam"],
    FieldChoices.adresBuitenland1: Target["sub.verblijfBuitenland"][
        "sub.adresBuitenland1"
    ],
    FieldChoices.adresBuitenland2: Target["sub.verblijfBuitenland"][
        "sub.adresBuitenland2"
    ],
    FieldChoices.adresBuitenland3: Target["sub.verblijfBuitenland"][
        "sub.adresBuitenland3"
    ],
}


@register("stufbg")
class StufBgPrefill(BasePlugin):
    verbose_name = _("StUF-BG")
    requires_auth = AuthAttribute.bsn

    def get_available_attributes(self) -> list[tuple[str, str]]:
        return FieldChoices.choices

    def _get_values_for_bsn(
        self, bsn: str, attributes: list[FieldChoices]
    ) -> dict[str, Any]:
        with get_client() as client:
            data = client.get_values(bsn, [str(attr) for attr in attributes])

        response_dict = {}
        for attribute in attributes:
            value = glom(data, ATTRIBUTES_TO_STUF_BG_MAPPING[attribute], default=None)
            # if the XML element has attributes, we don't get a return value of the content,
            # but rather an OrderedDict from xmltodict with the #text key for the content
            # and @<attribute> keys for the attributes.
            # E.g. <ns:geboortedatum StUF:indOnvolledigeDatum="M">19600701</ns:geboortedatum>,
            # see #1617 for such a regression.
            if isinstance(value, dict) and "#text" in value:
                value = value["#text"]

            if value and "@noValue" not in value:
                response_dict[attribute] = value

        # postcodes in StUF BG responses have this form "[1-9][0-9]{3}[A-Z]{0,2}"
        # Our prefill tests expect roughly "[1-9][0-9]{3} [A-Z]{0,2}"
        if FieldChoices.postcode in response_dict and " " not in (
            postcode := response_dict[FieldChoices.postcode]
        ):
            response_dict[FieldChoices.postcode] = postcode[:4] + " " + postcode[4:]

        return response_dict

    def get_identifier_value(
        self, submission: Submission, identifier_role: str
    ) -> str | None:
        if not submission.is_authenticated:
            return

        if (
            identifier_role == IdentifierRoles.main
            and submission.auth_info.attribute == self.requires_auth
        ):
            return submission.auth_info.value

        if identifier_role == IdentifierRoles.authorised_person:
            return submission.auth_info.machtigen.get("identifier_value")

    def get_prefill_values(
        self,
        submission: Submission,
        attributes: list[FieldChoices],
        identifier_role: str = IdentifierRoles.main,
    ) -> dict[str, Any]:
        if not (bsn_value := self.get_identifier_value(submission, identifier_role)):
            #  If there is no bsn we can't prefill any values so just return
            logger.info("No BSN associated with submission, cannot prefill.")
            return {}

        return self._get_values_for_bsn(bsn_value, attributes)

    def get_co_sign_values(self, identifier: str) -> tuple[dict[str, Any], str]:
        """
        Given an identifier, fetch the co-sign specific values.

        The return value is a dict keyed by field name as specified in
        ``self.co_sign_fields``.

        :param identfier: the unique co-signer identifier used to look up the details
          in the pre-fill backend.
        :return: a key-value dictionary, where the key is the requested attribute and
          the value is the prefill value to use for that attribute.
        """
        values = self._get_values_for_bsn(
            identifier,
            [
                FieldChoices.voornamen,
                FieldChoices.voorvoegselGeslachtsnaam,
                FieldChoices.geslachtsnaam,
            ],
        )
        representation_bits = [
            " ".join(
                [f"{name[0]}." for name in values[FieldChoices.voornamen].split(" ")]
            ),
            values.get(FieldChoices.voorvoegselGeslachtsnaam, ""),
            values[FieldChoices.geslachtsnaam],
        ]
        return (
            values,
            " ".join([bit for bit in representation_bits if bit]),
        )

    def check_config(self):
        check_bsn = "111222333"
        try:
            with get_client() as client:
                response = client.templated_request(
                    "npsLv01",
                    template="stuf_bg/StufBgRequest.xml",
                    context={"bsn": check_bsn},
                )
                response.raise_for_status()
        except NoServiceConfigured as exc:
            raise InvalidPluginConfiguration(_("Service not selected")) from exc
        except requests.RequestException as exc:
            raise InvalidPluginConfiguration(
                _("Client error: {exception}").format(exception=exc)
            ) from exc

        try:
            xml = fromstring(response.content)
        except etree.XMLSyntaxError as exc:
            raise InvalidPluginConfiguration(
                _("SyntaxError in response: {exception}").format(exception=exc)
            ) from exc

        # we expect a valid 'object not found' response,
        #   but also accept an empty response (for 3rd party backend implementation reasons)
        if not is_object_not_found_response(xml) and not is_empty_wrapped_response(xml):
            raise InvalidPluginConfiguration(
                _("Unexpected response: expected '{message}' SOAP response").format(
                    message="Object niet gevonden"
                )
            )

    def get_config_actions(self):
        return [
            (
                _("Configuration"),
                reverse(
                    "admin:stuf_bg_stufbgconfig_change",
                    args=(StufBGConfig.singleton_instance_id,),
                ),
            ),
        ]


def is_object_not_found_response(xml):
    faults = xml.xpath("//*[local-name()='Fault']/faultstring")
    if not faults or faults[0].text != "Object niet gevonden":
        return False
    else:
        return True


def is_empty_wrapped_response(xml):
    meta = xml.xpath("//*[local-name()='Body']/*/*[local-name()='stuurgegevens']")
    response = xml.xpath("//*[local-name()='Body']/*/*[local-name()='antwoord']")
    if meta and not response:
        return True
    else:
        return False
