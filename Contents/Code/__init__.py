# Rewrite (use JSON API, other matching tweaks) by ToMM

import time

# PROXY
import lastfm # This is only requried while we're emulating legacy calls for the proxy.
PROXY_THRESHOLD_URL = 'http://www.plexapp.com/agents/com.plexapp.agents.lastfm' # This should return desired percentage of "new style" requests.
PROXY_THRESHOLD_CACHE_TIME = CACHE_1DAY # How long to cache the proxy threshold value returned from the above.
PROXY_THRESHOLD = None # Hard-coded percentage of "new style" requests or None to make HTTP request instead.
# END PROXY

# Last.fm API
API_KEY = 'd5310352469c2631e5976d0f4a599773'

# BASE_URL = 'http://ws.audioscrobbler.com/2.0/'
BASE_URL = 'http://lastfm-z.plexapp.com/2.0/'

ARTIST_SEARCH_URL = BASE_URL + '?method=artist.search&artist=%s&page=%d&limit=%d&format=json&api_key=' + API_KEY
ARTIST_ALBUM_SEARCH_URL = BASE_URL + '?method=artist.gettopalbums&artist=%s&page=%s&limit=%s&format=json&api_key=' + API_KEY
ARTIST_INFO_URL = BASE_URL + '?method=artist.getInfo&artist=%s&autocorrect=1&lang=%s&format=json&api_key=' + API_KEY

ALBUM_SEARCH_URL = BASE_URL + '?method=album.search&album=%s&limit=%s&format=json&api_key=' + API_KEY
ALBUM_INFO_URL = BASE_URL + '?method=album.getInfo&artist=%s&album=%s&autocorrect=1&lang=%s&format=json&api_key=' + API_KEY

ARTWORK_SIZE_RANKING = { 'mega':0 , 'extralarge':1 , 'large':2 } # Don't even try to add 'medium' or 'small' artwork.
VARIOUS_ARTISTS_POSTER = 'http://userserve-ak.last.fm/serve/252/46209667.png'

# Tunables.
ARTIST_MATCH_LIMIT = 9 # Max number of artists to fetch for matching purposes.
ARTIST_MATCH_MIN_SCORE = 75 # Minimum score required to add to custom search results.
ARTIST_MANUAL_MATCH_LIMIT = 120 # Number of artists to fetch when trying harder for manual searches.  Multiple API hits.
ARTIST_SEARCH_PAGE_SIZE = 30 # Number of artists in a search result page.  Asking for more has no effect.
ARTIST_ALBUMS_MATCH_LIMIT = 5 # Max number of artist matches to try for album bonus.  Each one incurs an additional API request.
ARTIST_ALBUMS_LIMIT = 50 # Number of albums by artist to grab for artist matching bonus and quick album match.
ARTIST_MIN_LISTENER_THRESHOLD = 1000 # Minimum number of listeners for an artist to be considered credible.
ALBUM_MATCH_LIMIT = 8 # Max number of results returned from standalone album searches with no artist info (e.g. Various Artists).
ALBUM_MATCH_MIN_SCORE = 75 # Minimum score required to add to custom search results.
ALBUM_MATCH_GOOD_SCORE = 96 # Minimum score required to rely on only Albums by Artist and not search.
ALBUM_TRACK_BONUS_MATCH_LIMIT = 5 # Max number of albums to try for track bonus.  Each one incurs at most one API request per album.
QUERY_SLEEP_TIME = 0.5 # How long to sleep before firing off each API request.
REQUEST_RETRY_LIMIT = 3 # Number of times to retry failing API requests.
REQUEST_RETRY_SLEEP_TIME = 5 # Number of seconds to sleep between failing API requests.

# Advanced tunables.
NAME_DISTANCE_THRESHOLD = 2 # How close do album/track names need to be to match for bonuses?
ARTIST_INITIAL_SCORE = 90 # Starting point for artists before bonus/deductions.
ARTIST_ALBUM_BONUS_INCREMENT = 1 # How much to boost the bonus for a each good artist/album match.
ARTIST_ALBUM_MAX_BONUS = 15 # Maximum number of bonus points to give artists with good album matches.
ARTIST_LENGTH_PENALTY_COEFFICIENT = 2 # How much to penzlize for each character of name length difference.
ALBUM_INITIAL_SCORE = 92 # Starting point for albums before bonus/deductions.
ALBUM_TRACK_BONUS_INCREMENT = 1 # How much to boost the bonus for a each good album/track match.
ALBUM_TRACK_MAX_BONUS = 20 # Maximum number of bonus points to give to albums with good track name matches.
ALBUM_TRACK_NUM_DISTANCE_THRESHOLD = 2 # How close does the ordering need to match to get additional track order bonus.
ALBUM_NUM_TRACKS_BONUS = 5 # How much to boost the bonus if the total number of tracks match.

