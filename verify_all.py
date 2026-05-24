#!/usr/bin/env python3
"""
Verification suite for the TLA+ specs in
"The Price of Safe Exploration in Flexible Paxos".

Checks all structural properties for N=3..MAX_N.
No dependencies beyond Python 3.7+ stdlib.

Usage:
    python3 verify_all.py
    python3 verify_all.py --max-n 15
    python3 verify_all.py --dot --latex --cfg
"""
import argparse
import heapq
import time
import sys
from collections import deque, Counter


def configs(N):
    return [(r, w) for r in range(1, N+1) for w in range(1, N+1) if r + w > N]


def adjacent(q1, q2, N):
    return q1[1] + q2[0] > N and q2[1] + q1[0] > N


def build_adj_map(N):
    cfgs = configs(N)
    adj = {q: [] for q in cfgs}
    for q in cfgs:
        for q2 in cfgs:
            if q2 != q and adjacent(q, q2, N):
                adj[q].append(q2)
    return cfgs, adj


# -- FlexPaxosGraph structural properties --

def verify_structural(N):
    cfgs, adj = build_adj_map(N)
    read_opt, write_opt, hub = (1, N), (N, 1), (N, N)
    maj = (N // 2) + 1
    maj_cfgs = [(r, w) for r, w in cfgs if r >= maj and w >= maj]
    results = {}

    results["UniversalHub"] = all(adjacent(hub, q, N) for q in cfgs if q != hub)

    results["NoCheaperHub"] = all(
        any(not adjacent((h, h), q, N) for q in cfgs if q != (h, h))
        for h in range(1, N) if h + h > N
    )

    results["ExtremalsNotAdjacent"] = not adjacent(read_opt, write_opt, N)

    results["Diameter2"] = all(
        q1 == q2 or adjacent(q1, q2, N) or
        any(adjacent(q1, q3, N) and adjacent(q3, q2, N) for q3 in cfgs)
        for q1 in cfgs for q2 in cfgs
    )

    results["ForcedBottleneck"] = all(q[1] == N for q in adj[read_opt])
    results["ForcedBottleneckSym"] = all(q[0] == N for q in adj[write_opt])

    intermediates = [q for q in cfgs
                     if adjacent(read_opt, q, N) and adjacent(q, write_opt, N)]
    results["Unique2HopIntermediate"] = (intermediates == [hub])
    results["Min2HopCost"] = all(q[1] - 1 == N - 1 for q in intermediates)

    results["ClassicalComplete"] = all(
        adjacent(q1, q2, N) for q1 in maj_cfgs for q2 in maj_cfgs if q1 != q2
    )

    return results


# -- Transition cost via Dijkstra (verifies Remark 4.6) --

def min_transition_cost(N, source, target, alpha=0.0, beta=1.0):
    cfgs, adj = build_adj_map(N)
    target_lat = alpha * target[0] + beta * target[1]

    def subopt(q):
        return alpha * q[0] + beta * q[1] - target_lat

    dist = {q: float('inf') for q in cfgs}
    prev = {q: None for q in cfgs}
    dist[source] = 0
    pq = [(0, source)]

    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]:
            continue
        if u == target:
            break
        for v in adj[u]:
            cost = 0 if v == target else subopt(v)
            nd = dist[u] + cost
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))

    path = []
    u = target
    while u is not None:
        path.append(u)
        u = prev[u]
    path.reverse()
    return dist[target], path


def verify_remark46(N):
    cost, path = min_transition_cost(N, (1, N), (N, 1), alpha=0, beta=1)
    return {
        "min_cost": cost,
        "path": path,
        "equals_N_minus_1": cost == N - 1,
        "is_2hop_through_hub": path == [(1, N), (N, N), (N, 1)],
    }


# -- Diameter computation --

