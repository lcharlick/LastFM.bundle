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
    score = 100
    if media.artist == '[Unknown Artist]': return
    if media.artist == 'Various Artists':
      results.Append(MetadataSearchResult(id = 'Various%20Artists', name= 'Various Artists', thumb = 'http://userserve-ak.last.fm/serve/252/46209667.png', lang  = lang, score = 100))
      return
    for r in lastfm.SearchArtists(self.safe_strip(media.artist))[0]:
      id = r[0]
      if id.find('+noredirect') == -1:
        id = r[1]
        albumScore = self.checkArtistMatchUsingAlbums(media, id)
        Log('artist: ' + media.artist + ' albumScore: ' + str(albumScore))
        id = String.Quote(id.encode('utf-8'))
        Log('Artist result: id: ' + id + '  name: '+ r[1] + '   score: ' + str(score) + '   thumb: ' + str(r[2]))
        results.Append(MetadataSearchResult(id = id.replace('%2B','%20'), name  = r[1], thumb = r[2], lang  = lang, score = score))
        score = score - 2
    
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
  
  def checkArtistMatchUsingAlbums(self, media, artistID):
    lastFM_artistAlbums = []
    for album in lastfm.ArtistAlbums(artistID):
      (name, artist, thumb, url) = album
      lastFM_artistAlbums.append(name.lower())
    if len(lastFM_artistAlbums) == 0: return 100 #no last.fm albums for the artist, so abort!
    solidMatchCount = 0
    for a in media.children:
      artist = a.title.lower()
      for lfa in lastFM_artistAlbums:
        score = Util.LevenshteinDistance(lfa, artist)
        if score <= 2: 
          Log('solid match!')
          solidMatchCount += 1
    return solidMatchCount
    
  def update(self, metadata, media, lang):
    artist = XML.ElementFromURL(lastfm.ARTIST_INFO % String.Quote(String.Unquote(metadata.id), True))[0]
    albumScore = self.checkArtistMatchUsingAlbums(media, '11000')
    summary = artist.xpath('//bio/content')[0]
    metadata.title = String.Unquote(artist.xpath('//artist/name')[0].text, True)
    if summary.text:
      metadata.summary = self.decodeXml(re.sub(r'<[^<>]+>', '', summary.text))
    try:
      url = artist.xpath('//artist/image[@size="mega"]//text()')[0]
      if url not in metadata.posters:
        metadata.posters[url] = Proxy.Media(HTTP.Request(url))
    except:
      pass     
    metadata.genres.clear()
    for genre in artist.xpath('//artist/tags/tag/name'):
      metadata.genres.add(genre.text.capitalize())

  def decodeXml(self, text):
    trans = [('&amp;','&'),('&quot;','"'),('&lt;','<'),('&gt;','>'),('&apos;','\''),('\n ','\n')]
    for src, dst in trans:
      text = text.replace(src, dst)
    return text

class LastFmAlbumAgent(Agent.Album):
  name = 'Last.fm'
  languages = [Locale.Language.English]
  fallback_agent = 'com.plexapp.agents.allmusic'
  def search(self, results, media, lang):
    Log('album search')
    if media.parent_metadata.id == '[Unknown Album]': return #eventually, we might be able to look at tracks to match the album
    if media.parent_metadata.id != 'Various%20Artists': 
      for album in lastfm.ArtistAlbums(String.Unquote(media.parent_metadata.id)):
        (name, artist, thumb, url) = album
        albumID = url.split('/')[-1]
        id = media.parent_metadata.id + '/' + albumID.replace('+', '%20')
        dist = Util.LevenshteinDistance(name, media.album)
        results.Append(MetadataSearchResult(id = id, name = name, thumb = thumb, lang  = lang, score = 90-dist))
    else:
      (albums, more) = lastfm.SearchAlbums(media.title)
      for album in albums:
        (name, artist, thumb, url) = album
        if artist == 'Various Artists':
          albumID = url.split('/')[-1]
          id = media.parent_metadata.id + '/' + albumID.replace('+', '%20')
          dist = Util.LevenshteinDistance(name, media.album)
          results.Append(MetadataSearchResult(id = id, name = name, thumb = thumb, lang  = lang, score = 85-dist))
    results.Sort('score', descending=True)

  def checkAlbumMatchUsingTracks(self, media, albumID):
    lastfm.fetchAlbumTracks(albumID)
    score = 0
    return score
 
  def update(self, metadata, media, lang):
    Log('album update')
    (artistName, albumName) = metadata.id.split('/')
    artistName = String.Unquote(artistName).encode('utf-8')
    albumName = String.Unquote(albumName).encode('utf-8')
    album = XML.ElementFromURL(lastfm.ALBUM_INFO % (String.Quote(artistName, True), String.Quote(albumName, True)))
    thumb = album.xpath("//image[@size='extralarge']")[0].text
    metadata.title = album.xpath("//name")[0].text
    date = album.xpath("//releasedate")[0].text.split(',')[0].strip()
    metadata.originally_available_at = None
    if len(date) > 0:
      metadata.originally_available_at = Datetime.ParseDate(date).date()
    if thumb not in metadata.posters and thumb != None:
      metadata.posters[thumb] = Proxy.Media(HTTP.Request(thumb))
    
    tracks = lastfm.AlbumTrackList(artistName, albumName)
    for num in range(len(tracks)):
      metadata.tracks[str(num+1)].name = tracks[num][0]
      