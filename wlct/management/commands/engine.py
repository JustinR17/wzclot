# the main engine for the scheduler
import threading
import datetime
from wlct.logging import log, LogLevel, log_exception, Logger, TournamentLog
from bs4 import BeautifulSoup
from urllib.request import urlopen
from wlct.models import Clan, Engine, Player
from wlct.tournaments import ClanLeague, ClanLeagueTournament, find_tournament_by_id, Tournament, TournamentGame, TournamentPlayer, TournamentTeam, TournamentGameEntry, MonthlyTemplateRotation, MonthlyTemplateRotationMonth, TestContent
from django.conf import settings
from wlct.api import API
from django import db
import pytz
import threading
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from apscheduler.schedulers.background import BlockingScheduler
from apscheduler.jobstores.base import ConflictingIdError
from django_apscheduler.jobstores import DjangoJobStore
from django.core.management.base import BaseCommand
import gc
from django.utils import timezone

def get_run_time():
    return 180

class Command(BaseCommand):
    help = "Runs the engine for cleaning up logs and creating new tournament games every 180 seconds"
    def handle(self, *args, **options):
        self.schedule_jobs()

    def schedule_jobs(self):
        # lookup the main scheduler, if it's not currently scheduled, add it every 3 min
        try:
            scheduler = BlockingScheduler()
            # If you want all scheduled jobs to use this store by default,
            # use the name 'default' instead of 'djangojobstore'.
            scheduler.add_jobstore(DjangoJobStore(), 'default')
            if not scheduler.running:
                scheduler.add_job(tournament_engine, 'interval', seconds=get_run_time(), id='tournament_engine',
                                  max_instances=1, coalesce=False)
                scheduler.add_job(tournament_caching, 'interval', seconds=get_run_time()*2, id='tournament_caching',
                                  max_instances=1, coalesce=False)
                scheduler.add_job(cl_tournament_games_validation(), 'interval', seconds=get_run_time(), id='cl_tournament_games_validation',
                                  max_instances=1, coalesce=False)
                scheduler.start()
        except ConflictingIdError:
            pass

def parse_and_update_clan_logo():
    try:
        url = 'https://www.warzone.com/Clans/List'
        clan_page = urlopen(url)

        text_soup = BeautifulSoup(clan_page, features="html.parser")

        log("Refreshing clans", LogLevel.engine)
        links = text_soup.findAll("a")
        for link in links:
            try:
                clan_id = link.attrs["href"].split('=')[1]
                clan_href = link.attrs["href"]
                if '/Clans' in clan_href:
                    clan_name = link.contents[2].strip()
                    image = link.findAll("img")[0].attrs["src"]
                    clan_exist = Clan.objects.filter(name=clan_name)
                    if not clan_exist:
                        clan = Clan(name=clan_name, icon_link=clan_href, image_path=image)
                        clan.save()
                        log("Added new clan: {}".format(clan_name), LogLevel.engine)
                    elif clan_exist and clan_exist[0].image_path != image:  # updated image code path
                        clan_exist[0].image_path = image
                        clan_exist[0].save()
            except:
                continue
    except Exception:
        log_exception()

def is_correct_player(player_token, player_team):
    try:
        player = Player.objects.filter(token=player_token)[0]
        tt = TournamentTeam.objects.filter(pk=player_team)[0]
        if player.clan and player.clan.name == tt.clan_league_clan.clan.name:
            return True

        tplayers = TournamentPlayer.objects.filter(team=tt)
        for tplayer in tplayers:
            if tplayer.player.token == player_token:
                return True
        return False
    except:
        log_exception()
        return False


def is_valid_team_order(team_order, team_dict, teams):
    for i in range(len(team_order)):
        for player in team_dict[team_order[i]]:
            if is_correct_player(player, teams[i]):
                return True
    return False

def get_clan_league_games():
    cl_games = TournamentGame.objects.none()
    for cl in ClanLeague.objects.filter(has_started=True, is_official=True):
        for cl_tournament in ClanLeagueTournament.objects.filter(parent_tournament=cl):
            cl_games |= TournamentGame.objects.filter(tournament=cl_tournament, is_finished=False)
    return cl_games


