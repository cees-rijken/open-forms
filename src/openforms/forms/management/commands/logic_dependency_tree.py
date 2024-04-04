from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import TypeAlias

from django.core.management.base import BaseCommand, CommandError

from openforms.variables.registry import (
    register_static_variable as static_vars_register,
)

from ...models import Form, FormDefinition, FormLogic, FormStep, FormVariable


class Command(BaseCommand):
    help = "Show the logic evaluation dependency tree"

    def add_arguments(self, parser):
        parser.add_argument("form_id", help="ID of the form to inspect", type=int)

    def handle(self, *args, **options):
        form_id = options["form_id"]

        form = Form.objects.filter(id=form_id).first()
        if form is None:
            raise CommandError("Invalid form ID provided")

        tree = DependencyTree(form)
        self.stdout.write(str(tree))


VariablesOnly: TypeAlias = tuple[None, Sequence[FormVariable]]
StepWithVariables: TypeAlias = tuple[FormStep, Sequence[FormVariable]]


class DependencyTree:

    def __init__(self, form: Form) -> None:
        self.form = form

    def __str__(self):
        def str_generator() -> Iterable[str]:
            form_name = f"Form: {self.form.name}"
            yield "=" * len(form_name)
            yield "\n"
            yield form_name
            yield "\n"
            yield "=" * len(form_name)
            yield "\n\n"

            yield "Variables\n"
            yield "---------\n"
            for step, variables in self.get_all_variables():
                if step is None:
                    yield "  Static: "
                else:
                    yield f"  Step '{step.form_definition.name}': "
                yield ", ".join(variable.key for variable in variables)
                yield "\n"

        return "".join(str_generator())

    def get_all_variables(self) -> Iterable[VariablesOnly | StepWithVariables]:
        """
        Return a tiered sequency of variable information.

        Static variables are always available, so these are returned first. Then,
        each form step is processed in order to get their respective variables, as that
        is the order in which they become available.
        """
        # fetch the static variables
        static_vars = [
            var.get_static_variable(submission=None) for var in static_vars_register
        ]
        yield (None, static_vars)

        # then, fetch the variables for each step
        form_variables_by_step = defaultdict[FormDefinition, list[FormVariable]](list)
        for variable in (
            FormVariable.objects.filter(form=self.form).prefetch_related(
                "form_definition"
            )
            # typically they get created in order that they occur in the form definition
            .order_by("id")
        ):
            form_variables_by_step[variable.form_definition].append(variable)

        for form_step in FormStep.objects.filter(form=self.form).select_related(
            "form_definition"
        ):
            variables = form_variables_by_step[form_step.form_definition]
            yield (form_step, variables)
