# Flows Reference -- Complete Guide to `ws.query_flow()`

Deep reference for flow queries in `mixpanel_data`. Flows show user paths before and after anchor events -- graph traversal of sequential behavior across the user base.

## Complete Signature

```python
ws.query_flow(
    event: str | FlowStep | Sequence[str | FlowStep],
    *,
    forward: int = 3,
    reverse: int = 0,
    from_date: str | None = None,
    to_date: str | None = None,
    last: int = 30,
    conversion_window: int = 7,
    conversion_window_unit: Literal["day", "week", "month", "session"] = "day",
    count_type: Literal["unique", "total", "session"] = "unique",
    cardinality: int = 3,
    collapse_repeated: bool = False,
    hidden_events: list[str] | None = None,
    mode: Literal["sankey", "paths", "tree"] = "sankey",
) -> FlowQueryResult
```

## Parameter Reference

### `event` -- Anchor Event(s)

The event(s) that anchor the flow analysis. Three forms:

**Simple string** -- single anchor, uses query-level `forward`/`reverse`:
```python
result = ws.query_flow("Login")
```

**List of strings** -- multi-anchor flow, all share query-level direction:
```python
result = ws.query_flow(["Login", "Purchase"])
```

**FlowStep** -- per-step overrides for direction, filters, labels:
```python
from mixpanel_data import FlowStep, Filter

result = ws.query_flow(
    FlowStep(
        "Purchase",
        forward=5,
        reverse=3,
        label="Buy",
        filters=[Filter.equals("country", "US")],
        filters_combinator="all",
    )
)
```

**List of FlowStep objects** -- multi-anchor with per-step config:
```python
result = ws.query_flow([
    FlowStep("Login", forward=2, reverse=0),
    FlowStep("Purchase", forward=0, reverse=3),
])
```

**Mixed list** -- strings and FlowStep objects can be combined:
```python
result = ws.query_flow([
    "Login",
    FlowStep("Purchase", forward=0, reverse=5, filters=[Filter.equals("plan", "premium")]),
])
```

### FlowStep Fields

```python
@dataclass(frozen=True)
class FlowStep:
    event: str                                         # event name (required)
    forward: int | None = None                         # per-step forward (None = use query default)
    reverse: int | None = None                         # per-step reverse (None = use query default)
    label: str | None = None                           # display label (None = event name)
    filters: list[Filter] | None = None                # per-step filters
    filters_combinator: Literal["all", "any"] = "all"  # AND/OR for filters
```

### `forward` / `reverse` -- Direction Controls

| Parameter | Range | Default | Effect |
|-----------|-------|---------|--------|
| `forward` | 0-5 | 3 | Steps traced AFTER anchor event |
| `reverse` | 0-5 | 0 | Steps traced BEFORE anchor event |

**Rule**: At least one of `forward` or `reverse` must be nonzero (validation FL5).

**Direction patterns**:

```python
# Forward-only: "What happens after Login?"
result = ws.query_flow("Login", forward=5, reverse=0)

# Reverse-only: "What leads to Purchase?"
result = ws.query_flow("Purchase", forward=0, reverse=5)

# Bidirectional: "What surrounds the key event?"
result = ws.query_flow("Add to Cart", forward=3, reverse=3)

# Per-step overrides beat query-level defaults
result = ws.query_flow(
    FlowStep("Purchase", forward=0, reverse=5),
    forward=3, reverse=0,  # these are ignored for this step
)
```

### `from_date` / `to_date` / `last` -- Date Range

```python
# Relative (default): last 30 days
result = ws.query_flow("Login")

# Relative: last 90 days
result = ws.query_flow("Login", last=90)

# Absolute: specific date range
result = ws.query_flow("Login", from_date="2025-01-01", to_date="2025-03-31")
```

When `from_date` is set, `last` is ignored. `to_date` requires `from_date`.

### `conversion_window` / `conversion_window_unit` -- Time Constraint

How long users have to complete the flow path.

| Unit | Max `conversion_window` | Notes |
|------|------------------------|-------|
| `day` | 366 | Default: 7 days |
| `week` | 52 | |
| `month` | 12 | |
| `session` | 1 (only) | Session-scoped; count_type must also be "session" |