def compute_diameter(N):
    cfgs, adj = build_adj_map(N)
    max_d = 0
    for src in cfgs:
        d = {src: 0}
        queue = deque([src])
        while queue:
            u = queue.popleft()
            for v in adj[u]:
                if v not in d:
                    d[v] = d[u] + 1
                    queue.append(v)
        max_d = max(max_d, max(d.values()))
    return max_d


# -- PipelinedReconfigOpt state-space exploration --

def verify_pipelined_opt(N, max_steps):
    """
    Matches PipelinedReconfigOpt.text.
    State: (current, prev, firstStep, step, done, seenMaxW)
    """
    cfgs, adj = build_adj_map(N)
    start, target = (1, N), (N, 1)
    SENTINEL = (0, 0)

    init = (start, start, SENTINEL, 0, False, False)
    visited = {init}
    queue = deque([init])
    violations = []

    while queue:
        current, prev, first_step, step, done, seen_max_w = queue.popleft()

        if step > 0 and not adjacent(prev, current, N):
            violations.append("SafetyInvariant")
        if step >= 1 and first_step != SENTINEL and first_step[1] != N:
            violations.append("FirstStepBottleneck")
        if done and not seen_max_w:
            violations.append("CompletionRequiresMaxW")
        if done and step == 2 and first_step != (N, N):
            violations.append("MinCostAchieved")

        if done or step >= max_steps:
            continue

        for nxt in adj[current]:
            new_first = nxt if step == 0 else first_step
            new_state = (nxt, current, new_first, step + 1,
                         nxt == target, seen_max_w or nxt[1] == N)
            if new_state not in visited:
                visited.add(new_state)
                queue.append(new_state)

    return len(violations) == 0, len(visited), violations


# -- PipelinedReconfig original (with history, for state explosion demo) --

def pipelined_with_history(N, max_steps, limit=10_000_000):
    cfgs, adj = build_adj_map(N)
    start, target = (1, N), (N, 1)

    init = (start, 0, False, (start,))
    visited = {init}
    queue = deque([init])

    while queue:
        current, step, done, history = queue.popleft()
        if len(visited) > limit:
            return None
        if done or step >= max_steps:
            continue
        for nxt in adj[current]:
            s = (nxt, step + 1, nxt == target, history + (nxt,))
            if s not in visited:
                visited.add(s)
                queue.append(s)

    return len(visited)


# -- AdversarialAdapt state-space verification --

def verify_adversarial(N, max_switches=5, max_rounds=20):
    hub = (N, N)
    init = (0, "write", (N, 1), (N, 1), 0, 0, "stable", False)
    visited = {init}
    queue = deque([init])
    ok = True
    max_tc = 0

    while queue:
        rnd, regime, opt, active, sw, tc, state, viol = queue.popleft()

        if viol:
            ok = False
        if state == "transiting_from_hub" and active != hub:
            ok = False
        if tc < (sw - 1) * (N - 1):
            ok = False
        if state == "stable" and sw > 0 and tc != sw * (N - 1):
            ok = False
        max_tc = max(max_tc, tc)

        successors = []
        if state == "stable" and sw < max_switches and rnd < max_rounds:
            if regime == "write":
                successors.append((rnd, "read", (1, N), active, sw+1, tc, "transiting_to_hub", viol))
            else:
                successors.append((rnd, "write", (N, 1), active, sw+1, tc, "transiting_to_hub", viol))

        if state == "transiting_to_hub" and rnd < max_rounds:
            nv = viol or not adjacent(active, hub, N)
            sub = (hub[1] - 1) if regime == "write" else (hub[0] - 1)
            successors.append((rnd+1, regime, opt, hub, sw, tc+sub, "transiting_from_hub", nv))

        if state == "transiting_from_hub" and rnd < max_rounds:
            nv = viol or not adjacent(hub, opt, N)
            successors.append((rnd+1, regime, opt, opt, sw, tc, "stable", nv))

        if state == "stable" and rnd < max_rounds:
            successors.append((rnd+1, regime, opt, active, sw, tc, "stable", viol))

        for s in successors:
            if s not in visited:
                visited.add(s)
                queue.append(s)

    return ok, len(visited), max_tc