def validate_cl_tournament_games():
    try:
        print("Running validate_cl_tournament_games on thread {}".format(threading.get_ident()))
        tournament_games = get_clan_league_games()
        api = API()
        found_missing_games = 0
        corrected_missing_games = 0
        test_content = TestContent()

        # Iterate through unfinished games and check of missing player values
        for game in tournament_games:
            if not game.players:
                log("Found TournamentGame missing 'players' value with id: {}".format(game.id), LogLevel.engine)
                found_missing_games += 1
                teams = game.teams.split('.')
                test_msg = test_content.team_game(teams[0], teams[1])
                api_response = api.api_query_game_feed(game.gameid, test_msg).json()

                # Add player tokens by team
                team_dict = {}
                team_order = []
                for player in api_response.get("players"):
                    if "team" in player:
                        if not player["team"] in team_dict:
                            team_dict[player["team"]] = []
                            team_order.append(player["team"])
                        team_dict[player["team"]].append(player["id"])
                    else:
                        if not len(team_dict) in team_dict:
                            team_dict[len(team_dict)] = []
                            team_order.append(len(team_dict))
                        team_dict[len(team_dict) - 1].append(player["id"])
                # Check if team order matches with player and clan object on clot
                if not is_valid_team_order(team_order, team_dict, teams):
                    log("Possibly incorrect team order... Attempting reversing teams - TGame ID: {}".format(game.id), LogLevel.warning)
                    team_order.reverse()
                    if not is_valid_team_order(team_order, team_dict, teams):
                        log("Possibly incorrect team order... Using original order - TGame ID: {}".format(game.id), LogLevel.warning)
                        team_order.reverse()
                    else:
                        log("Correct team order found - TGame ID: {}".format(game.id), LogLevel.engine)
                else:
                    log("Correct team order found - TGame ID: {}".format(game.id), LogLevel.engine)

                # Combine player tokens in each team
                team_player_token_list = []
                for team in team_order:
                    team_player_token_list.append(".".join(team_dict[team]))

                # Set players value in TournamentGame with player tokens
                game.players = "-".join(team_player_token_list)
                game.save()
                if game.players:
                    corrected_missing_games += 1
        log("TournamentGames count with missing 'players' value: {}".format(found_missing_games), LogLevel.engine)
        if found_missing_games > 0:
            log("TournamentGames corrected count with missing 'players' value: {}".format(corrected_missing_games), LogLevel.engine)
    except Exception as ex:
        log_exception()


def check_games(**kwargs):
    print("Running check_games, type={} on thread {}".format(kwargs['type'], threading.get_ident()))
    caching = kwargs['type'] == 'cache'
    tournaments = Tournament.objects.filter(has_started=True, is_finished=False)
    for tournament in tournaments:
        child_tournament = find_tournament_by_id(tournament.id, True)
        if child_tournament and child_tournament.should_process_in_engine():
            log("Checking games for tournament: {}".format(tournament.name), LogLevel.engine)
            try:
                if child_tournament.update_in_progress and not caching:
                    continue
                elif not child_tournament.game_creation_allowed and not caching:
                    continue
                child_tournament.update_in_progress = True
                child_tournament.save()
                games = TournamentGame.objects.filter(is_finished=False, tournament=tournament)
                log("Processing {} games for tournament {}".format(games.count(), tournament.name), LogLevel.engine)
                for game in games.iterator():
                    # process the game
                    # query the game status
                    if not caching:
                        child_tournament.process_game(game)
                # in case tournaments get stalled for some reason
                # for it to process new games based on current tournament data
                if not caching:
                    child_tournament.process_new_games()

                # after we process games we always cache the latest data for quick reads
                if caching:
                    log("Caching data for {}".format(tournament.name), LogLevel.engine)
                    child_tournament.cache_data()
            except Exception as e:
                log_exception()
            finally:
                child_tournament.update_in_progress = False
                child_tournament.save()
        gc.collect()

