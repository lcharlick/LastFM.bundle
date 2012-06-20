import lastfm, re

GOOGLE_JSON = 'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&rsz=large&q=%s+site:last.fm+inurl:music'
BING_JSON   = 'http://api.bing.net/json.aspx?AppId=879000C53DA17EA8DB4CD1B103C00243FD0EFEE8&Version=2.2&Query=%s+site:last.fm&Sources=web&Web.Count=8&JsonType=raw'

def Start():
  HTTP.CacheTime = CACHE_1WEEK
  
class LastFmAgent(Agent.Artist):
  name = 'Last.fm'
  languages = [Locale.Language.English, Locale.Language.Korean]
  
  def safe_strip(self, ss):
    """
      This method strips the diacritic marks from a string, but if it's too extreme (i.e. would remove everything,
      as is the case with some foreign text), then don't perform the strip.
    """
    s = String.StripDiacritics(ss)
    if len(s.strip()) == 0:
      return ss
    return s
    
  def search(self, results, media, lang):
    if media.artist == '[Unknown Artist]': 
      return
      
    if media.artist == 'Various Artists':
      results.Append(MetadataSearchResult(id = 'Various%20Artists', name= 'Various Artists', thumb = 'http://userserve-ak.last.fm/serve/252/46209667.png', lang  = lang, score = 100))
      return
    
    # Search for artist.
    artist = self.safe_strip(media.artist.lower())
    try: self.findArtists(lang, results, media, artist)
    except: pass
    
    # If the artist starts with "The", try stripping.
    if artist.startswith('the '):
      try: self.findArtists(lang, results, media, artist[4:])
      except: pass
  
    # Finally, de-dupe the results.
    toWhack = []
    resultMap = {}
    for result in results:
      if not resultMap.has_key(result.id):
        resultMap[result.id] = True
      else:
        toWhack.append(result)
    for dupe in toWhack:
      results.Remove(dupe)

  def findArtists(self, lang, results, media, artist):
    score = 90
    for r in lastfm.SearchArtists(artist,limit=5)[0]:
      id = r[0]
      if id.find('+noredirect') == -1:
        id = r[1]
        dist = Util.LevenshteinDistance(r[1].lower(), media.artist.lower())
        albumBonus = self.bonusArtistMatchUsingAlbums(media, artistID=id, maxBonus=5)
        id = String.Quote(id.encode('utf-8'))
        Log('artist: ' + media.artist + ' albumBonus: ' + str(albumBonus))
        Log('Artist result: ' + r[1] + ' id: ' + id + ' score: ' + str(score) + ' thumb: ' + str(r[2]))
        results.Append(MetadataSearchResult(id = id.replace('%2B','%20'), name = r[1], thumb = r[2], lang  = lang, score = score + albumBonus - dist))
      else:
        # Get a correction.
        Log('Getting correction to artist.')
        correctArtists = lastfm.CorrectedArtists(artist)
        for result in correctArtists:
          id = String.Quote(result[0].encode('utf-8'))
          dist = Util.LevenshteinDistance(result[0].lower(), media.artist.lower())
          results.Append(MetadataSearchResult(id = id.replace('%2B','%20'), name = result[0], lang  = lang, score = score - dist))
          
      score = score - 2
      
  def bonusArtistMatchUsingAlbums(self, media, artistID, maxBonus=5):
    Log('bonusArtistMatchUsingAlbums')
    lastFM_artistAlbums = []
    for album in lastfm.ArtistAlbums(artistID):
      (name, artist, thumb, url) = album
      lastFM_artistAlbums.append(name.lower())
    if len(lastFM_artistAlbums) == 0: return 0 #no last.fm albums for the artist, so abort!
    bonus = 0
    for a in media.children:
      album = a.title.lower()
      for lfa in lastFM_artistAlbums:
        score = Util.LevenshteinDistance(lfa, album)
        #Log(lfa, album, score)
        if score <= 2: #pretty solid match
          bonus += 1
          if bonus == maxBonus: break
      if bonus == 0 and album[-1:] == ')': #if we got nothing, let's try again without anything in paranthesis [e.g.'limited edition'] 
        album = album[:album.rfind('(')].strip()
        for lfa in lastFM_artistAlbums:
          score = Util.LevenshteinDistance(lfa, album)
          #Log(lfa, album, score)
          if score <= 2: #pretty solid match
            bonus += 1
            if bonus == maxBonus: break
    return bonus
    
  def update(self, metadata, media, lang):
    #Log('artist update for: ' + metadata.id)
    artist = XML.ElementFromURL(lastfm.ARTIST_INFO % String.Quote(String.Unquote(metadata.id), True))[0]
    summary = artist.xpath('//bio/content')[0]
    metadata.title = String.Unquote(artist.xpath('//artist/name')[0].text, True)
    if summary.text:
      metadata.summary = decodeXml(re.sub(r'<[^<>]+>', '', summary.text))
    try:
      url = artist.xpath('//artist/image[@size="mega"]//text()')[0]
      if url not in metadata.posters:
        metadata.posters[url] = Proxy.Media(HTTP.Request(url))
    except:
      pass     
    metadata.genres.clear()
    for genre in artist.xpath('//artist/tags/tag/name'):
      metadata.genres.add(genre.text.capitalize())
    
class LastFmAlbumAgent(Agent.Album):
  name = 'Last.fm'
  languages = [Locale.Language.English]
  fallback_agent = 'com.plexapp.agents.allmusic'
  def search(self, results, media, lang):
    if media.parent_metadata.id is None:
      return None
    #Log('album search for: ' + media.album)
    if media.parent_metadata.id == '[Unknown Album]': return #eventually, we might be able to look at tracks to match the album
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
    album = XML.ElementFromURL(lastfm.ALBUM_INFO % (String.Quote(artistName, True), String.Quote(albumName, True)), sleep=0.7)
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
      try: metadata.posters[thumb] = Proxy.Media(HTTP.Request(thumb))
      except: Log('Error getting poster from %s' % thumb)
    #tracks = lastfm.AlbumTrackList(artistName, albumName)
    #for num in range(len(tracks)):
    #  pass
      #metadata.tracks[str(num+1)].name = tracks[num][0]

def decodeXml(text):
  trans = [('&amp;','&'),('&quot;','"'),('&lt;','<'),('&gt;','>'),('&apos;','\''),('\n ','\n')]
  for src, dst in trans:
    text = text.replace(src, dst)
  return text      