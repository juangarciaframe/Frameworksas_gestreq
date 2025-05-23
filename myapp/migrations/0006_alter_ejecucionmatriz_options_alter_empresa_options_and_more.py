# Generated by Django 4.2.11 on 2025-04-30 02:04

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion

# --- FUNCIONES AUXILIARES PARA RunPython ---
def alter_tiempo_validacion_to_int(apps, schema_editor):
    """
    Convierte tiempo_validacion de interval a integer (días)
    SOLO si la base de datos es PostgreSQL.
    """
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute(
            'ALTER TABLE "myapp_requisitolegal" ALTER COLUMN "tiempo_validacion" TYPE integer USING EXTRACT(DAY FROM "tiempo_validacion");'
        )
        schema_editor.execute(
            'ALTER TABLE "myapp_requisitoporempresadetalle" ALTER COLUMN "tiempo_validacion" TYPE integer USING EXTRACT(DAY FROM "tiempo_validacion");'
        )

def reverse_alter_tiempo_validacion_to_interval(apps, schema_editor):
    """
    Intenta revertir tiempo_validacion de integer a interval
    SOLO si la base de datos es PostgreSQL.
    """
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute(
            'ALTER TABLE "myapp_requisitolegal" ALTER COLUMN "tiempo_validacion" TYPE interval USING CAST("tiempo_validacion" || \' days\' AS interval);'
        )
        schema_editor.execute(
            'ALTER TABLE "myapp_requisitoporempresadetalle" ALTER COLUMN "tiempo_validacion" TYPE interval USING CAST("tiempo_validacion" || \' days\' AS interval);'
        )
# --- FIN FUNCIONES AUXILIARES ---


