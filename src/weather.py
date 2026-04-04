"""
weather.py
Weather integration for daily slate analysis.
Uses OpenWeatherMap free API for current conditions.

Research basis:
- Nathan (2008): ~1% carry change per 10F vs 72F baseline
- Wind: ~12-15% HR change per 15mph direct wind
- Coors Field: ~5-10% distance increase at 5,280ft
- Humidity: minor effect, moist air slightly less dense

Setup:
    1. Sign up free at openweathermap.org/api
    2. Add to .env file: OPENWEATHER_API_KEY=your_key_here
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY', '')


# ─────────────────────────────────────────────────────────────
# PARK DATA
# All 30 MLB stadiums with coordinates, elevation,
# roof type, and analytical context notes
# ─────────────────────────────────────────────────────────────

PARK_DATA = {
    'ARI': {
        'name':          'Chase Field',
        'lat':            33.4453,
        'lon':           -112.0667,
        'elevation_ft':   1086,
        'roof':           'retractable',
        'park_factor':    98,
        'hr_factor':      97,
        'notes':          'Retractable roof — confirm open/closed at game time. '
                          'Moderate elevation. Climate controlled when closed.',
    },
    'ATL': {
        'name':          'Truist Park',
        'lat':            33.8908,
        'lon':           -84.4678,
        'elevation_ft':   1050,
        'roof':           'open',
        'park_factor':    101,
        'hr_factor':      103,
        'notes':          'Moderate elevation boosts carry slightly. '
                          'Hot humid summers favor offense. '
                          'Generally hitter friendly.',
    },
    'BAL': {
        'name':          'Oriole Park at Camden Yards',
        'lat':            39.2838,
        'lon':           -76.6218,
        'elevation_ft':   20,
        'roof':           'open',
        'park_factor':    103,
        'hr_factor':      111,
        'notes':          'Short RF at 318ft — hitter friendly for LHH pull power. '
                          'Harbor location creates wind variability. '
                          'Above average HR park.',
    },
    'BOS': {
        'name':          'Fenway Park',
        'lat':            42.3467,
        'lon':           -71.0972,
        'elevation_ft':   20,
        'roof':           'open',
        'park_factor':    104,
        'hr_factor':      93,
        'notes':          'Green Monster 37ft wall in LF suppresses LHH HR. '
                          'Doubles alley in RF. Wind from NE helps carry to RF. '
                          'Highest doubles park in MLB.',
    },
    'CHC': {
        'name':          'Wrigley Field',
        'lat':            41.9484,
        'lon':           -87.6553,
        'elevation_ft':   595,
        'roof':           'open',
        'park_factor':    103,
        'hr_factor':      106,
        'wind_critical':  True,
        'notes':          'Most wind-affected park in MLB. '
                          'Lake Michigan wind is the dominant variable — '
                          'direction determines everything here. '
                          'Check wind carefully before every game.',
    },
    'CIN': {
        'name':          'Great American Ball Park',
        'lat':            39.0979,
        'lon':           -84.5082,
        'elevation_ft':   490,
        'roof':           'open',
        'park_factor':    105,
        'hr_factor':      115,
        'notes':          'One of the most HR-friendly parks in MLB. '
                          'Ohio River location creates variable wind. '
                          'Short power alleys favor pull hitters.',
    },
    'CLE': {
        'name':          'Progressive Field',
        'lat':            41.4962,
        'lon':           -81.6852,
        'elevation_ft':   660,
        'roof':           'open',
        'park_factor':    98,
        'hr_factor':      96,
        'notes':          'Lake Erie influence creates variable wind. '
                          'Generally neutral to pitcher friendly. '
                          'Cold spring temperatures suppress offense.',
    },
    'COL': {
        'name':          'Coors Field',
        'lat':            39.7559,
        'lon':          -104.9942,
        'elevation_ft':   5200,
        'roof':           'open',
        'park_factor':    115,
        'hr_factor':      122,
        'altitude_boost': True,
        'notes':          'Most offense-friendly park in MLB by wide margin. '
                          'Air 17% less dense than sea level — '
                          '5-10% more batted ball distance. '
                          'Breaking balls less effective. '
                          'Coors hangover effect on pitchers after leaving.',
    },
    'CWS': {
        'name':          'Rate Field',
        'lat':            41.8299,
        'lon':           -87.6338,
        'elevation_ft':   595,
        'roof':           'open',
        'park_factor':    102,
        'hr_factor':      104,
        'notes':          'Generally hitter friendly. '
                          'Lake Michigan wind variable. '
                          'Cold spring temperatures in early season.',
    },
    'DET': {
        'name':          'Comerica Park',
        'lat':            42.3390,
        'lon':           -83.0485,
        'elevation_ft':   600,
        'roof':           'open',
        'park_factor':    96,
        'hr_factor':      88,
        'notes':          'One of the largest parks in MLB — suppresses HR. '
                          'Deep power alleys hurt pull hitters. '
                          'Cold spring temperatures further suppress offense.',
    },
    'HOU': {
        'name':          'Minute Maid Park',
        'lat':            29.7573,
        'lon':           -95.3555,
        'elevation_ft':   43,
        'roof':           'retractable',
        'park_factor':    99,
        'hr_factor':      97,
        'notes':          'Retractable roof — weather irrelevant when closed. '
                          'Crawford Boxes in LF short at 315ft favor LHH. '
                          'Generally neutral park.',
    },
    'KC': {
        'name':          'Kauffman Stadium',
        'lat':            39.0517,
        'lon':           -94.4803,
        'elevation_ft':   909,
        'roof':           'open',
        'park_factor':    97,
        'hr_factor':      93,
        'notes':          'Large park with extensive foul territory — '
                          'suppresses offense, extra outs for pitchers. '
                          'Generally pitcher friendly.',
    },
    'LAA': {
        'name':          'Angel Stadium',
        'lat':            33.8003,
        'lon':          -117.8827,
        'elevation_ft':   160,
        'roof':           'open',
        'park_factor':    99,
        'hr_factor':      98,
        'notes':          'Generally neutral park. '
                          'Inland from coast — warmer temperatures than SD/SF. '
                          'Favorable hitting conditions overall.',
    },
    'LAD': {
        'name':          'Dodger Stadium',
        'lat':            34.0739,
        'lon':          -118.2400,
        'elevation_ft':   514,
        'roof':           'open',
        'park_factor':    97,
        'hr_factor':      94,
        'notes':          'Marine layer common at night — '
                          'suppresses carry on fly balls April through June. '
                          'One of the largest foul territories in MLB. '
                          'Generally pitcher friendly.',
    },
    'MIA': {
        'name':          'loanDepot Park',
        'lat':            25.7781,
        'lon':           -80.2197,
        'elevation_ft':   6,
        'roof':           'retractable',
        'park_factor':    97,
        'hr_factor':      94,
        'notes':          'Retractable roof — weather irrelevant when closed. '
                          'Climate controlled environment.',
    },
    'MIL': {
        'name':          'American Family Field',
        'lat':            43.0280,
        'lon':           -87.9712,
        'elevation_ft':   635,
        'roof':           'retractable',
        'park_factor':    100,
        'hr_factor':      101,
        'notes':          'Retractable roof — weather irrelevant when closed. '
                          'Generally neutral park factors.',
    },
    'MIN': {
        'name':          'Target Field',
        'lat':            44.9817,
        'lon':           -93.2781,
        'elevation_ft':   840,
        'roof':           'open',
        'park_factor':    97,
        'hr_factor':      94,
        'notes':          'Cold spring temperatures suppress offense significantly. '
                          'Generally pitcher friendly park. '
                          'One of the colder venues in early season.',
    },
    'NYM': {
        'name':          'Citi Field',
        'lat':            40.7571,
        'lon':           -73.8458,
        'elevation_ft':   12,
        'roof':           'open',
        'park_factor':    97,
        'hr_factor':      92,
        'notes':          'Flushing Bay wind from NE suppresses RF carry. '
                          'Historically one of the more pitcher friendly '
                          'parks in the NL. '
                          'Large dimensions hurt power hitters.',
    },
    'NYY': {
        'name':          'Yankee Stadium',
        'lat':            40.8296,
        'lon':           -73.9262,
        'elevation_ft':   55,
        'roof':           'open',
        'park_factor':    103,
        'hr_factor':      112,
        'lhh_hr_boost':   True,
        'notes':          'Short RF porch at 314ft — '
                          'significant LHH pull power advantage. '
                          'Wind from SW pushes toward RF. '
                          'Above average HR park, especially for lefties.',
    },
    'OAK': {
        'name':          'Sutter Health Park',
        'lat':            38.5816,
        'lon':          -121.4944,
        'elevation_ft':   25,
        'roof':           'open',
        'park_factor':    98,
        'hr_factor':      96,
        'notes':          'Sacramento temporary home. '
                          'Hot inland climate in summer months. '
                          'Generally neutral conditions.',
    },
    'PHI': {
        'name':          'Citizens Bank Park',
        'lat':            39.9061,
        'lon':           -75.1665,
        'elevation_ft':   20,
        'roof':           'open',
        'park_factor':    104,
        'hr_factor':      109,
        'notes':          'One of the more hitter friendly parks in MLB. '
                          'Wind from SW pushes toward RF in summer. '
                          'Hot humid summers boost offense further.',
    },
    'PIT': {
        'name':          'PNC Park',
        'lat':            40.4469,
        'lon':           -80.0057,
        'elevation_ft':   730,
        'roof':           'open',
        'park_factor':    98,
        'hr_factor':      96,
        'notes':          'River location creates variable wind conditions. '
                          'Generally neutral park factors. '
                          'Slight pitcher advantage overall.',
    },
    'SD': {
        'name':          'Petco Park',
        'lat':            32.7076,
        'lon':          -117.1570,
        'elevation_ft':   17,
        'roof':           'open',
        'park_factor':    94,
        'hr_factor':      86,
        'notes':          'One of the most pitcher friendly parks in MLB. '
                          'Marine layer suppresses carry April through June. '
                          'Large dimensions and ocean air significantly '
                          'reduce HR rates. '
                          'HR factor of 86 means 14% fewer HR than average.',
    },
    'SEA': {
        'name':          'T-Mobile Park',
        'lat':            47.5914,
        'lon':          -122.3325,
        'elevation_ft':   18,
        'roof':           'retractable',
        'park_factor':    97,
        'hr_factor':      94,
        'notes':          'Retractable roof — weather irrelevant when closed. '
                          'Generally pitcher friendly when open.',
    },
    'SF': {
        'name':          'Oracle Park',
        'lat':            37.7786,
        'lon':          -122.3893,
        'elevation_ft':   3,
        'roof':           'open',
        'park_factor':    95,
        'hr_factor':      88,
        'notes':          'Cold marine air off SF Bay suppresses carry. '
                          'Wind typically blows in from right center at night. '
                          'One of the most pitcher friendly parks in baseball. '
                          'HR factor of 88 — significant suppression.',
    },
    'STL': {
        'name':          'Busch Stadium',
        'lat':            38.6226,
        'lon':           -90.1928,
        'elevation_ft':   430,
        'roof':           'open',
        'park_factor':    99,
        'hr_factor':      98,
        'notes':          'Hot humid Midwest summers. '
                          'Generally neutral park factors. '
                          'Slight pitcher advantage in spring.',
    },
    'TB': {
        'name':          'Tropicana Field',
        'lat':            27.7682,
        'lon':           -82.6534,
        'elevation_ft':   15,
        'roof':           'fixed_dome',
        'park_factor':    97,
        'hr_factor':      95,
        'notes':          'Fixed dome — weather completely irrelevant. '
                          'Consistent controlled environment year round.',
    },
    'TEX': {
        'name':          'Globe Life Field',
        'lat':            32.7473,
        'lon':           -97.0832,
        'elevation_ft':   551,
        'roof':           'retractable',
        'park_factor':    101,
        'hr_factor':      103,
        'notes':          'Retractable roof — weather irrelevant when closed. '
                          'Generally neutral to slight hitter advantage.',
    },
    'TOR': {
        'name':          'Rogers Centre',
        'lat':            43.6414,
        'lon':           -79.3894,
        'elevation_ft':   287,
        'roof':           'retractable',
        'park_factor':    101,
        'hr_factor':      104,
        'notes':          'Retractable roof — weather irrelevant when closed. '
                          'Slight hitter advantage when roof is open.',
    },
    'WSH': {
        'name':          'Nationals Park',
        'lat':            38.8730,
        'lon':           -77.0074,
        'elevation_ft':   5,
        'roof':           'open',
        'park_factor':    101,
        'hr_factor':      103,
        'notes':          'Potomac River location creates variable wind. '
                          'Hot humid DC summers favor offense. '
                          'Slight hitter advantage overall.',
    },
}


# ─────────────────────────────────────────────────────────────
# WEATHER FETCH
# ─────────────────────────────────────────────────────────────

def get_weather(team_abbr: str) -> dict:
    """
    Fetches current weather for a team's home stadium.
    Requires OPENWEATHER_API_KEY in .env file.

    Args:
        team_abbr: Home team abbreviation e.g. 'NYY'

    Returns:
        Dictionary with conditions and baseball impact analysis

    Example:
        weather = get_weather('NYY')
        print_weather_report(weather)
    """
    if not OPENWEATHER_API_KEY:
        return {
            'team':  team_abbr,
            'error': 'No API key',
            'note':  'Add OPENWEATHER_API_KEY to .env file'
        }

    park = PARK_DATA.get(team_abbr.upper())
    if not park:
        return {
            'team':  team_abbr,
            'error': f'No park data for {team_abbr}'
        }

    # Fixed dome — skip API call entirely
    if park.get('roof') == 'fixed_dome':
        return {
            'team':          team_abbr,
            'park':          park['name'],
            'roof':          'fixed_dome',
            'is_dome':       True,
            'impact_level':  'NONE',
            'park_factor':   park.get('park_factor', 100),
            'hr_factor':     park.get('hr_factor', 100),
            'impact_factors': [],
            'notes':         park.get('notes', ''),
            'raw':           {}
        }

    try:
        url = (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?lat={park['lat']}"
            f"&lon={park['lon']}"
            f"&appid={OPENWEATHER_API_KEY}"
            f"&units=imperial"
        )
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

    except requests.exceptions.HTTPError as e:
        return {
            'team':  team_abbr,
            'park':  park['name'],
            'error': f'API error: {e}'
        }
    except requests.exceptions.ConnectionError:
        return {
            'team':  team_abbr,
            'park':  park['name'],
            'error': 'Connection failed — check internet'
        }
    except Exception as e:
        return {
            'team':  team_abbr,
            'park':  park['name'],
            'error': str(e)
        }

    # ── Parse conditions ──────────────────────────────────
    temp_f      = round(data['main']['temp'])
    feels_like  = round(data['main']['feels_like'])
    humidity    = data['main']['humidity']
    wind_speed  = round(data['wind']['speed'])
    wind_deg    = data['wind'].get('deg', 0)
    wind_dir    = _degrees_to_direction(wind_deg)
    description = data['weather'][0]['description'].title()
    visibility  = data.get('visibility', 10000)
    clouds      = data['clouds']['all']

    # ── Baseball impact analysis ──────────────────────────
    impact_factors = []
    impact_level   = 'LOW'

    # Temperature carry effect
    # Research: ~1% per 10F vs 72F baseline (Nathan 2008)
    carry_effect_pct = round((temp_f - 72) * 0.1, 1)

    if temp_f >= 85:
        impact_factors.append(
            f"Hot ({temp_f}F) — ball carries "
            f"~{abs(carry_effect_pct)}% farther than average"
        )
        impact_level = 'MODERATE'
    elif temp_f <= 40:
        impact_factors.append(
            f"Very cold ({temp_f}F) — significant offense suppression, "
            f"ball carries ~{abs(carry_effect_pct)}% shorter"
        )
        impact_level = 'HIGH'
    elif temp_f <= 50:
        impact_factors.append(
            f"Cold ({temp_f}F) — ball carries "
            f"~{abs(carry_effect_pct)}% shorter than average"
        )
        impact_level = 'MODERATE'

    # Wind effect
    # Research: ~12-15% HR change per 15mph direct wind
    if wind_speed >= 15:
        impact_level = 'HIGH'
        impact_factors.append(
            f"Significant wind: {wind_speed} mph from {wind_dir} "
            f"— 15mph out = ~12-15% more HR"
        )
    elif wind_speed >= 10:
        if impact_level == 'LOW':
            impact_level = 'MODERATE'
        impact_factors.append(
            f"Moderate wind: {wind_speed} mph from {wind_dir}"
        )
    else:
        impact_factors.append(
            f"Light wind: {wind_speed} mph from {wind_dir} "
            f"— minimal effect"
        )

    # Wrigley special case
    if park.get('wind_critical') and wind_speed >= 10:
        impact_level = 'HIGH'
        impact_factors.append(
            f"Wrigley wind alert: {wind_speed} mph from {wind_dir} "
            f"is the dominant variable today — direction is everything here"
        )

    # Humidity
    if humidity >= 80:
        impact_factors.append(
            f"High humidity ({humidity}%) — "
            f"moist air slightly less dense, minor carry benefit"
        )
    elif humidity <= 20:
        impact_factors.append(
            f"Low humidity ({humidity}%) — "
            f"dry air is denser, minor carry reduction"
        )

    # Altitude (Coors)
    if park.get('altitude_boost'):
        impact_level = 'HIGH'
        impact_factors.append(
            f"Altitude: {park['elevation_ft']}ft — "
            f"air 17% less dense than sea level, "
            f"5-10% more batted ball distance"
        )

    # Retractable roof reminder
    if park.get('roof') == 'retractable':
        impact_factors.append(
            f"Retractable roof — confirm open/closed before game"
        )

    # Reduced visibility
    if visibility < 5000:
        impact_factors.append(
            f"Reduced visibility ({visibility}m) — "
            f"fog or precipitation possible"
        )

    # Park factor context
    pf  = park.get('park_factor', 100)
    hrf = park.get('hr_factor', 100)
    if pf >= 105 or hrf >= 110:
        impact_factors.append(
            f"Park factor: {pf} runs | {hrf} HR — "
            f"significantly hitter friendly"
        )
    elif pf <= 95 or hrf <= 90:
        impact_factors.append(
            f"Park factor: {pf} runs | {hrf} HR — "
            f"significantly pitcher friendly"
        )
    else:
        impact_factors.append(
            f"Park factor: {pf} runs | {hrf} HR — neutral"
        )

    # Park notes
    if park.get('notes'):
        impact_factors.append(park['notes'])

    return {
        'team':             team_abbr,
        'park':             park['name'],
        'roof':             park.get('roof', 'open'),
        'is_dome':          False,
        'temp_f':           temp_f,
        'feels_like':       feels_like,
        'humidity':         humidity,
        'wind_speed':       wind_speed,
        'wind_direction':   wind_dir,
        'wind_deg':         wind_deg,
        'description':      description,
        'clouds':           clouds,
        'visibility':       visibility,
        'carry_effect_pct': carry_effect_pct,
        'impact_level':     impact_level,
        'impact_factors':   impact_factors,
        'park_factor':      pf,
        'hr_factor':        hrf,
        'raw':              data
    }


def get_park_info(team_abbr: str) -> dict:
    """
    Returns park data without making an API call.
    Use when you only need static park context
    rather than live weather conditions.

    Example:
        park = get_park_info('COL')
    """
    park = PARK_DATA.get(team_abbr.upper(), {})
    return {
        'team':        team_abbr,
        'park':        park.get('name', 'Unknown'),
        'roof':        park.get('roof', 'open'),
        'is_dome':     park.get('roof') in ('fixed_dome', 'retractable'),
        'park_factor': park.get('park_factor', 100),
        'hr_factor':   park.get('hr_factor', 100),
        'notes':       park.get('notes', ''),
        'elevation_ft': park.get('elevation_ft', 0),
        'altitude_boost': park.get('altitude_boost', False),
        'wind_critical':  park.get('wind_critical', False),
        'lhh_hr_boost':   park.get('lhh_hr_boost', False),
    }


# ─────────────────────────────────────────────────────────────
# DISPLAY
# ─────────────────────────────────────────────────────────────

def print_weather_report(weather: dict):
    """
    Prints a clean formatted weather and park context report.

    Example:
        weather = get_weather('CHC')
        print_weather_report(weather)
    """
    if 'error' in weather:
        print(f"  Weather unavailable: {weather.get('error')}")
        if weather.get('note'):
            print(f"  Note: {weather['note']}")
        return

    if weather.get('is_dome') or weather.get('roof') == 'fixed_dome':
        print(f"  {weather['park']} — Fixed dome")
        pf  = weather.get('park_factor', 100)
        hrf = weather.get('hr_factor', 100)
        print(f"  Park factor: {pf} runs | {hrf} HR")
        if weather.get('notes'):
            print(f"  {weather['notes']}")
        return

    pf   = weather.get('park_factor', 100)
    hrf  = weather.get('hr_factor', 100)
    carry = weather.get('carry_effect_pct', 0)
    carry_str = f"+{carry}%" if carry > 0 else f"{carry}%"

    print(f"  {weather['park']}")
    print(
        f"  {weather['description']} | "
        f"{weather['temp_f']}F "
        f"(feels {weather['feels_like']}F) | "
        f"Humidity {weather['humidity']}%"
    )
    print(
        f"  Wind: {weather['wind_speed']} mph {weather['wind_direction']} | "
        f"Clouds: {weather['clouds']}%"
    )
    print(
        f"  Carry effect: {carry_str} | "
        f"Park: {pf} runs / {hrf} HR | "
        f"Impact: {weather['impact_level']}"
    )

    if weather.get('impact_factors'):
        for factor in weather['impact_factors']:
            print(f"    → {factor}")


def format_weather_sms(weather: dict) -> str:
    """
    Returns a compact single-line weather summary
    formatted for SMS output.

    Example:
        line = format_weather_sms(get_weather('NYY'))
        # '72F | Wind 8mph SW | PF 103/112 | LOW impact'
    """
    if 'error' in weather:
        return "Weather unavailable"

    if weather.get('is_dome'):
        pf  = weather.get('park_factor', 100)
        hrf = weather.get('hr_factor', 100)
        return f"Dome | PF {pf}/{hrf}"

    carry = weather.get('carry_effect_pct', 0)
    carry_str = f"+{carry}%" if carry > 0 else f"{carry}%"
    pf   = weather.get('park_factor', 100)
    hrf  = weather.get('hr_factor', 100)

    return (
        f"{weather['temp_f']}F | "
        f"Wind {weather['wind_speed']}mph {weather['wind_direction']} | "
        f"Carry {carry_str} | "
        f"PF {pf}/{hrf} | "
        f"{weather['impact_level']} impact"
    )


# ─────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────

def _degrees_to_direction(degrees: float) -> str:
    """Converts wind degrees to 16-point compass direction."""
    directions = [
        'N',   'NNE', 'NE',  'ENE',
        'E',   'ESE', 'SE',  'SSE',
        'S',   'SSW', 'SW',  'WSW',
        'W',   'WNW', 'NW',  'NNW'
    ]
    idx = round(degrees / 22.5) % 16
    return directions[idx]


def get_all_park_factors() -> dict:
    """
    Returns park factor summary for all 30 teams.
    Useful for building context into leaderboard analysis.
    """
    return {
        team: {
            'park':        data['name'],
            'park_factor': data.get('park_factor', 100),
            'hr_factor':   data.get('hr_factor', 100),
            'roof':        data.get('roof', 'open'),
        }
        for team, data in PARK_DATA.items()
    }


if __name__ == "__main__":
    print("Weather module ready")
    print()
    print("Setup:")
    print("  Add OPENWEATHER_API_KEY to your .env file")
    print()
    print("Usage:")
    print("  from src.weather import get_weather, print_weather_report")
    print("  weather = get_weather('NYY')")
    print("  print_weather_report(weather)")
    print()
    print("Park factors available for all 30 MLB teams")
    print("API key loaded from .env — never hardcoded")