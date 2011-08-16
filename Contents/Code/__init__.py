#last.fm (w/ freebase help) Plex Music Metadata Agent
import lastfm, re, metaweb

def Start():
  HTTP.CacheTime = CACHE_1WEEK
  
class LastFmAgent(Agent.Artist):
  name = 'Last.fm'
  languages = [Locale.Language.English, Locale.Language.Korean]
  
  def safe_strip(self, ss):
    # This method strips the diacritic marks from a string, but if it's too extreme (i.e. would remove everything, as is the case with some foreign text), then don't perform the strip.
    s = String.StripDiacritics(ss)
    if len(s.strip()) == 0:
      return ss
    return s
  
  def search(self, results, media, lang):
    score = 90
    maxDist = 10
    if media.artist == '[Unknown Artist]': return
    if media.artist == 'Various Artists':
      results.Append(MetadataSearchResult(id = 'Various%20Artists', name= 'Various Artists', thumb = 'http://userserve-ak.last.fm/serve/252/46209667.png', lang  = lang, score = 100))
      return
    searchArtist = self.safe_strip(cleanSearchTerms(media.artist.lower()))
    try:
      artistSearch = XML.ElementFromURL(lastfm.SEARCH_ARTISTS % (String.Quote(searchArtist, True), 0, 5))[0]
    except:
      artistSearch = None
    if artistSearch:
      for a in artistSearch.xpath('//artist'):
        url = a.xpath('./url')[0].text
        if url.find('+noredirect') == -1:
          name = a.xpath('./name')[0].text
          self.scoreArtist(name, url, results, media, lang, maxDist, score)
          score = score - 1
    #Let's get similar/artist infos...last.fm hides good stuff in here :)
    score = 90
    try:
      Log(lastfm.ARTIST_INFO % String.Quote(searchArtist, True))
      artistInfo = XML.ElementFromURL(lastfm.ARTIST_INFO % String.Quote(searchArtist, True))[0]
    except:
      artistInfo = None
    if artistInfo:
      if artistInfo.xpath('//artist/url')[0].text.count('+noredirect') == 0:
        name = artistInfo.xpath('//artist/name')[0].text
        url = artistInfo.xpath('//artist/url')[0].text
        self.scoreArtist(name, url, results, media, lang, maxDist, score)
        score = score - 1
      for a in artistInfo.xpath('//similar/artist')[:2]:
        name = a.xpath('./name')[0].text
        url = a.xpath('./url')[0].text
        self.scoreArtist(name, url, results, media, lang, maxDist, score)
        score = score - 1
    #See if last.fm has a corrected artist for our spelling
    score = 90
    artistCorrects = XML.ElementFromURL(lastfm.ARTIST_CORRECTIONS % String.Quote(searchArtist, True)).xpath('//corrections/correction/artist') #[0]
    #Log('length of artistCorrects: ' + str(len(artistCorrects)))
    if len(artistCorrects) > 0:
      url = artistCorrects[0].xpath('./url')[0].text
      name = artistCorrects[0].xpath('./name')[0].text
      self.scoreArtist(name, url, results, media, lang, maxDist, score)
    # Finally, de-dupe the results.
    results.Sort('score', descending=True)
    toWhack = []
    resultMap = {}
    for result in results:
      if not resultMap.has_key(result.id):
        resultMap[result.id] = True
      else:
        toWhack.append(result)
    for dupe in toWhack:
      results.Remove(dupe)
  
  def scoreArtist(self, name, url, results, media, lang, maxDist, score):
    if media.album == None or media.album == '': #don't both with this if the album is blank/None
      return 
    id = String.Quote(url.split('/')[-1].encode('utf-8')).replace('%2B','%20').replace('%25','%')
    dist = Util.LevenshteinDistance(name.lower(), media.artist.lower())
    if dist > maxDist: 
      dist = maxDist
    lcs = len(Util.LongestCommonSubstring(name.lower(), media.artist.lower()))
    # If we don't have at least X% in common, then penalize the score
    if (float(lcs) / len(media.album)) < .15: 
      dist = maxDist
    albumBonus = self.freebase_bonusArtistMatchUsingAlbums(media, name.lower(), id, maxBonus=10)
    s = score + albumBonus - dist
    Log('artist: ' + media.artist + ' albumBonus: ' + str(albumBonus) + ' dist: ' + str(dist))
    Log('artist result: id: ' + id + '  name: '+ name + '   score: ' + str(s))
    results.Append(MetadataSearchResult(id = id.replace('%2B','%20').replace('%25','%'), name = name, lang = lang, score = s))
    
  def freebase_bonusArtistMatchUsingAlbums(self, media, artist, lastFMid, maxBonus=5):
    mbid = getMusicBrainzID(lastFMid)
    if mbid:
      query = getMQL(artist=None, musicBrainzID=mbid)
    else:
      query = getMQL(artist)
    freebase = metaweb.Session("freebase-cache.plexapp.com") # Create a session object
    result = freebase.read(query)                  # Submit query, get results
    #Log(result)
    if result:                                     # If we got a result
      artistAlbums = []
      for a in result['album']:
        if a['name']:
          artistAlbums.append(a['name'].lower())
        else:
          continue
      if len(artistAlbums) == 0: return 0 #no freebase albums for the artist, so abort!
      bonusPerAlbum = maxBonus / len(media.children)
      bonus = 0
      for a in media.children:
        album = a.title.lower()
        for aa in artistAlbums:
          score = Util.LevenshteinDistance(aa, album)
          #Log(aa, album, score)
          if score <= 2: #pretty solid match
            bonus += bonusPerAlbum
            if bonus == maxBonus: break
        if bonus == 0 and album[-1:] == ')': #if we got nothing, let's try again without anything in paranthesis [e.g.'limited edition'] 
          album = album[:album.rfind('(')].strip()
          for aa in artistAlbums:
            score = Util.LevenshteinDistance(aa, album)
            #Log(aa, album, score)
            if score <= 2: #pretty solid match
              bonus += bonusPerAlbum
              if bonus == maxBonus: break
      return bonus
    else:
      return 0
    
  def update(self, metadata, media, lang):
    Log('artist update for: ' + metadata.id)
    artist = XML.ElementFromURL(lastfm.ARTIST_INFO % String.Quote(String.Unquote(metadata.id), True))[0]
    summary = artist.xpath('//bio/content')[0]
    metadata.title = String.Unquote(artist.xpath('//artist/name')[0].text, False)
    if summary.text:
      metadata.summary = decodeXml(re.sub(r'<[^<>]+>', '', summary.text))
    try:
      url = artist.xpath('//artist/image[@size="mega"]//text()')[0]
    except:
      try:
        url = artist.xpath('//artist/image[@size="extralarge"]//text()')[0]
      except:
        try:
          url = artist.xpath('//artist/image[@size="large"]//text()')[0]
        except:
          url = None
    if url != None and url not in metadata.posters:
      metadata.posters[url] = Proxy.Media(HTTP.Request(url))     
    metadata.genres.clear()
    for genre in artist.xpath('//artist/tags/tag/name'):
      metadata.genres.add(genre.text.capitalize())
    
