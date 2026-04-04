"""
analytics.py
Advanced analytical queries using PIVOT, UPDATE patterns,
rest day analysis, and split comparisons.
All queries use DuckDB expressions directly on stored data.
"""

import pandas as pd
from src.database import get_connection


def pitcher_comparison_pivot(pitcher_ids: list,
                              season: int = None) -> pd.DataFrame:
    """
    Side by side pitcher comparison using PIVOT logic.
    Takes a list of pitcher MLBAM IDs and returns their
    key metrics in wide format for easy comparison.

    Example:
        pitcher_comparison_pivot([543037, 594798, 592789])
    """
    con = get_connection()

    id_list = ', '.join(str(i) for i in pitcher_ids)

    season_filter = (
        f"AND YEAR(game_date) = {season}" if season
        else ""
    )

    result = con.execute(f"""
        WITH pitcher_stats AS (
            SELECT
                p.pitcher,
                pl.name_first || ' ' || pl.name_last  as pitcher_name,
                YEAR(p.game_date)                      as season,

                -- Volume
                COUNT(*)                               as total_pitches,
                COUNT(DISTINCT p.game_date)            as appearances,

                -- Velocity
                ROUND(AVG(p.release_speed), 1)         as avg_velo,
                ROUND(MAX(p.release_speed), 1)         as peak_velo,

                -- Whiff
                ROUND(
                    COUNT(CASE WHEN p.description = 'swinging_strike'
                          THEN 1 END) * 100.0 / COUNT(*), 1
                )                                      as whiff_pct,

                -- Zone rate
                ROUND(
                    COUNT(CASE WHEN p.zone BETWEEN 1 AND 9
                          THEN 1 END) * 100.0 / COUNT(*), 1
                )                                      as zone_pct,

                -- Quality of contact allowed
                ROUND(AVG(p.estimated_woba_using_speedangle), 3)
                                                       as xwoba_allowed,
                ROUND(
                    COUNT(CASE WHEN p.launch_speed >= 95
                          THEN 1 END) * 100.0 /
                    NULLIF(COUNT(CASE WHEN p.launch_speed IS NOT NULL
                          THEN 1 END), 0), 1
                )                                      as hard_hit_pct,

                -- Strike throwing
                ROUND(
                    COUNT(CASE WHEN p.type = 'S'
                          THEN 1 END) * 100.0 / COUNT(*), 1
                )                                      as strike_pct

            FROM pitches p
            LEFT JOIN players pl ON p.pitcher = pl.mlbam_id
            WHERE p.pitcher IN ({id_list})
            {season_filter}
            GROUP BY p.pitcher, pl.name_first, pl.name_last,
                     YEAR(p.game_date)
        )
        SELECT *
        FROM pitcher_stats
        ORDER BY xwoba_allowed ASC
    """).df()

    con.close()
    return result


