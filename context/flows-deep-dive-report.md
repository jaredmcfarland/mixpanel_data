# Mixpanel Flows Report: Deep Dive & Graph Representation Analysis

## 1. What Is the Flows Report?

Flows identifies the **most frequent paths users take to or from any event**. It answers questions like:

- What do users do *after* signing up?
- What paths lead *to* a purchase?
- Where do users drop off between key actions?
- How do different segments (device, cohort, region) navigate differently?

It's the **discovery** complement to Funnels: Funnels measure conversion through a path *you define*; Flows discovers what paths users *actually take*.

### Two Visualization Modes

| Mode | What It Shows | API `query_type` |
|------|--------------|-----------------|
| **Sankey diagram** | Multi-branching visual of all paths, bar heights = user counts, connector widths = sequential users | `flows_sankey` |
| **Top Paths** | The 50 most common event sequences as rows, with conversion % between each step | `flows_top_paths` |

### Key Use Cases

1. **User journey discovery** — See actual behavior before/after key events
2. **Friction identification** — Large drop-off bars reveal UX problems
3. **Conversion path optimization** — Find and streamline the most common path to goal
4. **Segment comparison** — Break down by cohort to see how different user groups navigate
5. **Funnel drop-off investigation** — "View as Flow" from a funnel step to see what dropped-off users did instead

---

## 2. The API

### Endpoint

```
GET /api/2.0/arb_funnels
```

The Flows API **piggybacks on the funnels endpoint** (`arb_funnels`) with a different `query_type`. This is an internal/undocumented endpoint — Mixpanel does **not** expose a public Flows API.

### Request Parameters

```python
{
    "query_type": "flows_sankey",       # or "flows_top_paths" or legacy "flows"
    "bookmark_id": 12345678,            # saved report ID
    # OR inline bookmark params:
    "bookmark": {
        "steps": [
            {"event": "Login", "forward": 3, "reverse": 0},
            {"event": "Purchase", "forward": 0}
        ],
        "flows_merge_type": "graph",    # "graph" for sankey, "list" for top paths
        "date_range": {
            "type": "between",          # or "in the last"
            "from_date": "2025-01-01",
            "to_date": "2025-01-31"
        },
        "chartType": "sankey",          # or "paths"
        "count_type": "unique",         # "unique" | "total" | "session"
        "cardinality_threshold": 10,
        "version": 2,
        # Optional:
        "conversion_window": {"unit": "day", "value": 30},
        "exclusions": [...],            # events to exclude
        "hidden_events": [...],         # events to hide from display
        "group_by": [...],              # breakdown properties
        "segments": [...],              # segment definitions
        "filter_by_event": {...},       # pre-filters
        "filter_by_cohort": "...",      # cohort filter
        "collapse_repeated": true,      # merge consecutive duplicates
        "unique_flows": true,           # one path per user
        "show_custom_events": true,     # include custom events
        "time_percentiles_enabled": true # add timing data
    }
}
```

### Current mixpanel_data Implementation

```python
# api_client.py — uses bookmark_id only (no inline params yet)
def query_flows(self, bookmark_id: int) -> dict[str, Any]:
    url = self._build_url("query", "/arb_funnels")
    params = {"bookmark_id": bookmark_id, "query_type": "flows_sankey"}
    return self._request("GET", url, params=params)
```

---

## 3. Response Data Structure (The Graph)

### 3.1 Sankey Response (`FlowsSankeyResponse`)

This is the critical structure. It's a **directed acyclic graph** encoded as an adjacency list within a step-based layout:

```typescript
interface FlowsSankeyResponse {
    computed_at: string;
    metadata: { min_sampling_factor: number };
    breakdowns: Breakdown[];              // top-level breakdown data
    steps: SankeyStep[];                  // THE GRAPH
}

interface SankeyStep {
    nodes: SankeyNode[];                  // nodes at this step position
}

interface SankeyNode {
    event: string;                        // event name (e.g., "Login")
    type: "ANCHOR" | "NORMAL" | "DROPOFF" | "PRUNED" | "FORWARD" | "REVERSE";
    anchorType: "NORMAL" | "RELATIVE_REVERSE" | "RELATIVE_FORWARD";
    totalCount: string;                   // user count (string!)
    isComputed: boolean;                  // is a computed/custom event?
    isCustomEvent: boolean;
    segments: Segment[];                  // segment property values
    conversionRateChange?: number;        // lift vs. anchor step
    breakdowns: Breakdown[];              // per-segment counts
    edges: SankeyEdge[];                  // OUTGOING EDGES → next step
}

interface SankeyEdge {
    event: string;                        // target event name
    type: "ANCHOR" | "NORMAL" | "DROPOFF" | "PRUNED" | "FORWARD" | "REVERSE";
    anchorType: "NORMAL" | "RELATIVE_REVERSE" | "RELATIVE_FORWARD";
    step: number;                         // target step index
    totalCount: string;                   // users taking this transition
    isComputed: boolean;
    segments: Segment[];
    breakdowns: Breakdown[];
}

interface Segment {
    label: string;
    value: string;
    values: string[];
}

interface Breakdown {
    segments: Segment[];
    totalCount: string;
    timePercentilesFromPrev: number[];     // timing data (when enabled)
    timePercentilesFromStart: number[];
}
```