RE_STRIP_PARENS = Regex('\([^)]*\)')

def Start():
  HTTP.CacheTime = CACHE_1WEEK

class LastFmAgent(Agent.Artist):
  name = 'Last.fm'
  #languages = [Locale.Language.English, Locale.Language.Korean]
  languages = [Locale.Language.English, Locale.Language.Swedish, Locale.Language.French,
               Locale.Language.Spanish, Locale.Language.German, Locale.Language.Polish,
               Locale.Language.Italian, Locale.Language.Portuguese, Locale.Language.Japanese,
               Locale.Language.Turkish, Locale.Language.Russian, Locale.Language.Chinese]

  def search(self, results, media, lang, manual):

    # Handle a couple of edge cases where artist search will give bad results.
    if media.artist == '[Unknown Artist]': 
      return
      
    if media.artist == 'Various Artists':
      results.Append(MetadataSearchResult(id = 'Various%20Artists', name= 'Various Artists', thumb = VARIOUS_ARTISTS_POSTER, lang  = lang, score = 100))
      return
    
    # Search for artist.
    Log('Artist search: ' + media.artist)
    if manual:
      Log('Running custom search...')
    artists = []
    artist_results = []
    artists = SearchArtists(media.artist, ARTIST_MATCH_LIMIT)
    self.score_artists(artists, media, lang, artist_results)

    if manual and not artist_results:
      # We didn't find a good match in the top N.  If this is a manual/custom search, try harder.
      Log('Fetching additional artists for custom search...')
      artists = SearchArtists(media.artist, ARTIST_MANUAL_MATCH_LIMIT)
      self.score_artists(artists, media, lang, artist_results)

    for artist in artist_results:
      results.Append(artist)

  def score_artists(self, artists, media, lang, artist_results):
    for i, artist in enumerate(artists):
      # If there's only a single result, it will not include the 'listeners' key.
      # Distrust artists with fewer than N listeners.
      if artist.has_key('listeners') and artist['listeners'] < ARTIST_MIN_LISTENER_THRESHOLD:
        Log('Skipping %s with only %d listeners.' % (artist['name'], artist['listeners']))
        continue

      # Need to coerce this into a utf-8 string so String.Quote() escapes the right characters.
      id = String.Quote(artist['name'].decode('utf-8').encode('utf-8')).replace(' ','+')
      # Search returns ordered results, but no numeric score, so we approximate one with Levenshtein distance.
      dist = Util.LevenshteinDistance(artist['name'].lower(), media.artist.lower())
      # Penalize difference in length (further differentiate common mismatches, e.g. "Cave" matching "Nick Cave")
      dist = dist + ARTIST_LENGTH_PENALTY_COEFFICIENT * abs(len(artist['name'].decode('utf-8').encode('utf-8')) - len(media.artist.decode('utf-8').encode('utf-8')))
      if i < ARTIST_ALBUMS_MATCH_LIMIT:
        bonus = self.get_album_bonus(media, artist_id=id)
      else:
        bonus = 0
      score = ARTIST_INITIAL_SCORE + bonus - dist
      name = artist['name']
      Log('Artist result: ' + name + ' dist: ' + str(dist) + ' album bonus: ' + str(bonus) + ' score: ' + str(score))
      if score >= ARTIST_MATCH_MIN_SCORE:
        artist_results.append(MetadataSearchResult(id=id, name=name, lang=lang, score=score))
      else:
        Log('Skipping artist, didn\'t meet minimum score of ' + str(ARTIST_MATCH_MIN_SCORE))


  def get_album_bonus(self, media, artist_id):
    Log('Fetching artist\'s albums and applying album bonus.')
    bonus = 0
    albums = GetAlbumsByArtist(artist_id, albums=[], limit=ARTIST_ALBUMS_LIMIT)
    try:
      for a in media.children:
        media_album = a.title.lower()
        for album in albums:
          if Util.LevenshteinDistance(media_album,album['name'].lower()) <= NAME_DISTANCE_THRESHOLD:
            bonus += ARTIST_ALBUM_BONUS_INCREMENT
          # This is a cheap comparison, so let's try again with the contents of parentheses removed, e.g. "(limited edition)"
          elif Util.LevenshteinDistance(media_album,RE_STRIP_PARENS.sub('',album['name'].lower())) <= NAME_DISTANCE_THRESHOLD:
            bonus += ARTIST_ALBUM_BONUS_INCREMENT
          if bonus >= ARTIST_ALBUM_MAX_BONUS:
            break
    except:
      Log('Did\'t find usable albums in search results, not applying artist album bonus.')
      # raise
    if bonus > 0:
      Log('Applying album bonus of: ' + str(bonus))
    return bonus
  

  def update(self, metadata, media, lang):
    artist = GetArtist(metadata.id, lang)
    if not artist:
      return

    # Name.
    metadata.title = artist['name']

    # Bio.
    metadata.summary = String.StripTags(artist['bio']['content'][:artist['bio']['content'].find('\n\n')]).strip()

    # Artwork.
    if artist['name'] == 'Various Artists':
      metadata.posters[VARIOUS_ARTISTS_POSTER] = Proxy.Media(HTTP.Request(VARIOUS_ARTISTS_POSTER))
    else:
      valid_keys = []
      try:
        for image in artist['image']:
          try:
            if image['size'] in ARTWORK_SIZE_RANKING:
              valid_keys.insert(ARTWORK_SIZE_RANKING[image['size']],image['#text'])
          except:
            pass
        if valid_keys:
          metadata.posters[valid_keys[0]] = Proxy.Media(HTTP.Request(image['#text']))
          metadata.posters.validate_keys(valid_keys[0])
      except:
        Log('Couldn\'t add artwork for artist.')
        #raise

    # Genres.
    if Prefs['genres']:
      try:
        metadata.genres.clear()
        if isinstance(artist['tags'], dict) and artist['tags'].has_key('tag'):
          if not isinstance(artist['toptags']['tag'], list):
            artist['toptags']['tag'] = [artist['toptags']['tag']]
          for genre in artist['tags']['tag']:
            metadata.genres.add(genre['name'].capitalize())
      except:
        Log('Couldn\'t add genre tags for artist.')

  
