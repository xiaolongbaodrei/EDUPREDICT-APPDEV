import requests
from bs4 import BeautifulSoup
import io
import logging

base = 'http://127.0.0.1:5000'
s = requests.Session()
# register & login
try:
    s.post(base + '/register', data={'username': 'import_tester', 'password': 'pass', 'role': 'Teacher'})
except Exception:
    pass
s.post(base + '/', data={'username': 'import_tester', 'password': 'pass'})

# create sample csv
csv_data = io.StringIO()
csv_data.write('name,section,subject,activities,quizzes,performance_task,exam,attendance,notes\n')
csv_data.write('Alice,Section A,math,85,90,88,92,95,Good student\n')
csv_data.write('Bob,Section A,science,70,65,60,55,80,Needs help\n')
csv_data.seek(0)

files = {'file': ('students.csv', csv_data.read())}
# upload
r = s.post(base + '/import_csv', files=files)
logging.info('preview status %s', r.status_code)
# should contain preview
soup = BeautifulSoup(r.text, 'html.parser')
if 'Preview' in r.text:
    logging.info('Preview shown')
else:
    logging.info('Preview not shown')
