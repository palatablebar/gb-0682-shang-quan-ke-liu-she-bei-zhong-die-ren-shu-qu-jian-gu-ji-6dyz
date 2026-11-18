import random
from app.workflow import run
from tests.test_partial_buckets import build_csv,brute_union

def _random_zones(rng):
    a=rng.randint(4,14);b=rng.randint(4,14);c=rng.randint(4,14)
    return {'A':a,'B':b,'C':c}

def _feasible_pairs(zones,rng):
    a,b,c=sorted(zones);pairs={}
    ab=rng.randint(0,min(zones[a],zones[b]));ac=rng.randint(0,min(zones[a],zones[c]));bc=rng.randint(0,min(zones[b],zones[c]))
    return {'A|B':ab,'A|C':ac,'B|C':bc}

def test_random_partial_bounds_against_brute_force():
    rng=random.Random(20261118)
    pair_sets=[(),('A|B',),('A|C',),('B|C',),('A|B','A|C'),('A|B','B|C'),('A|C','B|C'),
        ('A|B','A|C','B|C')]
    checked=0
    for _ in range(120):
        zones=_random_zones(rng);full=_feasible_pairs(zones,rng)
        keep=pair_sets[rng.randrange(len(pair_sets))]
        pairs={k:full[k] for k in keep}
        state=run(build_csv(zones,pairs))
        want=brute_union(zones,pairs)
        if want is None:
            # 随机交集可能联合不相容：实现必须与暴力枚举一致判无解并隔离，而不是伪造区间
            assert state['calculations']==[] and any(q['code']=='CONSTRAINT' for q in state['quarantine'])
            checked+=1;continue
        calc=state['calculations'][0]
        got=(calc['lower'],calc['upper'])
        assert got==want,(zones,pairs,got,want)
        if keep==pair_sets[-1]:assert calc['status']=='COMPLETE'
        else:assert calc['status']=='PARTIAL'
        checked+=1
    assert checked==120

def test_random_triple_partial_against_brute_force():
    rng=random.Random(4242)
    choices=[('A|B',),('A|C',),('B|C',),('A|B','A|C')]
    for _ in range(60):
        zones=_random_zones(rng);full=_feasible_pairs(zones,rng)
        keep=rng.choice(choices)
        pairs={k:full[k] for k in keep}
        t0=rng.randint(0,min(pairs.values()))
        state=run(build_csv(zones,pairs,extra_rows=[('triple','ABC','',t0)]))
        want=brute_union(zones,pairs,triple=t0)
        if want is None:
            assert state['calculations']==[] and any(q['code']=='CONSTRAINT' for q in state['quarantine'])
        else:
            got=(state['calculations'][0]['lower'],state['calculations'][0]['upper'])
            assert got==want,(zones,pairs,t0,got,want)
