"""
daily_slate.py
Pulls today's MLB game slate from the MLB Stats API.
Includes probable pitchers, game status, scores,
venue info, and feeds into the matchup report pipeline.

MLB Stats API is free and requires no API key.
Data is typically available by 10am ET each day.
"""

import requests
import pandas as pd
from datetime import date, datetime
from src.database import get_connection
from src.player_lookup import get_player_id


# ─────────────────────────────────────────────────────────
# MLB TEAM ID TO ABBREVIATION MAPPING
# Used to connect MLB API team IDs to your database
# ─────────────────────────────────────────────────────────
MLB_TEAM_MAP = {
    133: 'OAK', 134: 'PIT', 135: 'SD',  136: 'SEA',
    137: 'SF',  138: 'STL', 139: 'TB',  140: 'TEX',
    141: 'TOR', 142: 'MIN', 143: 'PHI', 144: 'ATL',
    145: 'CWS', 146: 'MIA', 147: 'NYY', 158: 'MIL',
    108: 'LAA', 109: 'ARI', 110: 'BAL', 111: 'BOS',
    112: 'CHC', 113: 'CIN', 114: 'CLE', 115: 'COL',
    116: 'DET', 117: 'HOU', 118: 'KC',  119: 'LAD',
    120: 'WSH', 121: 'NYM'
}

# Stadium coordinates for weather and travel calculation
STADIUM_COORDS = {
    'OAK': (37.7516, -122.2005), 'PIT': (40.4469, -80.0057),
    'SD':  (32.7076, -117.1570), 'SEA': (47.5914, -122.3325),
    'SF':  (37.7786, -122.3893), 'STL': (38.6226, -90.1928),
    'TB':  (27.7682, -82.6534), 'TEX': (32.7473, -97.0832),
    'TOR': (43.6414, -79.3894), 'MIN': (44.9817, -93.2781),
    'PHI': (39.9061, -75.1665), 'ATL': (33.8908, -84.4678),
    'CWS': (41.8299, -87.6338), 'MIA': (25.7781, -80.2197),
    'NYY': (40.8296, -73.9262), 'MIL': (43.0280, -87.9712),
    'LAA': (33.8003, -117.8827),'ARI': (33.4453, -112.0667),
    'BAL': (39.2838, -76.6218), 'BOS': (42.3467, -71.0972),
    'CHC': (41.9484, -87.6553), 'CIN': (39.0979, -84.5082),
    'CLE': (41.4962, -81.6852), 'COL': (39.7559, -104.9942),
    'DET': (42.3390, -83.0485), 'HOU': (29.7573, -95.3555),
    'KC':  (39.0517, -94.4803), 'LAD': (34.0739, -118.2400),
    'WSH': (38.8730, -77.0074), 'NYM': (40.7571, -73.8458)
}

# Dome/retractable roof stadiums
# Weather less relevant for these
DOME_STADIUMS = {'TB', 'MIA', 'ARI', 'MIL', 'HOU', 'SEA', 'TOR'}


def get_todays_slate(game_date: str = None) -> list:
    """
    Pulls the full game slate from MLB Stats API
    for a given date.

    Args:
        game_date: 'YYYY-MM-DD' string, defaults to today

    Returns:
        List of game dictionaries with full context

    Example:
        slate = get_todays_slate()
        slate = get_todays_slate('2026-04-04')
    """
    target_date = game_date or str(date.today())

    print(f"Pulling MLB slate for {target_date}...")

    url = (
        f"https://statsapi.mlb.com/api/v1/schedule"
        f"?date={target_date}"
        f"&sportId=1"
        f"&hydrate=probablePitcher,team,linescore,venue"
    )

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error fetching slate: {e}")
        return []

    if not data.get('dates'):
        print(f"No games found for {target_date}")
        return []

    games_raw = data['dates'][0].get('games', [])
    print(f"Found {len(games_raw)} games on {target_date}")

    games = []
    for g in games_raw:
        try:
            game = _parse_game(g)
            if game:
                games.append(game)
        except Exception as e:
            print(f"Error parsing game: {e}")
            continue

    return games


