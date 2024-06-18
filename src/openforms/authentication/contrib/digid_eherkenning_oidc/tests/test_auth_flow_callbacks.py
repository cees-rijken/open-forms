"""
Test the authentication flow for a form.

These tests use VCR. When re-recording, making sure to:

.. code-block:: bash

    cd docker
    docker compose -f docker-compose.keycloak.yml up

to bring up a Keycloak instance.
"""

from django.test import tag

import requests
from furl import furl

from openforms.accounts.tests.factories import StaffUserFactory
from openforms.authentication.constants import FORM_AUTH_SESSION_KEY
from openforms.authentication.tests.utils import URLsHelper
from openforms.authentication.views import BACKEND_OUTAGE_RESPONSE_PARAMETER
from openforms.forms.tests.factories import FormFactory
from openforms.utils.tests.keycloak import keycloak_login

from .base import (
    IntegrationTestsBase,
    mock_digid_config,
    mock_digid_machtigen_config,
    mock_eherkenning_bewindvoering_config,
    mock_eherkenning_config,
)


class DigiDCallbackTests(IntegrationTestsBase):
    """
    Test the return/callback side after authenticating with the identity provider.
    """

    @mock_digid_config()
    def test_redirects_after_successful_auth(self):
        form = FormFactory.create(authentication_backends=["digid_oidc"])
        url_helper = URLsHelper(form=form)
        start_url = url_helper.get_auth_start(plugin_id="digid_oidc")
        start_response = self.app.get(start_url)

        # simulate login to Keycloak
        redirect_uri = keycloak_login(start_response["Location"])

        # complete the login flow on our end
        callback_response = self.app.get(redirect_uri, auto_follow=True)

        self.assertEqual(callback_response.request.url, url_helper.frontend_start)

    @mock_digid_config(bsn_claim="absent-claim")
    def test_failing_claim_verification(self):
        form = FormFactory.create(authentication_backends=["digid_oidc"])
        url_helper = URLsHelper(form=form)
        start_url = url_helper.get_auth_start(plugin_id="digid_oidc")
        start_response = self.app.get(start_url)
        # simulate login to Keycloak
        redirect_uri = keycloak_login(start_response["Location"])

        # complete the login flow on our end
        callback_response = self.app.get(redirect_uri, auto_follow=True)

        # XXX: shouldn't this be "digid" so that the correct error message is rendered?
        # Query: ?_digid-message=error
        expected_url = furl(url_helper.frontend_start).add(
            {BACKEND_OUTAGE_RESPONSE_PARAMETER: "digid_oidc"}
        )
        self.assertEqual(callback_response.request.url, str(expected_url))
        self.assertNotIn(FORM_AUTH_SESSION_KEY, self.app.session)

    @tag("gh-3656", "gh-3692")
    @mock_digid_config(oidc_rp_scopes_list=["badscope"])
    def test_digid_error_reported_for_cancelled_login_anon_django_user(self):
        form = FormFactory.create(authentication_backends=["digid_oidc"])
        url_helper = URLsHelper(form=form)
        start_url = url_helper.get_auth_start(plugin_id="digid_oidc")
        # initialize state, but don't actually log in - we have an invalid config and
        # keycloak redirects back to our callback URL with error parameters.
        start_response = self.app.get(start_url)
        auth_response = requests.get(start_response["Location"], allow_redirects=False)
        # check out assumptions/expectations before proceeding
        callback_url = furl(auth_response.headers["Location"])
        assert callback_url.netloc == "testserver"
        assert "state" in callback_url.args
        # modify the error parameters - there doesn't seem to be an obvious way to trigger
        # this via keycloak itself.
        # Note: this is an example of a specific provider. It may differ when a
        # different provider is used. According to
        # https://openid.net/specs/openid-connect-core-1_0.html#AuthError and
        # https://www.rfc-editor.org/rfc/rfc6749.html#section-4.1.2.1 , this is the
        # error we expect from OIDC.
        callback_url.args.update(
            {"error": "access_denied", "error_description": "The user cancelled"}
        )

        callback_response = self.app.get(str(callback_url), auto_follow=True)

        self.assertEqual(callback_response.status_code, 200)
        expected_url = furl(url_helper.frontend_start).add(
            {"_digid-message": "login-cancelled"}
        )
        assert BACKEND_OUTAGE_RESPONSE_PARAMETER not in expected_url.args
        self.assertEqual(callback_response.request.url, str(expected_url))

    @tag("gh-3656", "gh-3692")
    @mock_digid_config(oidc_rp_scopes_list=["badscope"])
    def test_digid_error_reported_for_cancelled_login_with_staff_django_user(self):
        self.app.set_user(StaffUserFactory.create())
        form = FormFactory.create(authentication_backends=["digid_oidc"])
        url_helper = URLsHelper(form=form)
        start_url = url_helper.get_auth_start(plugin_id="digid_oidc")
        # initialize state, but don't actually log in - we have an invalid config and
        # keycloak redirects back to our callback URL with error parameters.
        start_response = self.app.get(start_url)
        auth_response = requests.get(start_response["Location"], allow_redirects=False)
        # check out assumptions/expectations before proceeding
        callback_url = furl(auth_response.headers["Location"])
        assert callback_url.netloc == "testserver"
        assert "state" in callback_url.args
        callback_url.args.update(
            {"error": "access_denied", "error_description": "The user cancelled"}
        )

        callback_response = self.app.get(str(callback_url), auto_follow=True)

        self.assertEqual(callback_response.status_code, 200)
        expected_url = furl(url_helper.frontend_start).add(
            {"_digid-message": "login-cancelled"}
        )
        assert BACKEND_OUTAGE_RESPONSE_PARAMETER not in expected_url.args
        self.assertEqual(callback_response.request.url, str(expected_url))


