import json,re
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo

TZ=ZoneInfo('Europe/Amsterdam')
with open('data.json',encoding='utf8') as f:data=json.load(f)
now=datetime.now(TZ)
for x in data.get('incidents',[]):
    text=(x.get('title','')+' '+x.get('original','')).lower()
    if any(k in text for k in ['traumaheli','traumahelikopter','lifeliner',' mmt']):
        x['service']='Traumahelikopter'
    elif any(k in text for k in [' brt-',' bdh-',' brandweer',' oms ',' brandgerucht',' br woning',' br gebouw',' br buiten']):
        x['service']='Brandweer'
    elif 'prio ' in text or 'icnum' in text or ' politie' in text:
        x['service']='Politie'
    elif re.search(r'\b(?:a1|a2|b1|b2)\b',text) or 'ambu' in text or 'ambulance' in text:
        x['service']='Ambulance'
    try:
        d=datetime.fromisoformat(x['published'])
        if x.get('source')=='112-nu.nl' and d>now+timedelta(minutes=5):
            d-=timedelta(hours=2)
            x['published']=d.isoformat()
            x['time_label']=d.strftime('%a %d-%m · %H:%M')
        x['is_today']=d.date()==now.date()
    except Exception:
        pass
data['incidents'].sort(key=lambda z:z.get('published',''),reverse=True)
with open('data.json','w',encoding='utf8') as f:json.dump(data,f,ensure_ascii=False,separators=(',',':'))
