# Westie Radio on Render

Use the existing `westie-radio` Cron Job. Point its build source at this repo only when the test configuration is ready. Keep the Apps Script trigger running until the live test is complete.

## Test configuration

Use a separate Spotify playlist that the authorizing user can edit. In Google Drive, create a test history folder with a sample `YYYY-MM-DD.m3u` file. Upload a regular file named `checkpoint-test.json` with contents `{}` to the Westie Radio app folder. Give the Westie Radio service account Viewer access to history and Editor access to the checkpoint. The Google Drive API must be enabled in the service account's project. The app uses a read-only Drive session for reading and a write-scoped session for the checkpoint. Drive sharing limits what the account can modify.

| Render setting | Value |
| --- | --- |
| Runtime | Python 3.10 or newer |
| Build command | `pip install -r requirements.txt` |
| Cron command | `python -m westie_radio` |
| Schedule | `*/15 * * * *` |
| Secret file | `westie-radio-service-account.json` |
| `GOOGLE_APPLICATION_CREDENTIALS` | `/etc/secrets/westie-radio-service-account.json` |
| `VDJ_HISTORY_GOOGLE_DRIVE_FOLDER_ID` | Test history folder ID |
| `DRIVE_CHECKPOINT_FILE_ID` | Test JSON file ID |
| `SPOTIFY_PLAYLIST_ID` | Test playlist ID |
| `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` | Spotify app credentials |
| `SPOTIFY_REFRESH_TOKEN` | Authorizing user's refresh token |

Obtain the Spotify refresh token using Spotify's [Authorization Code flow](https://developer.spotify.com/documentation/web-api/tutorials/code-flow) and a redirect URI registered with the Spotify app. Request the applicable playlist write scopes (`playlist-modify-private` or `playlist-modify-public`) and `playlist-read-private` for private playlist reads. Enter private settings directly into Render or supply them as local environment variables for testing. Keep keys, tokens, and private IDs out of Git and logs.

## Verify the test job

- Run `python -m westie_radio check-drive` with the test configuration to check listing, downloading a matching file if present, and saving and reading back the checkpoint. This command does not contact Spotify. Run it while the sync job is idle because it rewrites the checkpoint with its current contents.
- Run the sync twice with unchanged history. Verify that the second run adds and removes zero entries. Append a repeated play, run again, and confirm that it is added once.
- Exercise overflow past 200 and confirm that trimming removes the URIs selected from the oldest entries. All copies of those URIs can be removed, including more recent copies.
- Verify the checkpoint survives a redeploy. If a write is interrupted, the next run checks the observed playlist against the expected result. An inconclusive result leaves the pending operation in Drive and stops the run. Review the actual playlist and saved pending operation before resuming.
- Use Render's Logs and Runs pages for sync summaries and errors.

## Spotify authorization alerts

Set the cron job's notifications to **Only failure notifications** and enable **Email** as a notification destination in the Render workspace. Render sends failure emails for failed runs, including when Spotify rejects the refresh token. The job logs a reconnect message for `invalid_grant` and exits before reading or updating the checkpoint or playlist.

Spotify refresh tokens expire six months after authorization. Reauthorize the Spotify app and replace `SPOTIFY_REFRESH_TOKEN` in Render to resume from the saved position. Trigger one run to verify the replacement. [Render notifications](https://render.com/docs/notifications) · [Spotify refresh token expiration](https://developer.spotify.com/blog/2026-06-18-refresh-token-expiration)

## Start production

After the test passes, stop the Apps Script trigger and wait for any in-flight sync. Upload a fresh production checkpoint file containing `{}`. With the production Drive folder, checkpoint file, and Spotify playlist IDs configured, run `python -m westie_radio seed` while the scheduled job is idle. It records the current end of every matching file and does not call Spotify. Then activate the schedule and verify both the first run and an unchanged rerun.
