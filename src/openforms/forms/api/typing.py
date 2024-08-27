from typing import TYPE_CHECKING, Required, TypedDict

if TYPE_CHECKING:
    from openforms.registrations.contrib.objects_api.models import ObjectsAPIGroupConfig


class _BasePrefillOptions(TypedDict):
    prefill_plugin: str


class ObjecttypeVariableMapping(TypedDict):
    variable_key: str
    target_path: list[str]


class ObjectsAPIPrefillOptions(_BasePrefillOptions):
    objects_api_group: Required[ObjectsAPIGroupConfig]
    objecttype_uuid: Required[str]
    objecttype_version: Required[int]
    variables_mapping: Required[list[ObjecttypeVariableMapping]]
