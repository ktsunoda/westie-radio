const MAX_SPOTIFY_PLAYLIST_SIZE = 200;
const SPOTIFY_API_BATCH_SIZE = 100;
const SPOTIFY_SEARCH_API_URL = 'https://api.spotify.com/v1/search';
const SPOTIFY_PLAYLISTS_API_URL = 'https://api.spotify.com/v1/playlists';

function getSpotifyService() {
  return OAuth2.createService('spotify')
    .setAuthorizationBaseUrl('https://accounts.spotify.com/authorize')
    .setTokenUrl('https://accounts.spotify.com/api/token')
    .setClientId(PropertiesService.getScriptProperties().getProperty('SPOTIFY_CLIENT_ID'))
    .setClientSecret(PropertiesService.getScriptProperties().getProperty('SPOTIFY_CLIENT_SECRET'))
    .setCallbackFunction('authCallback')
    .setPropertyStore(PropertiesService.getUserProperties())
    .setScope('playlist-modify-public playlist-modify-private')
    .setParam('response_type', 'code')
    .setTokenHeaders({
      Authorization:
        'Basic ' +
        Utilities.base64Encode(
          PropertiesService.getScriptProperties().getProperty('SPOTIFY_CLIENT_ID') +
            ':' +
            PropertiesService.getScriptProperties().getProperty('SPOTIFY_CLIENT_SECRET')
        ),
    });
}

function getSpotifyAccessToken() {
  const service = getSpotifyService();
  if (!service.hasAccess()) {
    throw new Error('Spotify access not authorized. Run authorizeSpotify() first.');
  }
  return service.getAccessToken();
}

// eslint-disable-next-line no-unused-vars
function authCallback(request) {
  const authorized = getSpotifyService().handleCallback(request);
  return HtmlService.createHtmlOutput(
    authorized ? 'Success! You can close this tab.' : 'Denied! You can close this tab.'
  );
}

// eslint-disable-next-line no-unused-vars
function authorizeSpotify() {
  const service = getSpotifyService();
  if (!service.hasAccess()) {
    const authorizationUrl = service.getAuthorizationUrl();
    log(`Open the following URL and authorize the app: ${authorizationUrl}`);
  } else {
    log('Spotify access already granted.');
  }
}

// eslint-disable-next-line no-unused-vars
function getSpotifyTrackUri(artist, title) {
  const query = encodeURIComponent(`track:${title} artist:${artist}`);
  const url = `${SPOTIFY_SEARCH_API_URL}?q=${query}&type=track&limit=1`;

  const response = UrlFetchApp.fetch(url, {
    method: 'get',
    headers: {
      Authorization: `Bearer ${getSpotifyAccessToken()}`,
    },
    muteHttpExceptions: true,
  });

  const result = JSON.parse(response.getContentText());

  if (result.tracks && result.tracks.items.length > 0) {
    return result.tracks.items[0].uri;
  }

  return null;
}

// eslint-disable-next-line no-unused-vars
function getSpotifyPlaylistSize() {
  const playlistId = PropertiesService.getScriptProperties().getProperty('SPOTIFY_PLAYLIST_ID');
  const url = `${SPOTIFY_PLAYLISTS_API_URL}/${playlistId}/tracks?fields=total`;

  const response = UrlFetchApp.fetch(url, {
    method: 'get',
    headers: {
      Authorization: 'Bearer ' + getSpotifyAccessToken(),
    },
  });

  const result = JSON.parse(response.getContentText());
  return result.total;
}

// eslint-disable-next-line no-unused-vars
function addTracksToSpotifyPlaylist(trackUris) {
  const playlistId = PropertiesService.getScriptProperties().getProperty('SPOTIFY_PLAYLIST_ID');
  const url = `${SPOTIFY_PLAYLISTS_API_URL}/${playlistId}/tracks`;
  const accessToken = getSpotifyAccessToken();

  for (const trackUri of trackUris) {
    const response = UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: 'Bearer ' + accessToken,
      },
      payload: JSON.stringify({ uris: [trackUri] }),
      muteHttpExceptions: true,
    });

    if (response.getResponseCode() !== 201) {
      const result = JSON.parse(response.getContentText());
      log(`Failed to add track ${trackUri}: ${JSON.stringify(result)}`);
    } else {
      log(`Successfully added track: ${trackUri}`);
    }
  }
}

// eslint-disable-next-line no-unused-vars
function removeFirstNTracks(n) {
  if (n <= 0) return;

  const playlistId = PropertiesService.getScriptProperties().getProperty('SPOTIFY_PLAYLIST_ID');
  const accessToken = getSpotifyAccessToken();
  const SPOTIFY_PLAYLISTS_API_URL = 'https://api.spotify.com/v1/playlists';

  const limit = Math.min(n, SPOTIFY_API_BATCH_SIZE); // Spotify's max page size
  const url = `${SPOTIFY_PLAYLISTS_API_URL}/${playlistId}/tracks?fields=items(track(uri))&limit=${limit}`;
  const response = UrlFetchApp.fetch(url, {
    method: 'get',
    headers: {
      Authorization: 'Bearer ' + accessToken,
    },
  });

  const result = JSON.parse(response.getContentText());
  const items = result.items;

  const tracksToRemove = items.slice(0, n).map((item, index) => ({
    uri: item.track.uri,
    positions: [index],
  }));

  const deleteResponse = UrlFetchApp.fetch(`${SPOTIFY_PLAYLISTS_API_URL}/${playlistId}/tracks`, {
    method: 'delete',
    contentType: 'application/json',
    headers: {
      Authorization: 'Bearer ' + accessToken,
    },
    payload: JSON.stringify({ tracks: tracksToRemove }),
    muteHttpExceptions: true,
  });

  const deleteResult = JSON.parse(deleteResponse.getContentText());
  if (deleteResponse.getResponseCode() !== 200) {
    log(`Error removing tracks: ${JSON.stringify(deleteResult)}`);
  } else {
    log(`Successfully removed the first ${tracksToRemove.length} tracks.`);
  }
}
