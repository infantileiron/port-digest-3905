import os,logging
from contextlib import asynccontextmanager
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from src.config.database import Base,engine,Session
from src.models import entities
from src.routes.api import router
from src.middlewares.request import RequestId,SecurityHeaders
def ensure_schema():
 # Idempotent upgrades for databases created before purge batches existed; fresh databases get everything from create_all.
 with engine.begin() as c:
  c.execute(text('ALTER TABLE arrivals ADD COLUMN IF NOT EXISTS planned_day VARCHAR(10)'))
  c.execute(text('ALTER TABLE arrivals ADD COLUMN IF NOT EXISTS delay_minutes DOUBLE PRECISION'))
  c.execute(text('ALTER TABLE arrivals ADD COLUMN IF NOT EXISTS purged BOOLEAN DEFAULT FALSE'))
  c.execute(text('ALTER TABLE receipts ADD COLUMN IF NOT EXISTS purged BOOLEAN DEFAULT FALSE'))
 from src.models.entities import Arrival,Receipt
 from src.utils.time import aware,SH
 with Session() as s:
  for r in s.query(Arrival).filter(Arrival.planned_day.is_(None),Arrival.planned_at.isnot(None)):
   r.planned_day=aware(r.planned_at).astimezone(SH).date().isoformat()
  s.query(Arrival).filter(Arrival.purged.is_(None)).update({Arrival.purged:False})
  s.query(Receipt).filter(Receipt.purged.is_(None)).update({Receipt.purged:False})
  s.commit()
@asynccontextmanager
async def lifespan(app):
 Base.metadata.create_all(engine)
 ensure_schema()
 if os.getenv('SEED_DEMO')=='true':
  try:
   from scripts.seed_demo import seed
   seed()
  except Exception:logging.exception('seed failed')
 yield
app=FastAPI(title='港站晨报定时分发',lifespan=lifespan)
app.add_middleware(RequestId);app.add_middleware(SecurityHeaders)
app.include_router(router)
@app.get('/health')
def health():
 from sqlalchemy import text
 import redis
 with engine.connect() as c:c.execute(text('SELECT 1'))
 redis.Redis.from_url(os.environ['REDIS_URL']).ping()
 return {'status':'ok'}
@app.exception_handler(Exception)
async def errors(request:Request,exc:Exception):
 logging.exception('request failed');return JSONResponse(status_code=500,content={'detail':'服务暂时异常，请稍后重试'})
