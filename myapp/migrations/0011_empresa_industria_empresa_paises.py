# Generated by Django 4.2.11 on 2025-05-26 00:36

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("myapp", "0010_alter_plan_periodicidad_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="industria",
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.PROTECT,
                to="myapp.industria",
                verbose_name="Industria",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="empresa",
            name="paises",
            field=models.ManyToManyField(
                blank=True, to="myapp.pais", verbose_name="Países de Operación"
            ),
        ),
    ]
