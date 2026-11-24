"""Sync appended VirtualDJ plays to a rolling Spotify playlist."""

import argparse
import json
import logging
import os
import re
from collections import Counter
from datetime import datetime

from virtualdj import parse_m3u

LOG = logging.getLogger(__name__)
HISTORY_NAME = re.compile(r"\d{4}-\d{2}-\d{2}\.m3u", re.IGNORECASE)
DRIVE = "https://www.googleapis.com/drive/v3/files"
SPOTIFY = "https://api.spotify.com/v1"
LIMIT = 200


class SyncError(Exception):
    pass


class HttpError(SyncError):
    def __init__(self, service, method, status):
        super().__init__(f"{service} {method} returned HTTP {status}")
        self.status = status


def request(session, service, method, url, **kwargs):
    # Keep request URLs, response bodies and credentials out of errors and logs.
    try:
        response = session.request(method, url, timeout=30, **kwargs)
    except Exception:
        raise SyncError(f"{service} {method} request failed") from None
    if service == "Spotify token" and response.status_code == 400:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict) and payload.get("error") == "invalid_grant":
            raise SyncError(
                "Spotify authorization expired or was revoked. "
                "Reconnect Westie Radio and update SPOTIFY_REFRESH_TOKEN in Render."
            )
    if not 200 <= response.status_code < 300:
        raise HttpError(service, method, response.status_code)
    return response


