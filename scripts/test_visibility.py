import logging
from app import app, db, User, Student

# Use Flask test client
with app.app_context():
    db.create_all()

    # Cleanup previous test users/students
    User.query.filter(User.username.in_(['t1','t2','admin_test'])).delete(synchronize_session=False)
    Student.query.delete()
    db.session.commit()

    client = app.test_client()

    # Register teacher 1
    r = client.post('/register', data={'username': 't1', 'password': 'pass', 'role': 'Teacher'}, follow_redirects=True)
    # Login teacher1
    r = client.post('/', data={'username': 't1', 'password': 'pass'}, follow_redirects=True)

    # Create two students as t1
    client.post('/predict', data={
        'name': 'Student A', 'attendance': '90', 'activities': '80', 'quizzes': '75', 'performance_task': '85', 'exam': '80', 'subject': 'math'
    }, follow_redirects=True)
    client.post('/predict', data={
        'name': 'Student B', 'attendance': '85', 'activities': '70', 'quizzes': '65', 'performance_task': '70', 'exam': '75', 'subject': 'science'
    }, follow_redirects=True)

    # Register teacher 2 and add one student
    client.get('/logout')
    client.post('/register', data={'username': 't2', 'password': 'pass', 'role': 'Teacher'}, follow_redirects=True)
    client.post('/', data={'username': 't2', 'password': 'pass'}, follow_redirects=True)
    client.post('/predict', data={
        'name': 'Student C', 'attendance': '80', 'activities': '60', 'quizzes': '60', 'performance_task': '60', 'exam': '60', 'subject': 'english'
    }, follow_redirects=True)

    # Login as t1 and check manage_students
    client.get('/logout')
    client.post('/', data={'username': 't1', 'password': 'pass'}, follow_redirects=True)
    r = client.get('/admin/students')
    text = r.get_data(as_text=True)
    t1_can_see = text.count('Student A') + text.count('Student B')
    t1_cant_see_c = 'Student C' in text

    logging.info('t1 sees count (expect 2): %s', t1_can_see)
    logging.info('t1 sees Student C (expect False): %s', t1_cant_see_c)

    # Create admin and verify admin sees all
    client.get('/logout')
    client.post('/register', data={'username': 'admin_test', 'password': 'adminpass', 'role': 'Admin'}, follow_redirects=True)
    client.post('/', data={'username': 'admin_test', 'password': 'adminpass'}, follow_redirects=True)
    r = client.get('/admin/students')
    text = r.get_data(as_text=True)
    admin_count = text.count('Student A') + text.count('Student B') + text.count('Student C')
    logging.info('admin sees count (expect 3): %s', admin_count)

    logging.info('Done')