def cleanup_logs():
    # get all the logs older than 2 days
    nowdate = datetime.datetime.now(tz=pytz.UTC)
    enddate = nowdate - datetime.timedelta(days=2)
    logs = Logger.objects.filter(timestamp__lt=enddate)
    for log_obj in logs.iterator():
        log_obj.delete()
        gc.collect()

        # only get 3 minutes to run, the engine must continue
        time_spent = datetime.datetime.now(tz=pytz.UTC) - nowdate
        if time_spent.total_seconds() >= get_run_time():
            log("Returned early from cleaning up logs, spent {} seconds cleaning.".format(time_spent.total_seconds()), LogLevel.engine)
            return

    if logs:
        log("Cleaned up {} logs.".format(logs.count()), LogLevel.engine)

    tournament_logs = TournamentLog.objects.filter(timestamp__lt=enddate)
    for tournament_log in tournament_logs.iterator():
        tournament_log.delete()
        gc.collect()

        # only get 3 minutes to run, the engine must continue
        time_spent = datetime.datetime.now(tz=pytz.UTC) - nowdate
        if time_spent.total_seconds() >= get_run_time():
            log("Returned early from cleaning up logs, spent {} seconds cleaning.".format(time_spent.total_seconds()),
                LogLevel.engine)
            return

    if tournament_logs:
        log("Cleaned up {} tournament logs.".format(tournament_logs.count()), LogLevel.engine)


def check_leagues():
    # placeholder to check league statuses
    pass

def check_bot_data():
    # placeholder to update the bot data cache
    pass

def validate_game_entries():
    # loop through all game entries not finished....query the games and see if they are...
    # these should have been finished in finish_game...but for some reason are not
    tournaments = MonthlyTemplateRotation.objects.all()
    for tournament in tournaments:
        print("Looking at MTC: {}".format(tournament.name))
        current_month = tournament.get_current_month()
        # grab all the games and game entries in that month
        games = TournamentGame.objects.filter(tournament=tournament)
        for game in games:
            print("Getting game entries for game {} between {}/{} which is finished: {}".format(game.id, game.teams.split('.')[0], game.teams.split('.')[1], game.is_finished))
            # get the game entries associated with this game
            entries = TournamentGameEntry.objects.filter(game=game, tournament=tournament)
            for entry in entries:
                print("Found Game Entry: Game: {}, Entry: {}".format(game, entry))
                if not entry.is_finished and game.is_finished:
                    print("Updating game entry")
                    entry.is_finished = True
                    entry.save()


# globals to get executed on every load of the web server
slow_update_threshold = 25
current_clan_update = 1

def cl_tournament_games_validation():
    validate_cl_tournament_games()

def tournament_caching():
    check_games(type='cache')
    cleanup_logs()

def tournament_engine():
    try:
        global slow_update_threshold
        global current_clan_update

        if (current_clan_update % slow_update_threshold) == 0:
            parse_and_update_clan_logo()
            current_clan_update = 1
        else:
            current_clan_update += 1

        engine = Engine.objects.all()
        if engine and engine.count() == 0:
            # create the engine object!
            engine = Engine()
            engine.save()
        else:
            engine = engine[0]
            engine.last_run_time = timezone.now()
            engine.next_run_time = timezone.now() + datetime.timedelta(seconds=get_run_time())
            engine.save()

        # bulk of the logic, we handle all types of tournaments separately here
        # there must be logic for each tournament type, as the child class contains
        # the logic
        #validate_game_entries()
        check_games(type='process')
    except Exception as e:
        log_exception()
    finally:
        finished_time = timezone.now()
        next_run = timezone.now() + datetime.timedelta(seconds=get_run_time())
        total_run_time = (finished_time - engine.last_run_time).total_seconds()
        log("Engine done running at {}, ran for a total of {} seconds. Next run at {}".format(finished_time, total_run_time, next_run),
            LogLevel.engine)
        engine.last_run_time = finished_time
        engine.next_run_time = next_run
        engine.save()

        pass