class LastFmAlbumAgent(Agent.Album):
  name = 'Last.fm'
  languages = [Locale.Language.English, Locale.Language.Swedish, Locale.Language.French,
               Locale.Language.Spanish, Locale.Language.German, Locale.Language.Polish,
               Locale.Language.Italian, Locale.Language.Portuguese, Locale.Language.Japanese,
               Locale.Language.Turkish, Locale.Language.Russian, Locale.Language.Chinese]

  fallback_agent = 'com.plexapp.agents.allmusic'
  
  def search(self, results, media, lang, manual):
    
    # Handle a couple of edge cases where album search will give bad results.
    if media.parent_metadata.id is None:
      return
    if media.parent_metadata.id == '[Unknown Album]':
      return #eventually, we might be able to look at tracks to match the album
    
    # Search for album.
    Log('Album search: ' + media.title)
    if manual:
      Log('Running custom search...')
    
    albums = []
    found_good_match = False
    # First search for albums by artist if not 'Various Artists', if we don't get a good match, search directly.
    if media.parent_metadata.id != 'Various%20Artists':
      if not manual:
        # Let's start with the first N albums (ideally a single API request)...
        albums = self.score_albums(media, lang, GetAlbumsByArtist(media.parent_metadata.id, albums=[], limit=ARTIST_ALBUMS_LIMIT))
        if albums and albums[0]['score'] >= ALBUM_MATCH_GOOD_SCORE:
          # We found a good match in the first set of results, stop looking.
          found_good_match = True
          Log('Good album match found (quick search)  with score: ' + str(albums[0]['score']))
      if not found_good_match or manual:
        if manual:
          Log('Custom search terms specified, fetching all albums by artist.')
        else:
          Log('No good matches found in first ' + str(len(albums)) + ' albums, fetching all albums by artist.')
        albums = self.score_albums(media, lang, GetAlbumsByArtist(media.parent_metadata.id, albums=[]), manual=manual)
        if albums and albums[0]['score'] >= ALBUM_MATCH_GOOD_SCORE:
          Log('Good album match found with score: ' + str(albums[0]['score']))
          found_good_match = True
        else:
          Log('No good matches found in ' + str(len(albums)) + ' albums by artist.')

    # Either we're looking at Various Artists, or albums by artist search did not contain a good match.
    if not found_good_match or albums:
      # PROXY
      # Only make these extra requests in the event of subpar AlbumsByArtist matches if we're okay with cache misses (old agent never makes them).
      #if not ShouldProxy(media.parent_metadata.id + '/' + media.title) or media.parent_metadata.id == 'Various%20Artists':
      if media.parent_metadata.id == 'Various%20Artists':
      # END PROXY  
        albums = self.score_albums(media, lang, SearchAlbums(media.title.lower(), ALBUM_MATCH_LIMIT), manual=manual) + albums
        if albums and albums[0]['score'] >= ALBUM_MATCH_GOOD_SCORE:
          # Found a good match, stop looking.
          found_good_match = True
          Log('Found a good match for album search.')
        if not albums or not found_good_match:
          stripped_title = RE_STRIP_PARENS.sub('',media.title).lower()
          if stripped_title != media.parent_metadata.id:
            Log('No good matches found in album search for %s, searching for %s.' % (media.title.lower(), stripped_title))
            # This time we extend the results  and re-sort so we consider the best-scoring matches from both searches.
            albums  = self.score_albums(media, lang, SearchAlbums(stripped_title), manual=manual) + albums
          if albums:
            albums = sorted(albums, key=lambda k: k['score'], reverse=True)

    # Dedupe albums.
    seen = {}
    deduped = []
    for album in albums:
      if album['id'] in seen:
        continue
      seen[album['id']] = True
      deduped.append(album)
    albums = deduped

    Log('Found ' + str(len(albums)) + ' albums...')

    for album in albums:
      results.Append(MetadataSearchResult(id = album['id'], name = album['name'], lang = album['lang'], score = album['score']))

  def score_albums(self, media, lang, albums, manual=False):
    res = []
    matches = []
    for album in albums:
      try:
        name = album['name']
        if album.has_key('artist'):
          if not isinstance(album['artist'], unicode) and not isinstance(album['artist'], str):
            artist = album['artist']['name']
          else:
            artist = album['artist']
        else:
          artist = ''
        id = media.parent_metadata.id + '/' + String.Quote(album['name'].decode('utf-8').encode('utf-8')).replace(' ','+')
        dist = Util.LevenshteinDistance(name.lower(),media.title.lower())
        if media.parent_metadata.id == 'Various%20Artists' and artist != 'Various Artists':
          artist_dist = 1000 # Penalize spurious Various Artists mismatches heavily (skip them)
          Log('Penalizing bad result for Various Artists search: ' + artist)
        else:
          artist_dist = Util.LevenshteinDistance(artist.lower(),String.Unquote(media.parent_metadata.id).lower())
        score = ALBUM_INITIAL_SCORE - dist - artist_dist
        res.append({'id':id, 'name':name, 'lang':lang, 'score':score})
      except:
        Log('Error scoring album.')

    if res:
      res = sorted(res, key=lambda k: k['score'], reverse=True)
      for i, result in enumerate(res):
          # Querying for track bonus is expensive (each one is an API request), so only do it for the top N results.
          if i < ALBUM_TRACK_BONUS_MATCH_LIMIT:
            bonus = self.get_track_bonus(media, result['name'], lang)
            res[i]['score'] = res[i]['score'] + bonus
          if res[i]['score'] >= ALBUM_MATCH_MIN_SCORE:
            Log('Album result: ' + result['name'] + ' album bonus: ' + str(bonus) + ' score: ' + str(result['score']))
            matches.append(res[i])
          else:
            Log('Skipping %d album results that don\'t meet the minimum score of %d.' % (len(res) - i, ALBUM_MATCH_MIN_SCORE))
            break

    if matches:
      return sorted(matches, key=lambda k: k['score'], reverse=True)
    else:
      return matches
  
  def get_track_bonus(self, media, name, lang):
    tracks = GetTracks(media.parent_metadata.id, String.Quote(name.decode('utf-8').encode('utf-8')).replace(' ','+'), lang)
    bonus = 0
    try:
      for i, t in enumerate(media.children):
        media_track = t.title.lower()
        for j, track in enumerate(tracks):
          score = Util.LevenshteinDistance(track['name'].lower(), media_track)
          if score <= NAME_DISTANCE_THRESHOLD:
            bonus += ALBUM_TRACK_BONUS_INCREMENT
            # If the tracks also appear close to the same order, boost a little more.
            if abs(i-j) < ALBUM_TRACK_NUM_DISTANCE_THRESHOLD:
              bonus += ALBUM_TRACK_BONUS_INCREMENT
      # If the albums have the same number of tracks, boost more.
      if len(media.children) == len(tracks):
        bonus += ALBUM_NUM_TRACKS_BONUS
      if bonus >= ALBUM_TRACK_MAX_BONUS:
        bonus = ALBUM_TRACK_MAX_BONUS
    except:
        Log('Didn\'t find any usable tracks in search results, not applying track bonus.')
        # raise
    if bonus > 0:
      Log('Applying track bonus of: ' + str(bonus))
    return bonus
 
  def update(self, metadata, media, lang):
    album = GetAlbum(metadata.id.split('/')[0], metadata.id.split('/')[1], lang)
    if not album:
      return

    # Title.
    metadata.title = album['name']
    
    # Artwork.
    valid_keys = []
    try:
      for image in album['image']:
        try:
          if image['size'] in ARTWORK_SIZE_RANKING:
            valid_keys.insert(ARTWORK_SIZE_RANKING[image['size']],image['#text'])
        except:
          pass
      if valid_keys:
        metadata.posters[valid_keys[0]] = Proxy.Media(HTTP.Request(image['#text']))
        metadata.posters.validate_keys(valid_keys[0])
    except:
      Log('Couldn\'t add artwork for album.')
      # raise

    # Release Date.
    try:
      if album['releasedate']:
        metadata.originally_available_at = Datetime.ParseDate(album['releasedate'].split(',')[0].strip())
    except:
      Log('Couldn\'t add release date to album.')
      
    # Genres.
    if Prefs['genres']:
      try:
        metadata.genres.clear()
        if isinstance(album['toptags'], dict) and album['toptags'].has_key('tag'):
          if not isinstance(album['toptags']['tag'], list):
            album['toptags']['tag'] = [album['toptags']['tag']]
          for genre in album['toptags']['tag']:
            metadata.genres.add(genre['name'].capitalize())
      except:
        Log('Couldn\'t add genre tags to album.')
        # raise

