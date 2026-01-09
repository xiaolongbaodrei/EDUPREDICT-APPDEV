import sys, os
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app, db, User, Student

with app.app_context():
    db.create_all()
    # Clean up
    User.query.filter(User.username.in_(['ti','t2','admin_test2'])).delete(synchronize_session=False)
    Student.query.delete()
    db.session.commit()

    client = app.test_client()

    # Register and login t1
    client.post('/register', data={'username': 'ti', 'password': 'pass', 'role': 'Teacher'}, follow_redirects=True)
    client.post('/', data={'username': 'ti', 'password': 'pass'}, follow_redirects=True)

    # Add student by ti, specify section A
    client.post('/predict', data={'name': 'S1', 'attendance': '90', 'activities': '80', 'quizzes': '80', 'performance_task': '80', 'exam': '80', 'section': 'Section A'}, follow_redirects=True)

    client.get('/logout')

    # Register and login t2
    client.post('/register', data={'username': 't2', 'password': 'pass', 'role': 'Teacher'}, follow_redirects=True)
    client.post('/', data={'username': 't2', 'password': 'pass'}, follow_redirects=True)
    client.post('/predict', data={'name': 'S2', 'attendance': '80', 'activities': '70', 'quizzes': '70', 'performance_task': '70', 'exam': '70', 'section': 'Section B'}, follow_redirects=True)
    client.get('/logout')

    # Login as ti and check manage_students
    client.post('/', data={'username': 'ti', 'password': 'pass'}, follow_redirects=True)
    r = client.get('/admin/students')
    text = r.get_data(as_text=True)
    s1_visible = 'S1' in text
    s2_visible = 'S2' in text
    logging.info('ti sees S1 (expect True): %s', s1_visible)
    logging.info('ti sees S2 (expect False): %s', s2_visible)

    # Attempt to edit S2 as ti (should be denied/redirect)
    # Find S2 id
    s2 = Student.query.filter_by(name='S2').first()
    r_edit = client.get(f'/admin/students/edit/{s2.id}', follow_redirects=True)
    edit_text = r_edit.get_data(as_text=True)
    denied_edit = 'You can only edit students you added.' in edit_text
    logging.info('ti denied edit of S2 (expect True): %s', denied_edit)

    # Attempt to delete S2 as ti (should be denied)
    r_delete = client.post(f'/admin/students/delete/{s2.id}', follow_redirects=True)
    delete_text = r_delete.get_data(as_text=True)
    denied_delete = 'You can only delete students you added.' in delete_text
    logging.info('ti denied delete of S2 (expect True): %s', denied_delete)

    # Check that section was saved for S1
    s1 = Student.query.filter_by(name='S1').first()
    logging.info('S1 section (expect "Section A"): %s', s1.section)

    # Login as Admin and verify sees both but cannot edit others' students
    client.get('/logout')
    client.post('/register', data={'username': 'admin_test2', 'password': 'pass', 'role': 'Admin'}, follow_redirects=True)
    client.post('/', data={'username': 'admin_test2', 'password': 'pass'}, follow_redirects=True)
    r_admin = client.get('/admin/students')
    admin_text = r_admin.get_data(as_text=True)
    admin_sees_both = 'S1' in admin_text and 'S2' in admin_text
    logging.info('Admin sees both (expect True): %s', admin_sees_both)

    # Admin should be allowed to edit S1 (even if not the owner)
    r_edit_admin = client.get(f'/admin/students/edit/{s1.id}', follow_redirects=True)
    admin_edit_text = r_edit_admin.get_data(as_text=True)
    admin_can_edit = 'You can only edit students you added.' not in admin_edit_text and ('name' in admin_edit_text or 'Edit Student' in admin_edit_text)
    logging.info('Admin can edit S1 (expect False): %s', admin_can_edit)
    assert not admin_can_edit, 'Admin should NOT be able to edit students they did not add'

    logging.info('Integration tests done')