class EHerkenningCallbackTests(IntegrationTestsBase):
    """
    Test the return/callback side after authenticating with the identity provider.
    """

    @mock_eherkenning_config()
    def test_redirects_after_successful_auth(self):
        form = FormFactory.create(authentication_backends=["eherkenning_oidc"])
        url_helper = URLsHelper(form=form)
        start_url = url_helper.get_auth_start(plugin_id="eherkenning_oidc")
        start_response = self.app.get(start_url)

        # simulate login to Keycloak
        redirect_uri = keycloak_login(start_response["Location"])

        # complete the login flow on our end
        callback_response = self.app.get(redirect_uri, auto_follow=True)

        self.assertEqual(callback_response.request.url, url_helper.frontend_start)

    @mock_eherkenning_config(legal_subject_claim="absent-claim")
    def test_failing_claim_verification(self):
        form = FormFactory.create(authentication_backends=["eherkenning_oidc"])
        url_helper = URLsHelper(form=form)
        start_url = url_helper.get_auth_start(plugin_id="eherkenning_oidc")
        start_response = self.app.get(start_url)
        # simulate login to Keycloak
        redirect_uri = keycloak_login(start_response["Location"])

        # complete the login flow on our end
        callback_response = self.app.get(redirect_uri, auto_follow=True)

        # XXX: shouldn't this be "eherkenning" so that the correct error message is rendered?
        # Query: ?_eherkenning-message=error
        expected_url = furl(url_helper.frontend_start).add(
            {BACKEND_OUTAGE_RESPONSE_PARAMETER: "eherkenning_oidc"}
        )
        self.assertEqual(callback_response.request.url, str(expected_url))
        self.assertNotIn(FORM_AUTH_SESSION_KEY, self.app.session)

    @tag("gh-3656", "gh-3692")
    @mock_eherkenning_config(oidc_rp_scopes_list=["badscope"])
    def test_eherkenning_error_reported_for_cancelled_login_anon_django_user(self):
        form = FormFactory.create(authentication_backends=["eherkenning_oidc"])
        url_helper = URLsHelper(form=form)
        start_url = url_helper.get_auth_start(plugin_id="eherkenning_oidc")
        # initialize state, but don't actually log in - we have an invalid config and
        # keycloak redirects back to our callback URL with error parameters.
        start_response = self.app.get(start_url)
        auth_response = requests.get(start_response["Location"], allow_redirects=False)
        # check out assumptions/expectations before proceeding
        callback_url = furl(auth_response.headers["Location"])
        assert callback_url.netloc == "testserver"
        assert "state" in callback_url.args
        # modify the error parameters - there doesn't seem to be an obvious way to trigger
        # this via keycloak itself.
        # Note: this is an example of a specific provider. It may differ when a
        # different provider is used. According to
        # https://openid.net/specs/openid-connect-core-1_0.html#AuthError and
        # https://www.rfc-editor.org/rfc/rfc6749.html#section-4.1.2.1 , this is the
        # error we expect from OIDC.
        callback_url.args.update(
            {"error": "access_denied", "error_description": "The user cancelled"}
        )

        callback_response = self.app.get(str(callback_url), auto_follow=True)

        self.assertEqual(callback_response.status_code, 200)
        expected_url = furl(url_helper.frontend_start).add(
            {"_eherkenning-message": "login-cancelled"}
        )
        assert BACKEND_OUTAGE_RESPONSE_PARAMETER not in expected_url.args
        self.assertEqual(callback_response.request.url, str(expected_url))

    @tag("gh-3656", "gh-3692")
    @mock_eherkenning_config(oidc_rp_scopes_list=["badscope"])
    def test_eherkenning_error_reported_for_cancelled_login_with_staff_django_user(
        self,
    ):
        self.app.set_user(StaffUserFactory.create())
        form = FormFactory.create(authentication_backends=["eherkenning_oidc"])
        url_helper = URLsHelper(form=form)
        start_url = url_helper.get_auth_start(plugin_id="eherkenning_oidc")
        # initialize state, but don't actually log in - we have an invalid config and
        # keycloak redirects back to our callback URL with error parameters.
        start_response = self.app.get(start_url)
        auth_response = requests.get(start_response["Location"], allow_redirects=False)
        # check out assumptions/expectations before proceeding
        callback_url = furl(auth_response.headers["Location"])
        assert callback_url.netloc == "testserver"
        assert "state" in callback_url.args
        callback_url.args.update(
            {"error": "access_denied", "error_description": "The user cancelled"}
        )

        callback_response = self.app.get(str(callback_url), auto_follow=True)

        self.assertEqual(callback_response.status_code, 200)
        expected_url = furl(url_helper.frontend_start).add(
            {"_eherkenning-message": "login-cancelled"}
        )
        assert BACKEND_OUTAGE_RESPONSE_PARAMETER not in expected_url.args
        self.assertEqual(callback_response.request.url, str(expected_url))