```python
# Tight window: 24-hour flow
result = ws.query_flow("Login", conversion_window=1, conversion_window_unit="day")

# Session-scoped flow
result = ws.query_flow(
    "Login",
    conversion_window=1,
    conversion_window_unit="session",
    count_type="session",
)
```

**Validation rules**:
- FL9: `count_type="session"` requires `conversion_window_unit="session"`
- FL10: `conversion_window_unit="session"` requires `conversion_window=1`
- FL7: `conversion_window` must be positive and within unit max

### `count_type` -- Counting Method

| Value | Meaning |
|-------|---------|
| `unique` | Count unique users (default) |
| `total` | Count total events (one user can appear multiple times) |
| `session` | Count sessions (requires session conversion window) |

### `cardinality` -- Path Granularity

Controls the number of top events shown at each step (1-50). Default: 3.

- Low cardinality (1-3): Shows only the dominant paths -- good for executive summaries
- Medium cardinality (5-10): Balanced view of user behavior
- High cardinality (20-50): Reveals long-tail paths -- useful for finding edge cases

```python
# High-level view: top 3 paths
result = ws.query_flow("Login", cardinality=3)

# Detailed analysis: top 20 paths
result = ws.query_flow("Login", cardinality=20)
```

### `collapse_repeated` -- Merge Consecutive Duplicates

When `True`, consecutive identical events are collapsed. Useful when users trigger the same event multiple times in sequence (e.g., page refreshes).

```python
# Without collapse: Login -> Login -> Search -> Search -> Purchase
# With collapse:    Login -> Search -> Purchase
result = ws.query_flow("Login", collapse_repeated=True)
```

### `hidden_events` -- Exclude Events

Filter out noisy or irrelevant events from the flow visualization:

```python
result = ws.query_flow("Login", hidden_events=["$mp_web_page_view", "Session Start"])
```

### `mode` -- Visualization Mode

Three modes produce different result structures:

| Mode | Primary data | Best for |
|------|-------------|----------|
| `sankey` | `nodes_df`, `edges_df`, `graph` | Visualizing transition volumes between steps |
| `paths` | `df` with path_index/step/event columns | Ranking top complete user paths |
| `tree` | `trees` (FlowTreeNode), `anytree` | Recursive branching analysis, per-path metrics |

---

## FlowQueryResult Properties

### Common Properties (All Modes)

```python
result = ws.query_flow("Login", forward=3)

result.overall_conversion_rate   # float: 0.0-1.0
result.computed_at               # str: ISO-8601 timestamp
result.params                    # dict: bookmark params JSON (for persistence)
result.meta                      # dict: API metadata (sampling, timing)
result.mode                      # str: "sankey", "paths", or "tree"
result.df                        # DataFrame: mode-aware (see below)
```

### Sankey Mode (`mode="sankey"`)

The default mode. Returns step-by-step nodes and edges.

#### `nodes_df` -- Node Table

```python
result = ws.query_flow("Login", forward=3)
result.nodes_df
# Columns: step | event | type | count | anchor_type | is_custom_event | conversion_rate_change
```

| Column | Type | Description |
|--------|------|-------------|
| `step` | int | Zero-based step index |
| `event` | str | Event name |
| `type` | str | ANCHOR, FORWARD, REVERSE, DROPOFF, PRUNED, NORMAL |
| `count` | int | User/event count at this node |
| `anchor_type` | str | NORMAL, RELATIVE_REVERSE, RELATIVE_FORWARD |
| `is_custom_event` | bool | Whether this is a computed/custom event |
| `conversion_rate_change` | float | Change in conversion rate |

#### `edges_df` -- Edge Table

```python
result.edges_df
# Columns: source_step | source_event | target_step | target_event | count | target_type
```

#### `graph` -- NetworkX DiGraph

```python
import networkx as nx

G = result.graph  # lazily constructed on first access

# Node format: "{event}@{step}" e.g. "Login@0", "Search@1"
# Node attrs: step, event, type, count, anchor_type
# Edge attrs: count, type
```

#### `top_transitions(n)` -- Highest-Traffic Edges

```python
for src, tgt, count in result.top_transitions(n=5):
    print(f"{src} -> {tgt}: {count:,}")
# Login@0 -> Search@1: 8,500
# Login@0 -> Browse@1: 4,200
# Search@1 -> Purchase@2: 3,100
```

