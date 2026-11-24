from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock

from virtualdj import parse_m3u
from westie_radio import Drive, HttpError, SyncError, request, sync


PLAY = "#EXTVDJ:<artist>SOFI TUKKER & Silva</artist><title>Café (Radio Edit)</title><remix>Live</remix><songlength>201.732</songlength>\r\n/music/Café.m4a\r\n"


class History:
    def __init__(self):
        self.state = {}
        self.text = PLAY
        self.files = [{"id": "older", "modifiedTime": "2026-10-02T00:00:00Z"},
                      {"id": "late", "modifiedTime": "2026-10-02T01:00:00Z"}]

    def load(self):
        return deepcopy(self.state)

    def save(self, state):
        self.state = deepcopy(state)

    def histories(self):
        return self.files

    def download(self, item):
        return self.text


class Playlist:
    playlist = "test"

    def __init__(self):
        self.uris = []
        self.writes = []

    def items(self):
        return str(len(self.writes)), self.uris.copy()

    def search(self, artist, title):
        return "repeat"

    def append(self, uris):
        self.writes.append("append")
        self.uris.extend(uris)

    def remove(self, snapshot, uris):
        self.writes.append("remove")
        self.uris = [uri for uri in self.uris if uri not in uris]
        return str(len(self.writes))


class SyncTests(TestCase):
    def setUp(self):
        self.drive = History()
        self.spotify = Playlist()

    def test_parser_reuses_order_and_metadata(self):
        plays = parse_m3u("\ufeff#EXTM3U\r\n" + PLAY * 2)
        self.assertEqual([play["position"] for play in plays], [1, 2])
        self.assertEqual(plays[0]["remix"], "Live")
        self.assertEqual(plays[1]["duration_seconds"], 201.732)

    def test_drive_private_download(self):
        reader = Mock()
        reader.request.return_value.status_code = 200
        reader.request.return_value.content = ("\ufeff" + PLAY).encode()
        drive = Drive(reader, Mock(), "history", "checkpoint")
        self.assertEqual(drive.download({"id": "file", "resourceKey": "key"}), PLAY)
        self.assertEqual(reader.request.call_args.kwargs["headers"], {
            "X-Goog-Drive-Resource-Keys": "file/key",
        })

    def test_late_history_repeats_and_unchanged_rerun(self):
        sync(self.drive, self.spotify)
        sync(self.drive, self.spotify)
        self.drive.text += PLAY
        sync(self.drive, self.spotify)
        self.assertEqual(self.spotify.writes, ["append", "append"])
        self.assertEqual(self.spotify.uris, ["repeat", "repeat"])
        self.assertEqual(self.drive.state["positions"], {"late": 2})

    def test_search_failure_advances(self):
        self.spotify.search = Mock(side_effect=SyncError("search failed"))
        sync(self.drive, self.spotify)
        sync(self.drive, self.spotify)
        self.spotify.search.assert_called_once_with("SOFI TUKKER & Silva", "Café")
        self.assertEqual(self.drive.state["positions"], {"late": 1})
        self.assertEqual(self.spotify.writes, [])

    def test_interrupted_append_is_reconciled(self):
        append = self.spotify.append

        def interrupted(uris):
            append(uris)
            raise SyncError("response lost")

        self.spotify.append = interrupted
        with self.assertRaises(SyncError):
            sync(self.drive, self.spotify)
        sync(self.drive, self.spotify)
        self.assertEqual(self.spotify.uris, ["repeat"])
        self.assertEqual(self.drive.state["positions"], {"late": 1})

    def test_definite_rejection_leaves_position_retryable(self):
        append = self.spotify.append
        self.spotify.append = Mock(side_effect=HttpError("Spotify", "POST", 429))
        with self.assertRaises(HttpError):
            sync(self.drive, self.spotify)
        self.assertEqual(self.drive.state["positions"], {})
        self.assertNotIn("pending", self.drive.state)
        self.spotify.append = append
        sync(self.drive, self.spotify)
        self.assertEqual(self.spotify.uris, ["repeat"])

    def test_trim_by_uri_can_remove_newer_copies(self):
        self.spotify.uris = ["repeat"] + [str(n) for n in range(199)]
        sync(self.drive, self.spotify)
        self.assertEqual(self.spotify.writes, ["append", "remove"])
        self.assertEqual(self.spotify.uris, [str(n) for n in range(199)])

    def test_interrupted_trim_is_reconciled(self):
        self.drive.text = ""
        self.spotify.uris = [str(n) for n in range(201)]
        remove = self.spotify.remove

        def interrupted(snapshot, uris):
            remove(snapshot, uris)
            raise SyncError("response lost")

        self.spotify.remove = interrupted
        with self.assertRaises(SyncError):
            sync(self.drive, self.spotify)
        sync(self.drive, self.spotify)
        self.assertEqual(self.spotify.writes, ["remove"])
        self.assertEqual(self.spotify.uris, [str(n) for n in range(1, 201)])

    def test_ambiguous_append_pauses_before_another_write(self):
        self.spotify.append = Mock(side_effect=SyncError("response lost"))
        with self.assertRaises(SyncError):
            sync(self.drive, self.spotify)
        with self.assertRaisesRegex(SyncError, "needs review"):
            sync(self.drive, self.spotify)
        self.spotify.append.assert_called_once()

    def test_missing_history_does_not_write(self):
        self.drive.files = []
        sync(self.drive, self.spotify)
        self.assertEqual(self.spotify.writes, [])

    def test_file_switch_keeps_old_positions(self):
        older, late = self.drive.files
        sync(self.drive, self.spotify)
        self.drive.files = [older]
        sync(self.drive, self.spotify)
        self.drive.files = [older, late]
        sync(self.drive, self.spotify)
        self.assertEqual(self.drive.state["positions"], {"late": 1, "older": 1})
        self.assertEqual(self.spotify.writes, ["append", "append"])

    def test_expired_spotify_authorization_reports_reconnect(self):
        session = Mock()
        response = session.request.return_value
        response.status_code = 400
        response.json.return_value = {
            "error": "invalid_grant", "error_description": "private diagnostic",
        }
        with self.assertRaisesRegex(SyncError, "Reconnect Westie Radio") as failure:
            request(session, "Spotify token", "POST", "https://example.test/token")
        self.assertNotIn("private diagnostic", str(failure.exception))
        session.request.assert_called_once()

    def test_successful_trim_can_leave_a_newer_copy(self):
        self.spotify.uris = ["repeat"] + [str(n) for n in range(199)]

        def keep_newer_copy(snapshot, uris):
            self.assertEqual(uris, ["repeat"])
            self.spotify.writes.append("remove")
            self.spotify.uris.pop(0)
            return str(len(self.spotify.writes))

        self.spotify.remove = keep_newer_copy
        sync(self.drive, self.spotify)
        self.assertEqual(self.spotify.uris, [str(n) for n in range(199)] + ["repeat"])
        self.assertNotIn("pending", self.drive.state)
