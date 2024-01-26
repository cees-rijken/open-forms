"""
API schema generation extension using drf-spectacular.
"""
import logging

from django.utils.translation import gettext_lazy as _

from drf_spectacular.extensions import OpenApiViewExtension
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.plumbing import force_instance, is_list_serializer
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import GenericAPIView
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSetMixin

from ..constants import NONCE_HTTP_HEADER
from .fields import CSPPostProcessedHTMLField

logger = logging.getLogger(__name__)

NONCE_PARAMETER = OpenApiParameter(
    name=NONCE_HTTP_HEADER,
    type=str,
    location=OpenApiParameter.HEADER,
    description=_(
        "The value of the CSP nonce generated by the page embedding the SDK. "
        "If provided, fields containing rich text from WYSIWYG editors will be post-"
        "processed to allow inline styles with the provided nonce. "
        "If the embedding page emits a `style-src` policy containing `unsafe-inline`, "
        "then you can omit this header without losing functionality. We recommend "
        "favouring the nonce mechanism though."
    ),
    required=False,
)


# Can't use the auto_schema as it's not passed to view inspectors. Code inspired on
# drf_spectacular.openapi.AutoSchema._get_serializer
def _get_serializer_class(view_cls: type[APIView]):
    # be lenient - there may be views that don't have any serializer set at all
    if not issubclass(view_cls, GenericAPIView):
        serializer_attrs = [
            "get_serializer",
            "get_serializer_class",
            "serializer_class",
        ]
        # can't guess serializer -> give up
        if not any((hasattr(view_cls, attr) for attr in serializer_attrs)):
            return None

    auto_schema = AutoSchema()

    if issubclass(view_cls, ViewSetMixin):
        callback = view_cls.as_view(actions={"get": "list"})
    else:
        callback = view_cls.as_view()

    view = callback.cls(**getattr(callback, "initkwargs", {}))
    view.args = ()
    view.kwargs = {}
    view.format_kwarg = None
    view.request = None
    view.action_map = getattr(callback, "actions", None)
    view.swagger_fake_view = True

    actions = getattr(callback, "actions", None)
    if actions is not None:
        # we don't have the request method in context at all, and it's not relevant either
        view.action = "metadata"

    auto_schema.view = view

    if issubclass(view_cls, GenericAPIView):
        if view_cls.get_serializer == GenericAPIView.get_serializer:
            try:
                view.get_serializer_class()
            except AssertionError:  # view without serializer class, ignore
                logger.warning("Could not determine view %r serializer class", view_cls)
                return None

    serializer = auto_schema.get_response_serializers()
    if is_list_serializer(serializer):
        serializer = serializer.child
    return serializer


class CSPPostProcessedHTMLFieldExtension(OpenApiViewExtension):
    """
    Add the NONCE_HTTP_HEADER param to operations that emit CSP post-processable fields.


    This is a DRF-spectacular extension to document the request header only for operations
    where it's relevant.
    """

    target_class = APIView
    match_subclasses = True

    def view_replacement(self):
        serializer = _get_serializer_class(self.target)
        # definitely not post-processable, as there is no (output) serializer
        if serializer is None:
            return self.target

        # now check if the serializer has a CSPPostProcessedHTMLField
        serializer = force_instance(serializer)
        is_post_processable = any(
            (
                isinstance(field, CSPPostProcessedHTMLField)
                for field in serializer.get_fields().values()
            )
        )
        if not is_post_processable:
            return self.target

        # ok, it's post proccessable -> add the header parameter
        @extend_schema(parameters=[NONCE_PARAMETER])
        class FixedView(self.target):
            pass

        return FixedView