#### `drop_off_summary()` -- Per-Step Attrition

```python
for step, info in result.drop_off_summary().items():
    print(f"{step}: {info['total']:,} total, {info['dropoff']:,} dropoff ({info['rate']:.0%})")
# step_0: 10000 total, 1200 dropoff (12%)
# step_1: 8800 total, 3500 dropoff (40%)
```

#### `overall_conversion_rate` -- End-to-End Rate

```python
print(f"Overall conversion: {result.overall_conversion_rate:.1%}")
```

### Paths Mode (`mode="paths"`)

Returns ranked complete user paths.

```python
result = ws.query_flow("Login", forward=3, mode="paths")
result.df
# Columns: path_index | step | event | type | count
```

Each `path_index` groups a complete path. Paths are ranked by frequency (path 0 is most common).

```python
# Print the top 5 paths
for path_idx in result.df["path_index"].unique()[:5]:
    path = result.df[result.df["path_index"] == path_idx]
    events = " -> ".join(path["event"].tolist())
    count = path["count"].iloc[0]
    print(f"Path {path_idx} ({count:,} users): {events}")
```

### Tree Mode (`mode="tree"`)

Returns recursive prefix trees preserving full path context.

```python
result = ws.query_flow("Login", forward=3, mode="tree")

result.trees   # list[FlowTreeNode] -- native recursive trees
result.anytree # list[AnyNode] -- anytree-converted trees (lazy cached)
result.df      # DataFrame: tree_index | depth | path | event | type | step_number |
               #            total_count | drop_off_count | converted_count
```

---

## FlowTreeNode Deep Reference

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `event` | str | Event name at this position |
| `type` | FlowNodeType | ANCHOR, NORMAL, DROPOFF, PRUNED, FORWARD, REVERSE |
| `step_number` | int | Zero-based step index |
| `total_count` | int | Users reaching this node |
| `drop_off_count` | int | Users who dropped off here |
| `converted_count` | int | Users who continued past here |
| `anchor_type` | FlowAnchorType | NORMAL, RELATIVE_REVERSE, RELATIVE_FORWARD |
| `is_computed` | bool | Whether this is a custom event |
| `children` | tuple[FlowTreeNode, ...] | Child nodes (subsequent events) |

### Computed Properties

```python
node.conversion_rate  # float: converted_count / total_count (0.0 if total is 0)
node.drop_off_rate    # float: drop_off_count / total_count (0.0 if total is 0)
node.depth            # int: max depth of subtree (leaf = 0)
node.node_count       # int: total nodes in subtree (always >= 1)
node.leaf_count       # int: leaf nodes in subtree (always >= 1)
```

### Methods

```python
# All root-to-leaf paths
paths = node.all_paths()  # list[list[FlowTreeNode]]

# Find all nodes matching an event name (depth-first)
purchases = node.find("Purchase")  # list[FlowTreeNode]

# Flatten to pre-order list
all_nodes = node.flatten()  # list[FlowTreeNode]

# ASCII rendering
print(node.render())
# Login (1000)
# +-- Search (600)
# |   +-- Purchase (400)
# |   +-- DROPOFF (100)
# +-- Browse (300)
# |   +-- Purchase (200)
# +-- DROPOFF (50)

# Serialize to dict (JSON-safe)
d = node.to_dict()

# Convert to anytree (gains parent references)
at = node.to_anytree()  # -> anytree.AnyNode
```

---

## FlowTreeNode Traversal Patterns

### Branching Analysis

At each fork, calculate the percentage of users taking each branch:

```python
result = ws.query_flow("Login", forward=3, mode="tree")

def analyze_branches(node, indent=0):
    """Show branching percentages at each fork."""
    prefix = "  " * indent
    print(f"{prefix}{node.event} ({node.total_count:,})")
    if node.children:
        for child in sorted(node.children, key=lambda c: c.total_count, reverse=True):
            pct = child.total_count / node.total_count * 100 if node.total_count else 0
            print(f"{prefix}  -> {child.event}: {child.total_count:,} ({pct:.1f}%)")
            analyze_branches(child, indent + 2)

for tree in result.trees:
    analyze_branches(tree)
```

### Best Path Finding (Highest Conversion)

