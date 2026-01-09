import sys, os
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app, db, User, Student

with app.app_context():
    db.create_all()
    # Cleanup
    User.query.filter(User.username.in_(['s_t1','s_t2','s_admin'])).delete(synchronize_session=False)
    Student.query.delete()
    db.session.commit()

    client = app.test_client()

    # Register and login t1
    client.post('/register', data={'username': 's_t1', 'password': 'pass', 'role': 'Teacher'}, follow_redirects=True)
    client.post('/', data={'username': 's_t1', 'password': 'pass'}, follow_redirects=True)
    client.post('/predict', data={'name': 'AS1', 'attendance': '90', 'activities': '80', 'quizzes': '80', 'performance_task': '80', 'exam': '80', 'section': 'Section A', 'subject': 'math'}, follow_redirects=True)

    client.get('/logout')

    # Register and login t2
    client.post('/register', data={'username': 's_t2', 'password': 'pass', 'role': 'Teacher'}, follow_redirects=True)
    client.post('/', data={'username': 's_t2', 'password': 'pass'}, follow_redirects=True)
    client.post('/predict', data={'name': 'BS1', 'attendance': '80', 'activities': '70', 'quizzes': '70', 'performance_task': '70', 'exam': '70', 'section': 'Section B', 'subject': 'science'}, follow_redirects=True)

    client.get('/logout')

    # Login as t1 and visit sections
    client.post('/', data={'username': 's_t1', 'password': 'pass'}, follow_redirects=True)
    r = client.get('/sections')
    text = r.get_data(as_text=True)
    sees_section_a = 'Section A' in text and 'AS1' in text and 'Section A <span' in text
    sees_section_b = 'Section B' in text and 'BS1' in text
    logging.info('t1 sees Section A (expect True): %s', sees_section_a)
    logging.info('t1 sees Section B (expect False): %s', sees_section_b)

    client.get('/logout')

    # Login as admin and verify sees both sections but cannot edit AS1
    client.post('/register', data={'username': 's_admin', 'password': 'pass', 'role': 'Admin'}, follow_redirects=True)
    client.post('/', data={'username': 's_admin', 'password': 'pass'}, follow_redirects=True)
    r_admin = client.get('/sections')
    admin_text = r_admin.get_data(as_text=True)
    admin_sees_both = 'Section A' in admin_text and 'Section B' in admin_text and 'Section A <span' in admin_text
    logging.info('Admin sees both (expect True): %s', admin_sees_both)

    # Attempt to edit AS1 as admin (should be allowed)
    as1 = Student.query.filter_by(name='AS1').first()
    r_edit_admin = client.get(f'/admin/students/edit/{as1.id}', follow_redirects=True)
    admin_can_edit = 'You can only edit students you added.' not in r_edit_admin.get_data(as_text=True) and ('name' in r_edit_admin.get_data(as_text=True) or 'Edit Student' in r_edit_admin.get_data(as_text=True))
    logging.info('Admin can edit of AS1 (expect False): %s', admin_can_edit)
    assert not admin_can_edit, 'Admin should NOT be able to edit students they did not add'

    # Now test bulk delete per section: login as t1 and delete their students in Section A
    client.get('/logout')
    client.post('/', data={'username': 's_t1', 'password': 'pass'}, follow_redirects=True)
    # t1 should have AS1 in Section A
    as1_before = Student.query.filter_by(name='AS1').first()
    assert as1_before is not None
    r_del = client.post('/sections/delete', data={'section': 'Section A'}, follow_redirects=True)
    after_text = r_del.get_data(as_text=True)
    logging.info('Bulk delete response contains success: %s', 'Deleted' in after_text)
    as1_after = Student.query.filter_by(name='AS1').first()
    bs1_after = Student.query.filter_by(name='BS1').first()
    logging.info('AS1 deleted (expect True): %s', as1_after is None)
    logging.info('BS1 remains (expect True): %s', bs1_after is not None)
    assert as1_after is None, 'AS1 should be deleted by its owner'
    assert bs1_after is not None, 'BS1 should not be deleted by t1'

    logging.info('Sections tests done')