# -- CrashRecovery state-space verification --

def verify_crash_recovery(N, max_rounds=8, max_crashes=2, max_recovery=3):
    """
    Matches CrashRecovery.text.
    State: (round, sourceConfig, activeConfig, targetConfig, phase,
            crashCount, recoveryRound, hubCostAccum, safetyOK)
    """
    cfgs = configs(N)
    adj_map = {q: [] for q in cfgs}
    for q in cfgs:
        for q2 in cfgs:
            if q2 != q and adjacent(q, q2, N):
                adj_map[q].append(q2)

    hub = (N, N)
    start = (N, 1)

    init = (0, start, start, start, "stable", 0, 0, 0, True)
    visited = {init}
    queue = deque([init])
    violations = []

    while queue:
        rnd, src, active, target, phase, cc, rr, hc, safe = queue.popleft()

        # Check invariants
        if not safe:
            violations.append("SafetyHolds")
        if active not in cfgs:
            violations.append("ValidConfig")
        if active == hub and not all(adjacent(hub, q, N) for q in cfgs if q != hub):
            violations.append("HubAlwaysSafe")
        if hc > cc * max_recovery + rnd:
            violations.append("BoundedHubCost")

        successors = []

        # BeginTransition
        if phase == "stable" and rnd < max_rounds:
            for tgt in cfgs:
                if tgt != active and adjacent(active, hub, N) and adjacent(hub, tgt, N):
                    successors.append((rnd, src, active, tgt, "draining",
                                       cc, rr, hc, safe))

        # DrainComplete
        if phase == "draining" and rnd < max_rounds:
            s = safe and adjacent(active, hub, N)
            successors.append((rnd+1, src, hub, target, "activating",
                               cc, rr, hc+1, s))

        # ActivateTarget
        if phase == "activating" and rnd < max_rounds:
            s = safe and adjacent(hub, target, N)
            successors.append((rnd+1, src, target, target, "stable",
                               cc, rr, hc, s))

        # Crash
        if phase in ("draining", "activating") and cc < max_crashes and rnd < max_rounds:
            successors.append((rnd+1, src, active, target, "crashed",
                               cc+1, 0, hc, safe))

        # RecoveryTick
        if phase == "crashed" and rr < max_recovery and rnd < max_rounds:
            new_hc = hc + 1 if active == hub else hc
            successors.append((rnd+1, src, active, target, "crashed",
                               cc, rr+1, new_hc, safe))

        # RecoveryComplete
        if phase == "crashed" and rnd < max_rounds:
            new_phase = "activating" if active == hub else "draining"
            successors.append((rnd+1, src, active, target, new_phase,
                               cc, 0, hc, safe))

        # Exploit
        if phase == "stable" and rnd < max_rounds:
            successors.append((rnd+1, src, active, target, "stable",
                               cc, rr, hc, safe))

        for s in successors:
            if s not in visited:
                visited.add(s)
                queue.append(s)

    safety_ok = "SafetyHolds" not in violations
    return safety_ok, len(visited), len(violations)


# -- Graph statistics --

def graph_stats(N):
    cfgs, adj = build_adj_map(N)
    degrees = [len(adj[q]) for q in cfgs]
    return {
        "configs": len(cfgs),
        "edges": sum(degrees) // 2,
        "density": sum(degrees) / (len(cfgs) * (len(cfgs) - 1)),
        "deg_hub": len(adj[(N, N)]),
        "deg_extremals": len(adj[(1, N)]),
    }


# -- Graphviz DOT export --

