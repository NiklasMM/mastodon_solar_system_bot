import argparse
import datetime
import json
import re
import tempfile
import urllib.request
from skyfield.api import load
from mastodon import Mastodon

kernel = load('de421.bsp')
timescale = load.timescale(builtin=True)


# A simple toot schedule, telling the bot at which hour of
# the day it should toot about which feed item entry.
# This is currently hardcoded for feed items with 5 entries.
TOOT_SCHEDULE = {
    8: 0,
    10: 1,
    12: 2,
    14: 3,
    16: 4
}

PLANETS = [
    "mercury",
    "venus",
    "mars",
    "jupiter barycenter",
    "saturn barycenter",
    "uranus barycenter",
    "neptune barycenter"
]

def parse_date_from_timestamp(timestamp):
    """ Parses a date object from a feed timestamp"""
    return datetime.datetime.strptime(timestamp, r"%Y-%m-%dT%H:%M:%SZ").date()

def load_feed_and_get_entry_for_today():
    """
        Loads the feed and returns the feed item for today.
        Raises Exception if no entry for today can be found
    """
    feed = feedparser.parse(FEED_URL)

    for entry in feed["items"]:
        # The "updated" timestamp always corresponds to the day the entry is about
        if parse_date_from_timestamp(entry["updated"]) == datetime.date.today():
            return entry
    else:
        raise Exception("Could not find feed entry for today.")

def parse_feed_item(feed_item):
    """
        Takes a dict representing a feed item for today and generates
        a strucutred dict from it:
        {
            "text": The plain text of this entry,
            "links": List of all links in this entry, which do not
                     link to the year or an image file.
            "year_link": Link to the article of the year (can be None)
            "image": Link to an image file (can be None)
        }

        All links are fully qualified URLs
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(feed_item["summary"], features="html.parser")
    entries = []

    for li in soup.find_all("li"):
        entry = {
            "text": li.get_text(),
            "links": [],
            "year_link": None,
            "year": None,
            "image": None
        }

        # find integer value for year. Assume text always begins with year.
        m = re.match(r"^(\d+)", entry["text"])
        if m:
            entry["year"] = int(m.group(1))
        else:
            raise Exception("Text does not start with year??")

        first_regular_link_found = False

        # iterate over all links in the entry
        for a in li.find_all("a"):
            href = a.get("href")
            full_url = WIKIPEDIA_PREFIX + href

            images = a.find_all("img")
            # If there are any images, we handle the first one and use it for a media post
            if len(images) > 0:
                image = images[0]

                # find the largest image file
                # "srcset" contains alternate image files in different sizes.
                # The format is a comma separated list of "<url> <size>x", e.g. 1.5x, 2x, etc..
                # We parse these and select the url with the max size
                candidates = [image.get("src") + " 1x"] + image.get("srcset").split(",")
                tmp = []
                for candidate in candidates:
                    candidate = candidate.strip()
                    url, size = candidate.split()
                    size = float(size.strip("x"))
                    tmp.append((size, url))
                url = sorted(tmp)[-1][1]

                entry["image"] = {
                    "url": "https:" + url,
                    "alt_text": image.get("alt")
                }
                continue

            # Assume a link with only numbers is a year link
            possible_year_link = re.match(r"^\/wiki\/\d+$", href)

            # Only make a link the year_link if it appears before
            # any other regular link
            if not first_regular_link_found and possible_year_link:
                entry["year_link"] = full_url
            else:
                entry["links"].append(full_url)
                first_regular_link_found = True
        entries.append(entry)
    return entries

def prepare_toot(item):
    """
        Take an item as returned by parse_feed_item and format
        a toot.
    """
    toot_text = "Heute vor {0} Jahren:\n\n".format(
        datetime.date.today().year - item["year"]
    )
    toot_text = toot_text + item["text"]

    if len(item["links"]) > 0:
        toot_text = "\n\n".join((toot_text, item["links"][0]))

    return toot_text

def get_feed_entry_for_today():
    """
        Get the feed entry for today.
        First tries to load the entry from a cached file and falls
        back to actually loading the feed from wikipedia.
    """
    try:
        with open(CACHE_FILE) as f:
            data = f.read()
        data = json.loads(data)
    except IOError:
        data = None

    if data is None or parse_date_from_timestamp(data["updated"]) != datetime.date.today():
        data = load_feed_and_get_entry_for_today()

    with open(CACHE_FILE, "w") as f:
        f.write(json.dumps(data))

    return data

def create_media_post(entry, mastodon):
    """
        Takes an entry and a mastodon instance, generates a media post with the entry["image"]
        if present and returns the obtained media_dict.
        If no image is present, returns None.
    """
    if entry["image"] is None:
        return None
    url = entry["image"]["url"]
    with tempfile.TemporaryDirectory() as tmpdirname:
        # download image
        extension = url.split(".")[-1]
        image_filename = tmpdirname + "/image.{ext}".format(ext=extension)
        urllib.request.urlretrieve(url, image_filename)

        # create media post
        return mastodon.media_post(image_filename, description=entry["image"]["alt_text"])

def distance_to_earth(planet, time=None):
    if time is None:
        time = timescale.now()

    return kernel["earth"].at(time).observe(kernel[planet]).radec()[2].au


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Toot about the configuration of the solar system')
    parser.add_argument('--dry-run', action="store_true", help="If given only prints the content of the toot")
    # parser.add_argument('access_token', type=str, help='access token for the targeted Mastodon account.')

    args = parser.parse_args()
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    next_hour = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(hours=1)
    for planet in PLANETS:
        print(planet, distance_to_earth(planet, time=timescale.utc(now)))
        print(planet, distance_to_earth(planet, time=timescale.utc(next_hour)))

    # if item is not None:
    #     entry = entries[item]
    #     toot_text = prepare_toot(entry)
    #     if args.dry_run:
    #         print(toot_text)
    #     else:
    #         mastodon = Mastodon(
    #             api_base_url = 'https://chaos.social',
    #             access_token=args.access_token
    #         )
    #         media_dict = create_media_post(entry, mastodon)
    #         mastodon.status_post(toot_text, visibility="unlisted", media_ids=media_dict)
    #         print("{0}: Successfully tooted!".format(datetime.datetime.now().isoformat()))
    # else:
    #     print("{0}: Nothing to toot about.".format(datetime.datetime.now().isoformat()))
