"""
main.py
Entry point for the baseball analytics system.

How to use:
    Run daily:     run_report('ARI')
    Update data:   update_to_today()
    Ad hoc:        ad_hoc()
"""

from datetime import date, timedelta


# ─────────────────────────────────────────────────────────────
# SETUP
# Run once when starting fresh on a new machine
# ─────────────────────────────────────────────────────────────

def setup():
    """
    Initializes all database tables.
    Safe to run multiple times — uses IF NOT EXISTS.
    """
    from src.database import initialize_database
    initialize_database()
    print("Database initialized")


# ─────────────────────────────────────────────────────────────
# DAILY DATA UPDATE
# Run each morning — pulls yesterday's games automatically
# Baseball Savant typically posts by 10am ET
# ─────────────────────────────────────────────────────────────

def update_to_today():
    """
    Finds the most recent date in your database and pulls
    everything from that date through yesterday.
    Safe to run daily — skips dates already loaded.
    Also refreshes current season leaderboards.
    """
    from src.data_pull import pull_statcast_range, build_bullpen_usage
    from src.database import get_connection
    from src.season_data import (
        pull_pitching_leaderboard,
        pull_batting_leaderboard
    )

    con = get_connection()
    last_date = con.execute(
        "SELECT MAX(game_date) FROM pitches"
    ).fetchone()[0]
    con.close()

    if last_date is None:
        print("No data found — run setup() first")
        return

    start = str(last_date + timedelta(days=1))
    end   = str(date.today() - timedelta(days=1))

    if start > end:
        print(f"Already current through {last_date}")
        return

    print(f"Pulling {start} through {end}...")
    pull_statcast_range(start, end)
    build_bullpen_usage()

    current_year = date.today().year
    pull_pitching_leaderboard(current_year, qual=1)
    pull_batting_leaderboard(current_year, qual=5)

    print("Update complete")


# ─────────────────────────────────────────────────────────────
# SEASON DATA
# Standings, FanGraphs leaderboards, team schedules
# Re-run a few times per season to refresh
# ─────────────────────────────────────────────────────────────

def pull_season_data(year: int = None):
    """
    Pulls standings, pitching and batting leaderboards,
    and team schedule for the given year and prior year.

    Args:
        year: Season year — defaults to current year

    Example:
        pull_season_data()
        pull_season_data(2025)
    """
    from src.season_data import (
        pull_standings,
        pull_pitching_leaderboard,
        pull_batting_leaderboard,
        pull_schedule
    )

    target = year or date.today().year
    prev   = target - 1

    print(f"Pulling {prev} and {target} season data...")

    pull_standings(prev)
    pull_pitching_leaderboard(prev,   qual=50)
    pull_batting_leaderboard(prev,    qual=100)
    pull_pitching_leaderboard(target, qual=1)
    pull_batting_leaderboard(target,  qual=5)

    # Update schedules — add any team you care about
    pull_schedule(prev,   'NYY')
    pull_schedule(target, 'NYY')
    pull_schedule(prev,   'ARI')
    pull_schedule(target, 'ARI')

    print("Season data complete")


# ─────────────────────────────────────────────────────────────
# DAILY REPORT
# The main output — run each morning before games
# Pulls the full slate, weather, and full matchup analysis
# for whichever team you specify as focus_team
# ─────────────────────────────────────────────────────────────

def run_report(focus_team: str = 'ARI',
               game_date:  str = None,
               season:     int = None):
    """
    Generates the full daily intelligence report.

    Outputs:
    - Full MLB slate with live scores
    - Weather for every outdoor park on the slate
    - Lineup danger ranking for the focus team's starter
      vs the opposing lineup
    - Full pitcher profile with arsenal, velocity trends,
      and count tendencies
    - Batter by batter matchup breakdown with head to head
      career history where available
    - Opposing pitcher profile and your lineup ranked
      against them by danger score

    Args:
        focus_team: Team abbreviation to run full matchup for
                    Defaults to 'ARI'
        game_date:  'YYYY-MM-DD' — defaults to today
        season:     Data filter. None = all seasons in database
                    (recommended for larger samples).
                    Pass a year e.g. 2025 to limit to one season.

    Examples:
        run_report('ARI')
        run_report('LAD', season=2025)
        run_report('NYY', game_date='2026-04-05')
    """
    from src.daily_report import run_daily_report

    run_daily_report(
        focus_team=focus_team,
        game_date=game_date,
        season=season,
        include_weather=True,
        include_matchup=True,
        min_batter_pitches=50
    )


# ─────────────────────────────────────────────────────────────
# POPULATE PLAYER NAMES
# Run after any large Statcast data pull to add names
# to all new player IDs found in the pitches table
# ─────────────────────────────────────────────────────────────