def export_dot(N, filename=None):
    cfgs, adj = build_adj_map(N)
    if filename is None:
        filename = f"flex_paxos_N{N}.dot"
    hub, ro, wo = (N, N), (1, N), (N, 1)
    maj = (N // 2) + 1

    lines = [f'graph FlexPaxosN{N} {{', '  rankdir=LR;']
    for q in cfgs:
        attrs = f'label="({q[0]},{q[1]})"'
        if q == hub:
            attrs += ', style=filled, fillcolor="#ff9999"'
        elif q == ro:
            attrs += ', style=filled, fillcolor="#99ccff"'
        elif q == wo:
            attrs += ', style=filled, fillcolor="#99ff99"'
        elif q[0] >= maj and q[1] >= maj:
            attrs += ', style=filled, fillcolor="#ffffcc"'
        lines.append(f'  q_{q[0]}_{q[1]} [{attrs}];')

    seen = set()
    for q1 in cfgs:
        for q2 in adj[q1]:
            e = tuple(sorted([q1, q2]))
            if e not in seen:
                seen.add(e)
                lines.append(f'  q_{q1[0]}_{q1[1]} -- q_{q2[0]}_{q2[1]};')
    lines.append('}')

    with open(filename, 'w') as f:
        f.write('\n'.join(lines))
    return filename


# -- TLC .cfg generation --

def generate_cfg(N, output_dir="."):
    import os
    cfgs = {
        "FlexPaxosGraph": f"CONSTANT N = {N}\nSPECIFICATION StructuralProperties\n",
        "PipelinedReconfig": (
            f"CONSTANT\n    N = {N}\n    MaxSteps = 5\n"
            f"SPECIFICATION Spec\nINVARIANT Invariant\nPROPERTY Liveness\n"
        ),
        "PipelinedReconfigOpt": (
            f"CONSTANT\n    N = {N}\n    MaxSteps = 20\n"
            f"SPECIFICATION Spec\nINVARIANT Invariant\nPROPERTY Liveness\n"
        ),
        "AdversarialAdapt": (
            f"CONSTANT\n    N = {N}\n    MaxSwitches = 5\n    MaxRounds = 20\n"
            f"SPECIFICATION Spec\nINVARIANT MasterInvariant\n"
        ),
        "CrashRecovery": (
            f"CONSTANT\n    N = {N}\n    MaxRounds = 8\n"
            f"    MaxCrashes = 2\n    MaxRecovery = 3\n"
            f"SPECIFICATION Spec\nINVARIANT Invariant\nPROPERTY Liveness\n"
        ),
    }
    for name, content in cfgs.items():
        path = os.path.join(output_dir, f"{name}_N{N}.cfg")
        with open(path, 'w') as f:
            f.write(content)


# -- LaTeX table --

def latex_table(results):
    lines = [
        r"\begin{table}[t]", r"\centering",
        r"\caption{Verification results for TLA+ specifications.}",
        r"\label{tab:tlc-results}",
        r"\begin{tabular}{r r r r r r}",
        r"\toprule",
        r"$n$ & $|\mathcal{S}_n|$ & Diam & Min TC & States (Opt) & Time \\",
        r"\midrule",
    ]
    for N, d in sorted(results.items()):
        lines.append(
            f"  {N} & {d['configs']} & {d['diam']} & {d['min_tc']} & "
            f"{d['opt_states']:,} & {d['time']:.2f} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


# -- Main --

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-n", type=int, default=10)
    parser.add_argument("--min-n", type=int, default=3)
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--dot", action="store_true")
    parser.add_argument("--latex", action="store_true")
    parser.add_argument("--cfg", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    print("=" * 70)
    print("  Flexible Paxos PoSE - Verification Suite")
    print("=" * 70)

    all_results = {}

    for N in range(args.min_n, args.max_n + 1):
        t0_total = time.time()
        print(f"\n--- N = {N} ---")

        # Structural properties
        t0 = time.time()
        props = verify_structural(N)
        t1 = time.time()
        all_pass = all(props.values())
        print(f"  Structural ({len(configs(N))} configs): "
              f"{'ALL PASS' if all_pass else 'FAIL'}  [{t1-t0:.4f}s]")
        if args.verbose or not all_pass:
            for p, v in props.items():
                if not v:
                    print(f"    FAILED: {p}")

        # Diameter
        diam = compute_diameter(N)
        print(f"  Diameter: {diam}")

        # Remark 4.6
        t0 = time.time()
        r46 = verify_remark46(N)
        t1 = time.time()
        print(f"  Min TC (1,N)->(N,1): {r46['min_cost']}  "
              f"path: {' -> '.join(str(q) for q in r46['path'])}  "
              f"[{'OK' if r46['equals_N_minus_1'] else 'MISMATCH'}]")

        # PipelinedReconfigOpt
        t0 = time.time()
        p_ok, p_states, p_viols = verify_pipelined_opt(N, args.max_steps)
        t1 = time.time()
        print(f"  PipelinedReconfigOpt (MaxSteps={args.max_steps}): "
              f"{'PASS' if p_ok else 'FAIL'}  {p_states:,} states  [{t1-t0:.3f}s]")

        # Original spec state explosion (only for small N)
        if N <= 7:
            st = pipelined_with_history(N, 5)
            label = f"{st:,}" if st else ">10M"
            print(f"  PipelinedReconfig [original, MaxSteps=5]: {label} states")

        # AdversarialAdapt
        t0 = time.time()
        aa_ok, aa_states, aa_tc = verify_adversarial(N)
        t1 = time.time()
        print(f"  AdversarialAdapt (S=5, T=20): "
              f"{'PASS' if aa_ok else 'FAIL'}  {aa_states} states  "
              f"max_tc={aa_tc} (expect {5*(N-1)})  [{t1-t0:.4f}s]")

        # CrashRecovery
        t0 = time.time()
        cr_ok, cr_states, cr_viols = verify_crash_recovery(N)
        t1 = time.time()
        print(f"  CrashRecovery (crashes=2, recovery=3): "
              f"{'PASS' if cr_ok else 'FAIL'}  {cr_states:,} states  [{t1-t0:.3f}s]")

        # Stats
        st = graph_stats(N)
        print(f"  Graph: {st['edges']} edges, density={st['density']:.3f}, "
              f"deg(hub)={st['deg_hub']}, deg(1,N)={st['deg_extremals']}")

        total_t = time.time() - t0_total
        all_results[N] = {
            "configs": len(configs(N)), "diam": diam,
            "min_tc": r46["min_cost"], "opt_states": p_states, "time": total_t
        }

    # Summary
    print(f"\n{'='*70}")
    print(f"{'N':>4} | {'|S_n|':>5} | {'Diam':>4} | {'Min TC':>6} | "
          f"{'Remark 4.6':>10} | {'States':>10} | {'Time':>6}")
    print("-" * 60)
    for N in range(args.min_n, args.max_n + 1):
        d = all_results[N]
        ok = "HOLDS" if d["min_tc"] == N - 1 else "VIOLATED"
        print(f"{N:>4} | {d['configs']:>5} | {d['diam']:>4} | "
              f"{d['min_tc']:>6} | {ok:>10} | {d['opt_states']:>10,} | {d['time']:>5.2f}s")

    conj_ok = all(all_results[N]["min_tc"] == N - 1
                  for N in range(args.min_n, args.max_n + 1))
    print(f"\nRemark 4.6 (min TC = N-1 for all path lengths): "
          f"{'VERIFIED' if conj_ok else 'COUNTEREXAMPLE'} for N={args.min_n}..{args.max_n}")

    if args.dot:
        for N in [4, 5]:
            fn = export_dot(N)
            print(f"DOT: {fn}")

    if args.latex:
        print("\n" + latex_table(all_results))

    if args.cfg:
        for N in [5, 10]:
            generate_cfg(N)
            print(f"Generated .cfg files for N={N}")

    all_ok = all(
        all_results[N]["min_tc"] == N - 1
        for N in range(args.min_n, args.max_n + 1)
    )
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
