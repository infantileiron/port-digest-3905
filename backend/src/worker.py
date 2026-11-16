import os,time,logging
from pathlib import Path
import redis
from redis.exceptions import LockError
from src.config.database import Session
from src.services.scheduler import run_due
from src.services.purge import run_due_purges
from src.utils.time import now_utc
r=redis.Redis.from_url(os.environ['REDIS_URL'])
while True:
 Path('/tmp/heartbeat').touch()
 try:
  with r.lock('port-digest:scheduler',timeout=20,blocking_timeout=0):
   with Session() as s:
    now=now_utc();run_due(s,now);run_due_purges(s,now)
 except LockError:pass
 except Exception:logging.exception('scheduler tick failed')
 time.sleep(1)
