"""Independent geometry/behavior verification for the new research candidates."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, localcontext
from fractions import Fraction
import json
import math
import random
from pathlib import Path

from geometry import clip_bearing, initial_polygon, optical_cover
from joint_dispatch_candidate import choose_task
from optical_policy_candidate import certified_optical_cover
from planner import Planner, Track
from verify_terminal import DeadlineAdapter
from polar_coverage_candidate import polar_certificate, polar_waypoints


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def verify_polar(variant):
    cert = polar_certificate(variant)
    points = polar_waypoints(variant)
    triangles = cert["triangles_ccw"]
    counts = Counter(tuple(sorted((t[k], t[(k+1)%3]))) for t in triangles for k in range(3))
    boundary = {tuple(sorted((13+k, 13+(k+1)%12))) for k in range(12)}
    assert len(points) == len(set(points)) == 25 and points[0] == (0., 0.)
    assert {edge for edge, count in counts.items() if count == 1} == boundary
    assert all(count == (1 if edge in boundary else 2) for edge, count in counts.items())
    assert len(counts) == 60 and len(triangles) == 36
    assert all(cross(*(points[i] for i in triangle)) > 0 for triangle in triangles)
    directed = Counter((t[k],t[(k+1)%3]) for t in triangles for k in range(3))
    for a,b in counts:
        if (a,b) not in boundary:
            assert directed[a,b] == directed[b,a] == 1
    for a,b in counts:
        for c,d in counts:
            if len({a,b,c,d}) < 4:
                continue
            # Strict crossings would invalidate the triangulation argument.
            assert not (cross(points[a],points[b],points[c])*cross(points[a],points[b],points[d]) < -1e-8
                        and cross(points[c],points[d],points[a])*cross(points[c],points[d],points[b]) < -1e-8)
    area = sum(cross(*(points[i] for i in t))/2 for t in triangles)
    outer_area = sum(cross((0,0),points[13+k],points[13+(k+1)%12])/2 for k in range(12))
    assert abs(area-outer_area) < 1e-6
    maximum = max(math.dist(points[a],points[b]) for a,b in counts)
    bound = cert["robust_certificate"]
    assert maximum <= bound["triangle_diameter_upper_bound_m"] + 1e-9
    # Exact rational lower/upper radical bounds used by the written proof.
    assert Fraction(14142,10000)**2 < 2 < Fraction(14143,10000)**2
    assert Fraction(24494,10000)**2 < 6 < Fraction(24495,10000)**2
    a,b = map(int,(cert["inner_radius_m"],cert["outer_radius_m"]))
    assert Fraction(b*9659,10000) > bound["guard_disk_radius_m"]
    assert a*a+b*b-2*a*b*Fraction(9659,10000) < bound["triangle_diameter_upper_bound_m"]**2
    with localcontext() as context:
        context.prec = 70
        root2, root3, root6 = Decimal(2).sqrt(), Decimal(3).sqrt(), Decimal(6).sqrt()
        c15, s15 = (root6+root2)/4, (root6-root2)/4
        expected = [(Decimal(0), Decimal(0))]
        for radius, start in ((a,(Decimal(1),Decimal(0))), (b,(c15,s15))):
            x,y = start
            for k in range(12):
                expected.append((radius*x,radius*y))
                x,y = x*root3/2-y/2, x/2+y*root3/2
        error = max(float(((Decimal(px)-ex)**2+(Decimal(py)-ey)**2).sqrt())
                    for (px,py),(ex,ey) in zip(points,expected,strict=True))
    assert error < 1e-8 < bound["per_waypoint_euclidean_error_bound_m"]
    rng = random.Random(340091)
    positions = [(1800*math.cos(k*math.pi/180),1800*math.sin(k*math.pi/180)) for k in range(360)]
    positions += points[:13]
    positions += [((points[a][0]+points[b][0])/2,(points[a][1]+points[b][1])/2)
                  for a,b in counts if math.hypot((points[a][0]+points[b][0])/2,
                                                (points[a][1]+points[b][1])/2)<=1800]
    for _ in range(400):
        r,phi = 1800*math.sqrt(rng.random()),rng.uniform(0,math.tau)
        positions.append((r*math.cos(phi),r*math.sin(phi)))
    checks, worst_distance, least_forward = 0, 0.0, float("inf")
    shift = bound["shift_m"]
    perturbation_cases = 0
    special = list(points[:13])
    special.extend(((points[a][0]+points[b][0])/2,(points[a][1]+points[b][1])/2)
                   for a,b in counts if math.hypot((points[a][0]+points[b][0])/2,
                                                 (points[a][1]+points[b][1])/2)<1790)
    for h in special:
        n = (math.cos(.713), math.sin(.713))
        positions.append((h[0]-shift*n[0],h[1]-shift*n[1]))
    for g in positions:
        angles = [k*math.pi/12 for k in range(24)] + [.713]
        for angle in angles:
            n = math.cos(angle), math.sin(angle)
            h = g[0]+shift*n[0],g[1]+shift*n[1]
            containing = next(t for t in triangles if all(cross(points[t[i]],points[t[(i+1)%3]],h) >= -1e-7 for i in range(3)))
            v = max((points[i] for i in containing),key=lambda p:(p[0]-g[0])*n[0]+(p[1]-g[1])*n[1])
            projection = (v[0]-g[0])*n[0]+(v[1]-g[1])*n[1]
            distance = math.dist(v,g)
            assert projection >= shift-1e-8 and distance <= maximum+shift+1e-8
            epsilon = bound["per_waypoint_euclidean_error_bound_m"]
            for offset in ((-epsilon*n[0],-epsilon*n[1]),
                           (epsilon*(v[0]-g[0])/distance,epsilon*(v[1]-g[1])/distance)):
                q = v[0]+offset[0],v[1]+offset[1]
                assert (q[0]-g[0])*n[0]+(q[1]-g[1])*n[1] >= shift-epsilon-1e-7
                assert math.dist(q,g) <= bound["perturbed_detection_distance_upper_bound_m"]+1e-7
                perturbation_cases += 1
            checks += 1
            worst_distance=max(worst_distance,distance)
            least_forward=min(least_forward,projection)
    route=cert["explicit_open_scan_route"]["indices"]
    route_length=sum(math.dist(points[a],points[b]) for a,b in zip(route,route[1:]))
    assert abs(route_length-cert["explicit_open_scan_route"]["analytic_length_m"])<1e-7
    return {"variant":variant,"triangles":len(triangles),"edges":len(counts),
            "noncrossing_tiling_verified":True,"maximum_edge_m":maximum,
            "coordinate_error_against_decimal_m":error,"directional_cases":checks,
            "adverse_single_vertex_perturbations":perturbation_cases,
            "maximum_witness_distance_m":worst_distance,"minimum_witness_projection_m":least_forward,
            "explicit_route_length_m":route_length,"robust_certificate":bound}


def verify_optical():
    rng=random.Random(342091)
    polygons=[[(0.,0.)],[(0.,0.),(1000.,0.)],[(0.,0.),(1000.,1e-9),(500.,0.)],
              [(0.,0.),(1500.,0.),(1500.,52.)],
              [(-100.,-40.),(100.,-40.),(100.,40.),(-100.,40.)]]
    for _ in range(120):
        phi=rng.uniform(0,math.tau)
        r=1800*math.sqrt(rng.random())
        g=r*math.cos(phi),r*math.sin(phi)
        poly=initial_polygon()
        for j in range(rng.randrange(1,5)):
            theta=rng.uniform(0,math.tau); distance=rng.uniform(6,1500)
            s=g[0]+distance*math.cos(theta),g[1]+distance*math.sin(theta)
            poly=clip_bearing(poly,s,(math.degrees(theta)+180+rng.uniform(-1,1))%360)
        assert poly
        polygons.append(poly)
    samples=0; improved=0; max_distance=0.0
    for poly in polygons:
        old=optical_cover(poly); new=certified_optical_cover(poly)
        old_cost=3*len(old)+sum(math.dist(p,old[i-1]) for i,p in enumerate(old))/5
        new_cost=3*len(new)+sum(math.dist(p,new[i-1]) for i,p in enumerate(new))/5
        assert new_cost<=old_cost+1e-7
        improved+=new_cost<old_cost-1e-7
        probes=list(poly)
        for a,b in zip(poly,poly[1:]+poly[:1]):
            probes.extend(((1-t/20)*a[0]+t/20*b[0],(1-t/20)*a[1]+t/20*b[1]) for t in range(21))
        for _ in range(100):
            weights=[rng.random() for _ in poly]; total=sum(weights)
            probes.append(tuple(sum(w*p[k] for w,p in zip(weights,poly))/total for k in (0,1)))
        for p in probes:
            distance=min(math.dist(p,c) for c in new)
            assert distance<=19.9+1e-7
            max_distance=max(max_distance,distance);samples+=1
    return {"polygons":len(polygons),"interior_and_boundary_samples":samples,
            "maximum_sampled_distance_m":max_distance,"lower_cover_proxy_cost_cases":improved,
            "scope":"interior sampling supplements exact per-cell corner certificates, not a proof by sampling"}


def verify_dispatch():
    anchors={7:(-2.,0.),9:(10.,0.)};targets={3:((1.,0.),20.)}
    kinds=[]
    for mode in ("center","guarded"):
        remaining_a=dict(anchors);remaining_t=dict(targets);position=(0.,0.);visited=[]
        while remaining_a or remaining_t:
            kind,key=choose_task(position,remaining_a,remaining_t,choice=mode)
            position=remaining_a.pop(key) if kind=="anchor" else remaining_t.pop(key)[0]
            visited.append((kind,key))
        assert set(visited)=={("anchor",7),("anchor",9),("target",3)}
        kinds.append({"choice":mode,"completed":visited})
    assert choose_task((0,0),{1:(0,0)},{2:((0,0),0)}) in (("anchor",1),("target",2))
    try:
        choose_task((0,0),{},{})
    except ValueError:
        pass
    else:
        raise AssertionError("Empty dispatch must not fabricate a task")
    return kinds


def verify_scan_obligations():
    records = []
    for problem, mode in ((3,"unknown"),(4,"useful")):
        adapter = DeadlineAdapter(max_virtual=360000)
        policy = Planner(adapter,problem=problem)
        policy.action("/enter")
        # A previously detected, unresolved singleton: a ready optical target,
        # not an absent channel even when every other channel has been scanned.
        policy.tracks[1] = Track(polygon=[(100.,0.)],readings=[((0.,0.),0.)])
        policy.channel_state[1] = "detected"
        for index in sorted(policy.pending):
            policy.scan_anchor(index)
        assert not policy.scan_records[1]
        assert not policy._result()["certificate_complete"]
        assert policy.channel_state[1] == "detected"
        policy.measure(1,(200.,0.))
        assert policy.channel_state[1] == "detected"
        policy.clear(1,(100.,0.))
        result = policy._result()
        assert result["certificate_complete"] and result["n_cleared"] == 1
        assert all(state == ("cleared" if channel == 1 else "absent-certified")
                   for channel,state in result["channel_certificates"].items())
        records.append({"problem":problem,"scan_policy":mode,
                        "known_skip_never_certified_absent":True,
                        "negative_reading_kept_detected":True,
                        "success_completed_remaining_obligation":True})
    return records


def main():
    polar=[verify_polar(variant) for variant in ("seed25","compact25")]
    assert polar[0]["explicit_route_length_m"]-polar[1]["explicit_route_length_m"]>179.5
    result={"evidence":"independent_finite_geometry_and_behavior_checks_not_official",
            "polar":polar,"optical":verify_optical(),"dispatch":verify_dispatch(),
            "scan_obligations":verify_scan_obligations()}
    Path("results/research_verification.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
