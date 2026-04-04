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

    Example:
        judge_id = get_player_id('judge', 'aaron')
    """
    player = pb.playerid_lookup(last_name, first_name)

    if player.empty:
        print(f"No player found for {first_name} {last_name}")
        return None

    mlbam_id = int(player['key_mlbam'].iloc[0])
    print(f"{first_name.title()} {last_name.title()} MLBAM ID: {mlbam_id}")
    return mlbam_id


def get_all_player_names() -> pd.DataFrame:
    """
    Pulls ALL unique pitcher and batter IDs from the pitches table
    and tries to match them with names from the players table.
    Returns a complete ID to name mapping for the entire database.
    This is the master reference used to enrich all query results.
    """
    con = get_connection()

    result = con.execute("""
        WITH all_ids AS (
            -- Get every unique pitcher ID
            SELECT DISTINCT pitcher as mlbam_id
            FROM pitches
            UNION
            -- Get every unique batter ID
            SELECT DISTINCT batter as mlbam_id
            FROM pitches
        )
        SELECT
            a.mlbam_id,
            CASE
                WHEN p.name_first IS NOT NULL
                THEN CONCAT(p.name_first, ' ', p.name_last)
                ELSE CONCAT('ID:', CAST(a.mlbam_id AS VARCHAR))
            END as full_name,
            p.name_first,
            p.name_last
        FROM all_ids a
        LEFT JOIN players p
            ON a.mlbam_id = p.mlbam_id
        ORDER BY p.name_last, p.name_first
    """).df()

    con.close()
    return result


def enrich_with_names(
    df: pd.DataFrame,
    pitcher_col: str = 'pitcher',
    batter_col: str = 'batter'
) -> pd.DataFrame:
    """
    Takes any DataFrame containing pitcher and/or batter ID columns
    and adds human readable name columns next to them.

    This is the core utility function used by all query modules
    to make output readable without manual ID lookups.

    Args:
        df:          Any DataFrame with pitcher or batter ID columns
        pitcher_col: Name of the pitcher ID column (default 'pitcher')
        batter_col:  Name of the batter ID column (default 'batter')

    Example:
        result = pitcher_tendencies(cole_id)
        result = enrich_with_names(result, pitcher_col='pitcher')
    """
    if df.empty:
        return df

    # Get the master name lookup
    names = get_all_player_names()[['mlbam_id', 'full_name']]

    # Add pitcher name if pitcher column exists
    if pitcher_col in df.columns:
        pitcher_names = names.rename(columns={
            'mlbam_id': pitcher_col,
            'full_name': 'pitcher_name'
        })
        df = df.merge(pitcher_names, on=pitcher_col, how='left')

        # Move pitcher_name next to pitcher column
        cols = list(df.columns)
        idx = cols.index(pitcher_col)
        cols.insert(idx + 1, cols.pop(cols.index('pitcher_name')))
        df = df[cols]

    # Add batter name if batter column exists
    if batter_col in df.columns:
        batter_names = names.rename(columns={
            'mlbam_id': batter_col,
            'full_name': 'batter_name'
        })
        df = df.merge(batter_names, on=batter_col, how='left')

        # Move batter_name next to batter column
        cols = list(df.columns)
        idx = cols.index(batter_col)
        cols.insert(idx + 1, cols.pop(cols.index('batter_name')))
        df = df[cols]

    return df


def populate_all_players():
    """
    Looks up and saves ALL unique player IDs in your database
    to the players table so names are available for enrichment.

    This function identifies every pitcher and batter ID in your
    pitches table that doesn't already have a name in the players
    table, then fetches their names from pybaseball in batches.

    Run this once after a large data pull to populate names.
    Warning: This takes 5-10 minutes for a full season of data
    because it makes many individual API calls.
    """
    con = get_connection()

    # Find IDs that don't have names yet
    missing = con.execute("""
        WITH all_ids AS (
            SELECT DISTINCT pitcher as mlbam_id FROM pitches
            UNION
            SELECT DISTINCT batter as mlbam_id FROM pitches
        )
        SELECT a.mlbam_id
        FROM all_ids a
        LEFT JOIN players p ON a.mlbam_id = p.mlbam_id
        WHERE p.mlbam_id IS NULL
          AND a.mlbam_id IS NOT NULL
        ORDER BY a.mlbam_id
    """).df()

    con.close()

    total = len(missing)
    print(f"Found {total} player IDs without names in database")

    if total == 0:
        print("All players already have names — nothing to do")
        return

    print("Fetching names from pybaseball...")
    print("This may take several minutes for large datasets")
    print("-" * 40)

    # Get the master lookup table from pybaseball
    # This single call gets all players at once - much faster
    # than individual lookups
    try:
        all_players = pb.playerid_reverse_lookup(
            list(missing['mlbam_id'].astype(int)),
            key_type='mlbam'
        )

        if all_players.empty:
            print("No players returned from pybaseball lookup")
            return

        con = get_connection()

        saved = 0
        for _, row in all_players.iterrows():
            try:
                con.execute("""
                    INSERT OR REPLACE INTO players
                    (mlbam_id, name_last, name_first,
                     key_bbref, key_fangraphs,
                     mlb_played_first, mlb_played_last)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, [
                    row.get('key_mlbam'),
                    row.get('name_last'),
                    row.get('name_first'),
                    row.get('key_bbref'),
                    row.get('key_fangraphs'),
                    row.get('mlb_played_first'),
                    row.get('mlb_played_last')
                ])
                saved += 1
            except Exception as e:
                continue

        con.close()
        print(f"Successfully saved {saved} player names to database")

    except Exception as e:
        print(f"Error during bulk lookup: {e}")
        print("Try running pull_player_lookup() for individual players instead")