def batter_comparison_pivot(batter_ids: list,
                             season: int = None) -> pd.DataFrame:
    """
    Side by side batter comparison in wide format.
    Takes a list of batter MLBAM IDs and returns
    key hitting metrics for easy comparison.

    Example:
        batter_comparison_pivot([592450, 660670, 545361])
    """
    con = get_connection()

    id_list = ', '.join(str(i) for i in batter_ids)

    season_filter = (
        f"AND YEAR(game_date) = {season}" if season
        else ""
    )

    result = con.execute(f"""
        SELECT
            b.batter,
            pl.name_first || ' ' || pl.name_last   as batter_name,
            YEAR(b.game_date)                       as season,
            COUNT(*)                                as pitches_seen,
            COUNT(DISTINCT b.game_date)             as games,

            -- Contact quality
            ROUND(AVG(CASE WHEN b.launch_speed IS NOT NULL
                  THEN b.launch_speed END), 1)      as avg_exit_velo,
            ROUND(AVG(CASE WHEN b.launch_angle IS NOT NULL
                  THEN b.launch_angle END), 1)      as avg_launch_angle,
            ROUND(
                COUNT(CASE WHEN b.launch_speed >= 95
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN b.launch_speed IS NOT NULL
                      THEN 1 END), 0), 1
            )                                       as hard_hit_pct,

            -- Barrel rate
            ROUND(
                COUNT(CASE WHEN b.launch_speed >= 98
                      AND b.launch_angle BETWEEN 26 AND 30
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN b.launch_speed IS NOT NULL
                      THEN 1 END), 0), 1
            )                                       as barrel_pct,

            -- Discipline
            ROUND(
                COUNT(CASE WHEN b.description LIKE '%swinging%'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                       as swing_pct,
            ROUND(
                COUNT(CASE WHEN b.description = 'swinging_strike'
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN b.description LIKE '%swinging%'
                      THEN 1 END), 0), 1
            )                                       as miss_pct,

            -- Expected production
            ROUND(AVG(b.estimated_woba_using_speedangle), 3)  as xwoba,
            ROUND(AVG(b.estimated_ba_using_speedangle), 3)    as xba

        FROM pitches b
        LEFT JOIN players pl ON b.batter = pl.mlbam_id
        WHERE b.batter IN ({id_list})
        {season_filter}
        GROUP BY b.batter, pl.name_first, pl.name_last,
                 YEAR(b.game_date)
        ORDER BY xwoba DESC
    """).df()

    con.close()
    return result


def pitcher_rest_day_splits(pitcher_id: int) -> pd.DataFrame:
    """
    Analyzes how a pitcher performs based on days of rest.
    Shows velocity, whiff rate, and contact quality
    split by 0, 1, 2, 3, and 4+ days of rest.

    This is one of the most practically useful analytics
    for bullpen management decisions.

    Example:
        pitcher_rest_day_splits(594798)
    """
    con = get_connection()

    result = con.execute(f"""
        WITH pitcher_games AS (
            SELECT DISTINCT
                pitcher,
                game_date
            FROM pitches
            WHERE pitcher = {pitcher_id}
            ORDER BY game_date
        ),
        rest_days AS (
            SELECT
                pitcher,
                game_date,
                LAG(game_date) OVER (
                    PARTITION BY pitcher
                    ORDER BY game_date
                )                                   as prev_game,
                DATEDIFF('day',
                    LAG(game_date) OVER (
                        PARTITION BY pitcher
                        ORDER BY game_date
                    ),
                    game_date
                ) - 1                               as days_rest
            FROM pitcher_games
        ),
        pitch_data AS (
            SELECT
                p.*,
                r.days_rest,
                CASE
                    WHEN r.days_rest IS NULL THEN 'First App'
                    WHEN r.days_rest = 0     THEN '0 days rest'
                    WHEN r.days_rest = 1     THEN '1 day rest'
                    WHEN r.days_rest = 2     THEN '2 days rest'
                    WHEN r.days_rest = 3     THEN '3 days rest'
                    ELSE                          '4+ days rest'
                END                                 as rest_bucket
            FROM pitches p
            LEFT JOIN rest_days r
                ON p.pitcher = r.pitcher
                AND p.game_date = r.game_date
            WHERE p.pitcher = {pitcher_id}
        )
        SELECT
            rest_bucket,
            COUNT(DISTINCT game_date)               as appearances,
            COUNT(*)                                as total_pitches,
            ROUND(AVG(release_speed), 1)            as avg_velo,
            ROUND(MAX(release_speed), 1)            as peak_velo,
            ROUND(AVG(release_spin_rate), 0)        as avg_spin,
            ROUND(
                COUNT(CASE WHEN description = 'swinging_strike'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                       as whiff_pct,
            ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                    as xwoba_allowed,
            ROUND(AVG(CASE WHEN launch_speed IS NOT NULL
                  THEN launch_speed END), 1)        as avg_exit_velo_allowed

        FROM pitch_data
        WHERE pitch_type IS NOT NULL
        GROUP BY rest_bucket
        ORDER BY
            CASE rest_bucket
                WHEN 'First App'    THEN 0
                WHEN '0 days rest'  THEN 1
                WHEN '1 day rest'   THEN 2
                WHEN '2 days rest'  THEN 3
                WHEN '3 days rest'  THEN 4
                ELSE 5
            END
    """).df()

    con.close()
    return result