def SearchArtists(artist, limit=10, legacy=False):
  artists = []
  url = ARTIST_SEARCH_URL % (String.Quote(artist.lower()), 1, limit)
  # PROXY
  if ShouldProxy(url):
    try:
      artist = SafeStrip(artist.lower())
      for lfm_artist in lastfm.SearchArtists(artist,limit=5)[0]:
        (url, name, image, listeners) = lfm_artist
        img = {}
        artists.append({'name':name, 'listeners':listeners})
      return artists
    except:
      Log('Error retreiving artist search results (legacy request).')
      # raise
  else:
  # END PROXY
    lim = min(limit,ARTIST_SEARCH_PAGE_SIZE)
    for i in range((limit-1)/ARTIST_SEARCH_PAGE_SIZE+1):
      url = ARTIST_SEARCH_URL % (String.Quote(artist.lower()), i+1, lim)
      try: 
        response = GetJSON(url)
        if response.has_key('error'):
          Log('Error retrieving artist search results: ' + response['message'])
          return artists
        else:
          artist_results = response['results']
        if artist_results.has_key('artistmatches') and not isinstance(artist_results['artistmatches'],dict) and not isinstance(artist_results['artistmatches'],list):
          Log('No results for artist search.')
          return artists
        # Note: If a single result is returned, it will not be in list form, it will be a single 'artist' dict, so we fix it to be consistent.
        if not isinstance(artist_results['artistmatches']['artist'], list):
          artist_results['artistmatches'] = {'artist':[artist_results['artistmatches']['artist']]}
        artists = artists + artist_results['artistmatches']['artist']
      except:
        Log('Error retrieving artist search results.')
        # raise
  return artists


