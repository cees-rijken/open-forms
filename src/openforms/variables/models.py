from urllib.parse import quote, quote_plus

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from openforms.typing import DataMapping

from .constants import DataMappingTypes, ServiceFetchMethods
from .validators import (
    HeaderValidator,
    validate_mapping_expression,
    validate_request_body,
)


class ServiceFetchConfiguration(models.Model):
    service = models.ForeignKey(
        "zgw_consumers.Service",
        on_delete=models.PROTECT,
        verbose_name=_("service"),
    )
    name = models.CharField(
        max_length=250,
        blank=True,
        help_text=_("human readable name for the configuration"),
    )
    path = models.CharField(
        _("path"),
        max_length=250,
        blank=True,  # allow "" for the root, but not None
        default="",
        help_text=_("path relative to the Service API root"),
    )
    method = models.CharField(
        _("HTTP method"),
        max_length=4,
        choices=ServiceFetchMethods.choices,
        default=ServiceFetchMethods.get,
        help_text=_("POST is allowed, but should not be used to mutate data"),
    )
    headers = models.JSONField(
        _("HTTP request headers"),
        blank=True,
        null=True,
        help_text=_(
            "Additions and overrides for the HTTP request headers as defined in the Service."
        ),
        validators=[HeaderValidator()],
    )
    query_params = models.JSONField(
        _("HTTP query string"),
        blank=True,
        default=dict,
    )
    body = models.JSONField(
        _("HTTP request body"),
        blank=True,
        null=True,
        help_text=_(
            'Request body for POST requests (only "application/json" is supported)'
        ),
    )
    data_mapping_type = models.CharField(
        _("mapping expression language"),
        max_length=10,
        blank=True,
        default="",
        choices=DataMappingTypes.choices,
    )
    mapping_expression = models.JSONField(
        _("mapping expression"),
        blank=True,
        null=True,
        help_text=_("For jq, pass a string containing the filter expression"),
    )

    class Meta:
        verbose_name = _("service fetch configuration")
        verbose_name_plural = _("service fetch configurations")

    def __str__(self):
        return f"{self.service} {self.path}"

    def clean(self):
        super().clean()

        # Similar implementation like models.Model.full_clean
        errors = {}
        for validator in (validate_request_body, validate_mapping_expression):
            try:
                validator(self)
            except ValidationError as e:
                errors = e.update_error_dict(errors)
        if errors:
            raise ValidationError(errors)

    def request_arguments(self, context: DataMapping) -> dict:
        """Return a dictionary with keyword arguments for a
        zgw_consumers.Service client request call.
        """
        # The zgw-consumers client uses the requests library to perform the request,
        # but requests sends out malformed headers if you ask it to. We are
        # interpolating user input into headers, so we might ask it to if we aren't careful.
        #
        # The Internet Standard currently applicable is RFC9110
        # What you and I call http headers, it calls `fields`
        # https://www.rfc-editor.org/rfc/rfc9110#section-5
        #
        # Validating the contents of headers is beyond the scope of this
        # function, we only make sure the requests we send are within the
        # Internet Standard spec. If some service needs emoji in the header,
        # we force it into a sequence of bytes that is allowed.
        #
        # extra knowledge not in the RFC: latin1 is a different name for ISO-8859-1

        headers = {
            # map all unicode into what the RFC allows with utf-8; remove padding space
            header: value.format(**context).encode("utf-8").decode("latin1").strip()
            for header, value in (self.headers or {}).items()
        }
        # before we go further
        # assert headers are still valid after we put submmitter data in there
        # this catches faults requests doesn't: https://github.com/psf/requests/issues/6359
        HeaderValidator()(headers)

        escaped_for_query = {k: quote(str(v)) for k, v in context.items()}
        escaped_for_path = {k: quote_plus(str(v)) for k, v in context.items()}

        query_params = self.query_params.format(**escaped_for_query)
        query_params = (
            query_params[1:] if query_params.startswith("?") else query_params
        )

        request_args = dict(
            path=self.path.format(**escaped_for_path),
            params=query_params,
            method=self.method,
            headers=headers,
            # XXX operationId is a required parameter to zds-client...
            # Maybe offer as alternative to path and method?
            operation="",
        )
        if self.body is not None:
            request_args["json"] = self.body
        return request_args
