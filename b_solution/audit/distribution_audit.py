"""Distribution/overfitting audit; diagnostic only, never starts simulator.
Evidence is official sanitized observations plus immutable synthetic result rows.
Run from repository root: python b_solution/audit/distribution_audit.py
"""
from __future__ import annotations
import csv, json, math, statistics
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HANDOFF=ROOT.parent/'ai_optimization_handoff_20260912'
OUT=ROOT/'results'/'audit_distribution.json'
SYN_FILES=[ROOT/'results'/'field_development.json', ROOT/'results'/'field_confirmation.json']
SEED_RANGES={'development_reserved_8200000_8200149':range(8200000,8200150), 'freeze_reserved_8300000_8300999':range(8300000,8301000)}

def qstats(xs):
    xs=[float(x) for x in xs if x is not None]
    if not xs:return {'n':0}
    ys=sorted(xs); q=lambda p: ys[min(len(ys)-1,max(0,math.ceil(p*len(ys))-1))]
    return {'n':len(xs),'min':ys[0],'p10':q(.1),'median':statistics.median(ys),'p90':q(.9),'max':ys[-1],'mean':statistics.mean(xs)}

def official():
    rows=list(csv.DictReader((HANDOFF/'manifest.csv').open()))
    out=[]
    for r in rows:
        log=HANDOFF/r['private_requests']; events=[json.loads(x) for x in log.read_text().splitlines()]
        accepted={e['request_id']:e for e in events if e['event']=='accepted'}
        replies={e['request_id']:json.loads(e['body_utf8']) for e in events if e['event']=='response' and e['http_status']==200}
        actions=[]
        for e in events:
            if e['event']=='accepted' and e['request_id'] in replies:
                actions.append((e['path'],e,replies[e['request_id']]))
        measures=[(e,b) for p,e,b in actions if p=='/measure']; clears=[(e,b) for p,e,b in actions if p=='/clear']
        outcomes=Counter(b.get('measure_result','clear_'+str(b.get('clear_result'))) for e,b in measures+clears)
        moves=[float(e.get('distance_m',0)) for p,e,b in actions if p in ('/measure','/clear')]
        switches=sum(float(e.get('switch_time_s',0))>0 for p,e,b in actions)
        phases=Counter()
        # Observable phase boundaries: pre-localization anchors are inferred only from policy labels, never hidden truth.
        obs=json.loads((HANDOFF/r['observed_result']).read_text())
        phases['entry_exit']=2; phases['measure_or_clear']=len(actions)-2
        out.append({'problem':int(r['problem']),'round':int(r['round']),'case_code':r['case_code'],'N_label':int(r['source_count']),'directional_label':int(r['directional_count']),'omni_label':int(r['omni_count']),'T_s':float(r['virtual_time_s']),'T_per_N_s':float(r['average_time_s']),'action_counts':Counter(p for p,e,b in actions),'measure_outcomes':outcomes,'measure_count':len(measures),'clear_count':len(clears),'switches':switches,'movement_m':sum(moves),'movement_share':None,'phase_counts':dict(phases),'phase_lengths_unavailable':True,'strategy':obs.get('strategy'),'coverage_policy':obs.get('coverage_policy'),'official_not_paired_counterfactual':True})
        out[-1]['movement_share']=None # no total-time decomposition is asserted from log metadata
    return out

def synthetic():
    out=[]
    for path in SYN_FILES:
        d=json.loads(path.read_text())
        for r in d.get('runs',[]):
            x=dict(r); x['source_file']=path.name; x['T_per_N_s']=x.get('average_time_s'); x['movement_share']= (x.get('distance_m',0)/5)/x['virtual_time_s'] if x.get('virtual_time_s') else None
            out.append(x)
    return out

def grouped(rows,key):
    return {str(k):qstats([r[key] for r in rows if r.get(key) is not None]) for k in sorted(set(r.get(key) for r in rows))}

def main():
    off=official(); syn=synthetic(); allseeds=Counter(int(r['seed']) for r in syn if 'seed' in r)
    overlap=[]
    for name,rr in SEED_RANGES.items():
        used=sorted(s for s in allseeds if s in rr); overlap.append({'range':name,'count':len(used),'seeds':used[:20],'truncated':len(used)>20})
    bycfg=Counter((r.get('problem'),r.get('configuration','unknown')) for r in syn)
    result={'evidence_type':'diagnostic distribution audit; official observations are unpaired and synthetic rows are local only','commands':['python b_solution/audit/distribution_audit.py'],'hard_gate_status':{'official_counterfactual_pairing':'FAIL_NOT_APPLICABLE','strategy_verified':'NOT_CLAIMED','reserved_seed_contamination':'PASS' if not any(x['count'] for x in overlap) else 'FAIL'},'provenance':{'official_manifest':'ai_optimization_handoff_20260912/manifest.csv','official_logs':'sanitized private_requests + observed_result + post-exit labels; no hidden coordinates/truth','synthetic_files':[str(p.relative_to(ROOT)) for p in SYN_FILES],'synthetic_configs':dict((f'Q{p}_{c}',n) for (p,c),n in bycfg.items())},'official':{'runs':off,'N':qstats([r['N_label'] for r in off]),'T_per_N':qstats([r['T_per_N_s'] for r in off]),'by_problem':{f'Q{p}':{'runs':[r for r in off if r['problem']==p],'N':qstats([r['N_label'] for r in off if r['problem']==p]),'T_per_N':qstats([r['T_per_N_s'] for r in off if r['problem']==p])} for p in (3,4)},'unavailable':['true source coordinates/radii/orientations','official action phase durations separated by semantic phase','official movement share (wire accepted distance is available but time decomposition is not asserted)','official failed-clear truth beyond responses']},'synthetic':{'runs':syn,'by_problem':{f'Q{p}':{'runs':len([r for r in syn if r.get('problem')==p]),'N':qstats([r.get('n_sources') for r in syn if r.get('problem')==p]),'measures':qstats([r.get('measures') for r in syn if r.get('problem')==p]),'switches':qstats([r.get('switches') for r in syn if r.get('problem')==p]),'failed_clears':qstats([r.get('failed_clears') for r in syn if r.get('problem')==p]),'movement_share':qstats([r.get('movement_share') for r in syn if r.get('problem')==p]),'T_per_N':qstats([r.get('T_per_N_s') for r in syn if r.get('problem')==p])} for p in (3,4)}},'seed_overlap_table':overlap,'diagnosis':{'likely':['Synthetic N is uniform 10..16 while official labels range 10..16 but only 10 cases per question; unequal N weighting can shift T/N.','Synthetic positions are iid uniform in radius-1800 disk and radii uniform 1000..1500; official coordinates/radii are unavailable, so boundary/cluster and directional geometry gaps can reverse Q3 direction.','Synthetic error fields are deterministic smooth/extreme/hash modes, not established official noise; repeated-coordinate semantics may differ.','Field parameters explicitly state selection from official-observation bottlenecks and development seeds; this is post-observation informed design, not an independent official holdout.'], 'unsupported':['No evidence supports treating official logs as paired refined-vs-field counterfactuals.','No evidence identifies official source placement, radio radius, directional orientation, or error distribution.','No evidence supports extrapolating 20 official runs to population quantiles.'],'protocol_controls':['Development 8200000..8200149 and final freeze 8300000..8300999 are reserved and uncontaminated by this audit.','Synthetic rows retain Q3/Q4 and configuration labels; no relabeling of refined as field.']}}
    OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n'); print(json.dumps(result['hard_gate_status'],indent=2))
if __name__=='__main__': main()
