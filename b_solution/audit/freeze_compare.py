"""Locked final paired comparison; do not retune after execution."""
from __future__ import annotations
import json, math, random, statistics
from pathlib import Path
from field_study import run_field

START, COUNT = 8300000, 1000
CONFIGS = {
    3: {"refined": None, "candidate": {"premeasure": True, "negative_updates": True, "portfolio": True, "approach_clear": True}},
    4: {"refined": None, "candidate": {"premeasure": True, "negative_updates": False, "portfolio": True, "approach_clear": False}},
}
OUT = Path(__file__).resolve().parents[1] / "results" / "audit_freeze_compare.json"

def boot(xs, seed=190912, reps=5000):
    r=random.Random(seed); n=len(xs); z=[]
    for _ in range(reps): z.append(sum(xs[r.randrange(n)] for _ in range(n))/n)
    z.sort(); return [z[int(.025*reps)], z[int(.975*reps)-1]]

def stats(control, candidate):
    d=[a["average_time_s"]-b["average_time_s"] for a,b in zip(control,candidate)]
    cv=[a["average_time_s"] for a in control]; nv=[a["average_time_s"] for a in candidate]
    def q(v,p): return sorted(v)[math.ceil(p*len(v))-1]
    return {"cases":len(d),"mean_saved_s":statistics.mean(d),"median_saved_s":statistics.median(d),"win_rate":sum(x>0 for x in d)/len(d),"paired_bootstrap_95pct_CI_s":boot(d),"control_mean":statistics.mean(cv),"candidate_mean":statistics.mean(nv),"control_median":statistics.median(cv),"candidate_median":statistics.median(nv),"control_p90":q(cv,.9),"candidate_p90":q(nv,.9),"control_worst":max(cv),"candidate_worst":max(nv),"all_clear_control":all(x["fraction_cleared"]==1 for x in control),"all_clear_candidate":all(x["fraction_cleared"]==1 for x in candidate),"all_certificate_control":all(x["certificate_complete"] for x in control),"all_certificate_candidate":all(x["certificate_complete"] for x in candidate)}

def main():
    rows={}
    for p, configs in CONFIGS.items():
        groups={}
        for name,cfg in configs.items():
            groups[name]=[dict(run_field(s,p,cfg), configuration=name) for s in range(START,START+COUNT)]
        rows[str(p)]={"seed_range":[START,START+COUNT-1],"summary":stats(groups["refined"],groups["candidate"]),"runs":groups}
    out={"evidence":"supplemental_locked_local_synthetic_paired_not_official","selection":"candidate configuration copied from the separately documented field_confirmation decision; this 8300000..8300999 run is an independent supplemental freeze check, not a parameter-selection dataset","seed_range":[START,START+COUNT-1],"configurations":CONFIGS,"results":rows}
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({p:v["summary"] for p,v in rows.items()},ensure_ascii=False,indent=2))
if __name__=="__main__": main()