def populate_names():
    """
    Looks up names for all player IDs in your database
    that don't have a name yet.
    Run after pulling a new season of Statcast data.
    Takes 5-10 minutes for a full season.
    """
    from src.player_lookup import populate_all_players
    populate_all_players()


# ─────────────────────────────────────────────────────────────
# AD HOC ANALYSIS
# Sandbox for manual queries — no hardcoded player names
# Use get_player_id() to look up any player dynamically
# ─────────────────────────────────────────────────────────────

def ad_hoc():
    """
    Sandbox for one-off analysis and exploration.
    All player lookups are dynamic — no hardcoded names.

    Examples of what you can run here:
    - Matchup reports for any pitcher vs any lineup
    - Season over season comparisons
    - Rest day splits
    - Home away splits
    - Leaderboard queries
    - Bullpen availability for any team
    """
    from src.player_lookup import get_player_id
    from src.matchup_report import quick_matchup
    from src.analytics import (
        season_over_season_pivot,
        home_away_splits,
        pitcher_rest_day_splits,
        leaderboard_query,
        pitcher_comparison_pivot,
        batter_comparison_pivot
    )
    from src.bullpen_monitor import bullpen_availability
    from src.matchup_queries import (
        pitcher_tendencies,
        batter_tendencies,
        print_head_to_head
    )

    # ── Look up any player by name ────────────────────────
    # pitcher_id = get_player_id('soroka',  'michael')
    # batter_id  = get_player_id('carroll', 'corbin')

    # ── Quick matchup report ──────────────────────────────
    # quick_matchup(
    #     pitcher_last='soroka',
    #     pitcher_first='michael',
    #     batter_last_first_pairs=[
    #         ('freeman', 'freddie'),
    #         ('betts',   'mookie'),
    #         ('ohtani',  'shohei')
    #     ],
    #     custom_notes={
    #         'freddie freeman': 'Your observation here'
    #     }
    # )

    # ── Season over season ────────────────────────────────
    # pid = get_player_id('glasnow', 'tyler')
    # print(season_over_season_pivot(pitcher_id=pid)
    #       .to_string(index=False))

    # ── Home away splits ──────────────────────────────────
    # bid = get_player_id('carroll', 'corbin')
    # print(home_away_splits(batter_id=bid)
    #       .to_string(index=False))

    # ── Rest day splits ───────────────────────────────────
    # pid = get_player_id('elder', 'bryce')
    # print(pitcher_rest_day_splits(pid)
    #       .to_string(index=False))

    # ── Pitcher tendencies ────────────────────────────────
    # pid = get_player_id('luzardo', 'jesus')
    # print(pitcher_tendencies(pid).to_string(index=False))

    # ── Head to head history ──────────────────────────────
    # p = get_player_id('soroka',  'michael')
    # b = get_player_id('freeman', 'freddie')
    # print_head_to_head(p, b)

    # ── Leaderboards ──────────────────────────────────────
    # top_fip = leaderboard_query(2025, 'fip', 'pitcher', 10)
    # print(top_fip[['name','team','era','fip','k_per_9','war']]
    #       .to_string(index=False))

    # top_war = leaderboard_query(2025, 'war', 'batter', 10)
    # print(top_war[['name','team','batting_avg','obp',
    #                'slg','woba','wrc_plus','war']]
    #       .to_string(index=False))

    # ── Bullpen availability ──────────────────────────────
    # print(bullpen_availability("ARI").to_string(index=False))

    # ── Pitcher comparison ────────────────────────────────
    # p1 = get_player_id('glasnow', 'tyler')
    # p2 = get_player_id('soroka',  'michael')
    # print(pitcher_comparison_pivot([p1, p2], season=2025)
    #       .to_string(index=False))

    # ── Batter comparison ─────────────────────────────────
    # b1 = get_player_id('carroll', 'corbin')
    # b2 = get_player_id('walker',  'christian')
    # print(batter_comparison_pivot([b1, b2], season=2025)
    #       .to_string(index=False))

    pass


# ─────────────────────────────────────────────────────────────
# ENTRY POINT
# Comment and uncomment what you need
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # ── Run each morning ──────────────────────────────────
    update_to_today()

    # ── Refresh season data periodically ─────────────────
    # pull_season_data()

    # ── Add player names after large data pulls ───────────
    # populate_names()

    # ── Daily report — primary output ────────────────────
    # season=None uses all seasons for larger samples
    # run_report(
    #     focus_team='DET',
    #     season=None
    # )

    # ── Ad hoc queries ────────────────────────────────────
    # ad_hoc()