### 3.2 Visual Mapping

```
Step 0              Step 1              Step 2              Step 3
┌──────────┐        ┌──────────┐        ┌──────────┐        ┌──────────┐
│ Login    │──edge──▶│ Search   │──edge──▶│ View Item│──edge──▶│ Purchase │
│ (ANCHOR) │        │ (NORMAL) │        │ (NORMAL) │        │ (ANCHOR) │
│ count=100│        │ count=80 │        │ count=50 │        │ count=30 │
├──────────┤        ├──────────┤        ├──────────┤        ├──────────┤
│          │──edge──▶│ Browse   │──edge──▶│ DROPOFF  │        │ DROPOFF  │
│          │        │ (NORMAL) │        │ count=30 │        │ count=20 │
│          │        │ count=20 │        └──────────┘        └──────────┘
│          │        ├──────────┤
│          │──edge──▶│ DROPOFF  │
│          │        │ count=0  │
└──────────┘        └──────────┘
```

**Key insight**: The response is already a graph! Each node has outgoing `edges` pointing to nodes in the next step. The `steps` array provides the positional layout (x-axis), and `nodes` within a step provide the vertical layout (y-axis, ordered by count).

### 3.3 Top Paths Response (`FlowsTopPathsResponse`)

A simpler structure — just lists of paths:

```typescript
interface FlowsTopPathsResponse {
    computed_at: string;
    metadata: { min_sampling_factor: number };
    flows: TopPathsFlow[];               // list of paths
}

interface TopPathsFlow {
    flowSteps: TopPathsFlowStep[];       // ordered events in this path
    segments: TopPathsFlowSegment[];     // segment values for this path
}

interface TopPathsFlowStep {
    event: string;
    type: "ANCHOR" | "NORMAL" | "DROPOFF" | ...;
    isComputed: boolean;
    totalCount: string;
    segments?: TopPathsFlowSegment[];
}
```

### 3.4 Node Type Semantics

| Type | Meaning |
|------|---------|
| `ANCHOR` | User-specified event in the query (the "waypoints") |
| `NORMAL` | Intermediate event discovered by the algorithm |
| `FORWARD` | Event appearing in forward direction from anchor |
| `REVERSE` | Event appearing in reverse direction from anchor |
| `DROPOFF` | Terminal node — user stopped / left the flow |
| `PRUNED` | Low-frequency events merged into "Other" |

---

## 4. Current `FlowsResult` Implementation

The current implementation in `types.py` is **minimal** — it stores `steps` and `breakdowns` as raw `list[dict[str, Any]]`:

```python
@dataclass(frozen=True)
class FlowsResult(ResultWithDataFrame):
    bookmark_id: int
    computed_at: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    breakdowns: list[dict[str, Any]] = field(default_factory=list)
    overall_conversion_rate: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def df(self) -> pd.DataFrame:
        # Just dumps steps list into a DataFrame
        return pd.DataFrame(self.steps) if self.steps else pd.DataFrame()
```

**Problems with the current DataFrame representation**:
1. `pd.DataFrame(self.steps)` creates one row per step with a `nodes` column containing nested dicts — not useful
2. No edge information is surfaced
3. The graph structure is completely lost
4. Can't answer basic questions like "what percentage of users go from Login to Purchase?"

---

## 5. Should We Add a Graph Representation?

### 5.1 The Case FOR a Graph Library

**The data IS a graph.** The Sankey response encodes a directed acyclic graph with weighted edges. Natural graph operations include:

