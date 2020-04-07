# Generated by Django 2.1.4 on 2020-04-06 19:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wlct', '0089_runtimelog'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='runtimelog',
            name='logger_ptr',
        ),
        migrations.AlterField(
            model_name='logger',
            name='level',
            field=models.CharField(max_length=64, null=True),
        ),
        migrations.DeleteModel(
            name='RuntimeLog',
        ),
    ]