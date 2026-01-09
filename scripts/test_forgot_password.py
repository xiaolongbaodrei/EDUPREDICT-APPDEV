import sys, os
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app, db, User, Student

with app.app_context():
    db.create_all()
    # Cleanup
    User.query.filter(User.username.in_(['fp_user'])).delete(synchronize_session=False)
    db.session.commit()

    client = app.test_client()

    # Register user
    client.post('/register', data={'username': 'fp_user', 'password': 'oldpass', 'role': 'Teacher'}, follow_redirects=True)

    # Request reset
    r = client.post('/forgot', data={'username': 'fp_user'}, follow_redirects=True)
    text = r.get_data(as_text=True)
    # Extract reset link from the page by finding the /reset/ anchor
    start = text.find('/reset/')
    link = None
    if start != -1:
        end = text.find('"', start)
        link = text[start:end]

    logging.info('Found reset link: %s', bool(link))

    assert link is not None, 'Reset link not shown in response'

    # Visit link and set new password (use path)
    path = link
    logging.info('Reset path: %s', path)
    r2 = client.get(path)
    r3 = client.post(path, data={'password': 'newpass', 'confirm': 'newpass'}, follow_redirects=True)
    logging.info('Reset POST response snippet: %s', r3.get_data(as_text=True)[:400])

    # Ensure logged-out, then attempt login with new password
    client.get('/logout', follow_redirects=True)

    # Check DB: verify password hash was updated
    from werkzeug.security import check_password_hash
    user = User.query.filter_by(username='fp_user').first()
    logging.info('DB pw hash set: %s', user and check_password_hash(user.password, 'newpass'))

    r4 = client.post('/', data={'username': 'fp_user', 'password': 'newpass'}, follow_redirects=True)
    text4 = r4.get_data(as_text=True)
    logging.info('Login POST response path: %s', r4.request.path)
    logging.info('Login POST status: %s', r4.status_code)
    logging.info('Login POST response snippet: %s', text4[:200])
    login_ok = 'fp_user' in text4 or '/dashboard' in r4.request.path or 'Dashboard' in text4
    logging.info('Login with new password successful (expect True): %s', login_ok)

    assert login_ok, 'Login with new password failed'

    logging.info('Forgot password test done')