| Operation | Graph Library | Raw dicts | Pandas |
|-----------|:------------:|:---------:|:------:|
| Find all paths from A to B | Trivial | Manual BFS/DFS | Not natural |
| Calculate max flow | Built-in | Write from scratch | No |
| Find bottleneck edges | Built-in | Manual | Awkward |
| Subgraph extraction | Built-in | Manual | No |
| Node degree analysis | Built-in | Manual | No |
| Reachability queries | Built-in | Manual BFS | No |
| Shortest path | Built-in | Dijkstra from scratch | No |
| Community detection | Built-in | No | No |

**Concrete useful queries a graph enables:**

```python
# "What's the highest-traffic path from Login to Purchase?"
nx.shortest_path(G, "Login@0", "Purchase@3", weight=lambda u,v,d: -d['count'])

# "What events are reachable from Signup within 2 steps?"
nx.ego_graph(G, "Signup@0", radius=2)

# "Which transition has the biggest drop-off?"
min(G.edges(data=True), key=lambda e: e[2]['count'] / G.nodes[e[0]]['count'])

# "What's the total flow through Search?"
sum(d['count'] for _, _, d in G.in_edges("Search@1", data=True))
```

### 5.2 Why NetworkX as a Hard Dependency

**NetworkX is the right choice**, and as a hard (not optional) dependency:

| Factor | NetworkX | Verdict |
|--------|----------|---------|
| **Install size** | 2.1 MB wheel | Lighter than httpx, pydantic, rich, or pandas — all already required |
| **Runtime deps** | **Zero** | No numpy, no scipy, nothing pulled in transitively |
| **Platform** | Pure Python (`py3-none-any`) | No compiler, no platform-specific wheels, works everywhere |
| **API** | Best-in-class, huge community | Users most likely to already know it |
| **Performance** | "Slow" (pure Python) | Irrelevant — Flows graphs have <50 nodes |

**Why NOT the alternatives:**
- **rustworkx** (~5MB, compiled Rust wheels) — overkill, platform-specific builds
- **igraph** (~10MB, C backend) — heavier install, less Pythonic API
- **graph-tool** (100MB+, system deps) — completely impractical for a PyPI library
- **No library** (dict-based) — forces users to reimplement graph traversal

### 5.3 Recommendation: NetworkX Graph + Better DataFrames

**Add `networkx>=3.0` as a required dependency.** The `FlowsResult` should provide three complementary views of the data:

#### A. Fix the DataFrame representation

The current `pd.DataFrame(self.steps)` is nearly useless. Instead, provide two meaningful DataFrames:

```python
@property
def nodes_df(self) -> pd.DataFrame:
    """DataFrame of all nodes: step, event, type, count, conversion_rate_change."""
    rows = []
    for step_idx, step in enumerate(self.steps):
        for node in step.get("nodes", []):
            rows.append({
                "step": step_idx,
                "event": node.get("event", ""),
                "type": node.get("type", ""),
                "anchor_type": node.get("anchorType", ""),
                "count": int(node.get("totalCount", "0")),
                "is_custom_event": node.get("isCustomEvent", False),
                "conversion_rate_change": node.get("conversionRateChange"),
            })
    return pd.DataFrame(rows)

@property
def edges_df(self) -> pd.DataFrame:
    """DataFrame of all edges: source_step, source_event, target_step, target_event, count."""
    rows = []
    for step_idx, step in enumerate(self.steps):
        for node in step.get("nodes", []):
            source = node.get("event", "")
            for edge in node.get("edges", []):
                rows.append({
                    "source_step": step_idx,
                    "source_event": source,
                    "target_step": edge.get("step", step_idx + 1),
                    "target_event": edge.get("event", ""),
                    "count": int(edge.get("totalCount", "0")),
                    "target_type": edge.get("type", ""),
                })
    return pd.DataFrame(rows)
```

This is **immediately useful** for pandas-native analysis:

```python
result = ws.query_flows(bookmark_id=12345)

# Top transitions by volume
result.edges_df.sort_values("count", ascending=False).head(10)

# Drop-off rates per step
dropoffs = result.nodes_df[result.nodes_df["type"] == "DROPOFF"]

# Events at step 2
result.nodes_df[result.nodes_df["step"] == 2]
```

#### B. Provide a lazily-cached `graph` property (NetworkX DiGraph)

