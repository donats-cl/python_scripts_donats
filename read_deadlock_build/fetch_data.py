import urllib.request, json, os, tempfile

T = os.path.join(tempfile.gettempdir(), 'opencode')


def get(u):
    r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=120)
    return json.load(r)


items = get('https://api.deadlock-api.com/v1/assets/items')
heroes = get('https://api.deadlock-api.com/v1/assets/heroes')
json.dump(items, open(os.path.join(T, 'dl_items.json'), 'w', encoding='utf-8'), ensure_ascii=False)
json.dump(heroes, open(os.path.join(T, 'dl_heroes.json'), 'w', encoding='utf-8'), ensure_ascii=False)
s = [h for h in heroes if h.get('id') == 80][0]
print('hero keys:', list(s.keys()))
print('name', s.get('name'))
print('sig', {k: v for k, v in (s.get('items') or {}).items() if 'signature' in k})