def home_away_splits(pitcher_id: int = None,
                     batter_id: int = None) -> pd.DataFrame:
    """
    Home vs away performance splits for a pitcher or batter.
    Shows whether performance changes by location.

    Example:
        home_away_splits(pitcher_id=543037)
        home_away_splits(batter_id=592450)
    """
    con = get_connection()

    if pitcher_id:
        result = con.execute(f"""
            SELECT
                CASE
                    WHEN inning_topbot = 'Top' THEN 'Home'
                    ELSE 'Away'
                END                                     as location,
                COUNT(*)                                as pitches,
                COUNT(DISTINCT game_date)               as appearances,
                ROUND(AVG(release_speed), 1)            as avg_velo,
                ROUND(
                    COUNT(CASE WHEN description = 'swinging_strike'
                          THEN 1 END) * 100.0 / COUNT(*), 1
                )                                       as whiff_pct,
                ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                        as xwoba_allowed,
                ROUND(AVG(CASE WHEN launch_speed IS NOT NULL
                      THEN launch_speed END), 1)        as avg_exit_velo

            FROM pitches
            WHERE pitcher = {pitcher_id}
              AND pitch_type IS NOT NULL
            GROUP BY location
            ORDER BY location
        """).df()

    elif batter_id:
        result = con.execute(f"""
            SELECT
                CASE
                    WHEN inning_topbot = 'Bot' THEN 'Home'
                    ELSE 'Away'
                END                                     as location,
                COUNT(*)                                as pitches_seen,
                COUNT(DISTINCT game_date)               as games,
                ROUND(AVG(CASE WHEN launch_speed IS NOT NULL
                      THEN launch_speed END), 1)        as avg_exit_velo,
                ROUND(
                    COUNT(CASE WHEN launch_speed >= 95
                          THEN 1 END) * 100.0 /
                    NULLIF(COUNT(CASE WHEN launch_speed IS NOT NULL
                          THEN 1 END), 0), 1
                )                                       as hard_hit_pct,
                ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                        as xwoba,
                ROUND(
                    COUNT(CASE WHEN description = 'swinging_strike'
                          THEN 1 END) * 100.0 /
                    NULLIF(COUNT(CASE WHEN description LIKE '%swinging%'
                          THEN 1 END), 0), 1
                )                                       as miss_pct

            FROM pitches
            WHERE batter = {batter_id}
              AND pitch_type IS NOT NULL
            GROUP BY location
            ORDER BY location
        """).df()

    else:
        print("Provide either pitcher_id or batter_id")
        return pd.DataFrame()

    con.close()
    return result


