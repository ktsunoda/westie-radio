function isVdjSyncDisabled() {
  const files = getVdjHistoryFolderFiles();

  while (files.hasNext()) {
    if (files.next().getName().toLowerCase() === 'disabled') {
      return true;
    }
  }

  return false;
}

function getCurrentVdjHistoryFile() {
  const files = getVdjHistoryFolderFiles();
  const datePattern = /^\d{4}-\d{2}-\d{2}$/;

  let latestFile = null;
  let latestModifiedTime = 0;

  while (files.hasNext()) {
    const currentFile = files.next();

    if (
      !currentFile.getName().toLowerCase().endsWith('.m3u') ||
      !datePattern.test(currentFile.getName().split('.')[0])
    ) {
      log(`Skipping ${currentFile.getName()}`);
      continue;
    }

    const currentModifiedTime = currentFile.getLastUpdated().getTime();
    if (currentModifiedTime > latestModifiedTime) {
      latestModifiedTime = currentModifiedTime;
      latestFile = currentFile;
    }
  }

  return latestFile;
}

function getVdjHistoryFolderFiles() {
  return DriveApp.getFolderById(
    PropertiesService.getScriptProperties().getProperty('VDJ_HISTORY_GOOGLE_DRIVE_FOLDER_ID')
  ).getFiles();
}

function getVdjHistoryFileTracks(content) {
  const trackLines = content.split('\n');
  const tracks = [];

  for (let i = 0; i < trackLines.length; i++) {
    const trackLine = trackLines[i].trim();

    if (trackLine.startsWith('#EXTVDJ:')) {
      const artistMatch = trackLine.match(/<artist>(.*?)<\/artist>/);
      const titleMatch = trackLine.match(/<title>(.*?)<\/title>/);

      if (artistMatch && titleMatch) {
        const artist = artistMatch[1].trim();
        const title = cleanTrackTitle(titleMatch[1]);
        tracks.push({ artist, title });
      }
    }
  }

  return tracks;
}

function cleanTrackTitle(title) {
  return title
    .replace(/\s*\(feat\.[^)]*\)/i, '')
    .replace(/\s*\(radio edit\)/i, '')
    .trim();
}

function getLastProcessedVdjHistoryFileId() {
  return PropertiesService.getScriptProperties().getProperty('LAST_PROCESSED_VDJ_HISTORY_FILE_ID');
}

function setLastProcessedVdjHistoryFileId(fileId) {
  PropertiesService.getScriptProperties().setProperty('LAST_PROCESSED_VDJ_HISTORY_FILE_ID', fileId);
}

function clearOldTrackKeys() {
  const props = PropertiesService.getScriptProperties();
  const allProps = props.getProperties();

  for (const key in allProps) {
    if (key.startsWith('track::')) {
      props.deleteProperty(key);
    }
  }
}

function createTrackKey(fileId, artist, title) {
  return `track::${fileId}::${artist.toLowerCase().trim()}::${title.toLowerCase().trim()}`;
}

function hasTrackBeenProcessed(key) {
  return PropertiesService.getScriptProperties().getProperty(key) !== null;
}

function markTrackAsProcessed(key) {
  PropertiesService.getScriptProperties().setProperty(key, 'true');
}
