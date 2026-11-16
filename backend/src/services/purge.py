import json,logging,os
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select,func
from src.models.entities import Arrival,Receipt,PurgeBatch,Audit
from src.services.digest import anonymize_payload
from src.utils.time import aware,SH
ARTIFACTS=Path(os.environ.get('ARTIFACTS_DIR','/artifacts'))
def sealed_cutoff(s):
 # Accepting a batch immediately seals plan days before its cutoff; the seal is permanent.
 return s.query(func.max(PurgeBatch.cutoff_day)).scalar()
def check_arrival_writable(s,planned_at,existing=None):
 cut=sealed_cutoff(s)
 if not cut:return
 new_day=aware(planned_at).astimezone(SH).date().isoformat()
 if new_day<cut:raise HTTPException(409,'计划日 '+new_day+' 早于清退截止日 '+cut+'，已封存，禁止补录或改日写入')
 if existing is not None:
  if existing.purged:raise HTTPException(409,'该记录已清退，仅保留无班次身份统计，禁止修订')
  old_day=existing.planned_day or (aware(existing.planned_at).astimezone(SH).date().isoformat() if existing.planned_at else None)
  if old_day and old_day<cut and old_day!=new_day:raise HTTPException(409,'该记录计划日 '+old_day+' 已封存，禁止改日写入')
def counts(s,batch):
 cut=batch.cutoff_day
 a_total=s.query(Arrival).filter(Arrival.planned_day<cut).count()
 a_cleared=s.query(Arrival).filter(Arrival.planned_day<cut,Arrival.purged.is_(True)).count()
 r_total=s.query(Receipt).filter(Receipt.report_day<cut).count()
 r_cleared=s.query(Receipt).filter(Receipt.report_day<cut,Receipt.purged.is_(True)).count()
 f_total=f_cleared=0
 for rid, in s.query(Receipt.id).filter(Receipt.report_day<cut):
  p=ARTIFACTS/(str(rid)+'.json')
  if not p.exists():continue
  f_total+=1
  try:
   if json.loads(p.read_text()).get('purged'):f_cleared+=1
  except Exception:pass
 def area(total,cleared):return {'total':total,'cleared':cleared,'pending':total-cleared}
 return {'arrivals':area(a_total,a_cleared),'receipts':area(r_total,r_cleared),'artifacts':area(f_total,f_cleared)}
def _anonymize_arrivals(s,cut):
 rows=s.query(Arrival).filter(Arrival.planned_day<cut,Arrival.purged.is_(False)).all()
 for r in rows:
  delay=None
  if r.actual_at is not None:delay=max(0,(aware(r.actual_at)-aware(r.planned_at)).total_seconds()/60)
  r.planned_day=r.planned_day or aware(r.planned_at).astimezone(SH).date().isoformat()
  r.delay_minutes=delay;r.code='PURGED-'+str(r.id);r.planned_at=None;r.actual_at=None;r.note='';r.purged=True
 s.commit()
 return len(rows)
def _anonymize_receipts(s,cut):
 n=0
 for r in s.query(Receipt).filter(Receipt.report_day<cut,Receipt.purged.is_(False)):
  r.payload=anonymize_payload(r.payload or {},r.report_day);r.purged=True;n+=1
 s.commit()
 return n
def _clear_artifacts(s,cut):
 n=0
 for rid, in s.query(Receipt.id).filter(Receipt.report_day<cut):
  p=ARTIFACTS/(str(rid)+'.json')
  if not p.exists():continue
  try:
   if json.loads(p.read_text()).get('purged'):continue
  except Exception:pass
  payload=s.get(Receipt,rid).payload
  tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2));os.replace(tmp,p);n+=1
 return n
def execute(s,batch,now):
 # Every step is idempotent and commits separately, so an interrupted batch resumes safely and retries never double-count.
 if batch.state=='pending':
  batch.state='running';batch.started_at=now.isoformat()
  s.add(Audit(actor='purge',action='清退批次开始执行 #'+str(batch.id)+' 截止 '+batch.cutoff_day,created=now.isoformat()));s.commit()
 cut=batch.cutoff_day
 _anonymize_arrivals(s,cut)
 _anonymize_receipts(s,cut)
 _clear_artifacts(s,cut)
 batch.state='completed';batch.finished_at=now.isoformat()
 s.add(Audit(actor='purge',action='清退批次完成 #'+str(batch.id)+' 截止 '+cut,created=now.isoformat()));s.commit()
def run_due_purges(s,now):
 batches=s.scalars(select(PurgeBatch).where(PurgeBatch.state.in_(('pending','running'))).with_for_update(skip_locked=True)).all()
 for b in batches:
  try:execute(s,b,now)
  except Exception:s.rollback();logging.exception('清退批次 %s 执行中断，下一周期自动恢复',b.id)
 return [b.id for b in batches]
