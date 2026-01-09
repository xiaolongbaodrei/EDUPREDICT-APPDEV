import os, tarfile
from datetime import datetime

confdir = os.path.join('instance','confirm')
if not os.path.exists(confdir):
    print('No confirm dir')
    raise SystemExit(0)
files = [os.path.join(confdir,f) for f in os.listdir(confdir) if f.endswith('.json')]
if not files:
    print('No tokens to archive')
    raise SystemExit(0)

bakdir = os.path.join('instance','backups')
os.makedirs(bakdir, exist_ok=True)
archive_name = os.path.join(bakdir, 'confirm-archive-' + datetime.now().strftime('%Y%m%d%H%M%S') + '.tar.gz')
print('Archiving', len(files), 'confirm tokens to', archive_name)
with tarfile.open(archive_name, 'w:gz') as tar:
    for f in files:
        tar.add(f, arcname=os.path.basename(f))

# remove originals
for f in files:
    try:
        os.remove(f)
    except Exception as e:
        print('Failed to remove', f, e)

print('Done')