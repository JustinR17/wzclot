# Generated by Django 2.1.4 on 2020-04-28 20:17

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('wlct', '0114_auto_20200428_1308'),
    ]

    operations = [
        migrations.AlterField(
            model_name='discordchannelclotbooklink',
            name='discord_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='wlct.DiscordUser'),
        ),
    ]
