"""
season_data.py
Pulls and stores season level data including schedule,
standings, team stats, and FanGraphs leaderboards.
"""

import pandas as pd
import pybaseball as pb
from src.database import get_connection


def pull_schedule(season: int, team: str) -> pd.DataFrame:
    """
    Pulls full season schedule and results for a team
    and stores in the schedule table.

    Example:
        pull_schedule(2025, 'NYY')
        pull_schedule(2026, 'ARI')
    """
    print(f"Pulling {season} schedule for {team}...")

    try:
        df = pb.schedule_and_record(season, team)
    except Exception as e:
        print(f"  Error pulling schedule: {e}")
        return pd.DataFrame()

    if df.empty:
        print(f"  No data found for {team} {season}")
        return df

    con = get_connection()

    # Clear existing data for this team/season
    con.execute(f"""
        DELETE FROM schedule
        WHERE team = '{team}'
          AND season = {season}
    """)

    inserted = 0
    skipped  = 0
    errors   = []

    for idx, row in df.iterrows():
        try:
            def safe_str(val):
                if val is None: return None
                if pd.isna(val) if not isinstance(
                        val, str) else False: return None
                return str(val).strip() or None

            def safe_int(val):
                if val is None: return None
                try:
                    if pd.isna(val): return None
                except Exception:
                    pass
                try:
                    return int(float(str(val)))
                except Exception:
                    return None

            def safe_float(val):
                if val is None: return None
                try:
                    if pd.isna(val): return None
                except Exception:
                    pass
                try:
                    return float(str(val))
                except Exception:
                    return None

            # GB — handle 'Tied', 'up X', numeric
            gb_raw = row.get('GB')
            games_back = None
            if gb_raw is not None:
                try:
                    if not pd.isna(gb_raw):
                        gb_str = str(gb_raw).strip()
                        if gb_str not in ('', 'Tied'):
                            if gb_str.startswith('up '):
                                games_back = -float(
                                    gb_str.replace('up ', '')
                                )
                            else:
                                games_back = float(gb_str)
                except Exception:
                    games_back = None

            con.execute("""
                            INSERT INTO schedule (
                                season, team, date, home_away,
                                opponent, result, runs_scored,
                                runs_allowed, innings, win_loss_record,
                                rank, games_back, winning_pitcher,
                                losing_pitcher, save_pitcher,
                                time, day_night, attendance, streak
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                      ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, [
                int(season),
                str(team),
                safe_str(row.get('Date')),
                safe_str(row.get('Home_Away')),
                safe_str(row.get('Opp')),
                safe_str(row.get('W/L')),
                safe_int(row.get('R')),
                safe_int(row.get('RA')),
                safe_int(row.get('Inn')) or 9,
                safe_str(row.get('W-L')),
                safe_int(row.get('Rank')),
                games_back,
                safe_str(row.get('Win')),
                safe_str(row.get('Loss')),
                safe_str(row.get('Save')),
                safe_str(row.get('Time')),
                safe_str(row.get('D/N')),
                safe_int(row.get('Attendance')),
                safe_str(row.get('Streak')),
            ])
            inserted += 1

        except Exception as e:
            skipped += 1
            errors.append(f"Row {idx}: {e}")
            continue

    con.close()

    print(f"  Stored {inserted} games | "
          f"Skipped {skipped} for {team} {season}")

    # Show first error if any skips occurred
    if errors:
        print(f"  First error: {errors[0]}")

    return df

def pull_standings(season: int) -> pd.DataFrame:
    """
    Pulls division standings for a given season.
    Returns combined standings across all divisions.

    Example:
        pull_standings(2025)
    """
    print(f"Pulling {season} standings...")

    try:
        division_standings = pb.standings(season)
    except Exception as e:
        print(f"Error pulling standings: {e}")
        return pd.DataFrame()

    division_names = [
        'AL East', 'AL Central', 'AL West',
        'NL East', 'NL Central', 'NL West'
    ]

    all_standings = []

    for i, df in enumerate(division_standings):
        division = (
            division_names[i]
            if i < len(division_names)
            else f'Division {i}'
        )
        df['division'] = division
        df['season'] = season
        all_standings.append(df)

    combined = pd.concat(all_standings, ignore_index=True)

    combined.columns = [
        c.lower().replace(' ', '_').replace('/', '_')
        for c in combined.columns
    ]

    print(f"Pulled standings for {len(combined)} teams")

    if 'tm' in combined.columns:
        print(combined[['tm', 'w', 'l', 'division']].to_string(
            index=False))

    con = get_connection()
    try:
        for _, row in combined.iterrows():
            con.execute("""
                INSERT OR REPLACE INTO standings
                (season, team, wins, losses, win_pct, division)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [
                season,
                row.get('tm'),
                row.get('w'),
                row.get('l'),
                row.get('w_l_'),
                row.get('division')
            ])
    except Exception as e:
        print(f"Note storing standings: {e}")
    con.close()

    return combined


