import argparse
import datetime
from skyfield.api import load
from mastodon import Mastodon

kernel = load('de421.bsp')
timescale = load.timescale(builtin=True)

INCREASE_ICON = "📈"
DECREASE_ICON = "📉"

PLANETS = {
    "mercury": "Mercury",
    "venus": "Venus",
    "mars": "Mars",
    "jupiter barycenter": "Jupiter",
    "saturn barycenter": "Saturn",
    "uranus barycenter": "Uranus",
    "neptune barycenter": "Neptune",
}

def distance_to_earth(planet, time=None):
    if time is None:
        time = timescale.now()

    return kernel["earth"].at(time).observe(kernel[planet]).radec()[2].au

def generate_toot(time=None):

    planets = []

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    next_hour = now + datetime.timedelta(hours=1)

    for key, display_name in PLANETS.items():
        distance_now = distance_to_earth(key, time=timescale.utc(now))
        distance_next_hour = distance_to_earth(key, time=timescale.utc(next_hour))

        planets.append(
            {
                "distance": distance_now,
                "increasing": distance_now < distance_next_hour,
                "name": display_name
            }
        )

    toot_text = "Current distance of Earth to the other planets in the solar system:\n\n"
    planet_entries = []

    for entry in sorted(planets, key=lambda x: x["distance"]):
        planet_entries.append(
            f"{entry['name']}: {entry['distance']:.3f} au "
            + (INCREASE_ICON if entry["increasing"] else DECREASE_ICON)
        )

    return toot_text + "\n".join(planet_entries)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Toot about the configuration of the solar system')
    parser.add_argument('--dry-run', action="store_true", help="If given only prints the content of the toot")
    parser.add_argument('access_token', type=str, help='access token for the targeted Mastodon account.')

    args = parser.parse_args()

    message = generate_toot()
    if args.dry_run:
        print(message)
    else:
        mastodon = Mastodon(
            api_base_url = 'https://chaos.social',
            access_token=args.access_token
        )
        mastodon.status_post(message, visibility="unlisted")
        print("{0}: Successfully tooted!".format(datetime.datetime.now().isoformat()))
