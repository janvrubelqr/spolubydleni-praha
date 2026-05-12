import re
import httpx

r = httpx.get('https://www.realingo.cz', timeout=30)
text = r.text
print('status', r.status_code)
for pat in [r'api/[^"\s]+', r'/[a-zA-Z0-9_\-/]+\?[^"\s]+', r'"(https?://www\.realingo\.cz/[^"]+)"']:
    found = re.findall(pat, text)
    print('PAT', pat, len(found))
    print(found[:30])
    print('---')
