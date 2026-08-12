import urllib.request, urllib.parse, xml.etree.ElementTree as ET, json, re, html, os, time
from html.parser import HTMLParser
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

BASE='https://112-nu.nl/'
TARGETS=['Pijnacker','Nootdorp','Delfgauw','Berkel en Rodenrijs','Oude Leede','Delft']
ALIASES={
 'Pijnacker':['pijnacker'],
 'Nootdorp':['nootdorp'],
 'Delfgauw':['delfgauw'],
 'Berkel en Rodenrijs':['berkel en rodenrijs','berkel-rodenrijs'],
 'Oude Leede':['oude leede','oude-leede'],
 'Delft':['delft']
}
UA={'User-Agent':'112-pijnacker-dashboard/1.1 (personal dashboard; github.com/stefanheijkoop-code/112-pijnacker)'}
CACHE_FILE='geocode_cache.json'
MAX_NEW_GEOCODES=3

class Links(HTMLParser):
 def __init__(self): super().__init__(); self.href=None; self.text=''; self.links=[]
 def handle_starttag(self,tag,attrs):
  if tag=='a': self.href=dict(attrs).get('href'); self.text=''
 def handle_data(self,d):
  if self.href: self.text+=d
 def handle_endtag(self,tag):
  if tag=='a' and self.href:
   self.links.append((self.text.strip(),self.href)); self.href=None

def get(url,headers=None):
 h=UA.copy(); h.update(headers or {})
 req=urllib.request.Request(url,headers=h)
 with urllib.request.urlopen(req,timeout=25) as r:return r.read()

def discover():
 p=Links();p.feed(get(BASE+'rss.html').decode('utf-8','ignore'))
 wanted={}
 for text,href in p.links:
  low=text.lower()
  if 'rss' in href.lower() or 'feed' in href.lower() or 'actuele meldingen' in low:
   if 'brandweer' in low: wanted['Brandweer']=urllib.parse.urljoin(BASE,href)
   elif 'politie' in low: wanted['Politie']=urllib.parse.urljoin(BASE,href)
   elif 'ambulance' in low: wanted['Ambulance']=urllib.parse.urljoin(BASE,href)
   elif 'traumahelikopter' in low: wanted['Traumahelikopter']=urllib.parse.urljoin(BASE,href)
 return wanted

def txt(el,name):
 x=el.find(name); return html.unescape(' '.join((x.text or '').split())) if x is not None else ''

def place_for(s):
 low=s.lower()
 for place,keys in ALIASES.items():
  if any(k in low for k in keys): return place
 return None

def clean(s):
 s=re.sub('<[^>]+>',' ',s);return html.unescape(re.sub(r'\s+',' ',s)).strip()

def street_from_link(link):
 try:
  parts=[urllib.parse.unquote(x) for x in urllib.parse.urlparse(link).path.split('/') if x]
  # expected: melding/<id>/<place>/<street>/<service...>
  if len(parts)>=5 and parts[0]=='melding':
   street=parts[3].replace('-',' ').strip()
   if street and street not in ('ambulance','brandweer','politie','trauma helikopter'):
    return street.title()
 except: pass
 return ''

def load_cache():
 try:
  with open(CACHE_FILE,encoding='utf8') as f:return json.load(f)
 except:return {}

def save_cache(c):
 with open(CACHE_FILE,'w',encoding='utf8') as f:json.dump(c,f,ensure_ascii=False,separators=(',',':'),sort_keys=True)

def geocode(query):
 params=urllib.parse.urlencode({'q':query,'format':'jsonv2','limit':1,'countrycodes':'nl'})
 url='https://nominatim.openstreetmap.org/search?'+params
 try:
  arr=json.loads(get(url,{'Accept-Language':'nl'}).decode('utf8'))
  if arr:return {'lat':float(arr[0]['lat']),'lon':float(arr[0]['lon']),'display_name':arr[0].get('display_name','')}
 except Exception as e: print('geocode failed',query,e)
 return None

def main():
 feeds=discover(); incidents=[]; seen=set(); now=datetime.now(ZoneInfo('Europe/Amsterdam'))
 cache=load_cache(); new_geo=0
 for service,url in feeds.items():
  try: root=ET.fromstring(get(url))
  except Exception as e: print(service,e);continue
  items=root.findall('.//item')
  for it in items[:180]:
   title=clean(txt(it,'title')); desc=clean(txt(it,'description')); link=txt(it,'link'); pub=txt(it,'pubDate'); blob=' '.join([title,desc,link])
   place=place_for(blob)
   if not place: continue
   key=(service,title,pub)
   if key in seen:continue
   seen.add(key)
   try:
    dt=parsedate_to_datetime(pub)
    if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
    dt=dt.astimezone(ZoneInfo('Europe/Amsterdam'))
   except: dt=now
   priority=''
   m=re.search(r'\b(PRIO\s*[123]|P\s*[123]|A[12])\b',blob,re.I)
   if m:priority=re.sub(r'\s+','',m.group(1).upper())
   street=street_from_link(link)
   location=(street+', '+place) if street else place
   lat=lon=None
   if street:
    q=f'{street}, {place}, Nederland'
    if q in cache:
     g=cache[q]
    elif new_geo<MAX_NEW_GEOCODES:
     # Public Nominatim periodic scripts: keep well below 4 requests/minute and cache results.
     if new_geo>0: time.sleep(16)
     g=geocode(q); cache[q]=g; new_geo+=1
    else:g=None
    if g:
     lat=g.get('lat');lon=g.get('lon')
   incidents.append({'service':service,'place':place,'title':title or desc[:160],'location':location,'original':desc,'priority':priority,'unit':'','published':dt.isoformat(),'time_label':dt.strftime('%a %d-%m · %H:%M'),'is_today':dt.date()==now.date(),'lat':lat,'lon':lon,'link':link})
 incidents.sort(key=lambda x:x['published'],reverse=True)
 out={'updated':now.isoformat(),'updated_label':now.strftime('%H:%M'),'feeds':feeds,'incidents':incidents[:400]}
 with open('data.json','w',encoding='utf8') as f:json.dump(out,f,ensure_ascii=False,separators=(',',':'))
 save_cache(cache)
 print('feeds',feeds,'incidents',len(incidents),'new geocodes',new_geo,'cache',len(cache))
if __name__=='__main__':main()