def SearchAlbums(album, limit=10, legacy=False):
  albums = []
  url = ALBUM_SEARCH_URL % (String.Quote(album.lower()), limit)
  # PROXY
  if ShouldProxy(url):
    try:
      (xml_albums, more) = lastfm.SearchAlbums(album)
      for album in xml_albums:
        (name, artist, thumb, url) = album
        albums.append({'name':name, 'artist':artist})
      return albums
    except:
      Log('Error retreiving album search results (legacy request).')
      # raise
  else:
  # END PROXY
    try:
      response = GetJSON(url)
      if response.has_key('error'):
        Log('Error retrieving album search results: ' + response['message'])
        return albums
      else:
        album_results = response['results']
      if album_results.has_key('albummatches') and not isinstance(album_results['albummatches'],dict) and not isinstance(album_results['albummatches'],list):
        Log('No results for album search.')
        return albums
      # Note: If a single result is returned, it will not be in list form, it will be a single 'album' dict, so we fix that to be consistent.
      if not isinstance(album_results['albummatches']['album'], list):
        album_results['albummatches'] = {'album':[album_results['albummatches']['album']]}
      albums = album_results['albummatches']['album']
    except:
      Log('Error retrieving album search results.')
      # raise
    return albums


def GetAlbumsByArtist(artist, page=1, limit=0, pg_size=50, albums=[], legacy=True):
  # Limit of 0 is taken to mean 'all'.
  url = ARTIST_ALBUM_SEARCH_URL % (String.Quote(String.Unquote(artist.lower())), page, pg_size)
  # PROXY
  if ShouldProxy(url) and legacy:
    try:
      for album in lastfm.ArtistAlbums(String.Unquote(artist)):
        (name, artist_name, thumb, url) = album
        albums.append({'name':name})
      return albums
    except:
      Log('Error retrieving artist album search results (legacy request).')
      # raise
  else:
  # END PROXY
    try:
      # Use a larger page size when fetching all to limit the number of API requests.
      # Can't use a huge value, e.g. 10000 because not all results will be returned for some unknown reason.
      if not limit:
        pg_size = 200
      
      response = GetJSON(url)
      
      if response.has_key('error'):
        Log('Error retrieving artist album search results: ' + response['message'])
        return albums
      else:
        album_results = response['topalbums']
      if album_results.has_key('@attr'):
        total = int(album_results['@attr']['total'])
      elif album_results.has_key('total'):
        total = int(album_results['total'])
      if total == 0:
        Log('No results for album search.')
        return albums

      try:
        # Note: Another special case for single-item results, make sure it's a list.
        # Also, sometimes the 'total' from the response is a lie (says 1 but contains only garbage), so just return in that case.
        if not isinstance(album_results['album'], list):
          album_results['album'] = [album_results['album']]
      except:
        return albums

    except:
      Log('Error retrieving artist album search results.')
      # raise

    try:
      albums.extend(album_results['album'])
    except:
      # Sometimes the API will lie and say there's an Nth page of results, but the last one will return garbage.  Just ignore it.
      pass

    if (total > page * pg_size and limit==0) or (page * pg_size < limit):
      return GetAlbumsByArtist(artist, page=page+1, limit=limit, pg_size=pg_size, albums=albums, legacy=False)
    else:
      return albums


