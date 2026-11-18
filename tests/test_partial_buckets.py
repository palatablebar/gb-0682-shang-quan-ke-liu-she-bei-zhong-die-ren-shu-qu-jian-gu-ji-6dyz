import itertools
import pytest
from app.workflow import run
from app.errors import DomainError

HEADER='id,bucket,version,kind,left,right,count,unit,note'
HOUR='2026-11-16T01:00:00Z'

def _row(i,kind,left,right,count):
    return f"r{i:03d},{HOUR},1,{kind},{left},{right},{count},人,t"

def build_csv(zones,pairs,shuffle=False,extra_rows=()):
    rows=[];i=1
    for z in sorted(zones):rows.append(_row(i,'zone',z,'',zones[z]));i+=1
    for k in sorted(pairs):
        a,b=k.split('|');rows.append(_row(i,'pair',a,b,pairs[k]));i+=1
    for kind,left,right,count in extra_rows:rows.append(_row(i,kind,left,right,count));i+=1
    if shuffle:rows=rows[::-1]
    return (HEADER+'\n'+'\n'.join(rows)+'\n').encode()

def brute_union(zones,pairs,triple=None):
    # Venn原子暴力枚举：x=AB-only y=AC-only z=BC-only t=三方，作为定界正确性的独立oracle。
    a,b,c=sorted(zones);A,B,C=zones[a],zones[b],zones[c]
    span=range(max(A,B,C)+1);found=[]
    for x,y,z,t in itertools.product(span,repeat=4):
        if min(A-(x+y+t),B-(x+z+t),C-(y+z+t))<0:continue
        if pairs.get('|'.join([a,b])) is not None and x+t!=pairs['|'.join([a,b])]:continue
        if pairs.get('|'.join([a,c])) is not None and y+t!=pairs['|'.join([a,c])]:continue
        if pairs.get('|'.join([b,c])) is not None and z+t!=pairs['|'.join([b,c])]:continue
        if triple is not None and t!=triple:continue
        found.append(A+B+C-(x+t)-(y+t)-(z+t)+t)
    if not found:return None
    return min(found),max(found)

ZONES={'A':12,'B':11,'C':9}

@pytest.mark.parametrize('missing',[['B|C'],['A|C','B|C'],['A|B','A|C','B|C']])
def test_partial_bounds_match_brute_force(missing):
    pairs={'A|B':4,'A|C':3,'B|C':2}
    for m in missing:del pairs[m]
    state=run(build_csv(ZONES,pairs))
    calc=state['calculations'][0]
    assert calc['status']=='PARTIAL' and calc['missing_pairs']==sorted(missing)
    assert (calc['lower'],calc['upper'])==brute_union(ZONES,pairs)

def test_missing_pair_keeps_bucket_and_marks_partial():
    state=run(build_csv(ZONES,{'A|B':4,'A|C':3}))
    assert len(state['calculations'])==1
    calc=state['calculations'][0]
    assert calc['status']=='PARTIAL' and calc['missing_pairs']==['B|C']
    # 缺BC：t取下界1时w=A容量仍不足，z必须补足1；z∈[1,6]，区间[19,25]，上界不被压低
    assert (calc['lower'],calc['upper'])==(19,25)
    assert state['business']['partial_buckets']==1 and state['business']['finalized'] is False

def test_missing_pair_is_not_treated_as_zero():
    # 把缺项当零会得到伪精确的[25,25]；正确口径必须保留下界并保留区间宽度
    state=run(build_csv(ZONES,{'A|B':4,'A|C':3}))
    calc=state['calculations'][0]
    assert calc['width']>0 and calc['upper']==25 and calc['lower']<25

def test_unobserved_pair_never_suppresses_upper():
    full=run(build_csv(ZONES,{'A|B':4,'A|C':3,'B|C':2}))['calculations'][0]
    partial=run(build_csv(ZONES,{'A|B':4,'A|C':3}))['calculations'][0]
    assert partial['upper']==full['upper'] and partial['lower']<=full['lower']

def test_observed_intersection_counted_once():
    # 两区域已知交集I：联合=A+B-I，而不是A+B
    state=run(build_csv({'A':100,'B':80},{'A|B':30}))
    calc=state['calculations'][0]
    assert (calc['lower'],calc['upper'])==(150,150)

def test_out_of_order_arrival_same_conclusion():
    pairs={'A|B':4,'A|C':3}
    ordered=run(build_csv(ZONES,pairs,shuffle=False))
    shuffled=run(build_csv(ZONES,pairs,shuffle=True))
    assert shuffled['calculations']==ordered['calculations']
    assert shuffled['business']==ordered['business']

