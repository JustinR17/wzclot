# Generated by Django 2.1.4 on 2020-03-19 22:32

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('wlct', '0082_promotionalrelegationleaguetournament'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tournamentteam',
            name='clan_league_division',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='clan_league_division', to='wlct.ClanLeagueDivision'),
        ),
    ]