def GetArtist(id, lang='en'):
  url = ARTIST_INFO_URL % (id.lower(), lang)
  # PROXY
  if ShouldProxy(url):
    try:
      xml_artist = XML.ElementFromURL(lastfm.ARTIST_INFO % String.Quote(String.Unquote(id), True))[0]
      image = []
      for xml_image in xml_artist.xpath('//lfm/artist/image'):
        image.append({'#text':xml_image.text, 'size':xml_image.get('size')})
      tags = []
      for xml_tag in xml_artist.xpath('//lfm/artist/tags/tag/name'):
        tags.append({'name':xml_tag})
      artist = {
        'name':String.Unquote(xml_artist.xpath('//lfm/artist/name')[0].text, True),
        'bio':{'content':xml_artist.xpath('//lfm/artist/bio/content')[0].text},
        'image':image,
        'toptags':{'tag':tags}
      }
      return artist
    except:
      Log('Error retreiving artist metadata (legacy request).')
      #raise
      return {}
  else:
  # END PROXY
    try:
      artist_results = GetJSON(url)
      if artist_results.has_key('error'):
        Log('Error retrieving artist metadata: ' + artist_results['message'])
        return {}
      return artist_results['artist']
    except:
      Log('Error retrieving artist metadata.')
      # raise
      return {}


