"""
main.py
Entry point for the baseball analytics system.
"""
from datetime import date, timedelta
from src.database import initialize_database
from src.data_pull import (
    pull_statcast_range,
    pull_player_lookup,
    build_bullpen_usage
)
from src.matchup_queries import (
    pitcher_vs_batter,
    pitcher_tendencies,
    batter_tendencies
)
from src.bullpen_monitor import bullpen_availability
from src.player_lookup import get_player_id, populate_all_players
from src.metrics import calculate_fip, calculate_whip
from src.season_data import (
    pull_standings,
    pull_pitching_leaderboard,
    pull_batting_leaderboard,
    pull_schedule
)
from src.analytics import (
    pitcher_comparison_pivot,
    batter_comparison_pivot,
    pitcher_rest_day_splits,
    home_away_splits,
    season_over_season_pivot,
    leaderboard_query
)
from src.matchup_report import quick_matchup
from src.daily_slate import (
    get_todays_slate,
    print_slate,
    get_probable_pitchers,
    build_game_matchup_inputs
)

def pull_season_level_data():
    """
    Pulls standings, leaderboards, and schedule data.
    Run this after Statcast data is loaded.
    """
    print("=" * 50)
    print("PULLING SEASON LEVEL DATA")
    print("=" * 50)

    # 2025 standings
    print("\n[1/7] Pulling 2025 standings...")
    pull_standings(2025)

    # 2025 pitching leaderboard
    print("\n[2/7] Pulling 2025 pitching leaderboard...")
    pull_pitching_leaderboard(2025, qual=50)

    # 2025 batting leaderboard
    print("\n[3/7] Pulling 2025 batting leaderboard...")
    pull_batting_leaderboard(2025, qual=100)

    # 2026 pitching leaderboard - lower qual since season just started
    print("\n[4/7] Pulling 2026 pitching leaderboard...")
    pull_pitching_leaderboard(2026, qual=1)

    # 2026 batting leaderboard - lower qual since season just started
    print("\n[5/7] Pulling 2026 batting leaderboard...")
    pull_batting_leaderboard(2026, qual=5)

    # Yankees 2025 schedule
    print("\n[6/7] Pulling Yankees 2025 schedule...")
    pull_schedule(2025, 'NYY')

    # Yankees 2026 schedule
    print("\n[7/7] Pulling Yankees 2026 schedule...")
    pull_schedule(2026, 'NYY')

    print("\n" + "=" * 50)
    print("SEASON DATA PULL COMPLETE")
    print("=" * 50)


def sample_analysis():
    """
    Sample analysis showcasing all system capabilities.
    """
    print("=" * 50)
    print("RUNNING SAMPLE ANALYSIS")
    print("=" * 50)

    # Player IDs
    cole_id = get_player_id("cole", "gerrit")
    judge_id = get_player_id("judge", "aaron")
    degrom_id = get_player_id("degrom", "jacob")
    ohtani_id = get_player_id("ohtani", "shohei")

    # ── Pitcher comparison pivot ──────────────────
    print("\nPitcher comparison - Cole vs deGrom:")
    if cole_id and degrom_id:
        comparison = pitcher_comparison_pivot(
            [cole_id, degrom_id], season=2025
        )
        print(comparison.to_string(index=False))

    # ── Batter comparison pivot ───────────────────
    print("\nBatter comparison - Judge vs Ohtani:")
    if judge_id and ohtani_id:
        comparison = batter_comparison_pivot(
            [judge_id, ohtani_id], season=2025
        )
        print(comparison.to_string(index=False))

    # ── Rest day splits ───────────────────────────
    print("\ndeGrom rest day splits:")
    if degrom_id:
        rest = pitcher_rest_day_splits(degrom_id)
        if rest.empty:
            print("No data available")
        else:
            print(rest.to_string(index=False))

    # ── Home away splits ──────────────────────────
    print("\nAaron Judge home vs away:")
    if judge_id:
        splits = home_away_splits(batter_id=judge_id)
        print(splits.to_string(index=False))

    # ── Season over season ────────────────────────
    print("\nJudge season over season:")
    if judge_id:
        sos = season_over_season_pivot(batter_id=judge_id)
        print(sos.to_string(index=False))

    # ── Leaderboard queries ───────────────────────
    print("\n2025 Top 10 pitchers by FIP:")
    top_fip = leaderboard_query(2025, 'fip', 'pitcher', 10)
    if top_fip.empty:
        print("Run pull_season_level_data() first")
    else:
        print(top_fip[['name', 'team', 'era', 'fip',
                        'xfip', 'k_per_9', 'war']].to_string(index=False))

    print("\n2025 Top 10 batters by WAR:")
    top_war = leaderboard_query(2025, 'war', 'batter', 10)
    if top_war.empty:
        print("Run pull_season_level_data() first")
    else:
        print(top_war[['name', 'team', 'batting_avg', 'obp',
                        'slg', 'woba', 'wrc_plus',
                        'war']].to_string(index=False))

    # ── Bullpen availability ──────────────────────
    print("\nSox bullpen availability:")
    availability = bullpen_availability("CHC")
    print(availability.to_string(index=False))

    print("\n" + "=" * 50)
    print("ANALYSIS COMPLETE")
    print("=" * 50)

