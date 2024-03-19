from unittest.mock import patch

from django.core.files import File
from django.test import TestCase, override_settings
from django.urls import reverse

import requests
from digid_eherkenning.choices import AssuranceLevels, XMLContentTypes
from digid_eherkenning.models import EherkenningConfiguration
from freezegun import freeze_time
from furl import furl
from privates.test import temp_private_root
from simple_certmanager.test.factories import CertificateFactory

from openforms.forms.tests.factories import FormStepFactory
from openforms.utils.tests.cache import clear_caches
from openforms.utils.tests.vcr import OFVCRMixin

from .utils import TEST_FILES, _parse_form

PLUGIN_ID = "eidas"
KEY = TEST_FILES / "our_key.pem"
CERT = TEST_FILES / "our_certificate.pem"
METADATA = TEST_FILES / "signicat_metadata.xml"

SIGNICAT_BROKER_BASE = furl("https://maykin.pre.ie01.signicat.pro/broker")
SELECT_EIDAS_SIM = SIGNICAT_BROKER_BASE / "authn/simulator/selection/eidas"


@patch(
    "openforms.submissions.tokens.submission_resume_token_generator.secret", new="dummy"
)
@patch(
    "onelogin.saml2.authn_request.OneLogin_Saml2_Utils.generate_unique_id",
    lambda *_, **__: "ONELOGIN_123456",
)
@temp_private_root()
@override_settings(
    COOKIE_CONSENT_ENABLED=False,
)
class SignicatEIDASIntegrationTests(OFVCRMixin, TestCase):
    """Test using Signicat broker.

    Instead of mocking responses. We do real requests to a Signicat test environment
    *once* and record the responses with VCR.

    Requests to ourself go through the regular Django TestClient.
    Requests to the broker use a requests Session.

    When Signicat updates their service, responses on VCR cassettes might be stale, and
    we'll need to re-test against the real service to assert everything still works.

    To do so:

    #. Ensure the config is still valid:
       - `CERT` needs to be valid
       - `CERT` and our SAML metadata need to be configured in Signicat
       - `METADATA` needs to contain their SAML metadata
    #. Delete the VCR cassettes
    #. Run the test
    #. Inspect the diff of the new cassettes

    The default dev settings set the record mode to 'once', but if you need a difference
    once, see the :module:`openforms.utils.tests.vcr` documentation.
    """

    VCR_TEST_FILES = TEST_FILES

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cert = CertificateFactory.create(
            label="eIDAS",
            with_private_key=True,
            public_certificate__from_path=CERT,
            private_key__from_path=KEY,
        )

        config = EherkenningConfiguration.get_solo()
        assert isinstance(config, EherkenningConfiguration)
        config.certificate = cert
        config.idp_service_entity_id = SIGNICAT_BROKER_BASE / "sp/saml"
        # broker insists using https
        config.entity_id = "https://localhost:8000/eherkenning"
        config.base_url = "https://localhost:8000"
        config.artifact_resolve_content_type = XMLContentTypes.text_xml
        config.want_assertions_signed = True
        config.want_assertions_encrypted = False

        config.service_name = "eHerkenning test"
        config.service_description = "CI eHerkenning SAML integration test"
        config.oin = "00000001002220647000"
        config.makelaar_id = "00000003244440010000"
        config.privacy_policy = "https://example.com"
        config.service_language = "nl"
        config.loa = AssuranceLevels.low_plus

        config.requested_attributes = [
            "urn:etoegang:1.9:EntityConcernedID:KvKnr",
            "urn:etoegang:1.9:EntityConcernedID:Pseudo",
        ]
        config.eh_attribute_consuming_service_index = "9052"
        config.eh_service_uuid = "588932b9-28ae-4323-ab6c-fabbddae05cd"
        config.eh_service_instance_uuid = "952cee6a-6553-4f58-922d-dd03486a772c"

        config.no_eidas = False
        config.eidas_attribute_consuming_service_index = "9053"
        config.eidas_requested_attributes = [
            {
                "name": "urn:etoegang:1.9:attribute:FirstName",
                "required": True,
                "purpose_statements": {
                    "en": "For testing purposes.",
                    "nl": "Voor testdoeleinden.",
                },
            },
            {
                "name": "urn:etoegang:1.9:attribute:FamilyName",
                "required": True,
                "purpose_statements": {
                    "en": "For testing purposes.",
                    "nl": "Voor testdoeleinden.",
                },
            },
            {
                "name": "urn:etoegang:1.9:attribute:DateOfBirth",
                "required": True,
                "purpose_statements": {
                    "en": "For testing purposes.",
                    "nl": "Voor testdoeleinden.",
                },
            },
            {
                "name": "urn:etoegang:1.11:attribute-represented:CompanyName",
                "required": True,
                "purpose_statements": {
                    "en": "For testing purposes.",
                    "nl": "Voor testdoeleinden.",
                },
            },
        ]
        config.eidas_service_uuid = "c36634fa-c059-440e-adcb-2b1e0e83d21c"
        config.eidas_service_instance_uuid = "44e08db1-9b33-4d15-9f77-5aea3a7b0b4c"

        with METADATA.open("rb") as md_file:
            config.idp_metadata_file = File(md_file, METADATA.name)
            config.save()

    def setUp(self):
        super().setUp()

        clear_caches()
        self.addCleanup(clear_caches)

        # We're freezing the time to whatever is on the cassette, because parts of the
        # body of the SAML messages are time dependant. (e.g. expiration datetimes)
        #
        # (this is funny if you're old enough to have seen your VCR with a blinking time
        # and it missed recording episodes during your holiday)
        if self.cassette.responses:
            now = self.cassette.responses[0]["headers"]["date"][0]
            time_ctx = freeze_time(now)
            self.addCleanup(time_ctx.stop)
            time_ctx.start()

    def test_login_with_extra_requested_attributes(self):
        session: requests.Session = requests.session()
        form = FormStepFactory.create(
            form__slug="slurm",
            form__authentication_backends=[PLUGIN_ID],
            form_definition__login_required=True,
        ).form

        login_url = reverse(
            "authentication:start", kwargs={"slug": form.slug, "plugin_id": PLUGIN_ID}
        )
        form_path = reverse("core:form-detail", kwargs={"slug": form.slug})
        form_url = furl("https://localhost:8000/") / form_path

        our_faux_redirect = self.client.get(
            login_url,
            {"next": str(form_url), "attr_consuming_service_index": "9053"},
            follow=True,
        )
        # do the js submit to get redirected to signicat broker
        method, redirect_url, form_values = _parse_form(our_faux_redirect)
        self.assertTrue(session.request(method, redirect_url, data=form_values).ok)

        # select eIDAS from the Signicat simulator selection screen
        sim_response = session.get(SELECT_EIDAS_SIM)
        self.assertTrue(sim_response.ok)

        sim_method, sim_action_url, sim_form = _parse_form(sim_response)
        # eIDAS selects LoA1 by default in the test env, which does not work
        sim_form["loa"] = "loa2plus"
        auth_response = session.request(
            sim_method, sim_action_url, data=sim_form, verify=False
        )

        self.assertTrue(auth_response.ok)
