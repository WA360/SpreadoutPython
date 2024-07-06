# Generated by Django 5.0.6 on 2024-07-06 01:10

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0002_pdffile_url_pdffile_user_chapter"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pdffile",
            name="url",
            field=models.URLField(),
        ),
        migrations.CreateModel(
            name="Chapter",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("start_page", models.IntegerField()),
                ("end_page", models.IntegerField()),
                ("level", models.IntegerField()),
                ("bookmarked", models.BooleanField(default=False)),
                (
                    "pdf_file",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="api.pdffile"
                    ),
                ),
            ],
        ),
    ]