```python
def best_path(tree):
    """Find the path with the highest end-to-end conversion."""
    paths = tree.all_paths()
    if not paths:
        return None
    return max(
        paths,
        key=lambda p: p[-1].total_count / p[0].total_count if p[0].total_count else 0,
    )

for tree in result.trees:
    bp = best_path(tree)
    if bp:
        events = " -> ".join(n.event for n in bp)
        rate = bp[-1].total_count / bp[0].total_count if bp[0].total_count else 0
        print(f"Best path ({rate:.1%}): {events}")
```

### Worst Drop-Off Identification

```python
def worst_dropoffs(tree, n=5):
    """Find the nodes with the highest drop-off rates."""
    nodes = tree.flatten()
    with_dropoff = [n for n in nodes if n.drop_off_count > 0]
    return sorted(with_dropoff, key=lambda n: n.drop_off_rate, reverse=True)[:n]

for tree in result.trees:
    for node in worst_dropoffs(tree):
        print(f"{node.event} (step {node.step_number}): "
              f"{node.drop_off_rate:.1%} drop-off ({node.drop_off_count:,} users)")
```

### Depth-First Exploration with Context

```python
def explore_tree(node, path=None):
    """Depth-first traversal accumulating path context."""
    path = path or []
    current_path = path + [node.event]

    if not node.children:
        # Leaf node -- print full path
        route = " -> ".join(current_path)
        print(f"  {route}: {node.total_count:,} users")
        return

    for child in node.children:
        explore_tree(child, current_path)

for tree in result.trees:
    print(f"Flow tree from {tree.event} ({tree.total_count:,} users):")
    explore_tree(tree)
```

---

## NetworkX Integration Patterns

The `.graph` property returns a `networkx.DiGraph` built from sankey mode data. Node keys follow the format `"{event}@{step}"`.

### Basic Graph Inspection

```python
import networkx as nx

result = ws.query_flow("Login", forward=5)
G = result.graph

print(f"Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")
print(f"Density: {nx.density(G):.4f}")

# Inspect a specific node
print(G.nodes["Login@0"])
# {'step': 0, 'event': 'Login', 'type': 'ANCHOR', 'count': 10000, 'anchor_type': 'NORMAL'}

# Inspect an edge
print(G.edges["Login@0", "Search@1"])
# {'count': 6000, 'type': 'NORMAL'}
```

### Shortest Path Between Events

```python
# Find shortest path from Login to Purchase
try:
    path = nx.shortest_path(G, "Login@0", "Purchase@3")
    print(" -> ".join(path))
except nx.NetworkXNoPath:
    print("No path exists")
except nx.NodeNotFound as e:
    print(f"Node not found: {e}")
```

### Micro-Conversion Rate Between Two Nodes

```python
def micro_conversion(G, source, target):
    """Calculate conversion rate between any two connected nodes."""
    source_count = G.nodes[source].get("count", 0)
    if source_count == 0:
        return 0.0
    # Sum all paths from source to target
    try:
        paths = list(nx.all_simple_paths(G, source, target))
        if not paths:
            return 0.0
        # Use target node count as a proxy (exact requires edge analysis)
        target_count = G.nodes[target].get("count", 0)
        return target_count / source_count
    except nx.NodeNotFound:
        return 0.0

rate = micro_conversion(G, "Login@0", "Purchase@3")
print(f"Login -> Purchase micro-conversion: {rate:.1%}")
```

### Betweenness Centrality -- Gateway Events

```python
centrality = nx.betweenness_centrality(G, weight="count")
sorted_centrality = sorted(centrality.items(), key=lambda x: x[1], reverse=True)

print("Gateway events (highest betweenness centrality):")
for node, score in sorted_centrality[:10]:
    event = G.nodes[node].get("event", node)
    count = G.nodes[node].get("count", 0)
    print(f"  {event} (step {G.nodes[node].get('step', '?')}): "
          f"centrality={score:.4f}, count={count:,}")
```

### PageRank -- Most Important Nodes

```python
pr = nx.pagerank(G, weight="count")
sorted_pr = sorted(pr.items(), key=lambda x: x[1], reverse=True)

print("Most important nodes (PageRank):")
for node, score in sorted_pr[:10]:
    print(f"  {node}: {score:.4f} (count: {G.nodes[node].get('count', 0):,})")
```

