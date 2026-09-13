
from __future__ import annotations
import argparse, hashlib, json, math, random, statistics
from pathlib import Path
from submission.支撑材料.environment import LocalSimulator
from submission.支撑材料.field_policy import FieldPlanner

START, CASES = 8200200, 150
CONFIGS = {
    "refined": {},
    "refined+route_only": {"portfolio": True},
    "refined+premeasure_only": {"premeasure": True},
    "refined+negative_geometry_only": {"negative_updates": True},
    "refined+approach_clear_only": {"approach_clear": True},
    "route+premeasure": {"portfolio": True, "premeasure": True},
    "route+negative": {"portfolio": True, "negative_updates": True},
    "full_field": {"portfolio": True, "premeasure": True, "negative_updates": True, "approach_clear": True},
}

def metrics(env, result):
    pos=(0.0,0.0); radio=1; move=measure_t=0.0
    measures=switches=clears=failed=0; switch_t=success_clear_time=failed_clear_time=0.0
    for event in env.log:
        req,resp=event["request"],event["response"]
        if req["path"] not in ("/measure","/clear"): continue
        p=(req["position"]["x"],req["position"]["y"]); move += math.dist(pos,p); pos=p
        if req["path"]=="/measure":
            measures+=1; measure_t+=event.get("action_time_s",0.0)
            if radio!=req["channel"]: switches+=1; switch_t+=event.get("switch_time_s",0.0)
            radio=req["channel"]
        else:
            clears+=1
            if resp.get("clear_result")=="success": success_clear_time+=event.get("action_time_s",0.0)
            else: failed+=1; failed_clear_time+=event.get("action_time_s",0.0)
    order=[(e["request"]["path"],e["request"].get("channel"),e["request"].get("position")) for e in env.log if e["request"]["path"] in ("/measure","/clear")]
    order_hash=hashlib.sha256(json.dumps(order,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    s=env.summary()
    return {"seed":s["seed"],"problem":s["problem"],"scenario":s["scenario"],"error_mode":s["error_mode"],"T_s":s["virtual_time_s"],"N":s["n_sources"],"n_sources":s["n_sources"],"T_over_N_s":s["virtual_time_s"]/s["n_sources"],"movement_distance_m":move,"movement_time_s":move/5,"measure_time_s":measure_t,"measure_count":measures,"switch_time_s":switch_t,"switch_count":switches,"success_clear_time_s":success_clear_time,"failed_clear_time_s":failed_clear_time,"failed_clear_count":failed,"clear_attempt_count":clears,"route_replanning_count":sum(1 for e in env.log if e["request"]["path"]=="/clear" and e.get("distance_m",0)>0),"probes":result.get("zero_travel_probes",0),"negative_cuts":result.get("negative_cuts",0),"certificate":bool(result.get("certificate_complete")),"cleared_count":s["n_cleared"],"termination":result.get("termination") or result.get("terminal_reason"),"action_order_hash":order_hash}

def run(seed, config):
    
    
    settings = {"premeasure": False, "negative_updates": False,
                "portfolio": False, "approach_clear": False}
    env=LocalSimulator(seed,3,"smooth","random")
    planner=FieldPlanner(env,3,**(settings | config),probe_scale=0.22)
    result=planner.run()
    return metrics(env,result)

def bootstrap(diffs, seed=99173, reps=5000):
    rng=random.Random(seed); n=len(diffs); vals=[sum(diffs[rng.randrange(n)] for _ in range(n))/n for _ in range(reps)]; vals.sort(); return [vals[int(.025*reps)],vals[int(.975*reps)-1]]

def summary(rows, baseline):
    vals=[r["T_over_N_s"] for r in rows]; diffs=[a["T_over_N_s"]-b["T_over_N_s"] for a,b in zip(baseline,rows)]; sv=sorted(vals); n=len(vals); bh={r["seed"]:r["action_order_hash"] for r in baseline}
    return {"cases":n,"mean_T_over_N_s":statistics.mean(vals),"median_T_over_N_s":statistics.median(vals),"p90_T_over_N_s":sv[math.ceil(.9*n)-1],"worst_T_over_N_s":max(vals),"mean_saved_vs_refined_s":statistics.mean(diffs),"win_rate_vs_refined":sum(x>0 for x in diffs)/n,"paired_bootstrap_95pct_CI_s":bootstrap(diffs),"ordering_changes_vs_refined":sum(r["action_order_hash"]!=bh[r["seed"]] for r in rows),"hard_gates":{"all_certificate":all(r["certificate"] for r in rows),"all_sources_cleared":all(r["cleared_count"]==r["n_sources"] for r in rows),"p90_not_materially_worse":sv[math.ceil(.9*n)-1]<=sorted(x["T_over_N_s"] for x in baseline)[math.ceil(.9*n)-1]*1.05}}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--start",type=int,default=START); ap.add_argument("--cases",type=int,default=CASES); ap.add_argument("--output",type=Path,default=Path("results/audit_q3_ablation.json")); a=ap.parse_args()
    if a.start < 8200150: raise SystemExit("seed range overlaps reserved 8200000..8200149")
    if a.output.exists(): raise SystemExit(f"refusing to overwrite {a.output}")
    seeds=list(range(a.start,a.start+a.cases)); allrows={name:[{**run(seed,cfg),"configuration":name} for seed in seeds] for name,cfg in CONFIGS.items()}
    base=allrows["refined"]; summaries={k:summary(v,base) for k,v in allrows.items()}
    out={"evidence_type":"local_synthetic_standard_random_smooth_not_official","exploratory_seed_range":[a.start,seeds[-1]],"configuration_contract":CONFIGS,"world_metadata":{"problem":3,"scenario":"random","error_mode":"smooth","paired_identical":True},"hard_gate_policy":"certificate and all sources cleared required; p90 <= refined p90*1.05; no verification claim from proxy alone","summaries":summaries,"runs":[r for rows in allrows.values() for r in rows]}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(out,indent=2)+"\n"); print(json.dumps({"output":str(a.output),"seed_range":out["exploratory_seed_range"],"configs":len(CONFIGS),"rows":len(out["runs"])},sort_keys=True))
if __name__=="__main__": main()