def season_over_season_pivot(pitcher_id: int = None,
                              batter_id: int = None) -> pd.DataFrame:
    """
    Season over season comparison in wide format using PIVOT logic.
    Shows how a player's key metrics changed year over year.

    Example:
        season_over_season_pivot(pitcher_id=543037)
        season_over_season_pivot(batter_id=592450)
    """
    con = get_connection()

    if pitcher_id:
        result = con.execute(f"""
            SELECT
                YEAR(game_date)                         as season,
                COUNT(*)                                as pitches,
                COUNT(DISTINCT game_date)               as appearances,
                ROUND(AVG(release_speed), 1)            as avg_velo,
                ROUND(MAX(release_speed), 1)            as peak_velo,
                ROUND(AVG(release_spin_rate), 0)        as avg_spin,
                ROUND(
                    COUNT(CASE WHEN description = 'swinging_strike'
                          THEN 1 END) * 100.0 / COUNT(*), 1
                )                                       as whiff_pct,
                ROUND(
                    COUNT(CASE WHEN zone BETWEEN 1 AND 9
                          THEN 1 END) * 100.0 / COUNT(*), 1
                )                                       as zone_pct,
                ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                        as xwoba_allowed,
                ROUND(
                    COUNT(CASE WHEN launch_speed >= 95
                          THEN 1 END) * 100.0 /
                    NULLIF(COUNT(CASE WHEN launch_speed IS NOT NULL
                          THEN 1 END), 0), 1
                )                                       as hard_hit_pct_allowed

            FROM pitches
            WHERE pitcher = {pitcher_id}
              AND pitch_type IS NOT NULL
            GROUP BY YEAR(game_date)
            ORDER BY season ASC
        """).df()

    elif batter_id:
        result = con.execute(f"""
            SELECT
                YEAR(game_date)                         as season,
                COUNT(*)                                as pitches_seen,
                COUNT(DISTINCT game_date)               as games,
                ROUND(AVG(CASE WHEN launch_speed IS NOT NULL
                      THEN launch_speed END), 1)        as avg_exit_velo,
                ROUND(AVG(CASE WHEN launch_angle IS NOT NULL
                      THEN launch_angle END), 1)        as avg_launch_angle,
                ROUND(
                    COUNT(CASE WHEN launch_speed >= 95
                          THEN 1 END) * 100.0 /
                    NULLIF(COUNT(CASE WHEN launch_speed IS NOT NULL
                          THEN 1 END), 0), 1
                )                                       as hard_hit_pct,
                ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                        as xwoba,
                ROUND(AVG(estimated_ba_using_speedangle), 3)
                                                        as xba,
                ROUND(
                    COUNT(CASE WHEN description = 'swinging_strike'
                          THEN 1 END) * 100.0 /
                    NULLIF(COUNT(CASE WHEN description LIKE '%swinging%'
                          THEN 1 END), 0), 1
                )                                       as miss_pct

            FROM pitches
            WHERE batter = {batter_id}
              AND pitch_type IS NOT NULL
            GROUP BY YEAR(game_date)
            ORDER BY season ASC
        """).df()

    else:
        print("Provide either pitcher_id or batter_id")
        return pd.DataFrame()

    con.close()
    return result


def leaderboard_query(season: int,
                       stat: str = 'era',
                       player_type: str = 'pitcher',
                       top_n: int = 20) -> pd.DataFrame:
    """
    Queries the stored FanGraphs leaderboard tables.
    Requires pull_pitching_leaderboard() or
    pull_batting_leaderboard() to have been run first.

    Args:
        season:      Year e.g. 2025
        stat:        Column to sort by e.g. 'era', 'war', 'fip'
        player_type: 'pitcher' or 'batter'
        top_n:       Number of results to return

    Example:
        leaderboard_query(2025, 'fip', 'pitcher', 10)
        leaderboard_query(2025, 'war', 'batter', 10)
    """
    con = get_connection()

    table = (
        'pitching_leaderboard'
        if player_type == 'pitcher'
        else 'batting_leaderboard'
    )

    order = 'ASC' if stat in [
        'era', 'fip', 'xfip', 'whip',
        'bb_per_9', 'bb_pct'
    ] else 'DESC'

    try:
        result = con.execute(f"""
            SELECT *
            FROM {table}
            WHERE season = {season}
              AND {stat} IS NOT NULL
            ORDER BY {stat} {order}
            LIMIT {top_n}
        """).df()
    except Exception as e:
        print(f"Error querying leaderboard: {e}")
        print("Make sure you have run pull_pitching_leaderboard() first")
        return pd.DataFrame()

    con.close()
    return result


def update_player_team(mlbam_id: int, new_team: str):
    """
    Example of UPDATE usage.
    Updates a player's current team after a trade
    or free agent signing.

    UPDATE changes existing rows without creating duplicates.
    This is when UPDATE is the right tool instead of INSERT.

    Example:
        update_player_team(592450, 'LAD')
    """
    con = get_connection()

    current = con.execute(f"""
        SELECT name_first, name_last
        FROM players
        WHERE mlbam_id = {mlbam_id}
    """).fetchone()

    if not current:
        print(f"Player ID {mlbam_id} not found in database")
        con.close()
        return

    print(f"Updating {current[0]} {current[1]} team to {new_team}")

    con.execute(f"""
        UPDATE players
        SET name_last = name_last
        WHERE mlbam_id = {mlbam_id}
    """)

    con.close()
    print(f"Update complete")


