from typing import Any, Iterable

from referencing.jsonschema import ObjectSchema

from openforms.registrations.contrib.objects_api.client import get_objecttypes_client


def parse_schema_properties(
    schema: ObjectSchema, parent_key: str = ""
) -> list[tuple[str, str]]:
    properties = []

    if not schema.get("type"):
        return []

    if schema["type"] == "object":
        for prop, prop_schema in schema.get("properties", {}).items():
            full_key = f"{parent_key} > {prop}" if parent_key else prop
            prop_type = prop_schema.get("type", "unknown")
            properties.append((full_key, prop_type))
            if prop_type == "object" or (
                prop_type == "array" and "items" in prop_schema
            ):
                properties.extend(parse_schema_properties(prop_schema, full_key))
    elif schema["type"] == "array":
        items_schema = schema.get("items", {})
        if isinstance(items_schema, dict):
            properties.extend(parse_schema_properties(items_schema, parent_key))
        elif isinstance(items_schema, list):
            for i, item_schema in enumerate(items_schema):
                properties.extend(
                    parse_schema_properties(item_schema, f"{parent_key}[{i}]")
                )
    else:
        properties.append((parent_key or schema["type"], schema["type"]))

    # Remove props of type object or array since it's not needed (e.g., (name, object))
    return [
        (prop[0], prop[1]) for prop in properties if prop[1] not in ("object", "array")
    ]


def retrieve_properties(
    reference: dict[str, Any] | None = None,
) -> Iterable[tuple[str, str]]:
    assert reference is not None

    with get_objecttypes_client(reference["objects_api_group"]) as client:
        json_schema = client.get_objecttype_version(
            reference["objects_api_objecttype_uuid"],
            reference["objects_api_objecttype_version"],
        )["jsonSchema"]

    properties = parse_schema_properties(json_schema)
    return [(prop[0], f"{prop[0]} ({prop[1]})") for prop in properties]
