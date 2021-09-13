import json
from copy import deepcopy

from django import forms
from django.core.validators import ValidationError
from django.utils.translation import gettext_lazy as _

import requests
from mozilla_django_oidc_db.constants import (
    OIDC_MAPPING as _OIDC_MAPPING,
    OPEN_ID_CONFIG_PATH,
)
from mozilla_django_oidc_db.forms import OpenIDConnectConfigForm

from openforms.forms.models import Form

from .models import OpenIDConnectPublicConfig

OIDC_MAPPING = deepcopy(_OIDC_MAPPING)

OIDC_MAPPING["oidc_op_logout_endpoint"] = "end_session_endpoint"


class OpenIDConnectPublicConfigForm(OpenIDConnectConfigForm):
    required_endpoints = [
        "oidc_op_authorization_endpoint",
        "oidc_op_token_endpoint",
        "oidc_op_user_endpoint",
        "oidc_op_logout_endpoint",
    ]
    oidc_mapping = OIDC_MAPPING

    class Meta:
        model = OpenIDConnectPublicConfig
        fields = "__all__"

    def clean_enabled(self):
        enabled = self.cleaned_data["enabled"]

        if not enabled:
            forms_with_digid_oidc = Form.objects.filter(
                authentication_backends__contains=["digid_oidc"]
            )

            if forms_with_digid_oidc.exists():
                raise ValidationError(
                    _(
                        "DigiD via OpenID Connect is selected as authentication backend "
                        "for one or more Forms, please remove this backend from these "
                        "Forms before disabling this authentication backend."
                    )
                )
        return enabled
