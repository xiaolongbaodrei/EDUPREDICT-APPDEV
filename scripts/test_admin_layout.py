import sys, os
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app, db, User, Student

with app.app_context():
    db.create_all()
    # Cleanup
    User.query.filter(User.username.in_(['layout_admin'])).delete(synchronize_session=False)
    Student.query.delete()
    db.session.commit()

    client = app.test_client()

    # Create admin and a sample student
    client.post('/register', data={'username': 'layout_admin', 'password': 'pass', 'role': 'Admin'}, follow_redirects=True)
    client.post('/', data={'username': 'layout_admin', 'password': 'pass'}, follow_redirects=True)

    client.post('/predict', data={'name': 'Ltest', 'attendance': '90', 'activities': '85', 'quizzes': '80', 'performance_task': '88', 'exam': '90', 'section': 'Sec1', 'subject': 'math'}, follow_redirects=True)

    r = client.get('/admin/students')
    text = r.get_data(as_text=True)

    headers_ok = 'ID' in text and 'Name' in text and 'Section' in text and 'Subject' in text and 'Attendance' in text and 'Activities' in text and 'Quizzes' in text and 'WW' in text and 'PT' in text and 'Exam' in text and 'Final Grade' in text and 'Risk' in text and 'Added by' in text
    actions_present = 'Actions' in text
    edit_present = 'Edit' in text and 'Delete' in text

    delete_confirm_attr = 'data-confirm="Delete student' in text

    # Now visit manage users and check role change confirm attr
    r2 = client.get('/admin/users')
    users_text = r2.get_data(as_text=True)
    role_confirm_attr = 'data-confirm="Change role' in users_text

    print('Headers present:', headers_ok)
    print('Actions column present (expect True):', actions_present)
    print('Edit/Delete present (expect True):', edit_present)
    print('Delete form has data-confirm (expect True):', delete_confirm_attr)
    print('Role change form has data-confirm (expect True):', role_confirm_attr)

    assert headers_ok, 'Expected headers are missing from admin students table'
    assert actions_present, 'Actions column missing'
    assert edit_present, 'Edit/Delete buttons missing'
    assert delete_confirm_attr, 'Delete student form is missing data-confirm attribute'
    assert role_confirm_attr, 'Role change form is missing data-confirm attribute'

    print('Admin layout test passed')