### Dead-End Detection -- Nodes with No Outgoing Edges

```python
dead_ends = [n for n in G.nodes() if G.out_degree(n) == 0 and G.nodes[n].get("type") != "DROPOFF"]
print("Dead-end events (non-DROPOFF nodes with no outgoing edges):")
for node in dead_ends:
    print(f"  {node}: {G.nodes[node].get('count', 0):,} users stuck")
```

### Cycle Detection

```python
try:
    cycles = list(nx.simple_cycles(G))
    if cycles:
        print(f"Found {len(cycles)} cycles:")
        for cycle in cycles[:5]:
            print(f"  {' -> '.join(cycle)}")
    else:
        print("No cycles found (expected for most flows)")
except nx.NetworkXError:
    print("Cycle detection failed")
```

### Subgraph Extraction -- Conversion vs Churn Paths

```python
# Extract subgraph of only nodes on paths to a target
target = "Purchase@3"
if target in G:
    ancestors = nx.ancestors(G, target) | {target}
    conversion_subgraph = G.subgraph(ancestors)
    print(f"Conversion subgraph: {conversion_subgraph.number_of_nodes()} nodes, "
          f"{conversion_subgraph.number_of_edges()} edges")

    # Extract churn subgraph (nodes that never reach target)
    all_nodes = set(G.nodes())
    churn_nodes = all_nodes - ancestors
    churn_subgraph = G.subgraph(churn_nodes)
    print(f"Churn subgraph: {churn_subgraph.number_of_nodes()} nodes")
```

### Weighted Graph Metrics

```python
# Average path length weighted by traffic
paths_to_target = list(nx.all_simple_paths(G, "Login@0", "Purchase@3"))
if paths_to_target:
    path_lengths = [len(p) - 1 for p in paths_to_target]
    path_weights = []
    for p in paths_to_target:
        # Weight by minimum edge count along the path
        min_edge = min(G.edges[p[i], p[i+1]].get("count", 0) for i in range(len(p)-1))
        path_weights.append(min_edge)

    import numpy as np
    weighted_avg_length = np.average(path_lengths, weights=path_weights)
    print(f"Weighted average path length to Purchase: {weighted_avg_length:.1f} steps")
```

### Community Detection (Louvain)

```python
# Requires: pip install python-louvain
try:
    import community as community_louvain
    # Convert to undirected for community detection
    undirected = G.to_undirected()
    partition = community_louvain.best_partition(undirected, weight="count")
    communities = {}
    for node, comm_id in partition.items():
        communities.setdefault(comm_id, []).append(node)
    for comm_id, members in sorted(communities.items()):
        events = [G.nodes[n].get("event", n) for n in members]
        print(f"  Community {comm_id}: {', '.join(events)}")
except ImportError:
    print("Install python-louvain: pip install python-louvain")
```

### Export Graph to Various Formats

```python
# GEXF (for Gephi)
nx.write_gexf(G, "flow.gexf")

# GraphML
nx.write_graphml(G, "flow.graphml")

# Adjacency matrix
adj = nx.to_pandas_adjacency(G, weight="count")
print(adj)

# Edge list as DataFrame
import pandas as pd
edges = [(u, v, d["count"]) for u, v, d in G.edges(data=True)]
edge_df = pd.DataFrame(edges, columns=["source", "target", "count"])
```

---

## anytree Integration Patterns

The `.anytree` property (on FlowQueryResult) and `.to_anytree()` method (on FlowTreeNode) convert flow trees into anytree nodes, gaining parent references and rich rendering.

### ASCII Rendering with RenderTree

```python
from anytree import RenderTree

result = ws.query_flow("Login", forward=3, mode="tree")
for root in result.anytree:
    for pre, fill, node in RenderTree(root):
        print(f"{pre}{node.event} ({node.total_count:,}) "
              f"[{node.type}, conv={node.converted_count/node.total_count:.0%}]"
              if node.total_count else f"{pre}{node.event}")
```

### Graphviz DOT Export