def pull_pitching_leaderboard(season: int,
                               qual: int = 50) -> pd.DataFrame:
    """
    Pulls FanGraphs pitching leaderboard for a season.
    Uses exact column names returned by pybaseball.

    Example:
        pull_pitching_leaderboard(2025)
        pull_pitching_leaderboard(2026, qual=20)
    """
    print(f"Pulling {season} pitching leaderboard...")

    try:
        df = pb.pitching_stats(season, qual=qual)
    except Exception as e:
        print(f"Error pulling pitching leaderboard: {e}")
        return pd.DataFrame()

    if df.empty:
        print("No pitching data returned")
        return df

    print(f"Pulled {len(df)} qualified pitchers for {season}")

    # Exact column names as returned by pybaseball
    # Verified from live column inspection
    column_map = {
        'IDfg':     'player_id',
        'Name':     'name',
        'Team':     'team',
        'W':        'wins',
        'L':        'losses',
        'ERA':      'era',
        'G':        'games',
        'GS':       'gs',
        'IP':       'innings_pitched',
        'SO':       'strikeouts',
        'BB':       'walks',
        'HR':       'home_runs',
        'WHIP':     'whip',
        'FIP':      'fip',
        'xFIP':     'xfip',
        'K/9':      'k_per_9',
        'BB/9':     'bb_per_9',
        'K%':       'k_pct',
        'BB%':      'bb_pct',
        'LOB%':     'lob_pct',
        'GB%':      'gb_pct',
        'HR/FB':    'hr_per_fb',
        'BABIP':    'babip',
        'WAR':      'war',
        'xERA':     'xera',
        'SIERA':    'siera',
        'SwStr%':   'swstr_pct',
        'Hard%':    'hard_pct',
        'Barrel%':  'barrel_pct',
        'HardHit%': 'hardhit_pct',
        'EV':       'avg_exit_velo',
        'Stuff+':   'stuff_plus',
        'Location+': 'location_plus',
        'Pitching+': 'pitching_plus'
    }

    # Only keep columns that exist in the dataframe
    available = {k: v for k, v in column_map.items() if k in df.columns}
    df_store = df[list(available.keys())].rename(columns=available)
    df_store['season'] = season

    con = get_connection()

    saved = 0
    for _, row in df_store.iterrows():
        try:
            con.execute("""
                INSERT OR REPLACE INTO pitching_leaderboard
                (season, player_id, name, team, wins, losses,
                 era, games, gs, innings_pitched, strikeouts,
                 walks, home_runs, whip, fip, xfip,
                 k_per_9, bb_per_9, k_pct, bb_pct,
                 lob_pct, gb_pct, hr_per_fb, babip, war)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                season,
                row.get('player_id'),
                row.get('name'),
                row.get('team'),
                row.get('wins'),
                row.get('losses'),
                row.get('era'),
                row.get('games'),
                row.get('gs'),
                row.get('innings_pitched'),
                row.get('strikeouts'),
                row.get('walks'),
                row.get('home_runs'),
                row.get('whip'),
                row.get('fip'),
                row.get('xfip'),
                row.get('k_per_9'),
                row.get('bb_per_9'),
                row.get('k_pct'),
                row.get('bb_pct'),
                row.get('lob_pct'),
                row.get('gb_pct'),
                row.get('hr_per_fb'),
                row.get('babip'),
                row.get('war')
            ])
            saved += 1
        except Exception:
            continue

    con.close()
    print(f"Stored {saved} pitchers in leaderboard for {season}")
    return df_store


def pull_batting_leaderboard(season: int,
                              qual: int = 100) -> pd.DataFrame:
    """
    Pulls FanGraphs batting leaderboard for a season.
    Uses exact column names returned by pybaseball.

    Example:
        pull_batting_leaderboard(2025)
        pull_batting_leaderboard(2026, qual=30)
    """
    print(f"Pulling {season} batting leaderboard...")

    try:
        df = pb.batting_stats(season, qual=qual)
    except Exception as e:
        print(f"Error pulling batting leaderboard: {e}")
        return pd.DataFrame()

    if df.empty:
        print("No batting data returned")
        return df

    print(f"Pulled {len(df)} qualified batters for {season}")

    # Exact column names as returned by pybaseball
    # Verified from live column inspection
    column_map = {
        'IDfg':      'player_id',
        'Name':      'name',
        'Team':      'team',
        'G':         'games',
        'PA':        'pa',
        'AB':        'ab',
        'H':         'hits',
        'HR':        'home_runs',
        'RBI':       'rbi',
        'SB':        'stolen_bases',
        'AVG':       'batting_avg',
        'OBP':       'obp',
        'SLG':       'slg',
        'OPS':       'ops',
        'wOBA':      'woba',
        'wRC+':      'wrc_plus',
        'BABIP':     'babip',
        'BB%':       'bb_pct',
        'K%':        'k_pct',
        'Hard%':     'hard_hit_pct',
        'EV':        'avg_exit_velo',
        'Barrel%':   'barrel_pct',
        'HardHit%':  'hardhit_pct',
        'WAR':       'war',
        'xBA':       'xba',
        'xSLG':      'xslg',
        'xwOBA':     'xwoba',
        'SwStr%':    'swstr_pct',
        'Pull%':     'pull_pct',
        'Cent%':     'cent_pct',
        'Oppo%':     'oppo_pct',
        'maxEV':     'max_exit_velo',
        'Barrels':   'barrels',
        'L-WAR':     'l_war'
    }

    available = {k: v for k, v in column_map.items() if k in df.columns}
    df_store = df[list(available.keys())].rename(columns=available)
    df_store['season'] = season

    con = get_connection()

    saved = 0
    for _, row in df_store.iterrows():
        try:
            con.execute("""
                INSERT OR REPLACE INTO batting_leaderboard
                (season, player_id, name, team, games, pa, ab,
                 hits, home_runs, rbi, stolen_bases,
                 batting_avg, obp, slg, ops, woba,
                 wrc_plus, babip, k_pct, bb_pct,
                 hard_hit_pct, avg_exit_velo, barrel_pct, war)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                season,
                row.get('player_id'),
                row.get('name'),
                row.get('team'),
                row.get('games'),
                row.get('pa'),
                row.get('ab'),
                row.get('hits'),
                row.get('home_runs'),
                row.get('rbi'),
                row.get('stolen_bases'),
                row.get('batting_avg'),
                row.get('obp'),
                row.get('slg'),
                row.get('ops'),
                row.get('woba'),
                row.get('wrc_plus'),
                row.get('babip'),
                row.get('k_pct'),
                row.get('bb_pct'),
                row.get('hard_hit_pct'),
                row.get('avg_exit_velo'),
                row.get('barrel_pct'),
                row.get('war')
            ])
            saved += 1
        except Exception:
            continue

    con.close()
    print(f"Stored {saved} batters in leaderboard for {season}")
    return df_store


if __name__ == "__main__":
    print("Season data module ready")
    print("Available functions:")
    print("  pull_schedule(season, team)")
    print("  pull_standings(season)")
    print("  pull_pitching_leaderboard(season, qual)")
    print("  pull_batting_leaderboard(season, qual)")