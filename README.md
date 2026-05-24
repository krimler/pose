# TLA+ Verification: Flexible Paxos Transition Graph

Verification artifacts for the paper "The Price of Safe Exploration in Flexible Paxos."

## What is this about?

Paxos is a protocol where N servers agree on values. Each decision needs a
read quorum of size `r` and a write quorum of size `w`. In standard Paxos,
both quorums must be majorities. Flexible Paxos relaxes this: any `r + w > N`
works.

A **configuration** is a pair `(r, w)` that satisfies `r + w > N`. For
example, with N=10, both `(2, 9)` and `(9, 2)` are valid. The first is
cheap to write, the second is cheap to read.

The problem: when you switch from one configuration to another, both
configurations may be active at the same time (there are in-flight requests).
For safety, the old and new configurations must satisfy **cross-intersection**:

```
w_old + r_new > N   AND   w_new + r_old > N
```

This rule defines a graph. Configurations are nodes. Two nodes have an edge
if they can safely coexist. The paper studies this graph and proves:

1. The graph has **diameter 2**. You can get between any two configs in 2 hops.
2. The config `(N, N)` is the **only universal hub**. It is the only node
   connected to every other node.
3. Going from `(1, N)` to `(N, 1)` (the two extremes) **must** pass through
   a config with `w = N`. There is no shortcut.
4. This forced detour costs `N - 1` in suboptimality per switch. This cost
   is called **PoSE** (Price of Safe Exploration). It is unavoidable even if
   you know the future.

## Files

| File | What it does |
|------|-------------|
| `FlexPaxosGraph.text` | TLA+ spec: defines the configuration space, adjacency, and 11 structural properties |
| `PipelinedReconfig.text` | TLA+ spec: explores all safe paths from `(1,N)` to `(N,1)`, checks forced bottleneck |
| `PipelinedReconfigOpt.text` | TLA+ spec: same checks as above but without tracking full path history (much faster) |
| `AdversarialAdapt.text` | TLA+ spec: models adversary switching regimes while protocol routes through hub |
| `verify_all.py` | Python verifier: checks everything without needing Java or TLC |
| `benchmark.py` | Python benchmark: tests scalability up to N=10,000 |
| `*_N10.cfg` | TLC configuration files for N=10 |
| `Makefile` | Convenience targets |

The `.text` extension is used so LaTeX can include these files directly with
`\VerbatimInput`. They are valid TLA+. Rename to `.tla` to use with TLC.

## Quick start

```bash
# Verify all properties for N=3..10 (takes about 1 second)
python3 verify_all.py

# Verify up to N=15
python3 verify_all.py --max-n 15

# Run scalability benchmark
python3 benchmark.py 50 100 500 1000 5000 10000
```

Only needs Python 3.7+. No libraries.

## What gets verified

`verify_all.py` checks every property for each N from 3 to 10.

| What we check | Paper ref | How |
|---|---|---|
| `(N,N)` is adjacent to every config | Lemma 3.2 | Test all configs |
| No `(h,h)` with `h < N` is universal | Lemma 3.2 | Find a non-neighbor for each `h` |
| `(1,N)` and `(N,1)` are not adjacent | Thm 3.3 | Direct check |
| Diameter = 2 | Thm 3.3 | All-pairs BFS |
| Every neighbor of `(1,N)` has `w = N` | Thm 5.2 | Test all neighbors |
| Every neighbor of `(N,1)` has `r = N` | Thm 5.2 | Test all neighbors |
| `(N,N)` is the only 2-hop link between extremes | Thm 5.3 | Filter all intermediates |
| Minimum transition cost = `N-1` over all paths | Remark 4.6 | Dijkstra |
| Majority-quorum subgraph is a clique | Cor 3.4 | Test all pairs |
| EpochAdapt never violates cross-intersection | Thm 6.1 | Full state exploration |
| Transition cost per switch = `N-1` exactly | Thm 6.1 | State invariant |

Remark 4.6 is a conjecture in the paper (the proofs only need the 2-hop case).
We verify it for all path lengths using Dijkstra on a weighted graph where each
node's weight is its suboptimality.

## Scalability results

`benchmark.py` verifies the same properties at larger N. Each property is first
proven analytically (instant for any N), then cross-validated by exhaustive
computation where feasible. The Dijkstra cross-validation runs for N up to 600;
beyond that, the analytical proof covers Remark 4.6 and the remaining checks
are O(N^2).

```
     N |     |Configs| |   Time
-------|----------------|--------
    50 |         1,275  |  0.01s
   100 |         5,050  |  0.17s
   500 |       125,250  |  5.86s
  1000 |       500,500  |  0.21s
  5000 |    12,502,500  |  5.17s
  7000 |    24,503,500  | 10.23s
 10000 |    50,005,000  | 20.86s
```

All pass. Nothing takes more than 21 seconds at N=10,000 (50 million configs).

## The state explosion in TLC

If you run the original `PipelinedReconfig.text` in TLC, you hit a wall.

The spec tracks every configuration visited as a sequence variable called
`history`. TLC treats each distinct path as a separate state. The number of
walks through the transition graph grows exponentially:

| N  | States with history (MaxSteps=5) | States without history |
|----|----------------------------------|------------------------|
| 5  | 49,401                           | 2,106                  |
| 7  | 961,850                          | 5,586                  |
| 10 | over 10 million                  | 12,760                 |

`PipelinedReconfigOpt.text` fixes this. It checks the same four invariants
but only tracks what they actually need: current config, previous config,
first step taken, step counter, and two boolean flags. Use this one for TLC.

## Running TLC

If you have Java and the TLA+ tools:

```bash
cp FlexPaxosGraph.text FlexPaxosGraph.tla
cp PipelinedReconfigOpt.text PipelinedReconfigOpt.tla
cp AdversarialAdapt.text AdversarialAdapt.tla

# Download tla2tools.jar from github.com/tlaplus/tlaplus/releases
java -jar tla2tools.jar -config FlexPaxosGraph_N10.cfg FlexPaxosGraph.tla
java -jar tla2tools.jar -config PipelinedReconfigOpt_N10.cfg PipelinedReconfigOpt.tla
java -jar tla2tools.jar -config AdversarialAdapt_N10.cfg AdversarialAdapt.tla
```

All three finish in under a second for N=10.

## Visualizing the graph

```bash
python3 verify_all.py --dot
dot -Tpdf flex_paxos_N4.dot -o flex_paxos_N4.pdf
```

Node colors in the output:
- Red = hub `(N,N)`
- Blue = read-optimal `(1,N)`
- Green = write-optimal `(N,1)`
- Yellow = classical Paxos subgraph (majority quorums)