def _parse_game(g: dict) -> dict:
    """
    Parses a single game from the MLB API response
    into a clean structured dictionary.
    """
    teams = g.get('teams', {})
    away = teams.get('away', {})
    home = teams.get('home', {})
    status = g.get('status', {})
    linescore = g.get('linescore', {})
    venue = g.get('venue', {})

    # Team info
    away_team = away.get('team', {})
    home_team = home.get('team', {})

    away_id = away_team.get('id')
    home_id = home_team.get('id')
    away_abbr = MLB_TEAM_MAP.get(away_id, away_team.get('abbreviation', '???'))
    home_abbr = MLB_TEAM_MAP.get(home_id, home_team.get('abbreviation', '???'))

    # Probable pitchers
    away_pitcher = away.get('probablePitcher', {})
    home_pitcher = home.get('probablePitcher', {})

    # Game time - convert UTC to readable format
    game_date_str = g.get('gameDate', '')
    game_time = 'TBD'
    if game_date_str:
        try:
            dt = datetime.strptime(
                game_date_str, '%Y-%m-%dT%H:%M:%SZ'
            )
            # Convert UTC to ET (subtract 4 hours)
            from datetime import timedelta
            dt_et = dt - timedelta(hours=4)
            game_time = dt_et.strftime('%-I:%M %p ET')
        except Exception:
            game_time = game_date_str

    # Current score if in progress or final
    away_score = away.get('score')
    home_score = home.get('score')

    # Records
    away_record = away.get('leagueRecord', {})
    home_record = home.get('leagueRecord', {})

    # Inning info
    current_inning = linescore.get('currentInningOrdinal', '')
    inning_state = linescore.get('inningState', '')
    game_state = status.get('abstractGameState', 'Preview')
    detailed_state = status.get('detailedState', '')

    # Venue
    venue_name = venue.get('name', home_team.get('venue', {}).get('name', ''))

    # Is dome
    is_dome = home_abbr in DOME_STADIUMS

    return {
        'game_pk':          g.get('gamePk'),
        'game_date':        g.get('officialDate'),
        'game_time':        game_time,
        'game_state':       game_state,
        'detailed_state':   detailed_state,
        'inning':           f"{inning_state} {current_inning}".strip(),

        # Away team
        'away_abbr':        away_abbr,
        'away_name':        away_team.get('name', ''),
        'away_pitcher_id':  away_pitcher.get('id'),
        'away_pitcher':     away_pitcher.get('fullName', 'TBD'),
        'away_score':       away_score,
        'away_wins':        away_record.get('wins', 0),
        'away_losses':      away_record.get('losses', 0),

        # Home team
        'home_abbr':        home_abbr,
        'home_name':        home_team.get('name', ''),
        'home_pitcher_id':  home_pitcher.get('id'),
        'home_pitcher':     home_pitcher.get('fullName', 'TBD'),
        'home_score':       home_score,
        'home_wins':        home_record.get('wins', 0),
        'home_losses':      home_record.get('losses', 0),

        # Venue
        'venue':            venue_name,
        'is_dome':          is_dome,
        'coords':           STADIUM_COORDS.get(home_abbr),
    }


def print_slate(games: list, show_scores: bool = True):
    """
    Prints a clean formatted daily slate.

    Args:
        games:       List from get_todays_slate()
        show_scores: Show live scores for in progress games
    """
    if not games:
        print("No games to display")
        return

    date_str = games[0]['game_date'] if games else str(date.today())
    print(f"\n{'═' * 65}")
    print(f"  MLB DAILY SLATE — {date_str}")
    print(f"{'═' * 65}")

    # Group by game state
    preview = [g for g in games if g['game_state'] == 'Preview']
    live = [g for g in games if g['game_state'] == 'Live']
    final = [g for g in games if g['game_state'] == 'Final']

    # Live games first
    if live:
        print(f"\n  🔴 LIVE ({len(live)} games)")
        print(f"  {'─' * 62}")
        for g in live:
            _print_game_row(g, show_score=show_scores)

    # Upcoming games
    if preview:
        print(f"\n  📅 UPCOMING ({len(preview)} games)")
        print(f"  {'─' * 62}")
        for g in preview:
            _print_game_row(g, show_score=False)

    # Final games
    if final:
        print(f"\n  ✅ FINAL ({len(final)} games)")
        print(f"  {'─' * 62}")
        for g in final:
            _print_game_row(g, show_score=show_scores)

    print(f"\n{'═' * 65}")