def search_players_in_db(last_name: str) -> pd.DataFrame:
    """
    Searches players already saved in your local database.

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
        print("Try pull_player_lookup() from data_pull.py to add them")
    else:
        print(f"\nPlayers matching '{last_name}':")
        print(result.to_string(index=False))

    return result


def get_active_pitchers_in_db() -> pd.DataFrame:
    """
    Returns all pitchers in your database with names where available.
    """
    con = get_connection()
    result = con.execute("""
        SELECT DISTINCT
            p.pitcher                               as mlbam_id,
            COALESCE(
                CONCAT(pl.name_first, ' ', pl.name_last),
                CONCAT('ID:', CAST(p.pitcher AS VARCHAR))
            )                                       as name,
            COUNT(*)                                as total_pitches,
            COUNT(DISTINCT p.game_date)             as games_in_db,
            MIN(p.game_date)                        as first_game,
            MAX(p.game_date)                        as last_game
        FROM pitches p
        LEFT JOIN players pl ON p.pitcher = pl.mlbam_id
        GROUP BY p.pitcher, pl.name_first, pl.name_last
        ORDER BY total_pitches DESC
    """).df()
    con.close()

    print(f"Pitchers in database: {len(result)}")
    return result


def get_active_batters_in_db() -> pd.DataFrame:
    """
    Returns all batters in your database with names where available.
    """
    con = get_connection()
    result = con.execute("""
        SELECT DISTINCT
            p.batter                                as mlbam_id,
            COALESCE(
                CONCAT(pl.name_first, ' ', pl.name_last),
                CONCAT('ID:', CAST(p.batter AS VARCHAR))
            )                                       as name,
            COUNT(*)                                as total_pitches_seen,
            COUNT(DISTINCT p.game_date)             as games_in_db,
            MIN(p.game_date)                        as first_game,
            MAX(p.game_date)                        as last_game
        FROM pitches p
        LEFT JOIN players pl ON p.batter = pl.mlbam_id
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
    print("  get_all_player_names()")
    print("  enrich_with_names(df, pitcher_col, batter_col)")
    print("  populate_all_players()")
    print("  search_players_in_db(last_name)")
    print("  get_active_pitchers_in_db()")
    print("  get_active_batters_in_db()")