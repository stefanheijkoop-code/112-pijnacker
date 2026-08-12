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
CITY_SLUGS={'Pijnacker':'pijnacker','Nootdorp':'nootdorp','Delfgauw':'delfgauw','Berkel en Rodenrijs':'berkel-en-rodenrijs','Oude Leede':'oude-leede','Delft':'delft'}
UA={'User-Agent':'112-pijnacker-dashboard/1.3 (personal dashboard; github.com/stefanheijkoop-code/112-pijnacker)'}
CACHE_FILE='geocode_cache.json'; MAX_NEW_GEOCODES=3

def get(url):
 req=urllib.request.Request(url,headers=UA)
 with urllib.request.urlopen(req,timeout=30) as r:return r.read()

def clean(s):return html.unescape(re.sub(r'\s+',' ',re.sub('<[^>]+>',' ',s or ''))).strip()

def xmltxt(el,name):
 x=el.find(name);return clean(x.text or '') if x is not None else ''

def place_for(s):
 low=(s or '').lower()
 for place in ['Berkel en Rodenrijs','Oude Leede','Delfgauw','Nootdorp','Pijnacker','Delft']:
  if any(k in low for k in ALIASES[place]):return place
 return None

def service_for(s,default='Overig'):
 low=(s or '').lower()
 if any(x in low for x in ['traumaheli','traumahelikopter','lifeliner',' mmt']):return 'Traumahelikopter'
 if 'brandweer' in low or re.search(r'\bp\s*[123]\b',low) and any(x in low for x in [' br ','oms','brand','dier','ass. ambu','hv '] ):return 'Brandweer'
 if 'politie' in low or 'prio ' in low or 'icnum' in low:return 'Politie'
 if 'ambulance' in low or 'ambu' in low or re.search(r'\b[ab][12]\b',low):return 'Ambulance'
 return default

def priority_for(s):
 m=re.search(r'\b(PRIO\s*[1-4]|P\s*[1-3]|A[12]|B[12])\b',s or '',re.I)
 return re.sub(r'\s+','',m.group(1).upper()) if m else ''

def parse_dt(pub,now):
 try:
  dt=parsedate_to_datetime(pub)
  if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
  return dt.astimezone(TZ)
 except:return now

def street_guess(text,place,link=''):
 try:
  parts=[urllib.parse.unquote(x) for x in urllib.parse.urlparse(link).path.split('/') if x]
  if len(parts)>=5 and parts[0]=='melding':return parts[3].replace('-',' ').title()
 except:pass
 s=clean(text)
 m=re.search(r'(?:naar|op|aan)\s+(.+?)\s+in\s+'+re.escape(place)+r'\b',s,re.I)
 if m:return m.group(1).strip(' ,.-')[:90]
 low=s.lower(); pos=low.find(place.lower())
 if pos>0:
  left=s[:pos]
  left=re.sub(r'^(?:prio\s*\d+|p\s*\d+|a[12]|b[12]|ambu\s*\d+|\(dia:\s*ja\)|dia:\s*ja)\s*','',left,flags=re.I)
  left=re.sub(r'\b\d{4}[a-z]{2}\b|\b\d{5,6}\b|\bbon\s*\d+\b',' ',left,flags=re.I)
  words=clean(left).split()
  if words:return ' '.join(words[-5:])[:90]
 return ''

def parse_feed(url,now,default='Overig',source='Alarmeringen.nl'):
 out=[]
 try:root=ET.fromstring(get(url))
 except Exception as e:print('feed failed',url,e);return out
 for it in root.findall('.//item')[:120]:
  title=xmltxt(it,'title');desc=xmltxt(it,'description');link=xmltxt(it,'link');pub=xmltxt(it,'pubDate');blob=' '.join([title,desc,link]);place=place_for(blob)
  if not place:continue
  dt=parse_dt(pub,now)
  if dt<now-timedelta(days=10):continue
  service=service_for(blob,default)
  if service=='Overig':continue
  street=street_guess(title+' '+desc,place,link)
  out.append({'service':service,'place':place,'title':title or desc[:160],'location':(street+', '+place) if street else place,'original':desc,'priority':priority_for(blob),'unit':'','published':dt.isoformat(),'time_label':dt.strftime('%a %d-%m · %H:%M'),'is_today':dt.date()==now.date(),'lat':None,'lon':None,'link':link,'source':source})
 return out