def _print_game_row(g: dict, show_score: bool = True):
    """Prints a single formatted game row."""
    away = g['away_abbr']
    home = g['home_abbr']
    away_pitcher = g['away_pitcher']
    home_pitcher = g['home_pitcher']
    venue = g['venue']
    away_rec = f"({g['away_wins']}-{g['away_losses']})"
    home_rec = f"({g['home_wins']}-{g['home_losses']})"
    dome = " [DOME]" if g['is_dome'] else ""

    if show_score and g['away_score'] is not None:
        score = f"{g['away_score']}-{g['home_score']}"
        inning = g['inning']
        print(f"  {away} {away_rec} @ {home} {home_rec} "
              f"| {score} {inning}")
    else:
        print(f"  {away} {away_rec} @ {home} {home_rec} "
              f"| {g['game_time']}")

    print(f"    SP: {away_pitcher} vs {home_pitcher}")
    print(f"    📍 {venue}{dome}")
    print()


def get_slate_as_dataframe(game_date: str = None) -> pd.DataFrame:
    """
    Returns today's slate as a pandas DataFrame.
    Useful for further analysis and filtering.

    Example:
        df = get_slate_as_dataframe()
        yankees_game = df[df['away_abbr'] == 'NYY']
    """
    games = get_todays_slate(game_date)
    if not games:
        return pd.DataFrame()
    return pd.DataFrame(games)


def get_game_for_team(team_abbr: str,
                      game_date: str = None) -> dict:
    """
    Returns the game entry for a specific team on a given date.

    Args:
        team_abbr: Team abbreviation e.g. 'NYY', 'LAD'
        game_date: Date string, defaults to today

    Example:
        game = get_game_for_team('NYY')
        game = get_game_for_team('LAD', '2026-04-05')
    """
    games = get_todays_slate(game_date)

    for game in games:
        if (game['away_abbr'] == team_abbr.upper() or
                game['home_abbr'] == team_abbr.upper()):
            return game

    print(f"No game found for {team_abbr} on "
          f"{game_date or str(date.today())}")
    return {}


def get_probable_pitchers(game_date: str = None) -> pd.DataFrame:
    """
    Returns a clean DataFrame of all probable pitchers
    for a given date with their MLBAM IDs.

    Useful for feeding directly into the matchup report.

    Example:
        pitchers = get_probable_pitchers()
    """
    games = get_todays_slate(game_date)

    if not games:
        return pd.DataFrame()

    rows = []
    for g in games:
        rows.append({
            'game_pk':      g['game_pk'],
            'game_time':    g['game_time'],
            'away_team':    g['away_abbr'],
            'away_pitcher': g['away_pitcher'],
            'away_pitcher_id': g['away_pitcher_id'],
            'home_team':    g['home_abbr'],
            'home_pitcher': g['home_pitcher'],
            'home_pitcher_id': g['home_pitcher_id'],
            'venue':        g['venue'],
            'is_dome':      g['is_dome']
        })

    df = pd.DataFrame(rows)
    print(f"\nProbable Pitchers — "
          f"{game_date or str(date.today())}")
    print(df[['game_time', 'away_team', 'away_pitcher',
              'home_team', 'home_pitcher']].to_string(index=False))
    return df


def get_roster(team_id: int) -> list:
    """
    Pulls the current 26-man active roster for a team
    from the MLB Stats API.

    Args:
        team_id: MLB team ID (from MLB_TEAM_MAP values reversed)

    Returns:
        List of player dictionaries with id and name
    """
    url = (
        f"https://statsapi.mlb.com/api/v1/teams/"
        f"{team_id}/roster?rosterType=active"
    )

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error fetching roster: {e}")
        return []

    roster = []
    for player in data.get('roster', []):
        person = player.get('person', {})
        position = player.get('position', {})
        roster.append({
            'mlbam_id':     person.get('id'),
            'name':         person.get('fullName'),
            'position':     position.get('abbreviation'),
            'position_type': position.get('type')
        })

    return roster


