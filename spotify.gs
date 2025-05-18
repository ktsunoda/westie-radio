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

function authCallback(request) {
  const authorized = getSpotifyService().handleCallback(request);
  return HtmlService.createHtmlOutput(
    authorized ? 'Success! You can close this tab.' : 'Denied! You can close this tab.'
  );
}

function authorizeSpotify() {
  const service = getSpotifyService();
  if (!service.hasAccess()) {
    const authorizationUrl = service.getAuthorizationUrl();
    log(`Open the following URL and authorize the app: ${authorizationUrl}`);
  } else {
    log('Spotify access already granted.');
  }
}

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

function getSpotifyPlaylistTracks() {
  const playlistId = PropertiesService.getScriptProperties().getProperty('SPOTIFY_PLAYLIST_ID');
  const baseUrl = `${SPOTIFY_PLAYLISTS_API_URL}/${playlistId}/tracks?fields=items(track(uri)),next`;
  const trackUris = [];
  let nextUrl = baseUrl;

  while (nextUrl) {
    const response = UrlFetchApp.fetch(nextUrl, {
      method: 'get',
      headers: {
        Authorization: 'Bearer ' + getSpotifyAccessToken(),
      },
    });
    const result = JSON.parse(response.getContentText());
    for (const item of result.items) {
      if (item.track && item.track.uri) {
        trackUris.push(item.track.uri);
      }
    }
    nextUrl = result.next;
  }

  return trackUris;
}

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

function removeTracksFromSpotifyPlaylist(trackUris) {
  const playlistId = PropertiesService.getScriptProperties().getProperty('SPOTIFY_PLAYLIST_ID');
  const accessToken = getSpotifyAccessToken();

  for (let i = 0; i < trackUris.length; i += SPOTIFY_API_BATCH_SIZE) {
    const batch = trackUris.slice(i, i + SPOTIFY_API_BATCH_SIZE);
    const tracksToRemove = batch.map((uri) => ({ uri }));

    const response = UrlFetchApp.fetch(`${SPOTIFY_PLAYLISTS_API_URL}/${playlistId}/tracks`, {
      method: 'delete',
      contentType: 'application/json',
      headers: {
        Authorization: 'Bearer ' + accessToken,
      },
      payload: JSON.stringify({ tracks: tracksToRemove }),
      muteHttpExceptions: true,
    });

    const result = JSON.parse(response.getContentText());
    if (response.getResponseCode() !== 200) {
      log(`Error removing tracks: ${JSON.stringify(result)}`);
    } else {
      log(`Successfully removed ${batch.length} tracks from the playlist.`);
    }
  }
}