def GetAlbum(artist_id, album_id, lang='en'):
  url = ALBUM_INFO_URL % (artist_id.lower(), album_id.lower(), lang)
  # PROXY
  if ShouldProxy(url):
    try:
      album = {}
      xml_album = XML.ElementFromURL(lastfm.ALBUM_INFO % (String.Quote(String.Unquote(artist_id), True), String.Quote(String.Unquote(album_id), True)))
      image = []
      for xml_image in xml_album.xpath('//image'):
        image.append({'#text':xml_image.text, 'size':xml_image.get('size')})
      tags = []
      for xml_tag in xml_album.xpath('//tags/tag/name'):
        tags.append({'name':xml_tag})
      return {
        'name':xml_album.xpath("//name")[0].text,
        'image':image,
        'releasedate':xml_album.xpath("//releasedate")[0],
        'toptags':{'tag':tags}
      }
    except:
      Log('Error retreiving album metadata (legacy request).')
      # raise
  else:
  # END PROXY
    try:
      album_results = GetJSON(url)
      if album_results.has_key('error'):
        Log('Error retrieving album metadata: ' + album_results['message'])
        return {}
      return album_results['album']
    except:
      Log('Error retrieving album metadata.')
      # raise
      return {}


def GetTracks(artist_id, album_id, lang='en'):
  tracks = []
  url = ALBUM_INFO_URL % (artist_id.lower(), album_id.lower(), lang)
  # PROXY
  if ShouldProxy(url):
    try:
      album = XML.ElementFromURL(lastfm.ALBUM_INFO % (String.Quote(String.Unquote(artist_id), True), String.Quote(String.Unquote(album_id), True)), sleep=0.7)
      xml_tracks = album.xpath('//track/name')
      for track in xml_tracks:
        tracks.append({'name':track.text})
      return tracks
    except:
      Log('Error retreiving tracks for album (legacy request).')
      # raise
  else:
  # END PROXY
    try:
      tracks_result = GetJSON(url)
      if tracks_result.has_key('error'):
        Log('Error retrieving tracks to apply track bonus: ' + tracks_result['message'])
        return tracks
      tracks = tracks_result['album']['tracks']['track']
      if not isinstance(tracks, list):
        tracks = [tracks]
      return tracks
    except:
      Log('Error retrieving tracks to apply track bonus.')
      # raise
      return tracks


def GetJSON(url, sleep_time=QUERY_SLEEP_TIME, cache_time=CACHE_1MONTH):
  # try n times waiting 5 seconds in between if something goes wrong
  d = None

  for t in reversed(range(REQUEST_RETRY_LIMIT)):
    try:
      d = JSON.ObjectFromURL(url, sleep=sleep_time, cacheTime=cache_time, headers={'Accept-Encoding':'gzip'})
    except:
      Log('Error fetching JSON, will try %s more time(s) before giving up.', str(t))
      time.sleep(REQUEST_RETRY_SLEEP_TIME)

    if isinstance(d, dict):
      return d

  Log('Error fetching JSON')
  return None


# PROXY
def ShouldProxy(url):
  if PROXY_THRESHOLD is None:
    try:
      proxy_pct = int(HTTP.Request(PROXY_THRESHOLD_URL, cacheTime=PROXY_THRESHOLD_CACHE_TIME).content.strip())
    except:
      proxy_pct = 0 # if we don't hear from the proxy server, assume the worst.
      pass
  else:
    proxy_pct = PROXY_THRESHOLD

  url_hash_val = float(int(''.join(list(Hash.MD5(url))[-2:]), 16)) / 255 * 100
  if url_hash_val <= proxy_pct:
    Log('URL hash value of %d is below the threshold of %d, sending compressed JSON request.' % (url_hash_val, proxy_pct))
    return False
  else:
    Log('URL hash value of %d is above the threshold of %d, sending legacy XML request.' % (url_hash_val, proxy_pct))
    return True

def SafeStrip(ss):
    """
      This method strips the diacritic marks from a string, but if it's too extreme (i.e. would remove everything,
      as is the case with some foreign text), then don't perform the strip.
    """
    s = String.StripDiacritics(ss)
    if len(s.strip()) == 0:
      return ss
    return s
# END PROXY