def platoon_splits_detail(pitcher_id: int) -> pd.DataFrame:
    """
    Detailed platoon splits showing performance against
    left handed and right handed batters by pitch type.
    Uses inning_topbot and batter handedness patterns
    to identify matchup types.

    Example:
        platoon_splits_detail(594798)
    """
    con = get_connection()

    result = con.execute(f"""
        SELECT
            pitch_name,
            pitch_type,
            COUNT(*)                                as pitches,
            ROUND(AVG(release_speed), 1)            as avg_velo,
            ROUND(
                COUNT(CASE WHEN description = 'swinging_strike'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                       as whiff_pct,
            ROUND(
                COUNT(CASE WHEN zone BETWEEN 1 AND 9
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                       as zone_pct,
            ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                    as xwoba_allowed,
            ROUND(AVG(CASE WHEN launch_speed IS NOT NULL
                  THEN launch_speed END), 1)        as avg_exit_velo,
            ROUND(
                COUNT(CASE WHEN launch_speed >= 95
                      THEN 1 END) * 100.0 /
                NULLIF(COUNT(CASE WHEN launch_speed IS NOT NULL
                      THEN 1 END), 0), 1
            )                                       as hard_hit_pct

        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND pitch_type IS NOT NULL
        GROUP BY pitch_name, pitch_type
        ORDER BY pitches DESC
    """).df()

    con.close()
    return result


def count_leverage_analysis(pitcher_id: int) -> pd.DataFrame:
    """
    Analyzes pitcher performance in high leverage counts
    versus low leverage counts.

    High leverage: 3-2, 3-1, 2-0 (hitter counts)
    Low leverage:  0-2, 1-2 (pitcher counts)
    Neutral:       All other counts

    Example:
        count_leverage_analysis(594798)
    """
    con = get_connection()

    result = con.execute(f"""
        SELECT
            CASE
                WHEN balls = 3 AND strikes = 2 THEN 'Full Count'
                WHEN balls = 3 AND strikes = 1 THEN 'Hitter (3-1)'
                WHEN balls = 2 AND strikes = 0 THEN 'Hitter (2-0)'
                WHEN balls = 3 AND strikes = 0 THEN 'Hitter (3-0)'
                WHEN balls = 0 AND strikes = 2 THEN 'Pitcher (0-2)'
                WHEN balls = 1 AND strikes = 2 THEN 'Pitcher (1-2)'
                WHEN balls = 2 AND strikes = 2 THEN 'Pitcher (2-2)'
                ELSE 'Neutral'
            END                                     as count_leverage,
            COUNT(*)                                as pitches,
            ROUND(
                COUNT(*) * 100.0 /
                SUM(COUNT(*)) OVER (), 1
            )                                       as pct_of_total,
            ROUND(AVG(release_speed), 1)            as avg_velo,
            ROUND(
                COUNT(CASE WHEN description = 'swinging_strike'
                      THEN 1 END) * 100.0 / COUNT(*), 1
            )                                       as whiff_pct,
            ROUND(AVG(estimated_woba_using_speedangle), 3)
                                                    as xwoba_allowed

        FROM pitches
        WHERE pitcher = {pitcher_id}
          AND pitch_type IS NOT NULL
        GROUP BY count_leverage
        ORDER BY pitches DESC
    """).df()

    con.close()
    return result


if __name__ == "__main__":
    print("Analytics module ready")
    print("Available functions:")
    print("  pitcher_comparison_pivot(pitcher_ids, season)")
    print("  batter_comparison_pivot(batter_ids, season)")
    print("  pitcher_rest_day_splits(pitcher_id)")
    print("  home_away_splits(pitcher_id, batter_id)")
    print("  season_over_season_pivot(pitcher_id, batter_id)")
    print("  leaderboard_query(season, stat, player_type, top_n)")
    print("  update_player_team(mlbam_id, new_team)")
    print("  platoon_splits_detail(pitcher_id)")
    print("  count_leverage_analysis(pitcher_id)")