# Westie Radio Python migration

Move the VirtualDJ history sync from Google Apps Script to a Python job on Render. Use two implementation commits and three verification checkpoints.

Use the [Apps Script audit](apps-script-audit.md) as the feature and regression acceptance checklist.

## Commit 1 — Python sync

- Copy the VirtualDJ parser, authenticated Drive download code, and relevant offline tests from the local `m3u-processor` checkout. Westie Radio owns the copied code and can run after the old repository is removed. Tagged Sheets import belongs to the future DJ History app.
- Scan the Drive folder every 15 minutes. Select the most recently modified exact `YYYY-MM-DD.m3u` filename, with a case-insensitive extension, so a late upload can make yesterday’s file active again.
- Track the last handled entry position by Drive file ID in a private, pre-created Drive JSON file outside the history folder. Configure its Drive file ID separately from the history folder ID so the checkpoint can live in a different folder. Process appended entries in order, preserve repeated plays, and ignore edits to handled entries. Flag a file that is shorter than its saved position.
- Preserve Spotify’s first-result artist/title matching and the existing title cleanup for featured artists and radio edits. Use Render for operational logs. Count and advance past unmatched plays, missing metadata, and search failures without a separate report.
- Persist pending Spotify appends and trims before sending them. Advance positions for matched plays after a confirmed append or a conclusive read-back. Retry definite failures when appropriate. Reconcile uncertain writes before retrying and pause for review if the result remains ambiguous. Stop before a Spotify mutation if the checkpoint cannot be read or the pending write cannot be saved.
- Cap the playlist at 200 entries by selecting URIs from the oldest entries. Spotify removes all occurrences of those URIs, so a trim can leave fewer than 200 entries.

**Checkpoint 1 — Offline tests.** Cover parsing, repeats, late uploads, unchanged reruns, and interrupted writes. Keep the Apps Script files available during testing.

## Commit 2 — Render configuration and setup

- Document the 15-minute schedule, build and run commands, required configuration, and setup steps. Use placeholders for credentials and private IDs. Keep keys, tokens, and private configuration out of GitHub and logs.
- Check the existing Render service type. The existing cron job has been renamed to `westie-radio`. Repoint it at this repository once the command is available and configure it for the separate live test.
- Verify whether the service account used by `m3u-processor` can read a test history folder and update a separate checkpoint file. The Apps Script uses `DriveApp`. If the existing account is unsuitable, set up a dedicated account. Use the same service account for both locations, with read access to the history folder and edit access to the checkpoint file.

**Checkpoint 2 — Live Render test.** Deploy against a separate test folder, Spotify playlist, and checkpoint. Verify that an unchanged rerun makes zero Spotify writes, a newly appended repeat is added once, the checkpoint survives a redeploy, and a run interrupted after Spotify accepts an append recovers without replaying it. Cross the 200-entry boundary with duplicates and verify URI-based trimming and the retained order.

## Production start

**Checkpoint 3 — Activate production.** Keep the test job isolated from production. Stop the Apps Script trigger and allow any in-flight run to finish. With DJ history idle, seed the production checkpoint at the end of the existing history files so late updates pick up new entries without replaying old ones. Start the Render job with production settings when ready and verify its first run and an unchanged rerun.
