import requests
from bs4 import BeautifulSoup
import logging

base = 'http://127.0.0.1:5000'
s = requests.Session()
# Try register/login
try:
    s.post(base + '/register', data={'username': 'smoketest_smoke', 'password': 'pass', 'role': 'Teacher'})
except Exception:
    pass
r = s.post(base + '/', data={'username': 'smoketest_smoke', 'password': 'pass'})
logging.info('login status %s url %s', r.status_code, r.url)
# Visit dashboard -> manage students (with filter) -> predict
s.get(base + '/dashboard')
r = s.get(base + '/admin/students?section=Section+A&subject=math')
logging.info('manage students status: %s', r.status_code)
r2 = s.get(base + '/predict')
logging.info('predict status: %s', r2.status_code)
soup = BeautifulSoup(r2.text, 'html.parser')
btn = soup.select_one('.btn-back')
if btn:
    href = btn.get('href')
    if href:
        logging.info('back href -> %s', href)
    else:
        logging.info('back is history/history button (no href)')
else:
    logging.info('no back button found')