class LastFmAlbumAgent(Agent.Album):
  name = 'Last.fm'
  languages = [Locale.Language.English]
  fallback_agent = 'com.plexapp.agents.discogs' 
  #fallback_agent = 'com.plexapp.agents.allmusic'
  def search(self, results, media, lang):
    if media.parent_metadata.id is None:
      return None
    #Log('album search for: ' + media.album)
    if media.parent_metadata.id == '[Unknown Artist]': return #eventually, we might be able to look at tracks to match the album
    if media.parent_metadata.id != 'Various%20Artists':
      for album in lastfm.ArtistAlbums(String.Unquote(media.parent_metadata.id)):
        (name, artist, thumb, url) = album
        albumID = url.split('/')[-1]
        id = '/'.join(url.split('/')[-2:]).replace('+','%20')
        dist = Util.LevenshteinDistance(name.lower(), media.album.lower())
        # Sanity check to make sure we have SOME common substring.
        longestCommonSubstring = len(Util.LongestCommonSubstring(name.lower(), media.album.lower()))
        # If we don't have at least X% in common, then penalize the score
        if (float(longestCommonSubstring) / len(media.album)) < .15: dist = dist + 10
        #Log('scannerAlbum: ' + media.album + ' last.fmAlbum: ' + name + ' score=' + str(92-dist))
        results.Append(MetadataSearchResult(id = id.replace('%2B','%20').replace('%25','%'), name = name, thumb = thumb, lang  = lang, score = 92-dist))
    else:
      (albums, more) = lastfm.SearchAlbums(media.title.lower())
      for album in albums:
        (name, artist, thumb, url) = album
        if artist == 'Various Artists':
          albumID = url.split('/')[-1]
          id = media.parent_metadata.id + '/' + albumID.replace('+', '%20')
          dist = Util.LevenshteinDistance(name.lower(), media.album.lower())
          # Sanity check to make sure we have SOME common substring.
          longestCommonSubstring = len(Util.LongestCommonSubstring(name.lower(), media.album.lower()))
          # If we don't have at least X% in common, then penalize the score
          if (float(longestCommonSubstring) / len(media.album)) < .15: dist = dist - 10
          results.Append(MetadataSearchResult(id = id, name = name, thumb = thumb, lang  = lang, score = 85-dist))
    results.Sort('score', descending=True)
    for r in results[:5]:
      #Track bonus on the top 5 closest title-based matches
      trackBonus = self.bonusAlbumMatchUsingTracks(media, r.id)
      #except: trackBonus = 0
      #Log('album: ' + media.title + ' trackBonus: ' + str(trackBonus))
      r.score = r.score + trackBonus
    results.Sort('score', descending=True)
    
  def bonusAlbumMatchUsingTracks(self, media, id):
    (artistName, albumName) = self.artistAlbumFromID(id)
    lastFM_albumTracks = []
    #Log('fetching AlbumTrackList for: ' + albumName)
    #WAS:
    #for track in lastfm.AlbumTrackList(artistName, albumName):
    #  (trackName, artist, none1, trackUrl, none2) = track
    try:
      album = XML.ElementFromURL(lastfm.ALBUM_INFO % (String.Quote(artistName, True), String.Quote(albumName, True)))
    except:
      return 0
    tracks = album.xpath('//track/name')
    for track in tracks:
      lastFM_albumTracks.append(track.text)
    if len(lastFM_albumTracks) == 0: return 0 #no last.fm tracks for the album, so abort!
    bonus = 0
    for a in media.children:
      track = a.title.lower()
      for lft in lastFM_albumTracks:
        score = Util.LevenshteinDistance(lft.lower(), track)
        if score <= 2:
          bonus += 1
    if len(media.children) == len(tracks): bonus += 5
    return bonus
  
  def artistAlbumFromID(self, id):
    (artistName, albumName) = id.split('/') 
    artistName = String.Unquote(artistName).encode('utf-8')
    albumName = String.Unquote(albumName).encode('utf-8')
    return (artistName, albumName)
 
  def update(self, metadata, media, lang):
    (artistName, albumName) = self.artistAlbumFromID(metadata.id)
    #Log('Album update for: ' + albumName)
    album = XML.ElementFromURL(lastfm.ALBUM_INFO % (String.Quote(artistName, True), String.Quote(albumName, True)))
    try: 
      thumb = album.xpath("//image[@size='mega']")[0].text
    except: 
      thumb = album.xpath("//image[@size='extralarge']")[0].text
    metadata.title = album.xpath("//name")[0].text
    try:
      metadata.summary = decodeXml(re.sub(r'<[^<>]+>', '', album.xpath('//wiki/summary')[0].text))
    except: 
      pass
    date = album.xpath("//releasedate")[0].text.split(',')[0].strip()
    metadata.originally_available_at = None
    if len(date) > 0:
      metadata.originally_available_at = Datetime.ParseDate(date).date()
    if thumb not in metadata.posters and thumb != None:
      metadata.posters[thumb] = Proxy.Media(HTTP.Request(thumb))
    #tracks = lastfm.AlbumTrackList(artistName, albumName)
    #for num in range(len(tracks)):
    #  pass
      #metadata.tracks[str(num+1)].name = tracks[num][0]