```python
@property
def graph(self) -> nx.DiGraph:
    """Lazily-built NetworkX directed graph of the flow.

    Each node is keyed as '{event}@{step}' to handle the same
    event appearing at multiple steps. Node attributes include
    count, type, and breakdowns. Edge attributes include count.

    Built once on first access and cached (same pattern as df).
    """
    if self._graph_cache is not None:
        return self._graph_cache

    import networkx as nx

    G = nx.DiGraph()
    for step_idx, step in enumerate(self.steps):
        for node in step.get("nodes", []):
            node_id = f"{node['event']}@{step_idx}"
            G.add_node(node_id,
                step=step_idx,
                event=node["event"],
                type=node.get("type", ""),
                count=int(node.get("totalCount", "0")),
                anchor_type=node.get("anchorType", ""),
                is_custom_event=node.get("isCustomEvent", False),
                conversion_rate_change=node.get("conversionRateChange"),
                breakdowns=node.get("breakdowns", []),
            )
            for edge in node.get("edges", []):
                target_id = f"{edge['event']}@{edge.get('step', step_idx + 1)}"
                G.add_edge(node_id, target_id,
                    count=int(edge.get("totalCount", "0")),
                    type=edge.get("type", ""),
                    breakdowns=edge.get("breakdowns", []),
                )

    object.__setattr__(self, "_graph_cache", G)
    return G
```

**What this unlocks for users:**

```python
result = ws.query_flows(bookmark_id=12345)
G = result.graph

# --- Path Analysis ---
# All paths from Login to Purchase
list(nx.all_simple_paths(G, "Login@0", "Purchase@3"))

# Highest-traffic path (weighted shortest path)
nx.shortest_path(G, "Login@0", "Purchase@3",
                 weight=lambda u,v,d: -d['count'])

# Events reachable within 2 steps of Signup
nx.ego_graph(G, "Signup@0", radius=2)

# Is there ANY path between two events?
nx.has_path(G, "Signup@0", "Purchase@3")

# --- Bottleneck & Drop-off Analysis ---
# Which transition loses the most users?
edges = [(u, v, d['count']) for u, v, d in G.edges(data=True)]
sorted(edges, key=lambda e: e[2])[:5]

# Drop-off ratio per node
for node, data in G.nodes(data=True):
    if data['type'] != 'DROPOFF':
        outflow = sum(d['count'] for _, _, d in G.out_edges(node, data=True))
        ratio = outflow / data['count'] if data['count'] else 0
        print(f"{node}: {ratio:.0%} retained")

# --- Subgraph Extraction ---
# Only high-traffic edges (>100 users)
heavy = nx.DiGraph((u,v,d) for u,v,d in G.edges(data=True) if d['count'] > 100)

# --- Graph Metrics ---
# Fan-out: which events branch most?
sorted(G.nodes(), key=lambda n: G.out_degree(n), reverse=True)

# Topological ordering (natural step sequence)
list(nx.topological_sort(G))

# --- Export to Visualization Tools ---
# D3.js-compatible JSON
from networkx.readwrite import json_graph
json_graph.node_link_data(G)

# Graphviz DOT format
nx.drawing.nx_pydot.write_dot(G, "flows.dot")
```

#### C. Provide high-level convenience methods

Built on top of the graph, these give quick answers without graph API knowledge:

```python
def paths(self, from_event: str | None = None, to_event: str | None = None) -> list[list[dict]]:
    """Extract all paths, optionally filtered by start/end event."""

def top_transitions(self, n: int = 10) -> list[tuple[str, str, int]]:
    """Return the N highest-traffic (source, target, count) transitions."""

def drop_off_summary(self) -> dict[str, Any]:
    """Per-step drop-off counts and percentages."""

def step_events(self, step: int) -> list[dict[str, Any]]:
    """Events at a given step with counts and types."""
```

---

## 6. Final Recommendation Summary

| Component | Action | Priority |
|-----------|--------|----------|
| **`networkx>=3.0`** | Add as hard dependency in `pyproject.toml` | **High** — enables everything below |
| **`.graph` property** | Lazily-cached `DiGraph` on `FlowsResult` | **High** — the natural representation |
| **`nodes_df` / `edges_df`** | Add as properties on `FlowsResult` | **High** — fixes the broken DataFrame |
| **Convenience methods** | `top_transitions()`, `drop_off_summary()`, `paths()` | **Medium** — quick answers without graph API knowledge |
| **rustworkx/igraph** | Don't do this — overkill for <50 nodes | N/A |

### Why This Isn't Overengineering

