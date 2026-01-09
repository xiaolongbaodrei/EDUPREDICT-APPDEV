import requests
import logging

base = 'http://127.0.0.1:5000'
s = requests.Session()

# Register a new admin user
r = s.post(base + '/register', data={'username':'admin_test','password':'pass123','role':'Admin'})
logging.info('Register status: %s Final URL: %s', r.status_code, r.url)

# Login
r = s.post(base + '/', data={'username':'admin_test','password':'pass123'}, allow_redirects=True)
logging.info('Login status: %s', r.status_code)
logging.info('After login URL: %s', r.url)
logging.info('Dashboard title found: %s', 'Dashboard' in r.text)

# Access dashboard directly
r = s.get(base + '/dashboard')
logging.info('/dashboard status: %s', r.status_code)
logging.info('Dashboard title found (get): %s', 'Dashboard' in r.text)

# Test predict access
r = s.get(base + '/predict')
logging.info('/predict access status: %s', r.status_code)
logging.info('Predict page title found: %s', 'Dropout Risk Prediction' in r.text)

# Try making a prediction (with new fields)
r = s.post(base + '/predict', data={
    'name':'Test',
    'attendance':'80',
    'activities':'85',
    'quizzes':'80',
    'performance_task':'88',
    'exam':'78',
    'subject':'filipino'
}, allow_redirects=True)
logging.info('Predict post status: %s', r.status_code)
logging.info('Predict result contains risk: %s', 'Result' in r.text or 'could not be loaded' in r.text)
logging.info('Final grade present: %s', 'Final Grade' in r.text or 'final_grade' in r.text)

# (Risk Reduction dashboard removed)
