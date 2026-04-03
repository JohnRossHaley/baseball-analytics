"""
player_lookup.py
Player ID resolution and search utilities.
Used to find MLBAM IDs needed for all other queries.
"""

import pandas as pd
import pybaseball as pb
from src.database import get_connection


def find_player(last_name: str, first_name: str) -> pd.DataFrame:
    """
    Look up a player's MLBAM ID and all associated IDs.
    Use this to find the ID needed for matchup and tendency queries.

    Example:
        find_player('judge', 'aaron')
        find_player('degrom', 'jacob')
    """
    player = pb.playerid_lookup(last_name, first_name)

    if player.empty:
        print(f"No player found for {first_name} {last_name}")
        return None

    # Show the most useful columns clearly
    display_cols = [
        'name_first', 'name_last',
        'key_mlbam', 'key_bbref',
        'key_fangraphs', 'mlb_played_first',
        'mlb_played_last'
    ]

    available = [c for c in display_cols if c in player.columns]
    print(f"\nPlayer found: {first_name.title()} {last_name.title()}")
    print(player[available].to_string(index=False))
    print(f"\nUse key_mlbam as the ID in all queries")

    return player


def get_player_id(last_name: str, first_name: str) -> int:
    """
    Returns just the MLBAM ID for a player as an integer.
    Useful when you just need the ID to pass into another function.

    Example:
        judge_id = get_player_id('judge', 'aaron')
        batter_tendencies(judge_id)
    """
    player = pb.playerid_lookup(last_name, first_name)

    if player.empty:
        print(f"No player found for {first_name} {last_name}")
        return None

    mlbam_id = int(player['key_mlbam'].iloc[0])
    print(f"{first_name.title()} {last_name.title()} MLBAM ID: {mlbam_id}")
    return mlbam_id


def search_players_in_db(last_name: str) -> pd.DataFrame:
    """
    Searches players already saved in your local database.
    Faster than pybaseball lookup for players you've already pulled.

    Example:
        search_players_in_db('judge')
    """
    con = get_connection()
    result = con.execute(f"""
        SELECT
            mlbam_id,
            name_first,
            name_last,
            key_bbref,
            mlb_played_first,
            mlb_played_last
        FROM players
        WHERE LOWER(name_last) LIKE LOWER('%{last_name}%')
        ORDER BY mlb_played_last DESC
    """).df()
    con.close()

    if result.empty:
        print(f"No players found in database matching '{last_name}'")
        print("Try pull_player_lookup() from data_pull.py to add them first")
    else:
        print(f"\nPlayers matching '{last_name}':")
        print(result.to_string(index=False))

    return result


def get_active_pitchers_in_db() -> pd.DataFrame:
    """
    Returns all pitchers currently stored in your database
    who appear in the pitches table.
    Useful for knowing who you can run analysis on.
    """
    con = get_connection()
    result = con.execute("""
        SELECT DISTINCT
            p.pitcher                   as mlbam_id,
            pl.name_first,
            pl.name_last,
            COUNT(*)                    as total_pitches,
            COUNT(DISTINCT p.game_date) as games_in_db,
            MIN(p.game_date)            as first_game,
            MAX(p.game_date)            as last_game
        FROM pitches p
        LEFT JOIN players pl
            ON p.pitcher = pl.mlbam_id
        GROUP BY p.pitcher, pl.name_first, pl.name_last
        ORDER BY total_pitches DESC
    """).df()
    con.close()

    print(f"Pitchers in database: {len(result)}")
    return result


def get_active_batters_in_db() -> pd.DataFrame:
    """
    Returns all batters currently stored in your database
    who appear in the pitches table.
    """
    con = get_connection()
    result = con.execute("""
        SELECT DISTINCT
            p.batter                    as mlbam_id,
            pl.name_first,
            pl.name_last,
            COUNT(*)                    as total_pitches_seen,
            COUNT(DISTINCT p.game_date) as games_in_db,
            MIN(p.game_date)            as first_game,
            MAX(p.game_date)            as last_game
        FROM pitches p
        LEFT JOIN players pl
            ON p.batter = pl.mlbam_id
        GROUP BY p.batter, pl.name_first, pl.name_last
        ORDER BY total_pitches_seen DESC
    """).df()
    con.close()

    print(f"Batters in database: {len(result)}")
    return result


if __name__ == "__main__":
    print("Player lookup module ready")
    print("Available functions:")
    print("  find_player(last_name, first_name)")
    print("  get_player_id(last_name, first_name)")
    print("  search_players_in_db(last_name)")
    print("  get_active_pitchers_in_db()")
    print("  get_active_batters_in_db()")
    print()
    print("Example usage:")
    print("  find_player('judge', 'aaron')")
    print("  id = get_player_id('degrom', 'jacob')")