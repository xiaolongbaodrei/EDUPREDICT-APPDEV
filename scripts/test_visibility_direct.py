import sys, os
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app, db, User, Student

with app.app_context():
    db.create_all()
    # Cleanup
    User.query.filter(User.username.in_(['t1','t2','admin_test'])).delete(synchronize_session=False)
    Student.query.delete()
    db.session.commit()

    # Create users
    t1 = User(username='t1', password='x', role='Teacher')
    t2 = User(username='t2', password='x', role='Teacher')
    admin = User(username='admin_test', password='x', role='Admin')
    db.session.add_all([t1,t2,admin])
    db.session.commit()

    # Create students
    s1 = Student(name='Student A', added_by='t1')
    s2 = Student(name='Student B', added_by='t1')
    s3 = Student(name='Student C', added_by='t2')
    db.session.add_all([s1,s2,s3])
    db.session.commit()

    logging.info('Total students (expect 3): %s', Student.query.count())
    logging.info("t1's students (expect 2): %s", Student.query.filter_by(added_by='t1').count())
    logging.info("t2's students (expect 1): %s", Student.query.filter_by(added_by='t2').count())

    logging.info('Direct DB test completed')
