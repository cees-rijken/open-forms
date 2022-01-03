"""
Process the complex variable schema and evaluate it against the submission data.

The variable schema is both a schema and an instance of the schema. Submission data
is injected and evaluated using json-logic expressions, while the remainder of the
data may be static/hardcoded.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Union

from django_camunda.types import JSONObject, JSONValue
from json_logic import jsonLogic

AnyVariable = Union[
    "ComponentVariable",
    "StringVariable",
    "NumberVariable",
    "BooleanVariable",
    "NullVariable",
    "ObjectVariable",
    "ArrayVariable",
]


@dataclass
class Variable:
    source: str

    @staticmethod
    def build(**kwargs) -> Union["ComponentVariable", "ManualVariable"]:
        _source_map = {
            "manual": ManualVariable,
            "component": ComponentVariable,
        }
        cls = _source_map[kwargs["source"]]
        return cls.build(**kwargs)

    def evaluate(self, data: Dict[str, Any]) -> JSONValue:
        raise NotImplementedError(
            "Subclass %r must implement 'def evaluate'.", type(self)
        )


@dataclass
class ComponentVariable(Variable):
    definition: Dict[str, Any]  # JSON-logic

    @classmethod
    def build(cls, **kwargs):
        return cls(**kwargs)

    def evaluate(self, data: dict) -> JSONValue:
        return jsonLogic(self.definition, data)


@dataclass
class ManualVariable(Variable):
    type: str

    @staticmethod
    def build(**kwargs) -> "ManualVariable":
        this_type = kwargs["type"]
        _type_map = {
            "string": StringVariable,
            "number": NumberVariable,
            "boolean": BooleanVariable,
            "null": NullVariable,
            "object": ObjectVariable,
            "array": ArrayVariable,
        }
        cls = _type_map[this_type]

        if this_type == "object":
            kwargs["definition"] = {
                key: Variable.build(**value)
                for key, value in kwargs["definition"].items()
            }

        if this_type == "array":
            kwargs["definition"] = [
                Variable.build(**value) for value in kwargs["definition"]
            ]

        return cls(**kwargs)

    def evaluate(self, data: dict) -> JSONValue:
        # recurse into the leaf nodes
        if self.type == "array":
            return [sub_definition.evaluate(data) for sub_definition in self.definition]

        elif self.type == "object":
            return {
                key: sub_definition.evaluate(data)
                for key, sub_definition in self.definition.items()
            }

        raise ValueError(f"Unknown type {self.type}")  # pragma: no cover


@dataclass
class StringVariable(ManualVariable):
    definition: str

    def evaluate(self, data: dict) -> str:
        return self.definition


@dataclass
class NumberVariable(ManualVariable):
    definition: Union[float, int]

    def evaluate(self, data: dict) -> Union[float, int]:
        return self.definition


@dataclass
class BooleanVariable(ManualVariable):
    definition: bool

    def evaluate(self, data: dict) -> bool:
        return self.definition


@dataclass
class NullVariable(ManualVariable):
    definition: None

    def evaluate(self, data: dict) -> None:
        return None


@dataclass
class ObjectVariable(ManualVariable):
    definition: Dict[str, AnyVariable]


@dataclass
class ArrayVariable(ManualVariable):
    definition: List[AnyVariable]


@dataclass
class ComplexVariable:
    enabled: bool
    alias: str
    type: str
    definition: Union[ObjectVariable, ArrayVariable]

    @classmethod
    def build(cls, **kwargs):
        # we assume that the data passed in has a valid schema - this is enforced by
        # the camunda options serializer(s)
        _type_map = {
            "object": ObjectVariable,
            "array": ArrayVariable,
        }
        Nested = _type_map[kwargs["type"]]
        kwargs["definition"] = Nested.build(
            type=kwargs["type"],
            definition=kwargs["definition"],
            source="manual",
        )
        return cls(**kwargs)

    def evaluate(self, data: dict) -> JSONValue:
        # defer evaluation to the underlying value definition
        return self.definition.evaluate(data)


def get_complex_process_variables(
    variables: List[dict], merged_data: dict
) -> Dict[str, JSONObject]:
    if not variables:
        return {}

    # normalize object into dataclasses
    variables = [
        ComplexVariable.build(**variable)
        for variable in variables
        if variable["enabled"]
    ]

    evaluated = {
        variable.alias: variable.evaluate(merged_data) for variable in variables
    }

    return evaluated
