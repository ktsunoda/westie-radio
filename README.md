# Westie Radio

Westie Radio syncs VirtualDJ play history from Google Drive to a rolling Spotify playlist. It runs as a Python command on a Render Cron Job, with a recommended schedule of every 15 minutes.

## How it works

- Upload VirtualDJ exports named `YYYY-MM-DD.m3u` directly to the configured history folder. Westie Radio picks the most recently modified matching file, including a prior day's file if it was updated later.
- The sync reads new media entries in order and searches Spotify using the artist, title, and any remix metadata. It checks the recording version and artist credits, and skips ambiguous matches. Repeated plays can appear more than once. Entries with missing metadata, no match, or a failed search are counted in the run logs and skipped.
- A private JSON file in Drive tracks the last handled position for each history file. Append new plays to the existing file to retain its Drive file ID and checkpoint. An unchanged rerun makes no Spotify writes if the playlist is already within the cap.
- The playlist is capped at 200 entries. Trimming selects URIs from the oldest entries. Spotify can remove newer copies of those URIs too, so the playlist may end up below 200.

## Set up your own deployment

Follow the [Render setup guide](docs/render-setup.md). The same guide is the runbook if you ask an agent to deploy Westie Radio for you.

You’ll need a Google Cloud project with the Drive API enabled, a service account, a Google Drive history folder and checkpoint file, a Spotify developer app and editable playlist, and a Render workspace. Start with a separate test playlist and checkpoint. Complete Spotify consent in your own browser, and put credentials directly into Render’s private settings. Keep keys, tokens, and private configuration out of the repository, chat, and logs.

If you’re migrating an existing sync, verify the test deployment before switching to the production playlist. The guide explains how to start at the end of your existing history so it doesn’t replay.

## Local development

Use Python 3.10 or newer.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

The offline tests need no Google or Spotify credentials. With the test configuration from the setup guide, run `python -m westie_radio check-drive` to verify Drive access or `python -m westie_radio` to sync the test playlist.

The [Apps Script audit](docs/apps-script-audit.md) and [migration plan](docs/migration-plan.md) document the retired implementation and the move to Python.

[MIT license](LICENSE)
