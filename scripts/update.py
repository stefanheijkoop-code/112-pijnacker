import urllib.request, urllib.parse, xml.etree.ElementTree as ET, json, re, html, time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

TZ=ZoneInfo('Europe/Amsterdam')
TARGETS=['Pijnacker','Nootdorp','Delfgauw','Berkel en Rodenrijs','Oude Leede','Delft']
ALIASES={
 'Pijnacker':['pijnacker','pijnak'], 'Nootdorp':['nootdorp','nootdp'],
 'Delfgauw':['delfgauw'], 'Berkel en Rodenrijs':['berkel en rodenrijs','berkrr'],
 'Oude Leede':['oude leede','oude-leede'], 'Delft':['delft']
}
CITY_SLUGS=['pijnacker','nootdorp','delfgauw','berkel-en-rodenrijs','oude-leede','delft']
UA={'User-Agent':'112-pijnacker-dashboard/1.4 (+github.com/stefanheijkoop-code/112-pijnacker)'}
CACHE_FILE='geocode_cache.json';MAX_NEW_GEOCODES=3

def get(url,timeout=8):
 req=urllib.request.Request(url,headers=UA)
 with urllib.request.urlopen(req,timeout=timeout) as r:return r.read()

def clean(s):return html.unescape(re.sub(r'\s+',' ',re.sub('<[^>]+>',' ',s or ''))).strip()
def xtext(el,name):
 x=el.find(name);return clean(x.text or '') if x is not None else ''

def place_for(s):
 low=(s or '').lower()
 for p in ['Berkel en Rodenrijs','Oude Leede','Delfgauw','Nootdorp','Pijnacker','Delft']:
  if any(a in low for a in ALIASES[p]):return p
 return None

def service_for(s,default='Overig'):
 low=(s or '').lower()
 if any(k in low for k in ['traumaheli','traumahelikopter','lifeliner',' mmt']):return 'Traumahelikopter'
 if 'politie' in low or 'prio ' in low or 'icnum' in low:return 'Politie'
 if 'brandweer' in low or (re.search(r'\bp\s*[123]\b',low) and any(k in low for k in [' br ','oms','brand','dier','hv ','ass. ambu'])):return 'Brandweer'
 if 'ambulance' in low or 'ambu' in low or re.search(r'\b[ab][12]\b',low):return 'Ambulance'
 return default

def priority_for(s):
 m=re.search(r'\b(PRIO\s*[1-4]|P\s*[1-3]|A[12]|B[12])\b',s or '',re.I)
 return re.sub(r'\s+','',m.group(1).upper()) if m else ''

def dt_for(pub,now):
 try:
  d=parsedate_to_datetime(pub)
  if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
  return d.astimezone(TZ)
 except:return now

def street_for(text,place,link=''):
 try:
  ps=[urllib.parse.unquote(x) for x in urllib.parse.urlparse(link).path.split('/') if x]
  if len(ps)>=5 and ps[0]=='melding':return ps[3].replace('-',' ').title()
 except:pass
 s=clean(text)
 m=re.search(r'(?:naar|op|aan)\s+(.+?)\s+in\s+'+re.escape(place)+r'\b',s,re.I)
 if m:return m.group(1).strip(' ,.-')[:80]
 pos=s.lower().find(place.lower())
 if pos>0:
  left=s[:pos]
  left=re.sub(r'^(?:prio\s*\d+|p\s*\d+|a[12]|b[12]|ambu\s*\d+|\(dia:\s*ja\)|dia:\s*ja)\s*','',left,flags=re.I)
  left=re.sub(r'\b\d{4}[a-z]{2}\b|\b\d{5,6}\b|\bbon\s*\d+\b',' ',left,flags=re.I)
  words=clean(left).split()
  if words:return ' '.join(words[-5:])[:80]
 return ''

def parse_feed(url,now,default='Overig',source='Alarmeringen.nl'):
 try:root=ET.fromstring(get(url))
 except Exception as e:print('feed failed',url,type(e).__name__,e);return []
 out=[]
 for it in root.findall('.//item')[:120]:
  title=xtext(it,'title');desc=xtext(it,'description');link=xtext(it,'link');pub=xtext(it,'pubDate');blob=' '.join([title,desc,link]);place=place_for(blob)
  if not place:continue
  d=dt_for(pub,now)
  if d<now-timedelta(days=10):continue
  service=service_for(blob,default)
  if service=='Overig':continue
  street=street_for(title+' '+desc,place,link)
  out.append({'service':service,'place':place,'title':title or desc[:160],'location':(street+', '+place) if street else place,'original':desc,'priority':priority_for(blob),'unit':'','published':d.isoformat(),'time_label':d.strftime('%a %d-%m · %H:%M'),'is_today':d.date()==now.date(),'lat':None,'lon':None,'link':link,'source':source})
 return out

