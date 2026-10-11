"""Read-only live P2000 endpoint: only fixed public feeds, no GitHub tokens."""
from http.server import BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import urllib.request
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import update

ORIGIN = 'https://stefanheijkoop-code.github.io'
FEEDS = [(f'https://alarmeringen.nl/feeds/city/{slug}.rss', 'Overig', 'Alarmeringen.nl')
         for slug in update.CITY_SLUGS if slug != 'oude-leede']
FEEDS += [(f'https://alarmeringen.nl/feeds/region/{slug}.rss', 'Overig', 'Alarmeringen.nl')
          for slug in ['haaglanden', 'rotterdam-rijnmond']]
FEEDS += [(f'https://alarmeringen.nl/feeds/discipline/{slug}.rss', service, 'Alarmeringen.nl')
          for slug, service in [('trauma', 'Traumahelikopter'), ('ambulance', 'Ambulance'), ('brandweer', 'Brandweer'), ('politie', 'Politie')]]
FEEDS += [(f'https://112-nu.nl/{slug}/rss', service, '112-nu.nl')
          for slug, service in [('trauma-helikopter', 'Traumahelikopter'), ('ambulance', 'Ambulance'), ('brandweer', 'Brandweer'), ('politie', 'Politie')]]

def fetch_feed(feed, now):
    url, service, source = feed
    try:
        req = urllib.request.Request(url, headers={**update.UA, 'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(req, timeout=8) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('Feed too large')
        root = ET.fromstring(raw)
        if root.tag != 'rss':
            raise ValueError('Not RSS')
        items = update.parse_feed(url, now, service, source, payload=raw)
        for item in items:
            date = datetime.fromisoformat(item['published'])
            if source == '112-nu.nl' and date > now + timedelta(minutes=5):
                date -= timedelta(hours=2)
                item['published'] = date.isoformat()
                item['time_label'] = date.strftime('%a %d-%m · %H:%M')
            item['is_today'] = date.date() == now.date()
            text = (item['title'] + ' ' + item['original']).lower()
            if any(word in text for word in [' brt-', ' bdh-', ' brandweer', ' oms ', ' brandgerucht', ' br woning', ' br gebouw', ' br buiten']):
                item['service'] = 'Brandweer'
        return items, None
    except Exception as error:
        print('feed unavailable', url, type(error).__name__, flush=True)
        return [], url

def collect_live():
    now = datetime.now(update.TZ)
    with ThreadPoolExecutor(max_workers=len(FEEDS)) as pool:
        results = list(pool.map(lambda feed: fetch_feed(feed, now), FEEDS))
    failed = [error for _, error in results if error]
    if len(failed) == len(FEEDS):
        raise RuntimeError('Alle bronnen zijn onbereikbaar')
    unique = {}
    for items, _ in results:
        for item in items:
            key = update.dkey(item)
            if key not in unique or item['source'] == 'Alarmeringen.nl':
                unique[key] = item
    incidents = sorted(unique.values(), key=lambda item: item['published'], reverse=True)[:600]
    return {'updated': now.isoformat(), 'incidents': incidents,
            'partial': bool(failed), 'failed_sources': len(failed), 'checked_sources': len(FEEDS)}

class handler(BaseHTTPRequestHandler):
    def reply(self, status, data):
        self.send_response(status)
        self.send_header('Access-Control-Allow-Origin', ORIGIN)
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Vary', 'Origin')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def do_OPTIONS(self):
        self.reply(200, {})

    def do_GET(self):
        origin = self.headers.get('Origin')
        if origin and origin != ORIGIN:
            self.reply(403, {'error': 'Origin niet toegestaan'})
            return
        try:
            self.reply(200, collect_live())
        except Exception as error:
            print('refresh failed', type(error).__name__, flush=True)
            self.reply(502, {'error': 'Nieuwe bronmeldingen konden niet worden opgehaald'})
