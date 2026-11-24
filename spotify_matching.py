"""Match VirtualDJ plays to Spotify catalog tracks.

Adapted from DJ Set Processor spotify_output.py at 96e4c9b.
Copyright (c) 2026 Koichi Tsunoda. Licensed under MIT.
"""

import re

FEATURED = re.compile(r"\s*\((?:feat\.?|ft\.?|featuring)\s+([^()]+)\)", re.I)
CREDIT_SEPARATOR = re.compile(r"\s*[,;]\s*|\s+(?:&|and|x)\s+", re.I)
VERSION_SUFFIX = re.compile(
    r"\s*[\[(]([^()[\]]*\b(?:mix|remix|edit|version|live|acoustic|stripped|reimagined)\b"
    r"[^()[\]]*)[\])]$",
    re.I,
)
TRACKING_ROOM = re.compile(
    r"(?:\s*\(nashville['’]?s tracking room studios\)|"
    r"\s+-\s+recorded at the tracking room nashville)$", re.I
)


def normalized(value):
    return " ".join(value.casefold().split())


def title_key(title):
    # Spotify uses both parentheses and a dash around the same version label.
    title = FEATURED.sub("", title)
    title = VERSION_SUFFIX.sub(r" - \1", title)
    return normalized(TRACKING_ROOM.sub(" - tracking room nashville", title))


def credits_match(credit, artists):
    if normalized(credit) in artists:
        return True
    names = [normalized(name) for name in CREDIT_SEPARATOR.split(credit)]
    return len(names) > 1 and all(name in artists for name in names)


def find_track(api, artist, title, remix):
    # VirtualDJ can put the same version in both title and remix fields.
    if remix:
        base = re.sub(
            rf"(?:\s*\({re.escape(remix)}\)|\s*\[{re.escape(remix)}\]|"
            rf"\s+-\s+{re.escape(remix)})$", "", title, flags=re.I
        ).rstrip()
        names = tuple(dict.fromkeys((f"{base} ({remix})", f"{base} - {remix}")))
        if base != title:
            names = (title, *[name for name in names if name != title])
    else:
        names = (title,)
    exact_titles = {normalized(name) for name in names}
    title_keys = {title_key(name) for name in names}
    featured = FEATURED.findall(title)
    queries = [f"track:{name} artist:{artist}" for name in names]
    exact_query_count = len(queries)
    lead = CREDIT_SEPARATOR.split(artist, maxsplit=1)[0]
    for name in names:
        clean = FEATURED.sub("", name)
        queries.extend((f"track:{clean} artist:{artist}", f"track:{clean} artist:{lead}"))
    queries.extend(f"{FEATURED.sub('', name)} {artist}" for name in names)

    fallback = None
    lead_matches = {}
    allow_lead_match = lead != artist or bool(featured)
    lead_credit = normalized(lead)
    for index, query in enumerate(dict.fromkeys(queries)):
        results = api(
            "GET", "/search",
            params={"q": query, "type": "track", "limit": 10},
        )["tracks"]["items"]
        for item in results:
            artists = {normalized(entry["name"]) for entry in item["artists"]}
            if normalized(item["name"]) in exact_titles and normalized(artist) in artists:
                return item["uri"]
            if title_key(item["name"]) not in title_keys:
                continue
            if (fallback is None and credits_match(artist, artists)
                    and all(credits_match(name, artists) for name in featured)):
                fallback = item["uri"]
            if allow_lead_match and lead_credit in artists:
                uri = item["uri"]
                recording = (item.get("external_ids", {}).get("isrc")
                             or item.get("linked_from", {}).get("uri") or uri)
                lead_matches.setdefault(recording, uri)
        if fallback is not None and index >= exact_query_count - 1:
            return fallback
    if len(lead_matches) == 1:
        return next(iter(lead_matches.values()))
    return None