class DigiDMachtigenCallbackTests(IntegrationTestsBase):
    """
    Test the return/callback side after authenticating with the identity provider.
    """

    @mock_digid_machtigen_config()
    def test_redirects_after_successful_auth(self):
        form = FormFactory.create(authentication_backends=["digid_machtigen_oidc"])
        url_helper = URLsHelper(form=form)
        start_url = url_helper.get_auth_start(plugin_id="digid_machtigen_oidc")
        start_response = self.app.get(start_url)

        # simulate login to Keycloak
        redirect_uri = keycloak_login(
            start_response["Location"],
            username="digid-machtigen",
            password="digid-machtigen",
        )

        # complete the login flow on our end
        callback_response = self.app.get(redirect_uri, auto_follow=True)

        self.assertEqual(callback_response.request.url, url_helper.frontend_start)

    @mock_digid_machtigen_config(
        representee_bsn_claim="absent-claim",
        authorizee_bsn_claim="absent-claim",
    )
    def test_failing_claim_verification(self):
        form = FormFactory.create(authentication_backends=["digid_machtigen_oidc"])
        url_helper = URLsHelper(form=form)
        start_url = url_helper.get_auth_start(plugin_id="digid_machtigen_oidc")
        start_response = self.app.get(start_url)
        # simulate login to Keycloak
        redirect_uri = keycloak_login(
            start_response["Location"],
            username="digid-machtigen",
            password="digid-machtigen",
        )

        # complete the login flow on our end
        callback_response = self.app.get(redirect_uri, auto_follow=True)

        # XXX: shouldn't this be "digid" so that the correct error message is rendered?
        # Query: ?_digid-message=error
        expected_url = furl(url_helper.frontend_start).add(
            {BACKEND_OUTAGE_RESPONSE_PARAMETER: "digid_machtigen_oidc"}
        )
        self.assertEqual(callback_response.request.url, str(expected_url))
        self.assertNotIn(FORM_AUTH_SESSION_KEY, self.app.session)

    @tag("gh-3656", "gh-3692")
    @mock_digid_machtigen_config(oidc_rp_scopes_list=["badscope"])
    def test_digid_error_reported_for_cancelled_login_anon_django_user(self):
        form = FormFactory.create(authentication_backends=["digid_machtigen_oidc"])
        url_helper = URLsHelper(form=form)
        start_url = url_helper.get_auth_start(plugin_id="digid_machtigen_oidc")
        # initialize state, but don't actually log in - we have an invalid config and
        # keycloak redirects back to our callback URL with error parameters.
        start_response = self.app.get(start_url)
        auth_response = requests.get(start_response["Location"], allow_redirects=False)
        # check out assumptions/expectations before proceeding
        callback_url = furl(auth_response.headers["Location"])
        assert callback_url.netloc == "testserver"
        assert "state" in callback_url.args
        # modify the error parameters - there doesn't seem to be an obvious way to trigger
        # this via keycloak itself.
        # Note: this is an example of a specific provider. It may differ when a
        # different provider is used. According to
        # https://openid.net/specs/openid-connect-core-1_0.html#AuthError and
        # https://www.rfc-editor.org/rfc/rfc6749.html#section-4.1.2.1 , this is the
        # error we expect from OIDC.
        callback_url.args.update(
            {"error": "access_denied", "error_description": "The user cancelled"}
        )

        callback_response = self.app.get(str(callback_url), auto_follow=True)

        self.assertEqual(callback_response.status_code, 200)
        expected_url = furl(url_helper.frontend_start).add(
            {"_digid-message": "login-cancelled"}
        )
        assert BACKEND_OUTAGE_RESPONSE_PARAMETER not in expected_url.args
        self.assertEqual(callback_response.request.url, str(expected_url))

    @tag("gh-3656", "gh-3692")
    @mock_digid_machtigen_config(oidc_rp_scopes_list=["badscope"])
    def test_digid_error_reported_for_cancelled_login_with_staff_django_user(self):
        self.app.set_user(StaffUserFactory.create())
        form = FormFactory.create(authentication_backends=["digid_machtigen_oidc"])
        url_helper = URLsHelper(form=form)
        start_url = url_helper.get_auth_start(plugin_id="digid_machtigen_oidc")
        # initialize state, but don't actually log in - we have an invalid config and
        # keycloak redirects back to our callback URL with error parameters.
        start_response = self.app.get(start_url)
        auth_response = requests.get(start_response["Location"], allow_redirects=False)
        # check out assumptions/expectations before proceeding
        callback_url = furl(auth_response.headers["Location"])
        assert callback_url.netloc == "testserver"
        assert "state" in callback_url.args
        callback_url.args.update(
            {"error": "access_denied", "error_description": "The user cancelled"}
        )

        callback_response = self.app.get(str(callback_url), auto_follow=True)

        self.assertEqual(callback_response.status_code, 200)
        expected_url = furl(url_helper.frontend_start).add(
            {"_digid-message": "login-cancelled"}
        )
        assert BACKEND_OUTAGE_RESPONSE_PARAMETER not in expected_url.args
        self.assertEqual(callback_response.request.url, str(expected_url))


