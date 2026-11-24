# Adapted from DJ Set Processor at 96e4c9b. Copyright (c) 2026 Koichi Tsunoda.
# Licensed under MIT.

import unittest
from unittest.mock import Mock

from westie_radio import Spotify


class SpotifyMatchingTests(unittest.TestCase):
    @staticmethod
    def candidate(uri, title, *artists):
        return {"uri": uri, "name": title, "artists": [{"name": name} for name in artists]}

    def test_search_recovers_reported_credit_differences(self):
        cases = [
            ("Feder & UPSAHL", "Let There Be Drums", "Let There Be Drums", ("Feder", "UPSAHL")),
            ("Rihanna", "Hate That I Love You (feat. Ne-Yo)", "Hate That I Love You", ("Rihanna", "Ne-Yo")),
            ("The Natural Synthetic, Miette Hope & Ariza", "Sacrifices", "Sacrifices",
             ("The Natural Synthetic", "Miette Hope", "Ariza")),
            ("Connor Price & Nic D", "Too Easy", "Too Easy", ("Connor Price", "Nic D")),
        ]
        for artist, title, catalog_title, credits in cases:
            with self.subTest(title=title):
                output = Spotify(Mock(), "test")
                output.api = Mock(side_effect=[
                    {"tracks": {"items": []}},
                    {"tracks": {"items": [
                        self.candidate("wrong", catalog_title, credits[0]),
                        self.candidate("right", catalog_title, *credits),
                    ]}},
                ])
                self.assertEqual(output.search(artist, title, ""), "right")
                query = output.api.call_args.kwargs["params"]["q"]
                self.assertEqual(query, f"track:{catalog_title} artist:{credits[0]}")

    def test_search_keeps_explicit_versions_including_radio_edit(self):
        for version in ("Radio Edit", "Live", "Acoustic", "Stripped", "Club Remix"):
            with self.subTest(version=version):
                output = Spotify(Mock(), "test")
                base = self.candidate("base", "Song", "Artist")
                correct = self.candidate("version", f"Song - {version}", "Artist")
                remix = version if version == "Club Remix" else ""
                title = "Song" if remix else f"Song ({version})"
                output.api = Mock(return_value={"tracks": {"items": [base, correct]}})
                self.assertEqual(output.search("Artist", title, remix), "version")
                output.api.return_value = {"tracks": {"items": [base]}}
                self.assertIsNone(output.search("Artist", title, remix))

    def test_search_prefers_literal_match_for_band_name(self):
        output = Spotify(Mock(), "test")
        output.api = Mock(return_value={"tracks": {"items": [
            self.candidate("split", "Song", "Earth", "Wind", "Fire"),
            self.candidate("band", "Song", "Earth, Wind & Fire"),
        ]}})
        self.assertEqual(output.search("Earth, Wind & Fire", "Song", ""), "band")
        output.api.assert_called_once()

    def test_plain_search_fallback_requires_the_tracking_room_recording(self):
        output = Spotify(Mock(), "test")
        original = self.candidate("original", "Delicate", "Taylor Swift")
        recording = self.candidate(
            "studio", "Delicate - Recorded at The Tracking Room Nashville", "Taylor Swift"
        )
        output.api = Mock(side_effect=[
            {"tracks": {"items": [original]}},
            {"tracks": {"items": [original, recording]}},
        ])
        title = "Delicate (Nashvilles Tracking Room Studios)"
        self.assertEqual(output.search("Taylor Swift", title, ""), "studio")
        self.assertEqual(output.api.call_args.kwargs["params"]["q"], f"{title} Taylor Swift")

    def test_search_does_not_duplicate_version_present_in_both_fields(self):
        for artist, title, version, catalog_title, credits in (
            ("Billy Raffoul", "Homebody (feat. OSKA) [The Red Version]", "The Red Version",
             "Homebody - The Red Version", ("Billy Raffoul", "OSKA")),
            ("Betcha", "July (Reimagined)", "Reimagined", "July - Reimagined", ("Betcha",)),
        ):
            with self.subTest(title=title):
                output = Spotify(Mock(), "test")
                output.api = Mock(return_value={"tracks": {"items": [
                    self.candidate("right", catalog_title, *credits),
                ]}})
                self.assertEqual(output.search(artist, title, version), "right")
                for request in output.api.call_args_list:
                    self.assertEqual(request.kwargs["params"]["q"].count(version), 1)

    def test_plain_search_rejects_cover_with_source_artist_only_in_title(self):
        output = Spotify(Mock(), "test")
        output.api = Mock(return_value={"tracks": {"items": [
            self.candidate("cover", "I Can Feel It (Originally Performed by Sickick)", "Vox Freaks"),
        ]}})
        self.assertIsNone(output.search("Sickick", "I Can Feel It", ""))

    def test_unique_lead_artist_recovers_missing_collaborator(self):
        output = Spotify(Mock(), "test")
        output.api = Mock(return_value={"tracks": {"items": [
            self.candidate("cover", "Aliens Need Love Too", "Another Artist"),
            self.candidate("live", "Aliens Need Love Too - Live", "Phlake"),
            self.candidate("match", "Aliens Need Love Too", "Phlake"),
        ]}})
        self.assertEqual(output.search("Phlake & Mercedes the Virus",
                                       "Aliens Need Love Too", ""), "match")

    def test_lead_artist_fallback_skips_distinct_recordings(self):
        output = Spotify(Mock(), "test")
        output.api = Mock(side_effect=[
            {"tracks": {"items": [self.candidate("one", "Song", "Artist")]}},
            {"tracks": {"items": [self.candidate("two", "Song", "Artist")]}},
            {"tracks": {"items": []}},
        ])
        self.assertIsNone(output.search("Artist & Guest", "Song", ""))

    def test_lead_artist_fallback_accepts_releases_of_same_recording(self):
        output = Spotify(Mock(), "test")
        candidates = [self.candidate(uri, "Song - Radio Edit", "Artist") for uri in ("single", "album")]
        for candidate in candidates:
            candidate["external_ids"] = {"isrc": "TEST00000001"}
        output.api = Mock(return_value={"tracks": {"items": candidates}})
        self.assertEqual(output.search("Artist & Guest", "Song (Radio Edit)", ""), "single")
