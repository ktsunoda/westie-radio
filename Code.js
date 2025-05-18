/* eslint-disable-next-line no-unused-vars */
function sync() {
  if (isVdjSyncDisabled()) {
    log('Sync is disabled.');
    return;
  }

  const file = getCurrentVdjHistoryFile();
  if (!file) {
    log('No VDJ history file found.');
    return;
  }

  log(`Sync is running on ${file.getName()}`);
  const fileId = file.getId();
  const lastProcessedFileId = getLastProcessedVdjHistoryFileId();

  if (fileId !== lastProcessedFileId) {
    log(`New file ${file.getName()} detected. Clearing old track keys.`);
    clearOldTrackKeys();
    setLastProcessedVdjHistoryFileId(fileId);
  }

  const tracks = getVdjHistoryFileTracks(file.getBlob().getDataAsString());
  const newTrackUris = [];

  for (const track of tracks) {
    const key = createTrackKey(fileId, track.artist, track.title);

    if (hasTrackBeenProcessed(key)) {
      log(`Skipping since already processed: ${track.artist} - ${track.title}`);
      continue;
    }
    markTrackAsProcessed(key);

    const trackUri = getSpotifyTrackUri(track.artist, track.title);
    if (trackUri) {
      newTrackUris.push(trackUri);
    } else {
      logNotFoundInSpotify(track.artist, track.title);
    }
  }

  if (newTrackUris.length > 0) {
    addTracksToSpotifyPlaylist(newTrackUris);
  }

  const trackUris = getSpotifyPlaylistTracks();
  let excessTrackCount = 0;
  if (trackUris.length > MAX_SPOTIFY_PLAYLIST_SIZE) {
    excessTrackCount = trackUris.length - MAX_SPOTIFY_PLAYLIST_SIZE;
    removeTracksFromSpotifyPlaylist(trackUris.slice(0, excessTrackCount));
  }

  log(`Finished syncing. Added ${newTrackUris.length} tracks and removed ${excessTrackCount}.`);
}
