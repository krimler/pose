# TLA+ Verification Artifacts

These files verify the formal claims of "The Price of Safe Exploration in
Flexible Paxos." The paper proves structural properties about a graph of
configurations. Each configuration is a pair (r, w) representing read and
write quorum sizes. The graph encodes which pairs of configurations can
safely coexist during pipelined consensus.


## Background (what the specs model)

In Flexible Paxos, the rule for safety is `r + w > N` (where N is the
number of processes). During reconfiguration, two configurations run
concurrently. Cross-intersection requires each to satisfy the other's
constraint: `w1 + r2 > N` AND `w2 + r1 > N`. This defines edges in a
transition graph.

The paper proves:
- The graph has diameter 2 (any config reaches any other in 2 hops)
- (N,N) is the unique universal hub (adjacent to everything)
- Moving between extreme configs (1,N) and (N,1) forces going through
  a config with w=N, costing N-1 in suboptimality
- This cost is unavoidable even with perfect knowledge (PoSE = Theta(Sn))


## Files

```
FlexPaxosGraph.text        Defines config space, adjacency, structural theorems
PipelinedReconfig.text     Nondeterministic reconfig from (1,N) to (N,1)
PipelinedReconfigOpt.text  Same properties, state-efficient (no history variable)
AdversarialAdapt.text      Adversary switches regimes; protocol routes through hub
verify_all.py              Python verification (no Java needed)
*_N10.cfg                  TLC model-checking configs for N=10
Makefile                   Convenience targets
```

The `.text` extension is for LaTeX inclusion. Rename to `.tla` for TLC.


## Quick start

```bash
python3 verify_all.py
```

This checks all properties for N=3 through N=10. No libraries needed,
just Python 3.7+. Exit code 0 means all passed.

Options:
```
--max-n 15     verify up to N=15
--max-steps 20 bound path exploration depth
--dot          emit Graphviz .dot files for N=4,5
--latex        print LaTeX table for paper
--cfg          generate TLC config files
--verbose      show per-property breakdown
```


## What gets verified

For every N from 3 to 10 (or higher with --max-n):

| Property | Paper reference | Method |
|----------|----------------|--------|
| (N,N) is adjacent to all configs | Lemma 3.2 | Exhaustive check |
| No (h,h) with h < N is universal | Lemma 3.2 | Find counterexample for each h |
| (1,N) and (N,1) are not adjacent | Theorem 3.3 | Direct computation |
| Diameter = 2 | Theorem 3.3 | All-pairs BFS |
| Neighbors of (1,N) all have w=N | Theorem 5.2 | Exhaustive check |
| Neighbors of (N,1) all have r=N | Theorem 5.2 (sym) | Exhaustive check |
| (N,N) is the only 2-hop connector between extremals | Theorem 5.3 | Filter intermediates |
| Min transition cost = N-1 over ALL paths | Remark 4.6 | Dijkstra |
| Majority subgraph is a clique | Corollary 3.4 | Pairwise check |
| EpochAdapt maintains safety | Theorem 6.1 | Full state exploration |
| Transition cost = (N-1) per switch | Theorem 6.1 | State invariant |

The Remark 4.6 result is a conjecture in the paper (the paper only needs
the 2-hop case). This script verifies it for all path lengths using
Dijkstra on a graph where node weights are suboptimalities. This is fast
(under 1ms per N) and avoids the state explosion of path enumeration.


## The state explosion problem

The original `PipelinedReconfig.text` tracks the full path as a sequence
variable `history`. TLC stores each distinct path as a separate state.
The number of walks of length k in the graph grows exponentially with k:

| N  | MaxSteps=5 states (with history) | MaxSteps=5 states (optimized) |
|----|----------------------------------|-------------------------------|
| 5  | 49,401                           | 2,106                         |
| 7  | 961,850                          | 5,586                         |
| 10 | too many (>10M)                  | 12,760                        |

`PipelinedReconfigOpt.text` verifies the same four invariants but tracks
only what the invariants actually need: current config, previous config,
first step, step count, and two boolean flags. This keeps the state space
polynomial in N and MaxSteps.

Both specs verify the same things. Use the optimized one for TLC.


## Running TLC (if you have Java)

```bash
# Copy specs with .tla extension
cp FlexPaxosGraph.text FlexPaxosGraph.tla
cp PipelinedReconfigOpt.text PipelinedReconfigOpt.tla
cp AdversarialAdapt.text AdversarialAdapt.tla

# Run (download tla2tools.jar from github.com/tlaplus/tlaplus/releases)
java -jar tla2tools.jar -config FlexPaxosGraph_N10.cfg FlexPaxosGraph.tla
java -jar tla2tools.jar -config PipelinedReconfigOpt_N10.cfg PipelinedReconfigOpt.tla
java -jar tla2tools.jar -config AdversarialAdapt_N10.cfg AdversarialAdapt.tla
```

All three complete in under a second for N=10.


## Graphviz output

```bash
python3 verify_all.py --dot
dot -Tpdf flex_paxos_N4.dot -o flex_paxos_N4.pdf
```

Node colors:
- Red: hub (N,N)
- Blue: read-optimal (1,N)
- Green: write-optimal (N,1)
- Yellow: classical Paxos subgraph (majority quorums)