```python
from anytree.exporter import UniqueDotExporter

result = ws.query_flow("Login", forward=3, mode="tree")
for i, root in enumerate(result.anytree):
    UniqueDotExporter(
        root,
        nodeattrfunc=lambda n: (
            f'label="{n.event}\n{n.total_count:,} users"'
            f', style=filled'
            f', fillcolor="{"#ff6b6b" if n.type == "DROPOFF" else "#4ecdc4"}"'
        ),
        edgeattrfunc=lambda parent, child: (
            f'label="{child.total_count:,}"'
        ),
    ).to_picture(f"flow_tree_{i}.png")
```

### Backward Tracing with Parent References

Unlike FlowTreeNode (which is immutable and has no parent pointer), anytree nodes have `.parent` and `.path`:

```python
from anytree import findall

result = ws.query_flow("Login", forward=5, mode="tree")
for root in result.anytree:
    # Find all Purchase nodes
    purchases = findall(root, filter_=lambda n: n.event == "Purchase")
    for p in purchases:
        # Trace backward to root
        ancestry = [n.event for n in p.path]
        print(f"Path to Purchase: {' -> '.join(ancestry)} ({p.total_count:,} users)")

        # Direct parent
        if p.parent:
            print(f"  Immediately preceded by: {p.parent.event}")
```

### Tree-Wide Search with anytree.find

```python
from anytree import find, findall, findall_by_attr

result = ws.query_flow("Login", forward=5, mode="tree")
root = result.anytree[0]

# Find first occurrence
first_purchase = find(root, filter_=lambda n: n.event == "Purchase")

# Find all occurrences
all_searches = findall(root, filter_=lambda n: n.event == "Search")

# Find by attribute
dropoffs = findall(root, filter_=lambda n: n.type == "DROPOFF")
print(f"Found {len(dropoffs)} drop-off points")

# Find high-dropoff nodes
high_dropoff = findall(
    root,
    filter_=lambda n: n.total_count > 0 and n.drop_off_count / n.total_count > 0.5,
)
for node in high_dropoff:
    path = " -> ".join(n.event for n in node.path)
    print(f"  {path}: {node.drop_off_count/node.total_count:.0%} drop-off")
```

### Tree Depth and Level Iteration

```python
from anytree import LevelOrderIter, LevelOrderGroupIter

result = ws.query_flow("Login", forward=3, mode="tree")
root = result.anytree[0]

# Level-by-level iteration
for level_nodes in LevelOrderGroupIter(root):
    level = level_nodes[0].depth if hasattr(level_nodes[0], 'depth') else 0
    total = sum(n.total_count for n in level_nodes)
    events = ", ".join(f"{n.event}({n.total_count:,})" for n in level_nodes)
    print(f"Level {level} ({total:,} total): {events}")
```

---

## Complete Workflow Examples

### Example 1: Forward Flow Analysis

```python
import mixpanel_data as mp

ws = mp.Workspace()

# What do users do after signing up?
result = ws.query_flow("Sign Up", forward=5, reverse=0, last=90, cardinality=10)

# High-level summary
print(f"Overall conversion: {result.overall_conversion_rate:.1%}")
print(f"\nTop transitions:")
for src, tgt, count in result.top_transitions(n=10):
    print(f"  {src} -> {tgt}: {count:,}")

# Drop-off analysis
print(f"\nDrop-off by step:")
for step, info in result.drop_off_summary().items():
    print(f"  {step}: {info['rate']:.0%} ({info['dropoff']:,} / {info['total']:,})")

# NetworkX analysis: which events are gateways?
import networkx as nx
G = result.graph
centrality = nx.betweenness_centrality(G, weight="count")
print(f"\nGateway events:")
for node, score in sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:5]:
    print(f"  {G.nodes[node]['event']}: centrality={score:.3f}")
```

### Example 2: Reverse Flow Investigation

```python
# What leads users to churn (last event before leaving)?
result = ws.query_flow("Cancel Subscription", forward=0, reverse=5, last=90)

# Which events precede cancellation?
edges = result.edges_df
print("Events immediately before cancellation:")
pre_cancel = edges[edges["target_event"] == "Cancel Subscription"]
for _, row in pre_cancel.sort_values("count", ascending=False).iterrows():
    print(f"  {row['source_event']}: {row['count']:,}")
```

### Example 3: Tree Mode Branching Analysis

