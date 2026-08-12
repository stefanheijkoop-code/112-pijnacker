import urllib.request, urllib.parse, xml.etree.ElementTree as ET, json, re, html, os, time
from html.parser import HTMLParser
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

TZ=ZoneInfo('Europe/Amsterdam')
BASE_112='https://112-nu.nl/'
BASE_AL='https://alarmeringen.nl/'
TARGETS=['Pijnacker','Nootdorp','Delfgauw','Berkel en Rodenrijs','Oude Leede','Delft']
ALIASES={
 'Pijnacker':['pijnacker','pijnak'], 'Nootdorp':['nootdorp','nootdp'],
 'Delfgauw':['delfgauw'], 'Berkel en Rodenrijs':['berkel en rodenrijs','berkrr'],
 'Oude Leede':['oude leede','oude-leede'], 'Delft':['delft']
}
AL_PATHS={
 'Pijnacker':'zuid-holland/haaglanden/pijnacker',
 'Nootdorp':'zuid-holland/haaglanden/nootdorp',
 'Delfgauw':'zuid-holland/haaglanden/delfgauw',
 'Berkel en Rodenrijs':'zuid-holland/rotterdam-rijnmond/berkel-en-rodenrijs',
 'Delft':'zuid-holland/haaglanden/delft'
}
UA={'User-Agent':'112-pijnacker-dashboard/1.2 (personal dashboard; github.com/stefanheijkoop-code/112-pijnacker)'}
CACHE_FILE='geocode_cache.json'; MAX_NEW_GEOCODES=3
MONTHS={'januari':1,'februari':2,'maart':3,'april':4,'mei':5,'juni':6,'juli':7,'augustus':8,'september':9,'oktober':10,'november':11,'december':12}

def get(url,headers=None):
 h=UA.copy(); h.update(headers or {})
 req=urllib.request.Request(url,headers=h)
 with urllib.request.urlopen(req,timeout=30) as r:return r.read()

def clean(s): return html.unescape(re.sub(r'\s+',' ',re.sub('<[^>]+>',' ',s or ''))).strip()

def place_for(s):
 low=(s or '').lower()
 # More specific names first so Delft does not steal Delfgauw.
 for place in ['Berkel en Rodenrijs','Oude Leede','Delfgauw','Nootdorp','Pijnacker','Delft']:
  if any(k in low for k in ALIASES[place]): return place
 return None

def priority_for(s):
 m=re.search(r'\b(PRIO\s*[1-4]|P\s*[1-3]|A[12]|B[12])\b',s or '',re.I)
 return re.sub(r'\s+','',m.group(1).upper()) if m else ''

def parse_nl_date(s):
 s=clean(s).lower()
 m=re.search(r'(\d{1,2})\s+([a-z]+)\s+(20\d{2})\s+(\d{1,2}):(\d{2})',s)
 if m and m.group(2) in MONTHS:
  return datetime(int(m.group(3)),MONTHS[m.group(2)],int(m.group(1)),int(m.group(4)),int(m.group(5)),tzinfo=TZ)
 m=re.search(r'(\d{1,2})-(\d{1,2})-(\d{2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?',s)
 if m:return datetime(2000+int(m.group(3)),int(m.group(2)),int(m.group(1)),int(m.group(4)),int(m.group(5)),int(m.group(6) or 0),tzinfo=TZ)
 return None

class CardParser(HTMLParser):
 def __init__(self):
  super().__init__();self.in_h3=False;self.buf=[];self.i=0;self.last_date=None;self.pending=None;self.entries=[]
 def handle_starttag(self,tag,attrs):
  if tag=='h3':self.in_h3=True;self.buf=[]
 def handle_data(self,d):
  self.i+=1; t=clean(d)
  if not t:return
  if self.in_h3:self.buf.append(t);return
  dt=parse_nl_date(t)
  if dt:
   if self.pending and self.i-self.pending[1]<25:
    self.entries.append((self.pending[0],dt));self.pending=None
   else:self.last_date=(dt,self.i)
 def handle_endtag(self,tag):
  if tag=='h3' and self.in_h3:
   title=clean(' '.join(self.buf));self.in_h3=False
   if not title:return
   if self.last_date and self.i-self.last_date[1]<25:
    self.entries.append((title,self.last_date[0]));self.last_date=None
   else:self.pending=(title,self.i)

