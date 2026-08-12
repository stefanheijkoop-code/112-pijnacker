import urllib.request, urllib.parse, xml.etree.ElementTree as ET, json, re, html
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
 'Berkel en Rodenrijs':['berkel en rodenrijs','berkel-rodenrijs','berkel rodenrijs'],
 'Oude Leede':['oude leede','oude-leede'],
 'Delft':['delft']
}
UA={'User-Agent':'112-pijnacker-dashboard/1.1 (+https://github.com/stefanheijkoop-code/112-pijnacker)'}

class Links(HTMLParser):
 def __init__(self): super().__init__(); self.href=None; self.text=''; self.links=[]
 def handle_starttag(self,tag,attrs):
  if tag=='a': self.href=dict(attrs).get('href'); self.text=''
 def handle_data(self,d):
  if self.href: self.text+=d
 def handle_endtag(self,tag):
  if tag=='a' and self.href:
   self.links.append((self.text.strip(),self.href)); self.href=None

def get(url):
 req=urllib.request.Request(url,headers=UA)
 with urllib.request.urlopen(req,timeout=25) as r:return r.read()

def discover():
 # Stable public P2000 RSS endpoints documented by 112-nu.nl
 return {
  'Brandweer': BASE+'brandweer/rss',
  'Politie': BASE+'politie/rss',
  'Ambulance': BASE+'ambulance/rss',
  'Traumahelikopter': BASE+'trauma-helikopter/rss'
 }

def txt(el,name):
 x=el.find(name); return html.unescape(' '.join((x.text or '').split())) if x is not None else ''

def place_for(s):
 low=s.lower()
 for place,keys in ALIASES.items():
  if any(k in low for k in keys): return place
 return None

def clean(s):
 s=re.sub('<[^>]+>',' ',s);return html.unescape(re.sub(r'\s+',' ',s)).strip()

def main():
 feeds=discover(); incidents=[]; seen=set(); now=datetime.now(ZoneInfo('Europe/Amsterdam'))
 for service,url in feeds.items():
  try: root=ET.fromstring(get(url))
  except Exception as e: print(service,e);continue
  items=root.findall('.//item')
  for it in items[:250]:
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
   m=re.search(r'\b(PRIO\s*[123]|P\s*[123]|A\s*[12])\b',blob,re.I)
   if m:priority=re.sub(r'\s+','',m.group(1).upper())
   loc=''
   for candidate in [desc,title]:
    if place.lower() in candidate.lower(): loc=candidate[:180];break
   incidents.append({'service':service,'place':place,'title':title or desc[:160],'location':loc or place,'original':desc,'priority':priority,'unit':'','published':dt.isoformat(),'time_label':dt.strftime('%d-%m · %H:%M'),'is_today':dt.date()==now.date(),'lat':None,'lon':None,'link':link})
 incidents.sort(key=lambda x:x['published'],reverse=True)
 out={'updated':now.isoformat(),'updated_label':now.strftime('%H:%M'),'feeds':feeds,'incidents':incidents[:500]}
 with open('data.json','w',encoding='utf8') as f:json.dump(out,f,ensure_ascii=False,separators=(',',':'))
 print('feeds',feeds,'incidents',len(incidents))
if __name__=='__main__':main()