def test_retry_same_batch_does_not_widen():
    payload=build_csv(ZONES,{'A|B':4,'A|C':3})
    first=run(payload);second=run(payload)
    assert first['run_id']==second['run_id']
    assert first['calculations']==second['calculations']
    assert all(a['width']==b['width'] for a,b in zip(first['calculations'],second['calculations']))

def test_backfill_rebounds_and_finalizes():
    before=run(build_csv(ZONES,{'A|B':4,'A|C':3}))
    assert before['business']['finalized'] is False
    after=run(build_csv(ZONES,{'A|B':4,'A|C':3,'B|C':2}))
    calc=after['calculations'][0]
    assert calc['status']=='COMPLETE' and calc['missing_pairs']==[]
    assert (calc['lower'],calc['upper'])==(23,25)
    assert after['business']['finalized'] is True and after['reconcile']['finalized'] is True

def test_reconcile_uses_same_caliber_as_calculate():
    state=run(build_csv(ZONES,{'A|B':4}))
    calc=state['calculations'][0]
    assert state['business']['total']==calc['lower']
    assert state['business']['upper_total']==calc['upper']
    assert state['reconcile']['partial_buckets']==1
    assert state['reconcile']['balanced'] is True and state['reconcile']['finalized'] is False

def test_partial_run_blocks_archive_export(client):
    r=client.post('/api/runs',json={'csv':build_csv(ZONES,{'A|B':4}).decode()})
    run_id=r.get_json()['run_id']
    blocked=client.get(f'/api/archive/{run_id}/export.csv')
    assert blocked.status_code==409 and blocked.get_json()['code']=='PARTIAL_RUN'
    ok=client.post('/api/runs',json={'csv':build_csv(ZONES,{'A|B':4,'A|C':3,'B|C':2}).decode()}).get_json()
    exported=client.get(f"/api/archive/{ok['run_id']}/export.csv")
    assert exported.status_code==200 and '运行清单' in exported.data.decode('utf-8-sig')

def test_contradiction_still_quarantined():
    state=run(build_csv({'A':100,'B':100,'C':100},{'A|B':80,'A|C':80,'B|C':0}))
    assert state['calculations']==[]
    assert any(q['code']=='CONSTRAINT' for q in state['quarantine'])

def test_triple_with_partial_pairs_matches_brute_force():
    pairs={'A|B':4,'A|C':3}  # 缺B|C，另给三方观测t=2
    csv=build_csv(ZONES,pairs,extra_rows=[('triple','ABC','',2)])
    state=run(csv)
    calc=state['calculations'][0]
    assert calc['status']=='PARTIAL'
    assert (calc['lower'],calc['upper'])==brute_union(ZONES,pairs,triple=2)
    assert calc['triple_lower']==calc['triple_upper']==2

def test_infeasible_triple_on_partial_bucket_rejected():
    csv=build_csv(ZONES,{'A|B':4},extra_rows=[('triple','ABC','',5)])  # t=5>AB=4
    state=run(csv)
    assert state['calculations']==[]
    assert any(q['code']=='CONSTRAINT' for q in state['quarantine'])

def test_no_pairs_at_all_bounds():
    state=run(build_csv(ZONES,{}))
    calc=state['calculations'][0]
    assert (calc['lower'],calc['upper'])==(12,32)==brute_union(ZONES,{})
    assert calc['triple_upper']==9

def test_mixed_buckets_day_summary_uses_same_caliber():
    # 两个小时桶：一个完整、一个缺口；日汇区间为分桶区间之和，口径与估界页一致
    h1='2026-11-16T01:00:00Z';h2='2026-11-16T02:00:00Z'
    lines=[HEADER]
    seq=[(h1,'zone','A','',12),(h1,'zone','B','',11),(h1,'zone','C','',9),
         (h1,'pair','A','B',4),(h1,'pair','A','C',3),(h1,'pair','B','C',2),
         (h2,'zone','A','',10),(h2,'zone','B','',8),(h2,'zone','C','',6),
         (h2,'pair','A','B',3),(h2,'pair','A','C',2)]
    for i,(bucket,kind,left,right,count) in enumerate(seq,1):
        lines.append(f"m{i:03d},{bucket},1,{kind},{left},{right},{count},人,t")
    state=run(('\n'.join(lines)+'\n').encode())
    assert state['business']['partial_buckets']==1 and state['business']['finalized'] is False
    assert state['business']['total']==sum(r['lower'] for r in state['calculations'])
    assert state['business']['upper_total']==sum(r['upper'] for r in state['calculations'])
    assert state['reconcile']['business']==state['business']