1. **The data IS a graph** — the Sankey response is literally a DAG with nodes and edges. Representing it as a graph is semantically correct, not an abstraction we're imposing.
2. **NetworkX costs almost nothing** — 2.1 MB, zero deps, pure Python. It's lighter than most things already in the project.
3. **It unlocks real value** — path queries, bottleneck analysis, subgraph extraction, and export to visualization tools are all one-liners with NetworkX but would require manual BFS/DFS implementations without it.
4. **The current DataFrame is broken** — `pd.DataFrame(self.steps)` produces a useless table. We need to fix this regardless.
5. **Three complementary views serve different users** — `.graph` for traversal/path queries, `.nodes_df`/`.edges_df` for pandas filtering/aggregation, convenience methods for quick answers.

### What WOULD Be Overengineering

- Building a custom graph library instead of using NetworkX
- Supporting multiple graph library backends
- Adding visualization/rendering capabilities to FlowsResult
- Wrapping every NetworkX algorithm in a convenience method
- Using a compiled graph library (rustworkx, igraph) for <50 nodes

---

## 7. Top Paths Representation

For the `FlowsTopPathsResponse`, a DataFrame is actually the natural representation:

```python
@property
def paths_df(self) -> pd.DataFrame:
    """For top-paths mode: each row is one path with step columns."""
    rows = []
    for flow in self.flows:
        row = {}
        for i, step in enumerate(flow.get("flowSteps", [])):
            row[f"step_{i}_event"] = step.get("event", "")
            row[f"step_{i}_count"] = int(step.get("totalCount", "0"))
            row[f"step_{i}_type"] = step.get("type", "")
        rows.append(row)
    return pd.DataFrame(rows)
```

No graph representation needed for top paths — it's already tabular.

### 7.2 Tree Response (Third Merge Type)

The Go backend also supports a **tree** merge type (`flows_merge_type: "tree"`), which returns a recursive tree structure:

```typescript
interface FlowsTreeResponse {
    trees: Tree[];
    has_time_percentiles: boolean;
    time_percentile_phis: number[];
    num_time_buckets: number;
}

interface Tree {
    root: MergeableFlowNode;    // recursive tree
    num_steps: number;
    segments: { segments: Segment[] };
}

interface MergeableFlowNode {
    step: {
        type: string;           // NORMAL, ANCHOR, DROPOFF, etc.
        step_number: number;
        event: string;
        segments: Segment[];
        is_computed: boolean;
        anchor_type: string;
    };
    children: MergeableFlowNode[];     // recursive!
    total_count: number;
    time_percentiles_from_start: { percentiles: number[], values: number[] };
    time_percentiles_from_prev: { ... };
    drop_off_total_count: number;
    converted_total_count: number;
}
```

This is less commonly used but represents another valid data model. For the Python library, we should focus on the graph (sankey) and list (top-paths) responses since those are what the UI primarily uses.

---

## 8. Implementation Notes

### Inline Query Support

The current `query_flows()` only supports `bookmark_id`. For feature parity, it should also support inline parameters (building the bookmark dict directly), similar to how `query_segmentation()` accepts parameters. The bookmark structure is:

```python
{
    "steps": [{"event": "Login", "forward": 3, "reverse": 0}],
    "flows_merge_type": "graph",  # "graph" for sankey, "list" for top paths
    "date_range": {"type": "between", "from_date": "...", "to_date": "..."},
    "chartType": "sankey",
    "count_type": "unique",
    "cardinality_threshold": 10,
    "version": 2,
}
```

### Dual Response Types

The API returns different structures for sankey vs top-paths. The `FlowsResult` type should handle both, or there should be separate result types. Given that sankey has `steps[].nodes[].edges[]` and top-paths has `flows[].flowSteps[]`, these are structurally different enough that dual types may be warranted:
- `FlowsSankeyResult` — graph-oriented with `nodes_df`, `edges_df`, `to_networkx()`
- `FlowsTopPathsResult` — tabular with `paths_df`

Or keep one `FlowsResult` with mode-aware properties.

---

## Sources

- [Mixpanel Flows Documentation](https://docs.mixpanel.com/docs/reports/flows)
- [Mixpanel Query API Reference](https://developer.mixpanel.com/reference/query-api)
- [Mixpanel User Flow Analysis Blog](https://mixpanel.com/blog/user-flow-analysis/)
- [rustworkx Benchmarks](https://www.rustworkx.org/benchmarks.html)
- [2025 SNA Tools Comparison (Springer)](https://link.springer.com/article/10.1007/s13278-025-01409-y)
- Analytics codebase: `api/version_2_0/arb_funnels/format_flows.py`, `test_flows.py`, `flows_utils.py`
- Frontend types: `iron/common/report/funnels/models/api-types.ts`, `iron/common/widgets/sankey-chart/models/serialized.ts`