```python
result = ws.query_flow("Login", forward=4, mode="tree", cardinality=10)

for tree in result.trees:
    print(f"\n=== Flow from {tree.event} ({tree.total_count:,} users) ===")
    print(tree.render())

    # Best conversion path
    paths = tree.all_paths()
    best = max(paths, key=lambda p: p[-1].total_count / p[0].total_count if p[0].total_count else 0)
    rate = best[-1].total_count / best[0].total_count if best[0].total_count else 0
    print(f"\nBest path ({rate:.1%}): {' -> '.join(n.event for n in best)}")

    # Worst drop-offs
    all_nodes = tree.flatten()
    high_dropoff = sorted(
        [n for n in all_nodes if n.drop_off_count > 100],
        key=lambda n: n.drop_off_rate,
        reverse=True,
    )
    if high_dropoff:
        print(f"\nWorst drop-off points:")
        for n in high_dropoff[:5]:
            print(f"  {n.event} (step {n.step_number}): "
                  f"{n.drop_off_rate:.0%} ({n.drop_off_count:,} users)")
```

### Example 4: Filtered Multi-Step Flow

```python
from mixpanel_data import FlowStep, Filter

# Flow for premium users: what happens between login and purchase?
result = ws.query_flow(
    [
        FlowStep("Login", forward=0, reverse=0, filters=[Filter.equals("plan", "premium")]),
        FlowStep("Purchase", forward=0, reverse=3),
    ],
    last=60,
    cardinality=15,
    collapse_repeated=True,
    hidden_events=["$mp_web_page_view", "Session Start", "Session End"],
)

print(f"Premium user flow to purchase ({result.overall_conversion_rate:.1%} conversion)")
print(result.nodes_df.to_string())
```

### Example 5: Saving a Flow as a Bookmark

```python
from mixpanel_data import CreateBookmarkParams

# Build params without executing
params = ws.build_flow_params("Login", forward=5, last=90, cardinality=10)

# Save as a Mixpanel report
ws.create_bookmark(CreateBookmarkParams(
    name="Post-Login User Paths (90d)",
    bookmark_type="flows",
    params=params,
))
```

---

## Validation Rules

### Query-Level Rules (FL*)

| Code | Rule |
|------|------|
| FL1 | At least one step event is required |
| FL2 | Step event name must be non-empty, no control chars, no invisible-only |
| FL3 | `forward` must be 0-5 |
| FL4 | `reverse` must be 0-5 |
| FL5 | At least one of forward/reverse must be nonzero |
| FL6 | `cardinality` must be 1-50 |
| FL7 | `conversion_window` must be positive and within unit max (day:366, week:52, month:12) |
| FL9 | `count_type="session"` requires `conversion_window_unit="session"` |
| FL10 | `conversion_window_unit="session"` requires `conversion_window=1` |

### Bookmark-Level Rules (FLB*)

| Code | Rule |
|------|------|
| FLB1 | Bookmark must have at least one step |
| FLB2 | Step event name must be non-empty |
| FLB3 | `count_type` must be valid |

---

## `build_flow_params()`

Same signature as `query_flow()` but returns the bookmark params dict without making an API call. Useful for debugging, inspecting generated JSON, or passing to `create_bookmark()`.

```python
params = ws.build_flow_params(
    "Login",
    forward=5,
    reverse=2,
    last=90,
    cardinality=10,
    mode="paths",
)
import json
print(json.dumps(params, indent=2))
```

---

## Tips and Gotchas

- **Node keys in graph**: Always `"{event}@{step}"` -- the same event at different steps produces different nodes (e.g., `"Login@0"` vs `"Login@2"`)
- **Tree mode trees**: `result.trees` returns `list[FlowTreeNode]` -- usually one tree per anchor event, but multi-anchor queries may produce multiple trees
- **anytree is optional**: Imported lazily. Install with `pip install anytree` if using `.anytree` or `.to_anytree()`
- **networkx is optional**: Imported lazily. Install with `pip install networkx` if using `.graph`
- **Frozen dataclasses**: Both `FlowStep` and `FlowTreeNode` are frozen (immutable). Build new instances to modify
- **Count strings**: The API returns `totalCount` as strings -- they are parsed to `int` automatically by `nodes_df`, `edges_df`, and `graph`
- **Empty results**: All DataFrame properties return empty DataFrames with correct column names when no data is available
- **Caching**: `nodes_df`, `edges_df`, `graph`, `anytree`, and tree `df` are all lazily computed and cached on first access