def service_from_text(t,default='Overig'):
 low=t.lower()
 if 'traumahel' in low or 'lifeliner' in low or 'mmt' in low:return 'Traumahelikopter'
 if 'brandweer' in low or re.search(r'\bp\s*[123]\b',low) and any(x in low for x in [' br ','oms','ass. ambu','dier','brand']):return 'Brandweer'
 if 'politie' in low or 'prio ' in low or 'icnum' in low:return 'Politie'
 if 'ambulance' in low or re.search(r'\b[ab][12]\b',low) or 'ambu' in low:return 'Ambulance'
 return default

def street_guess(title,place):
 s=clean(title)
 # Friendly overview titles: "... naar X in Delft" / "... op X in Delft"
 m=re.search(r'(?:naar|op|aan|in)\s+(.+?)\s+in\s+'+re.escape(place)+r'\b',s,re.I)
 if m:return m.group(1).strip(' ,.-')[:90]
 # Raw P2000: remove prefixes/codes and take words before place.
 low=s.lower(); pos=low.find(place.lower())
 if pos>0:
  left=s[:pos]
  left=re.sub(r'^(?:prio\s*\d+|p\s*\d+|a[12]|b[12]|ambu\s*\d+|dia:\s*ja)\s*','',left,flags=re.I)
  left=re.sub(r'\b\d{4}[a-z]{2}\b|\b\d{5,6}\b|\bbon\s*\d+\b',' ',left,flags=re.I)
  words=clean(left).split()
  if words:return ' '.join(words[-5:])[:90]
 return ''

def scrape_alarmeringen(now):
 out=[];sources=[]
 for place,path in AL_PATHS.items():
  pages=[('Ambulance','ambulance/'),('Brandweer','brandweer/'),('Politie','politie/'),('Overig','p2000/'),('Overig','')]
  for default,suffix in pages:
   url=urllib.parse.urljoin(BASE_AL,path+'/'+suffix);sources.append(url)
   try:raw=get(url).decode('utf-8','ignore')
   except Exception as e:print('page failed',url,e);continue
   p=CardParser();p.feed(raw)
   for title,dt in p.entries[:80]:
    actual=place_for(title) or place
    # Only keep our requested area; overview/p2000 page may contain related links.
    if actual not in TARGETS:continue
    service=service_from_text(title,default)
    if service=='Overig':continue
    # Avoid very old pagination/noise on the first page.
    if dt < now-timedelta(days=10):continue
    street=street_guess(title,actual)
    out.append({'service':service,'place':actual,'title':clean(title),'location':(street+', '+actual) if street else actual,'original':clean(title),'priority':priority_for(title),'unit':'','published':dt.isoformat(),'time_label':dt.strftime('%a %d-%m · %H:%M'),'is_today':dt.date()==now.date(),'lat':None,'lon':None,'link':url,'source':'Alarmeringen.nl'})
 return out,sources

class Links(HTMLParser):
 def __init__(self):super().__init__();self.href=None;self.text='';self.links=[]
 def handle_starttag(self,tag,attrs):
  if tag=='a':self.href=dict(attrs).get('href');self.text=''
 def handle_data(self,d):
  if self.href:self.text+=d
 def handle_endtag(self,tag):
  if tag=='a' and self.href:self.links.append((self.text.strip(),self.href));self.href=None

def discover_112():
 p=Links();p.feed(get(BASE_112+'rss.html').decode('utf-8','ignore'));wanted={}
 for text,href in p.links:
  low=text.lower()
  if 'brandweer' in low:wanted['Brandweer']=urllib.parse.urljoin(BASE_112,href)
  elif 'politie' in low:wanted['Politie']=urllib.parse.urljoin(BASE_112,href)
  elif 'ambulance' in low:wanted['Ambulance']=urllib.parse.urljoin(BASE_112,href)
  elif 'traumahelikopter' in low:wanted['Traumahelikopter']=urllib.parse.urljoin(BASE_112,href)
 return wanted

def xmltxt(el,name):
 x=el.find(name);return clean(x.text or '') if x is not None else ''