def get_lineup_batters(team_id: int) -> list:
    """
    Returns only position players (non-pitchers)
    from a team's active roster.

    Args:
        team_id: MLB team ID

    Example:
        # Get Yankees team ID
        nyy_id = [k for k, v in MLB_TEAM_MAP.items()
                  if v == 'NYY'][0]
        batters = get_lineup_batters(nyy_id)
    """
    roster = get_roster(team_id)
    batters = [
        p for p in roster
        if p['position_type'] != 'Pitcher'
    ]
    return batters


def get_team_id(abbr: str) -> int:
    """
    Returns MLB team ID from abbreviation.

    Example:
        nyy_id = get_team_id('NYY')  # returns 147
    """
    reverse_map = {v: k for k, v in MLB_TEAM_MAP.items()}
    team_id = reverse_map.get(abbr.upper())
    if not team_id:
        print(f"Team not found: {abbr}")
    return team_id


def build_game_matchup_inputs(team_abbr: str,
                               game_date: str = None,
                               season: int = None) -> dict:
    """
    Master function that pulls everything needed
    to run a full matchup report for a specific team's game.

    Pulls:
    - Today's game info and probable pitcher
    - Opposing team's active roster batters
    - Feeds into generate_matchup_report()

    Args:
        team_abbr: Your team of interest e.g. 'NYY'
        game_date: Date string, defaults to today
        season:    Season for historical data filter

    Example:
        inputs = build_game_matchup_inputs('NYY')
        # Then pass to generate_matchup_report()
    """
    target_date = game_date or str(date.today())

    print(f"\n{'─' * 60}")
    print(f"Building matchup inputs for {team_abbr} "
          f"on {target_date}")
    print(f"{'─' * 60}")

    # Get the game
    game = get_game_for_team(team_abbr, target_date)
    if not game:
        return {}

    # Determine which side our team is on
    is_home = game['home_abbr'] == team_abbr.upper()
    our_side = 'home' if is_home else 'away'
    opp_side = 'away' if is_home else 'home'

    our_pitcher_id = game[f'{our_side}_pitcher_id']
    our_pitcher = game[f'{our_side}_pitcher']
    opp_team = game[f'{opp_side}_abbr']
    opp_pitcher_id = game[f'{opp_side}_pitcher_id']
    opp_pitcher = game[f'{opp_side}_pitcher']

    print(f"\nGame: {game['away_abbr']} @ {game['home_abbr']}")
    print(f"Time: {game['game_time']}")
    print(f"Venue: {game['venue']}")
    print(f"Our SP: {our_pitcher} ({team_abbr})")
    print(f"Opp SP: {opp_pitcher} ({opp_team})")

    # Get opposing team's batters from active roster
    opp_team_id = get_team_id(opp_team)
    opp_batters = []

    if opp_team_id:
        print(f"\nFetching {opp_team} active roster...")
        roster = get_lineup_batters(opp_team_id)
        print(f"Found {len(roster)} position players")

        # Get MLBAM IDs for batters in our database
        batter_ids = []
        for player in roster:
            pid = player['mlbam_id']
            if pid:
                batter_ids.append(pid)

        opp_batters = batter_ids

    return {
        'game':             game,
        'our_team':         team_abbr,
        'our_pitcher_id':   our_pitcher_id,
        'our_pitcher':      our_pitcher,
        'opp_team':         opp_team,
        'opp_pitcher_id':   opp_pitcher_id,
        'opp_pitcher':      opp_pitcher,
        'opp_batter_ids':   opp_batters,
        'season':           season,
        'game_date':        target_date
    }


if __name__ == "__main__":
    print("Daily slate module ready")
    print()

    # Pull and display today's slate
    games = get_todays_slate()
    print_slate(games)

    print()
    print("Probable pitchers:")
    get_probable_pitchers()