def getMQL(artist=None, musicBrainzID=None):
  return     { #'type|=' : ['/music/artist","/music/musical_group'],       # Our MQL query in Python.
                'type' : '/music/artist',
                'name': artist,                  # Place the band in the query.
                'id': None,
                '/common/topic/image' : [{'id' : None, 'optional' : True, 'limit' : 10}],
                'key': [{'*' : None, 'namespace' : '/authority/musicbrainz', 'value' : musicBrainzID}],
                '/common/topic/weblink' : [{'*' : None, 'optional': True}],
                '/common/topic/webpage' : [{'*' : None, 'uri~=' : 'discogs', 'optional': True}],
                'album': [{ 'name': None,
                            'release_date': None,
                            'sort': 'release_date',
                            '/common/topic/image' : [{'id' : None, 'optional' : True, 'limit' : 10}],
                            'releases': [{ 'release_date': None,
                                           '/common/topic/image' : [{'id' : None, 'optional' : True, 'limit' : 10}],
                                           'track': [{ 'name': None }] }] }]}

def decodeXml(text):
  trans = [('&amp;','&'),('&quot;','"'),('&lt;','<'),('&gt;','>'),('&apos;','\''),('\n ','\n')]
  for src, dst in trans:
    text = text.replace(src, dst)
  return text

def cleanSearchTerms(string):
  while string.find('  ') > 0:
    string.replace('  ', ' ')
  return string

def getMusicBrainzID(lastFMid):
  try:
    mbid = XML.ElementFromURL(lastfm.ARTIST_INFO % lastFMid.replace('%2B','%20').replace('%25','%')).xpath('//artist/mbid')[0].text 
  except:
    mbid = None
  return mbid