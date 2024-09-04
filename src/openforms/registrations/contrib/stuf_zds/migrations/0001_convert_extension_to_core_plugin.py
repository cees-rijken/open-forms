# Generated by Django 4.2.15 on 2024-09-04 14:01

from django.apps.registry import Apps
from django.db import migrations

from ..plugin import PLUGIN_IDENTIFIER

EXTENSION_PLUGIN_IDENTIFIER = "stuf-zds-create-zaak:ext-utrecht"


def convert(apps: Apps, _):
    ContentType = apps.get_model("contenttypes", "ContentType")
    FormRegistrationBackend = apps.get_model("forms", "FormRegistrationBackend")
    TimelineLog = apps.get_model("timeline_logger", "TimelineLog")

    backends = FormRegistrationBackend.objects.filter(
        backend=EXTENSION_PLUGIN_IDENTIFIER
    )
    if not backends:
        return

    log_entries = [
        TimelineLog(
            content_type=ContentType.objects.get_for_model(backend),
            object_id=backend.id,
            extra_data={
                "action": "convert-plugin-id",
                "from_id": backend.backend,
                "to_id": PLUGIN_IDENTIFIER,
            },
        )
        for backend in backends
    ]

    TimelineLog.objects.bulk_create(log_entries)
    backends.update(backend=PLUGIN_IDENTIFIER)


class Migration(migrations.Migration):

    dependencies = [
        ("timeline_logger", "0004_alter_fields"),
        ("forms", "0103_rename_identifier_role_prefill"),
    ]

    operations = [
        migrations.RunPython(convert, migrations.RunPython.noop),
    ]
