import sqlite3, os
import logging
p = os.path.join(os.getcwd(),'database.db')
logging.info('DB exists: %s %s', os.path.exists(p), p)
if os.path.exists(p):
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info('user')")
    rows = cur.fetchall()
    logging.info('PRAGMA table_info output:')
    for r in rows:
        logging.info('%s', r)
    conn.close()
else:
    logging.warning('database.db not found')
