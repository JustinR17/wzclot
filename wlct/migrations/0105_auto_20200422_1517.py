# Generated by Django 2.1.4 on 2020-04-22 22:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wlct', '0104_auto_20200422_1203'),
    ]

    operations = [
        migrations.AddField(
            model_name='player',
            name='losses',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='player',
            name='rating',
            field=models.IntegerField(default=1000),
        ),
        migrations.AddField(
            model_name='player',
            name='wins',
            field=models.IntegerField(default=0),
        ),
    ]