class Drive:
    def __init__(self, reader, writer, folder, checkpoint):
        self.reader = reader
        self.writer = writer
        self.folder = folder
        self.checkpoint = checkpoint

    def histories(self):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.folder):
            raise SyncError("Invalid history folder ID")
        params = {
            "q": f"'{self.folder}' in parents and trashed = false",
            "fields": "nextPageToken,files(id,name,modifiedTime,mimeType,resourceKey)",
            "pageSize": 1000,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        files = []
        while True:
            page = request(self.reader, "Drive", "GET", DRIVE, params=params).json()
            files.extend(
                item for item in page["files"]
                if HISTORY_NAME.fullmatch(item["name"])
                and not item["mimeType"].startswith("application/vnd.google-apps.")
            )
            if not page.get("nextPageToken"):
                return files
            params["pageToken"] = page["nextPageToken"]

    def download(self, item):
        file_id = item["id"]
        key = item.get("resourceKey")
        headers = {"X-Goog-Drive-Resource-Keys": f"{file_id}/{key}"} if key else {}
        response = request(
            self.reader, "Drive", "GET", f"{DRIVE}/{file_id}",
            params={"alt": "media", "supportsAllDrives": "true"}, headers=headers,
        )
        return response.content.decode("utf-8-sig")

    def load(self):
        return json.loads(self.download({"id": self.checkpoint}))

    def save(self, state):
        request(
            self.writer, "Drive", "PATCH",
            f"https://www.googleapis.com/upload/drive/v3/files/{self.checkpoint}",
            params={"uploadType": "media", "supportsAllDrives": "true"},
            headers={"Content-Type": "application/json"},
            data=json.dumps(state).encode(),
        )


class Spotify:
    def __init__(self, session, playlist):
        self.session = session
        self.playlist = playlist
        self.path = f"/playlists/{playlist}"

    def api(self, method, path, **kwargs):
        return request(self.session, "Spotify", method, SPOTIFY + path, **kwargs).json()

    def search(self, artist, title):
        result = self.api(
            "GET", "/search",
            params={"q": f"track:{title} artist:{artist}", "type": "track", "limit": 1},
        )["tracks"]["items"]
        return result[0]["uri"] if result else None

    def snapshot(self):
        return self.api("GET", self.path, params={"fields": "snapshot_id"})["snapshot_id"]

    def items(self):
        snapshot = self.snapshot()
        uris = []
        while True:
            page = self.api("GET", self.path + "/items", params={"limit": 50, "offset": len(uris)})
            uris.extend((row.get("item") or {}).get("uri") for row in page["items"])
            if not page["next"]:
                break
            if not page["items"]:
                raise SyncError("Spotify returned an empty intermediate page")
        if len(uris) != page["total"] or self.snapshot() != snapshot:
            raise SyncError("Spotify playlist changed during pagination")
        return snapshot, uris

    def append(self, uris):
        self.api("POST", self.path + "/items", json={"uris": uris})

    def remove(self, snapshot, uris):
        self.api("DELETE", self.path + "/items", json={
            "snapshot_id": snapshot, "items": [{"uri": uri} for uri in uris],
        })


def checkpoint(drive, playlist):
    state = drive.load()
    if state == {}:
        return {"playlist": playlist, "positions": {}}
    if (
        not isinstance(state, dict)
        or state.get("playlist") != playlist
        or not isinstance(state.get("positions"), dict)
        or any(type(n) is not int or n < 0 for n in state["positions"].values())
    ):
        raise SyncError("Checkpoint is invalid or belongs to another playlist")
    return state


def finish(drive, state):
    pending = state.pop("pending")
    if pending["kind"] == "append":
        state["positions"][pending["file"]] = pending["position"]
    drive.save(state)


def reconcile(drive, spotify, state):
    if "pending" not in state:
        return
    pending = state["pending"]
    _, current = spotify.items()
    if current != pending["after"]:
        raise SyncError("Pending Spotify write needs review")
    finish(drive, state)
    LOG.info("Reconciled a pending Spotify write")


def send_pending(drive, state, send, *args):
    drive.save(state)
    try:
        send(*args)
    except HttpError as error:
        if error.status in {400, 401, 403, 404, 409, 429}:
            del state["pending"]
            drive.save(state)
        raise


def trim(drive, spotify, state, counts):
    snapshot, current = spotify.items()
    while len(current) > LIMIT:
        excess = min(len(current) - LIMIT, 100)
        targets = list(dict.fromkeys(uri for uri in current[:excess] if uri))
        if not targets:
            raise SyncError("Spotify's oldest entries have no removable URI")
        expected = [uri for uri in current if uri not in targets]
        state["pending"] = {"kind": "trim", "after": expected}
        send_pending(drive, state, spotify.remove, snapshot, targets)
        snapshot, updated = spotify.items()
        if updated != expected:
            raise SyncError("Spotify trim result needs review")
        finish(drive, state)
        counts["removed"] += len(current) - len(updated)
        current = updated


def sync(drive, spotify):
    state = checkpoint(drive, spotify.playlist)
    reconcile(drive, spotify, state)
    files = drive.histories()
    if not files:
        LOG.info("No matching history file")
        return
    item = max(files, key=lambda f: (datetime.fromisoformat(f["modifiedTime"].replace("Z", "+00:00")), f["id"]))
    plays = parse_m3u(drive.download(item))
    file_id = item["id"]
    last = state["positions"].get(file_id, 0)
    if last > len(plays):
        raise SyncError("History file is shorter than its checkpoint")

    counts = Counter(added=0, removed=0, unmatched=0, missing_metadata=0, search_failed=0)
    batch = []
    handled = last

    def flush():
        if batch:
            _, before = spotify.items()
            state["pending"] = {
                "kind": "append", "file": file_id, "position": handled,
                "after": before + batch,
            }
            send_pending(drive, state, spotify.append, batch)
            finish(drive, state)
            counts["added"] += len(batch)
            batch.clear()
        elif handled != state["positions"].get(file_id, 0):
            state["positions"][file_id] = handled
            drive.save(state)

    for entry in plays[last:]:
        handled = entry["position"]
        artist = entry.get("artist", "").strip()
        title = re.sub(r"\s*\(feat\.[^)]*\)", "", entry.get("title", ""), count=1, flags=re.I)
        title = re.sub(r"\s*\(radio edit\)", "", title, count=1, flags=re.I).strip()
        if not artist or not title:
            counts["missing_metadata"] += 1
            continue
        try:
            uri = spotify.search(artist, title)
        except (SyncError, ValueError, KeyError, TypeError) as error:
            counts["search_failed"] += 1
            LOG.warning("Search failed (%s)", str(error) if isinstance(error, SyncError) else "invalid response")
            continue
        if uri:
            batch.append(uri)
        else:
            counts["unmatched"] += 1
        if len(batch) == 100:
            flush()
    flush()
    trim(drive, spotify, state, counts)
    LOG.info("Sync finished: %s", " ".join(f"{key}={value}" for key, value in counts.items()))


def seed(drive, playlist):
    state = checkpoint(drive, playlist)
    if state["positions"] or "pending" in state:
        raise SyncError("Seeding requires a fresh checkpoint")
    state["positions"] = {item["id"]: len(parse_m3u(drive.download(item))) for item in drive.histories()}
    drive.save(state)
    LOG.info("Seeded positions for %s history files", len(state["positions"]))


def main():
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2.service_account import Credentials
    from requests import Session

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=["sync", "seed", "check-drive"], default="sync")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        credentials = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
        base_scope = "https://www.googleapis.com/auth/drive"
        with (
            AuthorizedSession(Credentials.from_service_account_file(credentials, scopes=[base_scope + ".readonly"]), refresh_timeout=30) as reader,
            AuthorizedSession(Credentials.from_service_account_file(credentials, scopes=[base_scope]), refresh_timeout=30) as writer,
            Session() as session,
        ):
            drive = Drive(reader, writer, os.environ["VDJ_HISTORY_GOOGLE_DRIVE_FOLDER_ID"], os.environ["DRIVE_CHECKPOINT_FILE_ID"])
            if args.mode == "check-drive":
                files = drive.histories()
                if files:
                    parse_m3u(drive.download(files[0]))
                original = drive.load()
                drive.save(original)
                if drive.load() != original:
                    raise SyncError("Drive checkpoint read-back differed")
                LOG.info("Drive checkpoint read and write verified, matching history files=%s", len(files))
                return 0
            playlist = os.environ["SPOTIFY_PLAYLIST_ID"]
            if args.mode == "seed":
                seed(drive, playlist)
                return 0
            token = request(
                session, "Spotify token", "POST", "https://accounts.spotify.com/api/token",
                auth=(os.environ["SPOTIFY_CLIENT_ID"], os.environ["SPOTIFY_CLIENT_SECRET"]),
                data={"grant_type": "refresh_token", "refresh_token": os.environ["SPOTIFY_REFRESH_TOKEN"]},
            ).json()["access_token"]
            session.headers["Authorization"] = f"Bearer {token}"
            sync(drive, Spotify(session, playlist))
        return 0
    except SyncError as error:
        LOG.error("%s", error)
    except KeyError:
        LOG.error("Required configuration or API field is missing")
    except Exception as error:
        LOG.error("Sync failed (%s)", type(error).__name__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
