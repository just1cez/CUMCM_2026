"""Deterministic exhaustive audit of open-route dispatch proxies.

Synthetic evidence only: this script never starts the official simulator and does not
read or alter historical result files. Run from b_solution: python audit/route_exact_audit.py
"""
from __future__ import annotations
import json, math, random, itertools, sys
from pathlib import Path
from statistics import mean
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from route_portfolio import (_control_route, _cost, _improve,
    _cheapest_route, _nearest_route, choose_portfolio_task)
from joint_dispatch_candidate import choose_task

OUT = Path(__file__).resolve().parents[1] / "results" / "audit_route_exact.json"
SEED_RANGE = (8200150, 8200199)  # outside reserved 8200000..8200149

def instance(origin, targets, anchors, weight):
    tasks=[("target",k) for k in sorted(targets)]+[("anchor",k) for k in sorted(anchors)]
    pts=[targets[k][0] for _,k in tasks[:len(targets)]] + [anchors[k] for _,k in tasks[len(targets):]]
    # above task order is targets then anchors by construction
    radii=[targets[k][1] for k in sorted(targets)]+[0.0 for _ in anchors]
    o=[math.dist(origin,p) for p in pts]
    e=[[math.dist(a,b) for b in pts] for a in pts]
    pen=[weight*r for r in radii]
    return tasks,o,e,pen

def exact(o,e,p):
    best=None; route_count=0
    for r in itertools.permutations(range(len(o))):
        c=o[r[0]]+p[r[0]]+sum(e[a][b] for a,b in zip(r,r[1:]))
        route_count+=1
        if best is None or (c, r)<(best[0],best[1]): best=(c,r)
    return list(best[1]),best[0],route_count

def ils(seed,o,e,p):
    # deterministic iterated local search: exhaustive neighborhood perturbations,
    # then the same strict best-improvement kernel used by portfolio.
    best,_=_improve(list(seed),o,e,p)
    bestc=_cost(best,o,e,p)
    for cut in range(1,len(seed)):
        q=list(best); x=q.pop(cut); q.insert((cut*3+1)%len(q),x)
        q,c=_improve(q,o,e,p)
        if c<bestc: best,bestc=q,c
    return best,bestc

def evaluate(name, origin, targets, anchors, weight, source):
    tasks,o,e,p=instance(origin,targets,anchors,weight); n=len(tasks)
    opt,oc,rc=exact(o,e,p)
    control=_control_route(o,e,p); cr=_cost(control,o,e,p)
    starts=sorted(range(n),key=lambda i:(o[i]+p[i],i))[:2]
    candidates=[("portfolio", _cheapest_route(o,e,p)), ("nn0",_nearest_route(starts[0],e))]
    if len(starts)>1: candidates.append(("nn1",_nearest_route(starts[1],e)))
    routes={"exact":(opt,oc),"control":(control,cr)}
    for label,s in candidates:
        r,c=_improve(s,o,e,p); routes[label]=(r,c)
    routes["ils"]=ils(control,o,e,p)
    # local-world T/N: paired deterministic worlds differ only in target miss radius;
    # T is actual open travel, N is weighted unresolved exposure after the route.
    rows=[]
    for label,(r,c) in routes.items():
        travel=o[r[0]]+sum(e[a][b] for a,b in zip(r,r[1:]))
        nmiss=sum((p[i] > 0 and p[i] > weight*0.5) for i in r) # transparent local-world proxy
        rows.append({"method":label,"route":[tasks[i] for i in r],"J":c,
          "T":travel,"N":int(nmiss),"gap_abs":c-oc,"gap_rel":(c/oc-1 if oc else 0),
          "first_hop":tasks[r[0]]})
    rev_targets=dict(reversed(list(targets.items())))
    rev_anchors=dict(reversed(list(anchors.items())))
    invariant=(choose_portfolio_task(origin,anchors,targets,weight)==
               choose_portfolio_task(origin,rev_anchors,rev_targets,weight))
    return {"case":name,"evidence":source,"n":n,"weight":weight,"origin":origin,
      "insertion_order_invariant":invariant,
      "tasks": [{"kind":k,"key":i,"point":(targets[i][0] if k=="target" else anchors[i]),
                  "radius":(targets[i][1] if k=="target" else 0)} for k,i in tasks],
      "exhaustive":True,"permutations":rc,"optimum_J":oc,"routes":rows}

