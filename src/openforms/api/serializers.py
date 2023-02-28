from dataclasses import dataclass
from functools import total_ordering
from itertools import groupby
from typing import Any, Iterable, List, MutableMapping, Type

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Model
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from openforms.api.utils import underscore_to_camel


class DummySerializer(serializers.Serializer):
    """
    Defines a valid-name-having empty serializer.

    drf-spectacular does serializer name validation, and using plain
    :class:`serializers.Serializer` in some places throws warnings because the schema
    component name resolves to an empty string.

    In some places we need to map something to an empty serializer (we can't just say
    there is _no_ serializer), so there we can use the DummySerializer to avoid schema
    generation warnings.
    """


class FieldValidationErrorSerializer(serializers.Serializer):
    """
    Validation error format, following the NL API Strategy.

    See https://docs.geostandaarden.nl/api/API-Strategie/ and
    https://docs.geostandaarden.nl/api/API-Strategie-ext/#error-handling-0
    """

    name = serializers.CharField(help_text=_("Name of the field with invalid data"))
    code = serializers.CharField(help_text=_("System code of the type of error"))
    reason = serializers.CharField(
        help_text=_("Explanation of what went wrong with the data")
    )


class ExceptionSerializer(serializers.Serializer):
    """
    Error format for HTTP 4xx and 5xx errors.

    See https://docs.geostandaarden.nl/api/API-Strategie-ext/#error-handling-0 for the NL API strategy guidelines.
    """

    type = serializers.CharField(
        help_text=_("URI reference to the error type, intended for developers"),
        required=False,
        allow_blank=True,
    )
    code = serializers.CharField(
        help_text=_("System code indicating the type of error")
    )
    title = serializers.CharField(help_text=_("Generic title for the type of error"))
    status = serializers.IntegerField(help_text=_("The HTTP status code"))
    detail = serializers.CharField(
        help_text=_("Extra information about the error, if available")
    )
    instance = serializers.CharField(
        help_text=_(
            "URI with reference to this specific occurrence of the error. "
            "This can be used in conjunction with server logs, for example."
        )
    )


class ValidationErrorSerializer(ExceptionSerializer):
    invalid_params = FieldValidationErrorSerializer(many=True)


@dataclass
@total_ordering
class BatchItem:
    priority: int
    instance: Model
    source: str  # index.field_name of the source data

    @property
    def model(self) -> Type[Model]:
        return type(self.instance)

    def __post_init__(self):
        # high priority first, grouped by type
        self._sorting_key = (-self.priority, self.model.__name__)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, BatchItem):  # pragma: no cover
            raise TypeError(f"Can't compare BatchItem to {type(other)}")
        return self._sorting_key < other._sorting_key


class ListWithChildSerializer(serializers.ListSerializer):
    child_serializer_class = None  # class or dotted import path

    def __init__(self, *args, **kwargs):
        child_serializer_class = self.get_child_serializer_class()
        kwargs.setdefault("child", child_serializer_class())
        super().__init__(*args, **kwargs)

    def get_child_serializer_class(self):
        if isinstance(self.child_serializer_class, str):
            self.child_serializer_class = import_string(self.child_serializer_class)
        return self.child_serializer_class

    def process_object(self, obj):
        return obj

    def _batch(
        self,
        data: Iterable[MutableMapping[str, Any]],
    ) -> Iterable[BatchItem]:
        # Helps create() and validate() deal with nested serializers in O(1) db
        # queries. i.e. one insert per model type.
        #
        # It helps by yielding BatchItems of unsafed Model instances. Nested
        # models should be safed first, so parent gets saved with the new
        # foreign keys. The order of BatchItems is defined such that high
        # priority comes first, and models of the same type are grouped
        # together for a single bulk_create.

        child_serializer = self.get_child_serializer_class()
        model = child_serializer.Meta.model
        child_fields = child_serializer().get_fields()
        prio = 0

        for index, data_dict in enumerate(data):
            for field_name, sub_data in data_dict.items():
                if field_name not in child_fields:  # pragma: no cover
                    continue
                source = f"{index}.{field_name}"
                field = child_fields[field_name]
                if isinstance(field, serializers.ModelSerializer):
                    # Turn sub_data into *unsaved* instance
                    # if only drf Serializers had a "build" method that just
                    # instantiated without saving
                    sub_model = field.Meta.model
                    sub_instance = (
                        sub_data
                        if isinstance(sub_data, sub_model)
                        else sub_model(**sub_data)
                    )
                    # and replace sub_data with sub_instance
                    data_dict[field_name] = sub_instance
                    # yield it with higher prio then ourselves, so it will be
                    # instantiated before our child instance
                    yield BatchItem(prio + 1, sub_instance, source)
            yield BatchItem(
                prio,
                self.process_object(model(**data_dict)),
                str(index),
            )

    def validate(self, attrs):
        attrs = super().validate(attrs)

        for item in self._batch(attrs):
            try:
                item.instance.clean()
            except DjangoValidationError as e:
                # reconstruct the full source path
                raise ValidationError(
                    {
                        f"{item.source}.{field}": errors
                        for field, errors in e.message_dict.items()
                    }
                )
        return attrs

    def create(self, validated_data):
        inserted = []
        # sort on (prio, model)
        batch = sorted(self._batch(validated_data))
        # group them by model
        for model, batch_items in groupby(batch, key=lambda i: i.model):
            inserted = model._default_manager.bulk_create(
                item.instance for item in batch_items
            )

        # the last inserted batch are of our child_serializer
        return inserted


class PublicFieldsSerializerMixin:
    # Mixin to distinguish between public and private serializer fields
    # Public fields are displayed for all users and private fields are (by default) only
    # displayed for staff users.

    # Example usage:

    #     class PersonSerializer(PublicFieldsSerializerMixin, serializers.ModelSerializer):
    #         class Meta:
    #             fields = (
    #                 "first_name",
    #                 "family_name",
    #                 "phone_number",
    #             )
    #             public_fields = (
    #                 "first_name",
    #                 "family_name",
    #             )

    @classmethod
    def _get_admin_field_names(cls, camelize=True) -> List[str]:
        formatter = underscore_to_camel if camelize else lambda x: x
        return [
            formatter(name)
            for name in cls.Meta.fields
            if name not in cls.Meta.public_fields
        ]

    def get_fields(self):
        fields = super().get_fields()

        request = self.context.get("request")
        view = self.context.get("view")
        is_api_schema_generation = (
            getattr(view, "swagger_fake_view", False) if view else False
        )
        is_mock_request = request and getattr(
            request, "is_mock_request", is_api_schema_generation
        )

        admin_only_fields = self._get_admin_field_names(camelize=False)

        # filter public fields if not staff and not exporting or schema generating
        # request.is_mock_request is set by the export serializers (possibly from management command etc)
        # also this can be called from schema generator without request
        if request and not is_mock_request:
            if not request.user.is_staff:
                for admin_field in admin_only_fields:
                    del fields[admin_field]

        return fields
