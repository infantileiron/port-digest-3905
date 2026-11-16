import json,hashlib
from datetime import date
from src.utils.time import aware,SH
VERSION='planned-day-linear-quantile-v1'
def quantile(values,p):
 if not values:return None
 values=sorted(values);position=(len(values)-1)*p;lower=int(position);upper=min(lower+1,len(values)-1)
 return values[lower]+(values[upper]-values[lower])*(position-lower)
def row_day(r):
 # Purged rows have no timestamps left; their Shanghai plan day survives as statistical basis.
 if r.get('planned_day'):return r['planned_day']
 return aware(r['planned_at']).astimezone(SH).date().isoformat() if r.get('planned_at') else None
def row_delay(r):
 if r.get('purged'):return r.get('delay_minutes')
 if r.get('actual_at') is None:return None
 return max(0,(aware(r['actual_at'])-aware(r['planned_at'])).total_seconds()/60)
def public_row(r):
 # Payload rows must never carry shift identity of purged records.
 if r.get('purged'):return {'station':r.get('station'),'planned_day':r.get('planned_day'),'delay_minutes':r.get('delay_minutes'),'purged':True}
 return r
def summarize(day,station,selected,delays):
 late=sum(d>0 for d in delays)
 return dict(report_day=day,timezone='Asia/Shanghai',station=station,scheduled=len(selected),completed=len(delays),pending=len(selected)-len(delays),late=late,late_rate=late/len(delays) if delays else None,p50=quantile(delays,.5),p95=quantile(delays,.95),mean_delay=sum(delays)/len(delays) if delays else None,max_delay=max(delays) if delays else None)
def calculate(rows,report_day,station='全部'):
 day=date.fromisoformat(report_day);selected=[];delays=[]
 for r in rows:
  if row_day(r)!=report_day:continue
  if station!='全部' and r['station']!=station:continue
  selected.append(public_row(r));d=row_delay(r)
  if d is not None:delays.append(d)
 result=summarize(report_day,station,selected,delays)
 result.update(rows=selected,delays=delays,checksum=hashlib.sha256(json.dumps(selected,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),version=VERSION,method='按计划到发时间的上海自然日归档；延误=max(0,实际−计划)分钟；未到发不进入分位数/延误率分母。P50/P95为(n−1)p线性插值；无已到发样本为null，不伪造0。已清退记录仅保留无班次身份的计划日/港站/延误分钟，统计口径不变。')
 return result
def anonymize_payload(payload,report_day):
 # Strip shift code/times/note from a frozen receipt payload while keeping every delay value,
 # so historical digests still recompute the original late rate and exact quantiles.
 rows=payload.get('rows') or [];anon=[]
 for r in rows:
  if r.get('purged'):d=r.get('delay_minutes');day=r.get('planned_day') or report_day
  else:day=report_day;d=row_delay(r) if r.get('actual_at') is not None else None
  anon.append({'station':r.get('station'),'planned_day':day,'delay_minutes':d,'purged':True})
 kept=[a['delay_minutes'] for a in anon if a['delay_minutes'] is not None]
 out=dict(payload);out.update(rows=anon,delays=kept,checksum=hashlib.sha256(json.dumps(anon,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),purged=True,purged_note='本回执明细已按清退批次清除班次编号、时间与备注，保留无班次身份统计，可重算原延误率与精确分位数。')
 return out
