# Generated by Django 2.2.4 on 2020-07-02 16:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wlct', '0124_auto_20200604_1957'),
    ]

    operations = [
        migrations.AddField(
            model_name='swisstournament',
            name='extra_rounds',
            field=models.IntegerField(blank=True, default=0, null=True),
        ),
    ]