class Migration(migrations.Migration):
    dependencies = [
        ("myapp", "0005_requisitolegal_periodicidad_and_more"),
    ]

    operations = [
        # --- AlterModelOptions (Sin Cambios) ---
        migrations.AlterModelOptions(
            name="ejecucionmatriz",
            options={
                "ordering": ["matriz", "requisito", "plan"],
                "verbose_name": "Ejecucion del Plan",
                "verbose_name_plural": "Ejecucion de los Planes",
            },
        ),
        migrations.AlterModelOptions(
            name="empresa",
            options={
                "ordering": ["nombreempresa"],
                "verbose_name": "Empresa",
                "verbose_name_plural": "Empresas",
            },
        ),
        migrations.AlterModelOptions(
            name="industria",
            options={
                "ordering": ["nombre"],
                "verbose_name": "Industria",
                "verbose_name_plural": "Industrias",
            },
        ),
        migrations.AlterModelOptions(
            name="pais",
            options={
                "ordering": ["nombre"],
                "verbose_name": "Pais",
                "verbose_name_plural": "Paises",
            },
        ),
        migrations.AlterModelOptions(
            name="plan",
            options={
                "ordering": ["empresa__nombreempresa", "year", "requisito_empresa"],
                "verbose_name": "Plan",
                "verbose_name_plural": "Planes",
            },
        ),
        migrations.AlterModelOptions(
            name="requisitolegal",
            options={
                "ordering": ["tema", "numero"],
                "verbose_name": "Requisito Legal",
                "verbose_name_plural": "Requisitos Legales",
            },
        ),
        migrations.AlterModelOptions(
            name="requisitoporempresadetalle",
            options={
                "ordering": ["matriz", "requisito"],
                "verbose_name": "Requisito Por Empresa Detalle",
                "verbose_name_plural": "Requisitos Por Empresa Detalle",
            },
        ),
        migrations.AlterModelOptions(
            name="requisitosporempresa",
            options={
                "ordering": ["empresa__nombreempresa", "nombre"],
                "verbose_name": "Requisitos Por Empresa",
                "verbose_name_plural": "Requisitos Por Empresa",
            },
        ),
        migrations.AlterModelOptions(
            name="sede",
            options={
                "ordering": ["empresa__nombreempresa", "nombre"],
                "verbose_name": "Sede",
                "verbose_name_plural": "Sedes",
            },
        ),
        # --- Fin AlterModelOptions ---

        # --- AlterField (Sin Cambios, excepto tiempo_validacion) ---
        migrations.AlterField(
            model_name="ejecucionmatriz",
            name="ejecucion",
            field=models.BooleanField(default=False, verbose_name="Ejecutado"),
        ),
        migrations.AlterField(
            model_name="ejecucionmatriz",
            name="razon_no_conforme",
            field=models.TextField(
                blank=True,
                default=None,
                help_text="Obligatorio si el estado es 'No conforme'.",
                null=True,
                verbose_name="Razón No Conforme",
            ),
        ),
        migrations.AlterField(
            model_name="empresa",
            name="logo",
            field=models.ImageField(blank=True, null=True, upload_to="logos_empresa/"),
        ),
        migrations.AlterField(
            model_name="pais",
            name="codigo",
            field=models.CharField(
                help_text="Código ISO 3166-1 alpha-2 del país (ej. CO, MX, US)",
                max_length=2,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name="plan",
            name="descripcion_periodicidad",
            field=models.TextField(
                blank=True,
                help_text="Requerido si la periodicidad es 'Otro'.",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="plan",
            name="year",
            field=models.PositiveIntegerField(verbose_name="Año del Plan"),
        ),
        migrations.AlterField(
            model_name="requisitolegal",
            name="industria",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="myapp.industria",
            ),
        ),
        migrations.AlterField(
            model_name="requisitolegal",
            name="pais",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="myapp.pais",
            ),
        ),
        # --- Fin AlterField (excepto tiempo_validacion) ---

        # --- REEMPLAZO DE RunSQL por RunPython ---
        migrations.RunPython(alter_tiempo_validacion_to_int, reverse_code=reverse_alter_tiempo_validacion_to_interval),
        # --- FIN REEMPLAZO ---

        # --- AlterField (Sin Cambios, excepto tiempo_validacion) ---
        migrations.AlterField(
            model_name="requisitoporempresadetalle",
            name="fecha_final",
            field=models.DateField(
                blank=True,
                editable=False,
                help_text="Calculada automáticamente basada en Fecha Inicio, Días Hábiles y País del Requisito.",
                null=True,
                verbose_name="Fecha Final Estimada (Días Hábiles)",
            ),
        ),
        migrations.AlterField(
            model_name="requisitoporempresadetalle",
            name="matriz",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="detalles",
                to="myapp.requisitosporempresa",
            ),
        ),
        # --- Fin AlterField (excepto tiempo_validacion) ---

        # --- AddIndex (CORREGIDOS) ---
        migrations.AddIndex(
            model_name="ejecucionmatriz",
            # Reemplaza '...' con la definición del índice de EjecucionMatriz
            index=models.Index(fields=['matriz', 'requisito', 'plan'], name='myapp_ejecu_matriz__81ac72_idx'),
        ),
        migrations.AddIndex(
            model_name="plan",
            # Reemplaza '...' con la definición del primer índice de Plan
            index=models.Index(fields=['empresa', 'year'], name='myapp_plan_empresa_f703ed_idx'),
        ),
        migrations.AddIndex(
            model_name="plan",
            # Reemplaza '...' con la definición del segundo índice de Plan
            index=models.Index(fields=['requisito_empresa'], name='myapp_plan_requisi_9a5ebe_idx'),
        ),
        migrations.AddIndex(
            model_name="requisitoporempresadetalle",
            # Reemplaza '...' con la definición del índice de RequisitoPorEmpresaDetalle
            index=models.Index(fields=['matriz', 'requisito'], name='myapp_requi_matriz__6510c5_idx'),
        ),
        # --- Fin AddIndex ---

        # --- AlterField para estado Django (Sin Cambios) ---
        migrations.AlterField(
            model_name="requisitolegal",
            name="tiempo_validacion",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Número de días hábiles (según país) estimados o requeridos para validar.",
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="Tiempo de Validación (Días Hábiles)",
            ),
        ),
        migrations.AlterField(
            model_name="requisitoporempresadetalle",
            name="tiempo_validacion",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Número de días hábiles (según país del requisito) para validar. Usado para calcular Fecha Final.",
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="Tiempo de Validación (Días Hábiles)",
            ),
        ),
        # --- FIN AlterField para estado Django ---
    ]


