# Generated by Django 4.2.11 on 2025-04-30 02:14

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("myapp", "0006_alter_ejecucionmatriz_options_alter_empresa_options_and_more"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="requisitoporempresadetalle",
            unique_together=set(),
        ),
        migrations.AddField(
            model_name="requisitoporempresadetalle",
            name="sede",
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.CASCADE,
                to="myapp.sede",
                verbose_name="Sede de Aplicación",
            ),
            preserve_default=False,
        ),
        migrations.AlterUniqueTogether(
            name="requisitoporempresadetalle",
            unique_together={("matriz", "requisito", "sede")},
        ),
    ]