def scrape_112(now):
 out=[]
 try:feeds=discover_112()
 except Exception as e:print('rss discovery',e);return out,{}
 for service,url in feeds.items():
  try:root=ET.fromstring(get(url))
  except Exception as e:print('rss failed',service,e);continue
  for it in root.findall('.//item')[:220]:
   title=xmltxt(it,'title');desc=xmltxt(it,'description');link=xmltxt(it,'link');pub=xmltxt(it,'pubDate');blob=' '.join([title,desc,link]);place=place_for(blob)
   if not place:continue
   try:
    dt=parsedate_to_datetime(pub)
    if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
    dt=dt.astimezone(TZ)
   except:dt=now
   if dt<now-timedelta(days=10):continue
   # street comes reliably from 112-nu detail URL when present
   street=''
   try:
    parts=[urllib.parse.unquote(x) for x in urllib.parse.urlparse(link).path.split('/') if x]
    if len(parts)>=5 and parts[0]=='melding':street=parts[3].replace('-',' ').title()
   except:pass
   out.append({'service':service,'place':place,'title':title or desc[:160],'location':(street+', '+place) if street else place,'original':desc,'priority':priority_for(blob),'unit':'','published':dt.isoformat(),'time_label':dt.strftime('%a %d-%m · %H:%M'),'is_today':dt.date()==now.date(),'lat':None,'lon':None,'link':link,'source':'112-nu.nl'})
 return out,feeds

def load_cache():
 try:
  with open(CACHE_FILE,encoding='utf8') as f:return json.load(f)
 except:return {}

def save_cache(c):
 with open(CACHE_FILE,'w',encoding='utf8') as f:json.dump(c,f,ensure_ascii=False,separators=(',',':'),sort_keys=True)

def geocode(q):
 try:
  params=urllib.parse.urlencode({'q':q,'format':'jsonv2','limit':1,'countrycodes':'nl'});arr=json.loads(get('https://nominatim.openstreetmap.org/search?'+params,{'Accept-Language':'nl'}).decode())
  if arr:return {'lat':float(arr[0]['lat']),'lon':float(arr[0]['lon'])}
 except Exception as e:print('geo',q,e)
 return None

def normkey(x):
 # Merge page/RSS duplicates by service, place, minute and main location words.
 try:minute=x['published'][:16]
 except:minute=''
 loc=re.sub(r'[^a-z0-9]+',' ',(x.get('location') or x.get('title','')).lower())
 words=' '.join(w for w in loc.split() if len(w)>2 and w not in ['met','spoed','naar','ambulance','brandweer','politie'])
 return (x['service'],x['place'],minute,words[:55])

def main():
 now=datetime.now(TZ); incidents=[]
 a,apages=scrape_alarmeringen(now);incidents.extend(a)
 r,feeds=scrape_112(now);incidents.extend(r)
 # Exact-ish dedupe, preferring richer page records but keeping genuinely distinct units/calls.
 uniq={}
 for x in sorted(incidents,key=lambda z:(z.get('source')!='Alarmeringen.nl',z['published']),reverse=True):
  k=normkey(x)
  if k not in uniq:uniq[k]=x
 incidents=list(uniq.values());incidents.sort(key=lambda x:x['published'],reverse=True)
 cache=load_cache();newgeo=0
 for x in incidents:
  loc=x.get('location','')
  if ',' not in loc:continue
  street=loc.rsplit(',',1)[0].strip();q=f'{street}, {x["place"]}, Nederland'
  g=cache.get(q)
  if q not in cache and newgeo<MAX_NEW_GEOCODES:
   if newgeo:time.sleep(16)
   g=geocode(q);cache[q]=g;newgeo+=1
  if g:x['lat']=g.get('lat');x['lon']=g.get('lon')
 out={'updated':now.isoformat(),'updated_label':now.strftime('%H:%M'),'sources':{'pages':apages,'rss':feeds},'incidents':incidents[:600]}
 with open('data.json','w',encoding='utf8') as f:json.dump(out,f,ensure_ascii=False,separators=(',',':'))
 save_cache(cache);print('alarmeringen',len(a),'rss',len(r),'unique',len(incidents),'geocodes',newgeo)
if __name__=='__main__':main()