def main():
    cases=[]
    crafted=[
      ("mixed",[(0,0),(3,0),(0,4)],[(3,4)], [2,0,5],1),
      ("duplicates",[(0,0),(0,0),(4,0)],[(0,0),(4,0)], [0,4,1],4),
      ("ties",[(1,0),(-1,0)],[(0,1),(0,-1)], [1,1],0),
      ("risk0",[(2,0),(8,0)],[(4,2)], [0,4],0),
      ("risk1",[(2,0),(8,0)],[(4,2)], [0,4],1),
      ("risk4",[(2,0),(8,0)],[(4,2)], [0,4],4),
    ]
    for name,pts,aps,rs,w in crafted:
      cases.append(evaluate(name,(0,0),{i:(p,rs[i]) for i,p in enumerate(pts)},
        {i:p for i,p in enumerate(aps)},w,"crafted synthetic"))
    rng=random.Random(8200150)
    for j in range(50):
      nt=2+(j%3); na=1+((j//3)%3); pts=[(rng.randrange(-10,11),rng.randrange(-10,11)) for _ in range(nt)]
      aps=[(rng.randrange(-10,11),rng.randrange(-10,11)) for _ in range(na)]
      rs=[rng.choice([0,1,4]) for _ in range(nt)]; w=[0,1,4][j%3]
      cases.append(evaluate(f"random_{j:02d}",(rng.randrange(-3,4),rng.randrange(-3,4)),
        {i:(p,rs[i]) for i,p in enumerate(pts)},{i:p for i,p in enumerate(aps)},w,"bounded random synthetic"))
    # rank/discordance summaries against exact J and local T/N (all methods/cases).
    gaps=[r["gap_abs"] for c in cases for r in c["routes"] if r["method"]!="exact"]
    lower_higher=[]
    for c in cases:
      rr=c["routes"]
      for a,b in itertools.permutations(rr,2):
        if a["J"]<b["J"] and (a["T"],a["N"])>(b["T"],b["N"]): lower_higher.append((c["case"],a["method"],b["method"]))
    jt_discord=tn_discord=pairs=0
    for c in cases:
      for a,b in itertools.combinations(c["routes"],2):
        pairs += 1
        if (a["J"]-b["J"])*(a["T"]-b["T"]) < 0: jt_discord += 1
        if (a["J"]-b["J"])*(a["N"]-b["N"]) < 0: tn_discord += 1
    result={"evidence_type":"synthetic audit only; no official logs and no simulator",
      "configuration":{"objective":"origin + consecutive open edges + weight*first target radius","no_return_edge":True,
        "seed_range":list(SEED_RANGE),"random_cases":50,"crafted_cases":6},
      "hard_gates":{"exhaustive_n_le_8":all(c["n"]<=8 and c["exhaustive"] for c in cases),
        "insertion_order_invariant":all(c["insertion_order_invariant"] for c in cases),
        "official_simulator_started":False,"reserved_seeds_consumed":False},
      "aggregate":{"cases":len(cases),"nonexact_route_rows":sum(len(c["routes"])-1 for c in cases),
        "max_abs_gap":max(gaps),"max_relative_gap":max(r["gap_rel"] for c in cases for r in c["routes"]),
        "lower_J_higher_TN_count":len(lower_higher),"lower_J_higher_TN_examples":lower_higher[:20],
        "first_hop_disagreements":sum(len({r["first_hop"] for r in c["routes"]})>1 for c in cases),
        "J_vs_T_pair_discordance":jt_discord,"J_vs_N_pair_discordance":tn_discord,"rank_pairs":pairs},
      "cases":cases}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"output":str(OUT),"cases":len(cases),"permutation_proof":sum(c["permutations"] for c in cases),"hard_gates":result["hard_gates"]},indent=2))
if __name__=="__main__": main()