def alarmeringen(now):
 urls=[];out=[]
 for place,slug in CITY_SLUGS.items():
  url=f'https://alarmeringen.nl/feeds/city/{slug}.rss';urls.append(url);out+=parse_feed(url,now,source='Alarmeringen.nl')
 # Region feeds catch aliases/edge cases and some MMT calls just outside a city feed.
 for reg in ['haaglanden','rotterdam-rijnmond']:
  for suffix,default in [('', 'Overig'),('/ambulance','Ambulance'),('/brandweer','Brandweer'),('/politie','Politie')]:
   url=f'https://alarmeringen.nl/feeds/region/{reg}{suffix}.rss';urls.append(url);out+=parse_feed(url,now,default,source='Alarmeringen.nl')
 for disc,default in [('trauma','Traumahelikopter'),('ambulance','Ambulance'),('brandweer','Brandweer'),('politie','Politie')]:
  url=f'https://alarmeringen.nl/feeds/discipline/{disc}.rss';urls.append(url);out+=parse_feed(url,now,default,source='Alarmeringen.nl')
 return out,urls

def nu112(now):
 feeds={'Politie':'https://112-nu.nl/politie/rss','Ambulance':'https://112-nu.nl/ambulance/rss','Brandweer':'https://112-nu.nl/brandweer/rss','Traumahelikopter':'https://112-nu.nl/trauma-helikopter/rss'};out=[]
 for service,url in feeds.items():out+=parse_feed(url,now,service,'112-nu.nl')
 return out,feeds

def load_cache():
 try:
  with open(CACHE_FILE,encoding='utf8') as f:return json.load(f)
 except:return {}

def save_cache(c):
 with open(CACHE_FILE,'w',encoding='utf8') as f:json.dump(c,f,ensure_ascii=False,separators=(',',':'),sort_keys=True)

def geocode(q):
 try:
  params=urllib.parse.urlencode({'q':q,'format':'jsonv2','limit':1,'countrycodes':'nl'});req=urllib.request.Request('https://nominatim.openstreetmap.org/search?'+params,headers={**UA,'Accept-Language':'nl'});arr=json.loads(urllib.request.urlopen(req,timeout=25).read().decode())
  if arr:return {'lat':float(arr[0]['lat']),'lon':float(arr[0]['lon'])}
 except Exception as e:print('geo failed',q,e)
 return None

def key(x):
 minute=x['published'][:16];loc=re.sub(r'[^a-z0-9]+',' ',(x.get('location') or x.get('title','')).lower());words=' '.join(w for w in loc.split() if len(w)>2 and w not in ['met','spoed','naar','ambulance','brandweer','politie'])
 return (x['service'],x['place'],minute,words[:50])

def main():
 now=datetime.now(TZ);a,afeeds=alarmeringen(now);n,nfeeds=nu112(now);allitems=a+n
 uniq={}
 for x in sorted(allitems,key=lambda z:z['published'],reverse=True):
  k=key(x)
  if k not in uniq or (uniq[k]['source']=='112-nu.nl' and x['source']=='Alarmeringen.nl'):uniq[k]=x
 incidents=sorted(uniq.values(),key=lambda x:x['published'],reverse=True)
 cache=load_cache();newgeo=0
 for x in incidents:
  loc=x.get('location','')
  if ',' not in loc:continue
  street=loc.rsplit(',',1)[0].strip();q=f'{street}, {x["place"]}, Nederland';g=cache.get(q)
  if q not in cache and newgeo<MAX_NEW_GEOCODES:
   if newgeo:time.sleep(16)
   g=geocode(q);cache[q]=g;newgeo+=1
  if g:x['lat']=g.get('lat');x['lon']=g.get('lon')
 out={'updated':now.isoformat(),'updated_label':now.strftime('%H:%M'),'sources':{'alarmeringen':afeeds,'112-nu':nfeeds},'incidents':incidents[:600]}
 with open('data.json','w',encoding='utf8') as f:json.dump(out,f,ensure_ascii=False,separators=(',',':'))
 save_cache(cache);print('alarmeringen',len(a),'112nu',len(n),'unique',len(incidents),'geocodes',newgeo)
if __name__=='__main__':main()
