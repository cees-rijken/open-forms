# Generated by Django 2.2.20 on 2021-05-27 09:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stuf", "0001_initial"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="soapservice",
            options={
                "verbose_name": "SOAP service",
                "verbose_name_plural": "SOAP services",
            },
        ),
        migrations.AddField(
            model_name="soapservice",
            name="label",
            field=models.CharField(
                default="LABEL MISSING",
                help_text="Human readable label to identify services",
                max_length=100,
                verbose_name="label",
            ),
            preserve_default=False,
        ),
    ]
