from django.test import SimpleTestCase

from ..utils import parse_schema_properties

SCHEMA_WITH_NESTED_PROPERTIES = {
    "$id": "https://example.com/person.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "invalid": {},
        "name": {"type": "string"},
        "address": {
            "type": "object",
            "properties": {
                "street": {
                    "type": "string",
                },
                "street.let": {"type": "string"},
                "city": {"type": "string"},
                "zipCode": {"type": "string"},
            },
            "required": ["street", "city", "zipCode"],
        },
        "contacts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                    },
                    "value": {"type": "string"},
                },
                "required": ["type", "value"],
            },
        },
    },
    "required": ["id", "name", "address", "contacts"],
}


SCHEMA_STR_TYPE = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "string",
    "minLength": 5,
    "maxLength": 100,
    "pattern": "^[a-zA-Z0-9_-]*$",
    "format": "date-time",
    "examples": ["2024-08-27T14:00:00Z", "user-123"],
}

SCHEMA_ARRAY_TYPE = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "array",
    "items": {
        "type": "array",
        "items": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}],
    },
}

SCHEMA_NO_TYPE = {
    "$id": "https://example.com/person.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "properties": {
        "name": {"type": "string"},
    },
}


class SchemaParsingTests(SimpleTestCase):
    def test_simple_schema(self):
        result = parse_schema_properties(SCHEMA_WITH_NESTED_PROPERTIES)
        self.assertEqual(
            result,
            [
                ("id", "string"),
                ("invalid", "unknown"),
                ("name", "string"),
                ("address > street", "string"),
                ("address > street.let", "string"),
                ("address > city", "string"),
                ("address > zipCode", "string"),
                ("contacts > type", "string"),
                ("contacts > value", "string"),
            ],
        )

    def test_schema_str_type(self):
        result = parse_schema_properties(SCHEMA_STR_TYPE)
        self.assertEqual(result, [("string", "string")])

    def test_schema_array_type(self):
        result = parse_schema_properties(SCHEMA_ARRAY_TYPE)
        self.assertEqual(
            result, [("[0]", "string"), ("[1]", "number"), ("[2]", "boolean")]
        )

    def test_schema_no_type(self):
        result = parse_schema_properties(SCHEMA_NO_TYPE)
        self.assertEqual(result, [])
