import lastfm, re

GOOGLE_JSON = 'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&rsz=large&q=%s+site:last.fm+inurl:music'
BING_JSON   = 'http://api.bing.net/json.aspx?AppId=879000C53DA17EA8DB4CD1B103C00243FD0EFEE8&Version=2.2&Query=%s+site:last.fm&Sources=web&Web.Count=8&JsonType=raw'

def Start():
  HTTP.CacheTime = CACHE_1WEEK
  
class LastFmAgent(Agent.Artist):
  name = 'Last.fm'
  languages = [Locale.Language.English]
  
  def search(self, results, media, lang):
    
    score = 100
    for r in lastfm.SearchArtists(String.StripDiacritics(media.artist))[0]:
      id = r[0]
      if id.find('+noredirect') == -1:
        id = r[1]
        id = String.Quote(id.encode('utf-8'))
        Log('id: ' + id + '  name: '+ r[1] + '   score: ' + str(score) + '   thumb: ' + str(r[2]))
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

  def update(self, metadata, lang):
    artist = XML.ElementFromURL(lastfm.ARTIST_INFO % String.Quote(String.Unquote(metadata.id), True))[0]
    summary = artist.xpath('//bio/content')[0]

    metadata.title = String.Unquote(artist.xpath('//artist/name')[0].text, True)
    print "TITLE:", metadata.title
    
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
  
  def search(self, results, media, lang):
    for album in lastfm.ArtistAlbums(String.Unquote(media.parent_metadata.id)):
      (name, artist, thumb, url) = album
      albumID = url.split('/')[-1]
      id = media.parent_metadata.id + '/' + albumID.replace('+', '%20')
      dist = Util.LevenshteinDistance(name, media.album)
      results.Append(MetadataSearchResult(id = id, name = name, thumb = thumb, lang  = lang, score = 90-dist))
    results.Sort('score', descending=True)
 
  def update(self, metadata, lang):
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
    if thumb not in metadata.posters:
      metadata.posters[thumb] = Proxy.Media(HTTP.Request(thumb))
    
    tracks = lastfm.AlbumTrackList(artistName, albumName)
    for num in range(len(tracks)):
      metadata.tracks[str(num+1)].name = tracks[num][0]
      