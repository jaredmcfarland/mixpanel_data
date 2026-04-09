# Mixpanel Infrastructure Cost Analysis

**Date:** 2026-04-09
**Project:** inframetrics (1297132)
**Period:** April 2025 – March 2026 (12 months)
**Showcase Dashboard:** [Infrastructure Cost Optimization Analysis](https://mixpanel.com/project/1297132/view/9017/app/boards#id=11090539)

---

## Executive Summary

Mixpanel's GCP infrastructure costs **~$2M/month** to run, processing **~2.9 trillion events/month** across **~347 million queries/month**. Cost efficiency is improving — **cost per million events dropped 42%** from $1.13 to $0.66 over 12 months despite 50% ingestion growth. However, three areas represent 69% of total spend and offer the highest optimization potential:

| Cost Center | Monthly Spend | % of Total | Key Opportunity |
|---|---|---|---|
| [Compute Engine](https://mixpanel.com/project/1297132/view/9017/app/boards#id=5124636) | **$704K** | 36% | Query LQS nodepools ($335K) dominate; $142K unattributed |
| [Cloud Storage](https://mixpanel.com/project/1297132/view/9017/app/boards#id=1137252) | **$470K** | 24% | Storage team GCS at $393K; garbage collection metrics broken |
| [Cloud Spanner](https://mixpanel.com/project/1297132/view/9017/app/boards#id=5124636) | **$179K** | 9% | Ingestion uses $89K; storage $59K; opportunity in right-sizing |

**Estimated optimization potential: $150K–250K/month** (~8–13% of total spend).

---

## 1. Total GCP Spend

Monthly GCP costs (with all discounts/SUDs/CUDs applied):

| Month | Total Spend | vs. Prior Month |
|---|---|---|
| Oct 2025 | $2,549,801 | — |
| Nov 2025 | $1,869,019 | -27% |
| Dec 2025 | $1,983,553 | +6% |
| Jan 2026 | $2,133,707 | +8% |
| Feb 2026 | $1,580,476 | -26% |
| Mar 2026 | $2,165,609 | +37% |

**Source:** [GCP Costs report](https://mixpanel.com/project/1297132/view/9017/app/boards#id=3641516) (bid=32162167)

Feb is consistently low (shorter month + potential billing cycle effects). The underlying trend is flat at ~$2M/month average.

**CUD/SUD savings:** Without committed-use discounts, Q1 2026 totals ~$6.75M vs $5.82M with CUDs — **CUDs save ~$925K/quarter (~14%)**.

---

## 2. Cost by GCP Service (Top 10)

| Rank | Service | Monthly Spend | % of Total |
|---|---|---|---|
| 1 | **Compute Engine** | $704,231 | 35.6% |
| 2 | **Cloud Storage** | $470,217 | 23.8% |
| 3 | **Cloud Spanner** | $178,737 | 9.0% |
| 4 | **Support** | $115,692 | 5.8% |
| 5 | **Networking** | $80,060 | 4.0% |
| 6 | **BigQuery** | $77,979 | 3.9% |
| 7 | **Cloud Pub/Sub** | $64,026 | 3.2% |
| 8 | **App Engine** | $52,722 | 2.7% |
| 9 | **Cloud Logging** | $48,682 | 2.5% |
| 10 | **Claude Opus 4.6** | $33,050 | 1.7% |

**Source:** [Spend By Cloud Service](https://mixpanel.com/project/1297132/view/9017/app/boards#id=5124636) (bid=40800543)

**Notable:** AI/LLM spending is emerging — Claude models (Opus 4.6: $33K, Sonnet 4.5: $3.3K, Haiku 4.5: $1.5K, Opus 4.5: $852, Sonnet 4.6: $884, Opus 4.1: $798) total ~$40K/month. Vertex AI adds another $11K. Total AI spend: **~$51K/month** and likely growing.

---

## 3. Cost by Team

| Team | Monthly Spend | % of Total | Top Services |
|---|---|---|---|
| **Storage** | $594,478 | 27% | GCS ($393K), Spanner ($59K), Compute ($30K) |
| **Query** | $377,750 | 17% | Compute ($344K) |
| **OpEx** | $283,556 | 13% | Compute ($123K), Spanner ($8K) |
| **Ingestion** | $296,087 | 13% | Spanner ($89K), Compute ($52K) |
| **Support** | $128,000 | 6% | Support contract |
| **DWE** | $114,133 | 5% | Compute ($69K), GCS ($35K) |
| **Product** | $121,451 | 5% | Compute ($59K) |
| **Other prod** | $106,724 | 5% | Spanner ($21K), GCS ($26K) |

**Source:** [Spend By Team](https://mixpanel.com/project/1297132/view/9017/app/boards#id=5124636) (bid=40800145)

**Regional breakdown:** US accounts for 85% ($1.84M), EU for 11% ($232K), IN for 4% ($99K).

---

## 4. Compute Engine Deep Dive ($704K/month)

### By Team

| Team | Compute Spend | Top Nodepools |
|---|---|---|
| **Query** | $343,645 (49%) | `arb-lqs` $204K, `arb-lqs-hv` $131K |
| **OpEx** | $122,893 (17%) | `null` $81K, `cis-workers` $22K, `github-actions` $7K |
| **DWE** | $68,925 (10%) | `null` $32K, `dwe-transformer` $14K, `dwe-worker-pipelines` $14K |
| **Product** | $58,976 (8%) | `null` $22K, `webapp-and-query-api` $13K |
| **Ingestion** | $52,301 (7%) | `remap-ingestion` $18K, `api-ingestion` $13K |
| **Storage** | $29,791 (4%) | `arb-storage` $15K, `arb-manifester-query` $3K |

**Source:** [Compute Engine Spend By Nodepool](https://mixpanel.com/project/1297132/view/9017/app/boards#id=5124636) (bid=40800804)

### Key Finding: $142K in Unattributed "null" Compute

Across teams, **$142K/month** of Compute Engine spend has `nodepool=null` — meaning it's not attributed to any specific nodepool/workload:
- OpEx null: $81K
- DWE null: $32K
- Product null: $22K
- Other: $7K

**Opportunity:** Attributing these costs to specific workloads would reveal whether they're necessary or represent idle/orphaned resources.

### Query LQS: $335K/month on Two Nodepools

The query system's Local Query Service (LQS) dominates compute:
- `arb-lqs`: $204K — primary query execution pool
- `arb-lqs-hv`: $131K — high-volume query execution pool

**Source code context:** `analytics/go/src/mixpanel.com/arb/dqs/metrics/dqs_metrics.go` — the DQS tracks every query with 281 properties including `lqs_events_scanned`, `lqs_total_cpu_ms`, `lqs_gcs_load_bytes`, cache hit/miss rates. The `dqs-query` event is emitted from `analytics/go/src/mixpanel.com/arb/dqs/service.go`.

**Query efficiency metrics:**
- Monthly queries: ~347M (Mar 2026)
- Monthly events scanned: ~13.5 quadrillion
- Events per query: ~39M average
- Query volume growing +5.3% MoM
- Funnel queries are **2.4x more CPU-intensive** per event than Insights queries (4.5M vs 10.8M events/CPU-sec at P90)
- p99 latency: 33–69s, highly variable (weekdays higher)

---

## 5. Cloud Storage Analysis ($470K/month)

### By Team

| Team | GCS Spend | % |
|---|---|---|
| **Storage** | $392,860 | 84% |
| **DWE** | $34,746 | 7% |
| **Other prod** | $25,730 | 5% |
| **Other non-prod** | $6,180 | 1% |
| **Ingestion** | $3,997 | 1% |

**Source:** [Cloud Storage Spend by Team](https://mixpanel.com/project/1297132/view/9017/app/boards#id=5124636) (bid=40800761)

### Storage Weekly Cost Breakdown

| Component | Weekly Cost | Monthly (est.) | % |
|---|---|---|---|
| **GCS Costs** | $84,204 | $337K | 60% |
| **Other Costs** | $35,381 | $142K | 25% |
| **Spanner Costs** | $11,529 | $46K | 8% |
| **GCS Backup Costs** | $9,182 | $37K | 7% |
| **Instance Costs** | $7,230 | $29K | 5% |

**Source:** [Storage Server Weekly Costs Summary](https://mixpanel.com/project/1297132/view/9017/app/boards#id=1137252) (bid=13713283)

### Broken Monitoring: Data Stored & GCS Usage Reports Return Zeros

Two critical reports are returning all-zero data:
- **Data Stored (in Petabytes)** (bid=32162685) — all zeros
- **GCS Data Usage** (bid=26972885) — all zeros

These rely on the `storage-usage` event with custom properties (`gcs_bytes`, `pdssd_bytes`). The event has **0 properties in Lexicon**, suggesting the tracking pipeline may have stopped or the properties were dropped. **This is a monitoring gap** — you can't optimize storage without knowing how much data you're storing.

**Source code context:** The `storage-usage` event tracking call site was **not found** in the Go/Python source code. The source searcher confirmed no dedicated event emitter exists in the codebase. This event was likely tracked from an external cron or ETL job that has stopped functioning. Related cost metrics exist in `analytics/tools/costs/ingestion/` but don't feed this event.

**Write amplification** (from `event-compaction`): Ranges 10x–37x, averaging ~18x. Weekend compaction runs cause spikes (36.6x on Apr 6). Compaction events are **sampled at 10%** (`inSample()` in `arb/compaction/binary/event_compacter.go:350`).

---

## 6. Cloud Spanner ($179K/month)

| Team | Spanner Spend | % |
|---|---|---|
| **Ingestion** | $89,339 | 50% |
| **Storage** | $58,532 | 33% |
| **Other prod** | $20,569 | 12% |
| **OpEx** | $8,336 | 5% |
| **Product** | $1,260 | <1% |

**Source:** [Spanner Spend By Team](https://mixpanel.com/project/1297132/view/9017/app/boards#id=5124636) (bid=40800768)

Ingestion's $89K Spanner spend is likely identity management (ID mapping tables). The `IDM-LookupAndUpdate` event (17.8M/month, -7.3%) and `IDM-Identify` (2.1M/month, -14.3%) suggest heavy ID management workloads. Right-sizing Spanner nodes based on actual throughput needs could yield savings.

---

## 7. Cost Efficiency Trends

### Cost Per Million Events — 42% Improvement

| Month | $/M Events | Trend |
|---|---|---|
| Apr 2025 | $1.13 | — |
| Jul 2025 | $0.90 | -20% |
| Oct 2025 | $0.98 | +9% (seasonal) |
| Jan 2026 | $0.76 | -22% |
| Mar 2026 | $0.66 | -13% |

**Source:** [Cost Per Million Events](https://mixpanel.com/project/1297132/view/9017/app/boards#id=3641516) (bid=32162279)

### Ingestion Volume — 50% Growth

| Month | Events Ingested |
|---|---|
| Apr 2025 | 1.90T |
| Aug 2025 | 2.72T (peak) |
| Mar 2026 | 2.86T (new peak) |

**Source:** [Ingestion Volume](https://mixpanel.com/project/1297132/view/9017/app/boards#id=3641516) (bid=32126488)

### Ingestion by Source

| Source | Monthly Events | % |
|---|---|---|
| Server-Side | 1.06T | 53% |
| Mobile SDKs | 682B | 34% |
| Web SDKs | 154B | 8% |
| Segment | 85B | 4% |
| Rudderstack | 13B | <1% |

**Source:** [Event Volume by Ingestion Source](https://mixpanel.com/project/1297132/view/9017/app/boards#id=3641516) (bid=32322695)

---

## 8. CPU Usage & Query Efficiency

The [CPU usage deepdive](https://mixpanel.com/project/1297132/view/9017/app/boards#id=985461) dashboard tracks events-scanned-per-CPU-second, a key efficiency metric for the query system.

**Source code context:** `analytics/go/src/mixpanel.com/arb/lqs/executor/executor.go` — the LQS executor tracks CPU time per query via `lqs_total_cpu_ms` and `lqs_events_scanned`. The `dqs-query` event combines these into an `events per cpu-sec` custom property.

**Key CPU properties tracked:**
- `lqs_total_cpu_ms` — total CPU milliseconds per query
- `lqs_events_scanned` — events scanned per query
- `lqs_gcs_load_bytes` — GCS bytes loaded from storage
- `lqs_cache_hits` / `lqs_cache_misses` — query cache performance
- `dqs_merger_total_cpu_ms` — DQS merger CPU

The cache hit/miss metrics are particularly interesting — improved caching directly reduces both CPU and GCS I/O costs.

---

## 9. Top Optimization Opportunities

### Opportunity 1: Attribute $142K/month in "null" Compute (Estimated: $30–70K savings)

**$142K/month** of Compute Engine costs have `nodepool=null`. Some of this is likely idle or orphaned capacity. Attributing these costs to specific workloads would:
- Reveal idle resources that can be downscaled
- Identify workloads that should be on spot/preemptible instances
- Enable team-level cost accountability

**Action:** Update the cost attribution pipeline in `analytics/go/src/mixpanel.com/sre/metrics-cost-tracker/main.go` to tag unattributed compute.

### Opportunity 2: Optimize LQS Query Nodepools ($335K → target $270K, save $65K)

Query LQS spends $335K/month on two nodepools. The `dqs-query` event tracks cache hit rates, events scanned, and CPU per query. Analysis opportunities:
- **Cache hit optimization** — `lqs_cache_hits` vs `lqs_cache_misses` ratio improvements could reduce redundant GCS loads
- **Spot instance migration** — `arb-lqs` workloads may tolerate preemption for batch/non-interactive queries
- **Right-sizing** — correlate `lqs_total_cpu_ms` distribution with instance types to identify over-provisioning

**Action:** Build a query efficiency report from `dqs-query` breaking down cache hit rates and CPU utilization per nodepool.

### Opportunity 3: Fix Broken Storage Monitoring (Enable $50K+ savings discovery)

The `storage-usage` event has stopped reporting `gcs_bytes` and `pdssd_bytes`. Without this data:
- Can't measure GCS garbage ratio (live data vs. garbage waiting for collection)
- Can't track storage growth rate
- Can't identify projects with disproportionate storage footprints

**Action:** Investigate why `storage-usage` event properties are empty. Check the ETL/cron job that feeds this data.

### Opportunity 4: Reduce Cloud Logging Costs ($49K/month)

Cloud Logging at $49K/month is a common over-spend area. Typical optimizations:
- Reduce log verbosity for high-volume services
- Route logs to cheaper storage tiers after 7 days
- Filter out health-check and heartbeat logs at ingestion

### Opportunity 5: Evaluate Support Contract ($116K/month)

$116K/month (6% of total) on GCP Support seems high. Evaluate whether the current support tier is fully utilized or if a lower tier would suffice.

### Opportunity 6: Right-Size Spanner for Ingestion ($89K/month)

Ingestion's Spanner spend ($89K) is for identity management. With `IDM-LookupAndUpdate` volume declining 7.3%, there may be room to reduce Spanner nodes or move to a more cost-effective solution for ID mapping.

---

## 10. Source Code Context

| Event | Source File | Line | Key Properties | Status |
|---|---|---|---|---|
| `track_events` | `go/src/mixpanel.com/ingestion/remap/configs/tracking.go` | 67 | pre_sampling, post_sampling, project_id | Active |
| `track_events` | `go/src/mixpanel.com/perf/crons/cmd/per-project-costs/main.go` | 70 | Used in cost calculation queries | Active |
| `dqs-query` | `go/src/mixpanel.com/arb/dqs/metrics/dqs_metrics.go` | 30, 541 | lqs_events_scanned, lqs_total_cpu_ms, merger metrics (281 props) | Active |
| `dwe_run` | `go/src/mixpanel.com/dwe/worker/scheduler/metrics.go` | 138 | job, task, latency, success, error details | Active |
| `event-compaction` | `go/src/mixpanel.com/arb/compaction/binary/event_compacter.go` | 271 | rusage metrics, duplicates, num_events | Active (10% sampled) |
| `gcp-billing` | `go/src/mixpanel.com/sre/metrics-cost-tracker/main.go` | 82 | gcp_project, cluster, cost (tracks as "metric-cost") | Active |
| `storage-usage` | Not found in source tree | — | gcs_bytes, pdssd_bytes | **Broken** |

**Inframetrics client:** `go/src/mixpanel.com/inframetrics/client.go` — central token management for project 1297132.

**Tracking infrastructure:** `go/src/mixpanel.com/obs/mixpanel/track_metrics.go` — `MetricsTracker` base class with retries and insert_id generation.

---

## 11. Methodology

This analysis was performed using `mixpanel_data` Python library to:
1. Read all 4 source dashboards via `ws.get_dashboard()` — extracting layout, contents, and report params
2. Execute all 34 saved reports via `ws.query_saved_report()` — converting results to pandas DataFrames
3. Cross-reference event names with Mixpanel analytics source code at `analytics/`
4. Resolve custom event IDs to human-readable names via `ws.list_custom_events()`
5. Query event property schemas via `ws.properties()` for Lexicon metadata

**Source Dashboards:**
- [Intro to Mixpanel Infra Metrics](https://mixpanel.com/project/1297132/view/9017/app/boards#id=3641516) — 10 reports, high-level overview
- [Understanding Unit Costs](https://mixpanel.com/project/1297132/view/9017/app/boards#id=5124636) — 10 reports, team/service breakdowns
- [Storage Server Costs](https://mixpanel.com/project/1297132/view/9017/app/boards#id=1137252) — 6 reports, storage deep dive
- [CPU usage deepdive](https://mixpanel.com/project/1297132/view/9017/app/boards#id=985461) — 8 reports, query CPU efficiency
