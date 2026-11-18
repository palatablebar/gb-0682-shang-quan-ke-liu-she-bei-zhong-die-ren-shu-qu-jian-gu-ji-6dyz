from itertools import product
from app.errors import DomainError

# 裁决口径：未观测的两两交集是自由变量，不取零、不丢桶。
# 三区域按七个Venn原子建模：仅A(oA)、仅B(oB)、仅C(oC)、AB-only(x)、AC-only(y)、BC-only(z)、三方(t)。
# 联合人数 U = oA+oB+oC+x+y+z+t = A+B+C - x - y - z - 2t。
# 已观测交集把对应 pair-only 原子钉死(如AB=p => x=p-t)，只进入约束一次，不重复相加；
# 缺失交集对应的原子自由枚举，上界不会被未观测部分压低。
# 缺口桶的自由原子数量<=3、取值域为区域人数量级，全量扫描可行整数组合取极值，
# 结果只取决于观测集合：乱序到达与同批重试得到完全相同的区间。

def _key(a,b):
    return '|'.join(sorted([a,b]))

def _t_bounds(zones,pairs,triple):
    lo,hi=0,min(zones.values())
    for key,ij in pairs.items():
        a,b=key.split('|');hi=min(hi,ij)
        # Bonferroni: t>=I+J-区域人数，缺失的交集按自由变量取下界0处理（不把缺项当零定值）
        for other in zones:
            if other in (a,b):continue
            j=pairs.get(_key(a,other));k=pairs.get(_key(b,other))
            lo=max(lo,ij+(j or 0)-zones[a],ij+(k or 0)-zones[b])
    if triple is not None:lo,hi=max(lo,triple),min(hi,triple)
    if lo>hi:raise DomainError('CONSTRAINT','三方观测不存在可行人数')
    return lo,hi

def _three(zones,pairs,triple):
    a,b,c=sorted(zones);A,B,C=zones[a],zones[b],zones[c];S1=A+B+C
    names=[_key(a,b),_key(a,c),_key(b,c)]
    missing=[v for v in names if pairs.get(v) is None]
    tlo,thi=_t_bounds(zones,pairs,triple)
    lows,highs,t_seen=[],[],[]
    for t in range(tlo,thi+1):
        fixed={}
        bad=False
        for key,ij in pairs.items():
            fixed[tuple(key.split('|'))]=ij-t
            if ij-t<0:bad=True
        if bad:continue
        free=[tuple(k.split('|')) for k in missing]
        caps={atom:min(zones[r] for r in atom) for atom in free}
        found=False
        for values in product(*[range(caps[atom]+1) for atom in free]):
            assign=dict(zip(free,values))
            x=fixed.get((a,b),assign.get((a,b),0));y=fixed.get((a,c),assign.get((a,c),0));z=fixed.get((b,c),assign.get((b,c),0))
            if min(A-(x+y+t),B-(x+z+t),C-(y+z+t))<0:continue
            lows.append(S1-x-y-z-2*t);highs.append(S1-x-y-z-2*t);found=True
        if found:t_seen.append(t)
    if not lows:raise DomainError('CONSTRAINT','部分观测不存在可行人数')
    return min(lows),max(highs),min(t_seen),max(t_seen),missing

def bounds(model):
    low,high,tlo,thi,_=_bounds(model)
    return low,high,tlo,thi

def _bounds(model):
    zones=model['zones'];keys=sorted(zones);pairs=model['pairs'];values=[zones[k] for k in keys]
    missing=model.get('missing_pairs',[])
    if len(keys)==1:return values[0],values[0],0,0,missing
    if len(keys)==2:
        common=pairs.get(_key(*keys))
        if common is not None:return sum(values)-common,sum(values)-common,common,common,missing
        return max(values),sum(values),0,min(values),missing
    return _three(zones,pairs,model.get('triple'))

def apply(state):
    results=[];bad=set();partial=0
    for item in state['models']:
        try:
            low,high,tlo,thi,missing=_bounds(item['model'])
            if missing:partial+=1
            results.append({'id':item['bucket'],'line':item['line'],'lower':low,'upper':high,'width':high-low,
                'triple_lower':tlo,'triple_upper':thi,'status':'PARTIAL' if missing else 'COMPLETE','missing_pairs':missing,
                'code':'EXACT' if low==high else 'INTERVAL'})
        except DomainError as e:
            bad.add(item['bucket'])
            for r in state['rows']:
                if r['bucket']==item['bucket']:state['quarantine'].append({'line':r['_line'],'id':r['id'],'code':e.code,'raw':r['_raw']})
    state['rows']=[r for r in state['rows'] if r['bucket'] not in bad]
    state['calculations']=results
    state['business']={'total':sum(r['lower'] for r in results),'upper_total':sum(r['upper'] for r in results),
        'buckets':len(results),'partial_buckets':partial,
        'finalized':bool(results) and partial==0,'unit':'客次'}
    return state
