const LOG_SHEET_NAME = 'Logs';
const TRACKS_NOT_FOUND_SHEET_NAME = 'Tracks Not Found';

function log(message) {
  Logger.log(message);

  const sheet = getOrCreateLogSheet();
  sheet.appendRow([new Date().toISOString(), message]);
  cleanupOldLogs(sheet);
}

function printLogEntries() {
  const data = getOrCreateLogSheet().getDataRange().getValues();
  for (let i = 1; i < data.length; i++) {
    Logger.log(`[${data[i][0]}] ${data[i][1]}`);
  }
}

function cleanupOldLogs(sheet) {
  const cutoffDate = new Date(new Date().getTime() - 7 * 24 * 60 * 60 * 1000); // 7 days ago
  const data = sheet.getDataRange().getValues();

  for (let i = data.length - 1; i > 0; i--) {
    const logDate = new Date(data[i][0]);
    if (logDate < cutoffDate) {
      sheet.deleteRow(i + 1);
    }
  }
}

function getOrCreateLogSheet() {
  const googleSheet = getLoggingGoogleSheet();
  let sheet = googleSheet.getSheetByName(LOG_SHEET_NAME);

  if (!sheet) {
    sheet = googleSheet.insertSheet(LOG_SHEET_NAME);
    sheet.appendRow(['Timestamp', 'Message']);
  }

  return sheet;
}

function logNotFoundInSpotify(artist, title) {
  log(`Failed to find in Spotify: ${artist} - ${title}`);

  const googleSheet = getLoggingGoogleSheet();
  let sheet = googleSheet.getSheetByName(TRACKS_NOT_FOUND_SHEET_NAME);

  if (!sheet) {
    sheet = googleSheet.insertSheet(TRACKS_NOT_FOUND_SHEET_NAME);
    sheet.appendRow(['Timestamp', 'Artist', 'Title']);
  }

  sheet.appendRow([new Date().toISOString(), artist, title]);
}

function getLoggingGoogleSheet() {
  return SpreadsheetApp.openById(
    PropertiesService.getScriptProperties().getProperty('LOG_GOOGLE_DRIVE_SHEET_ID')
  );
}