def collect(now):
 out=[];sources=[]
 # Official Alarmeringen per-city feeds; documented feed pattern /feeds/city/<slug>.rss.
 for slug in CITY_SLUGS:
  u=f'https://alarmeringen.nl/feeds/city/{slug}.rss';sources.append(u);out+=parse_feed(u,now)
 # Confirmed general region feeds catch edge cases near boundaries.
 for reg in ['haaglanden','rotterdam-rijnmond']:
  u=f'https://alarmeringen.nl/feeds/region/{reg}.rss';sources.append(u);out+=parse_feed(u,now)
 # Confirmed national discipline feeds; useful for traumaheli/MMT in particular.
 for disc,default in [('trauma','Traumahelikopter'),('ambulance','Ambulance'),('brandweer','Brandweer'),('politie','Politie')]:
  u=f'https://alarmeringen.nl/feeds/discipline/{disc}.rss';sources.append(u);out+=parse_feed(u,now,default)
 # Second provider as fallback/extra coverage.
 other={'Politie':'https://112-nu.nl/politie/rss','Ambulance':'https://112-nu.nl/ambulance/rss','Brandweer':'https://112-nu.nl/brandweer/rss','Traumahelikopter':'https://112-nu.nl/trauma-helikopter/rss'}
 for default,u in other.items():out+=parse_feed(u,now,default,'112-nu.nl')
 return out,{'alarmeringen':sources,'112-nu':other}

def load_cache():
 try:
  with open(CACHE_FILE,encoding='utf8') as f:return json.load(f)
 except:return {}
def save_cache(c):
 with open(CACHE_FILE,'w',encoding='utf8') as f:json.dump(c,f,ensure_ascii=False,separators=(',',':'),sort_keys=True)
def geocode(q):
 try:
  p=urllib.parse.urlencode({'q':q,'format':'jsonv2','limit':1,'countrycodes':'nl'});req=urllib.request.Request('https://nominatim.openstreetmap.org/search?'+p,headers={**UA,'Accept-Language':'nl'});a=json.loads(urllib.request.urlopen(req,timeout=8).read().decode())
  if a:return {'lat':float(a[0]['lat']),'lon':float(a[0]['lon'])}
 except Exception as e:print('geo failed',q,e)
 return None

def dkey(x):
 minute=x['published'][:16];loc=re.sub(r'[^a-z0-9]+',' ',(x.get('location') or x['title']).lower());loc=' '.join(w for w in loc.split() if len(w)>2 and w not in ['met','spoed','naar','ambulance','brandweer','politie'])
 return (x['service'],x['place'],minute,loc[:50])

def main():
 now=datetime.now(TZ);items,sources=collect(now);uniq={}
 for x in sorted(items,key=lambda z:z['published'],reverse=True):
  k=dkey(x)
  if k not in uniq or (uniq[k]['source']=='112-nu.nl' and x['source']=='Alarmeringen.nl'):uniq[k]=x
 incidents=sorted(uniq.values(),key=lambda x:x['published'],reverse=True)
 cache=load_cache();new=0
 for x in incidents:
  if ',' not in x['location']:continue
  street=x['location'].rsplit(',',1)[0].strip();q=f'{street}, {x["place"]}, Nederland';g=cache.get(q)
  if q not in cache and new<MAX_NEW_GEOCODES:
   if new:time.sleep(16)
   g=geocode(q);cache[q]=g;new+=1
  if g:x['lat']=g.get('lat');x['lon']=g.get('lon')
 with open('data.json','w',encoding='utf8') as f:json.dump({'updated':now.isoformat(),'updated_label':now.strftime('%H:%M'),'sources':sources,'incidents':incidents[:600]},f,ensure_ascii=False,separators=(',',':'))
 save_cache(cache);print('items',len(items),'unique',len(incidents),'new geocodes',new)
if __name__=='__main__':main()