class EHerkenningBewindvoeringCallbackTests(IntegrationTestsBase):
    """
    Test the return/callback side after authenticating with the identity provider.
    """

    @mock_eherkenning_bewindvoering_config()
    def test_redirects_after_successful_auth(self):
        form = FormFactory.create(
            authentication_backends=["eherkenning_bewindvoering_oidc"]
        )
        url_helper = URLsHelper(form=form)
        start_url = url_helper.get_auth_start(
            plugin_id="eherkenning_bewindvoering_oidc"
        )
        start_response = self.app.get(start_url)

        # simulate login to Keycloak
        redirect_uri = keycloak_login(
            start_response["Location"],
            username="eherkenning-bewindvoering",
            password="eherkenning-bewindvoering",
        )

        # complete the login flow on our end
        callback_response = self.app.get(redirect_uri, auto_follow=True)

        self.assertEqual(callback_response.request.url, url_helper.frontend_start)

    @mock_eherkenning_bewindvoering_config(
        legal_subject_claim="absent-claim",
        representee_claim="absent-claim",
    )
    def test_failing_claim_verification(self):
        form = FormFactory.create(
            authentication_backends=["eherkenning_bewindvoering_oidc"]
        )
        url_helper = URLsHelper(form=form)
        start_url = url_helper.get_auth_start(
            plugin_id="eherkenning_bewindvoering_oidc"
        )
        start_response = self.app.get(start_url)
        # simulate login to Keycloak
        redirect_uri = keycloak_login(
            start_response["Location"],
            username="eherkenning-bewindvoering",
            password="eherkenning-bewindvoering",
        )

        # complete the login flow on our end
        callback_response = self.app.get(redirect_uri, auto_follow=True)

        # XXX: shouldn't this be "eherkenning" so that the correct error message is rendered?
        # Query: ?_eherkenning-message=error
        expected_url = furl(url_helper.frontend_start).add(
            {BACKEND_OUTAGE_RESPONSE_PARAMETER: "eherkenning_bewindvoering_oidc"}
        )
        self.assertEqual(callback_response.request.url, str(expected_url))
        self.assertNotIn(FORM_AUTH_SESSION_KEY, self.app.session)

    @tag("gh-3656", "gh-3692")
    @mock_eherkenning_bewindvoering_config(oidc_rp_scopes_list=["badscope"])
    def test_eherkenning_error_reported_for_cancelled_login_anon_django_user(self):
        form = FormFactory.create(
            authentication_backends=["eherkenning_bewindvoering_oidc"]
        )
        url_helper = URLsHelper(form=form)
        start_url = url_helper.get_auth_start(
            plugin_id="eherkenning_bewindvoering_oidc"
        )
        # initialize state, but don't actually log in - we have an invalid config and
        # keycloak redirects back to our callback URL with error parameters.
        start_response = self.app.get(start_url)
        auth_response = requests.get(start_response["Location"], allow_redirects=False)
        # check out assumptions/expectations before proceeding
        callback_url = furl(auth_response.headers["Location"])
        assert callback_url.netloc == "testserver"
        assert "state" in callback_url.args
        # modify the error parameters - there doesn't seem to be an obvious way to trigger
        # this via keycloak itself.
        # Note: this is an example of a specific provider. It may differ when a
        # different provider is used. According to
        # https://openid.net/specs/openid-connect-core-1_0.html#AuthError and
        # https://www.rfc-editor.org/rfc/rfc6749.html#section-4.1.2.1 , this is the
        # error we expect from OIDC.
        callback_url.args.update(
            {"error": "access_denied", "error_description": "The user cancelled"}
        )

        callback_response = self.app.get(str(callback_url), auto_follow=True)

        self.assertEqual(callback_response.status_code, 200)
        expected_url = furl(url_helper.frontend_start).add(
            {"_eherkenning-message": "login-cancelled"}
        )
        assert BACKEND_OUTAGE_RESPONSE_PARAMETER not in expected_url.args
        self.assertEqual(callback_response.request.url, str(expected_url))

    @tag("gh-3656", "gh-3692")
    @mock_eherkenning_bewindvoering_config(oidc_rp_scopes_list=["badscope"])
    def test_eherkenning_error_reported_for_cancelled_login_with_staff_django_user(
        self,
    ):
        self.app.set_user(StaffUserFactory.create())
        form = FormFactory.create(
            authentication_backends=["eherkenning_bewindvoering_oidc"]
        )
        url_helper = URLsHelper(form=form)
        start_url = url_helper.get_auth_start(
            plugin_id="eherkenning_bewindvoering_oidc"
        )
        # initialize state, but don't actually log in - we have an invalid config and
        # keycloak redirects back to our callback URL with error parameters.
        start_response = self.app.get(start_url)
        auth_response = requests.get(start_response["Location"], allow_redirects=False)
        # check out assumptions/expectations before proceeding
        callback_url = furl(auth_response.headers["Location"])
        assert callback_url.netloc == "testserver"
        assert "state" in callback_url.args
        callback_url.args.update(
            {"error": "access_denied", "error_description": "The user cancelled"}
        )

        callback_response = self.app.get(str(callback_url), auto_follow=True)

        self.assertEqual(callback_response.status_code, 200)
        expected_url = furl(url_helper.frontend_start).add(
            {"_eherkenning-message": "login-cancelled"}
        )
        assert BACKEND_OUTAGE_RESPONSE_PARAMETER not in expected_url.args
        self.assertEqual(callback_response.request.url, str(expected_url))