def update_to_today():
    """
    Pulls the most recent available Statcast data.
    Run this daily to keep database current.
    Baseball Savant typically has data available
    by 10am the morning after games are played.
    """
    from datetime import date, timedelta
    from src.data_pull import pull_statcast_range, build_bullpen_usage
    from src.database import get_connection

    # Find most recent date already in database
    con = get_connection()
    last_date = con.execute(
        "SELECT MAX(game_date) FROM pitches"
    ).fetchone()[0]
    con.close()

    if last_date is None:
        print("No data in database - run full setup first")
        return

    # Pull from day after last date through yesterday
    start = str(last_date + timedelta(days=1))
    end = str(date.today() - timedelta(days=1))

    if start > end:
        print(f"Database already current through {last_date}")
        return

    print(f"Updating database from {start} to {end}")
    pull_statcast_range(start, end)
    build_bullpen_usage()

    # Update leaderboards with latest data
    from src.season_data import (
        pull_pitching_leaderboard,
        pull_batting_leaderboard
    )
    current_year = date.today().year
    pull_pitching_leaderboard(current_year, qual=1)
    pull_batting_leaderboard(current_year, qual=5)

    print("Database update complete")


if __name__ == "__main__":
    # Uncomment what you need to run

    # pull_statcast_range("2021-04-01", "2021-10-03")

    # Run analysis
    # sample_analysis()
    # Test matchup report
    # quick_matchup(
    #     pitcher_last='degrom',
    #     pitcher_first='jacob',
    #     batter_last_first_pairs=[
    #         ('judge', 'aaron'),
    #         ('ohtani', 'shohei'),
    #         ('betts', 'mookie')
    #     ],
    #     season=2025,
    #     game_date='2026-04-05',
    #     custom_notes={
    #         'aaron judge': 'Has been pulling off on breaking '
    #                        'balls early in counts — look for '
    #                        'deGrom to establish slider in '
    #                        'and work fastball away late',
    #         'shohei ohtani': 'Historically struggles vs elite '
    #                           'spin — deGrom curveball could '
    #                           'be the primary weapon here'
    #     }
    # )
    # update_to_today()
    # Pull today's slate
    # games = get_todays_slate()
    # print_slate(games)
    #
    # print()
    # get_probable_pitchers()
    #
    # from src.daily_slate import build_game_matchup_inputs
    # from src.matchup_report import generate_matchup_report
    #
    # # Pull today's slate and Yankees game
    # inputs = build_game_matchup_inputs('NYY')
    #
    # if inputs and inputs['opp_batter_ids']:
    #     generate_matchup_report(
    #         pitcher_id=inputs['our_pitcher_id'],
    #         batter_ids=inputs['opp_batter_ids'],
    #         game_date=inputs['game_date'],
    #         season=2025,
    #         custom_notes={},
    #         min_pitches_filter=50
    #     )