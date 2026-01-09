import os, tarfile
from datetime import datetime

scripts = ['scripts/archived', 'scripts/debug_reset_flow.py', 'scripts/inspect_db.py']
exists = [p for p in scripts if os.path.exists(p)]
if not exists:
    print('No debug scripts found to archive')
    raise SystemExit(0)

bakdir = os.path.join('instance','backups')
os.makedirs(bakdir, exist_ok=True)
archive_name = os.path.join(bakdir, 'debug-scripts-' + datetime.now().strftime('%Y%m%d%H%M%S') + '.tar.gz')
print('Archiving debug scripts to', archive_name)
with tarfile.open(archive_name, 'w:gz') as tar:
    for p in exists:
        tar.add(p, arcname=os.path.basename(p))

# remove originals (if directories, remove tree)
import shutil
for p in exists:
    try:
        if os.path.isdir(p):
            shutil.rmtree(p)
        else:
            os.remove(p)
    except Exception as e:
        print('Failed to remove', p, e)

print('Done')