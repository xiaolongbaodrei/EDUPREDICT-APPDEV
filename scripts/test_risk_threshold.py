import sys, os
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app, db, Student

with app.app_context():
    db.create_all()
    # Cleanup
    Student.query.filter(Student.name.in_(['HighRisk','LowRisk'])).delete(synchronize_session=False)
    db.session.commit()

    client = app.test_client()

    # Register & login a teacher
    client.post('/register', data={'username': 'rtester', 'password': 'p', 'role': 'Teacher'}, follow_redirects=True)
    client.post('/', data={'username': 'rtester', 'password': 'p'}, follow_redirects=True)

    # Post student with final_grade below or equal 75 -> expect High Risk
    client.post('/predict', data={'name': 'HighRisk', 'attendance': '90', 'activities': '50', 'quizzes': '50', 'performance_task': '60', 'exam': '65', 'subject': 'math'}, follow_redirects=True)
    s = Student.query.filter_by(name='HighRisk').first()
    logging.info('HighRisk final_grade: %s risk: %s', s.final_grade, s.risk)

    # Post student with final_grade >=76 -> expect Low Risk
    client.post('/predict', data={'name': 'LowRisk', 'attendance': '90', 'activities': '90', 'quizzes': '88', 'performance_task': '90', 'exam': '92', 'subject': 'science'}, follow_redirects=True)
    s2 = Student.query.filter_by(name='LowRisk').first()
    logging.info('LowRisk final_grade: %s risk: %s', s2.final_grade, s2.risk)

    assert s.risk == 'High Risk', 'Expected HighRisk to be High Risk'
    assert s2.risk == 'Low Risk', 'Expected LowRisk to be Low Risk'

    logging.info('Risk threshold tests passed')
