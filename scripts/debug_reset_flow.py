import sys, os
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app, db, User, generate_reset_token, verify_reset_token
from werkzeug.security import check_password_hash

with app.app_context():
    db.create_all()
    u = User.query.filter_by(username='fp_user').first()
    logging.info('Before: %s', u and u.password)
    token = generate_reset_token('fp_user')
    logging.info('Token generated: %s', token[:20])
    uname = verify_reset_token(token)
    logging.info('verify returned: %s', uname)
    # set new password
    if u:
        u.password = 'xxxx'
        db.session.commit()
        logging.info('After set raw: %s', u.password)
        logging.info('check raw newpass: %s', check_password_hash(u.password, 'newpass'))
        # now set proper hash
        from werkzeug.security import generate_password_hash
        u.password = generate_password_hash('newpass')
        db.session.commit()
        logging.info('After hash set: %s', check_password_hash(u.password, 'newpass'))
    logging.info('done')