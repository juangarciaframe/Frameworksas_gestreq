# Generated by Django 4.2.11 on 2025-04-30 13:21

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("myapp", "0007_alter_requisitoporempresadetalle_unique_together_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="plan",
            options={
                "ordering": [
                    "empresa__nombreempresa",
                    "year",
                    "requisito_empresa",
                    "fecha_proximo_cumplimiento",
                ],
                "verbose_name": "Plan (Tarea)",
                "verbose_name_plural": "Planes (Tareas)",
            },
        ),
        migrations.AddField(
            model_name="plan",
            name="responsable_ejecucion",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="planes_asignados",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Responsable Ejecución",
            ),
        ),
        migrations.AlterField(
            model_name="plan",
            name="fecha_proximo_cumplimiento",
            field=models.DateField(
                blank=True, null=True, verbose_name="Fecha de Cumplimiento Programada"
            ),
        ),
        migrations.AlterUniqueTogether(
            name="plan",
            unique_together={
                ("requisito_empresa", "year", "fecha_proximo_cumplimiento")
            },
        ),
        migrations.AddIndex(
            model_name="plan",
            index=models.Index(
                fields=["year", "fecha_proximo_cumplimiento"],
                name="myapp_plan_year_8d7a40_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="plan",
            index=models.Index(
                fields=["responsable_ejecucion"], name="myapp_plan_respons_4f09d1_idx"
            ),
        ),
    ]
