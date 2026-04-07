❯ /mixpanel-data:mixpanel-analyst Tell me about how you think and how you work? What are your principles and methodologies? What tools do you
use? How do you use them? Why? Why should I hire you to help me with my Mixpanel data?

⏺ How I Think

  I'm a code-first analyst. When you ask me a question about your data, I don't point you at dashboards or tell you which buttons to click — I
  write and execute Python code that gets you answers directly.

  My mental model starts with one question: what type of question are you actually asking?

  ┌─────────────────────────────────────────┬────────────────────────────────────────┐
  │           If you're asking...           │             I reach for...             │
  ├─────────────────────────────────────────┼────────────────────────────────────────┤
  │ "How much? How many? What's the trend?" │ Insights — the measurement engine      │
  ├─────────────────────────────────────────┼────────────────────────────────────────┤
  │ "Do users complete this process?"       │ Funnels — the conversion engine        │
  ├─────────────────────────────────────────┼────────────────────────────────────────┤
  │ "Do users come back?"                   │ Retention — the repeat-behavior engine │
  ├─────────────────────────────────────────┼────────────────────────────────────────┤
  │ "What paths do users take?"             │ Flows — the journey engine             │
  ├─────────────────────────────────────────┼────────────────────────────────────────┤
  │ "Why did X change?"                     │ All four, cross-referenced             │
  └─────────────────────────────────────────┴────────────────────────────────────────┘

  Choosing the right engine is the most important decision in any analysis. Get it wrong and you're answering a different question than the one
  that matters.

  How I Work

  1. Discovery first. Before I touch a query, I explore your schema — what events exist, what properties they carry, what values those properties
  take. I never assume I know your data model.

  2. Decompose vague questions. "How is onboarding doing?" isn't a query — it's five queries. I use GQM (Goal-Question-Metric) to break it apart:
  what's the business goal, what specific sub-questions answer it, and which engine + parameters measure each one.

  3. Code over clicks. Every result type has a .df property that gives me a pandas DataFrame. From there I can join across engines, run
  statistical tests with scipy, do graph analysis with NetworkX on flow data, build visualizations with matplotlib — things you can't do inside
    the Mixpanel UI.

  4. Cross-engine synthesis. The real insights live at the intersections. Funnels tell me that conversion dropped; Flows tell me where users went
  instead. Insights tell me a metric changed; Retention tells me whether it's a new-user problem or a returning-user problem. I routinely run all
    four engines in parallel and join the results.

  My Principles

  - Actionable over interesting. I don't just show you a number — I quantify the impact, compare to previous periods, note sample sizes, and
  suggest a concrete next step.
  - Evidence over assumptions. I verify before I claim. Small samples get flagged. Correlations don't get called causation.
  - AARRR as a compass. Every question maps to Acquisition, Activation, Retention, Revenue, or Referral. This keeps analysis tied to business
  outcomes.
  - Reproducibility. Every query I run generates bookmark params you can save as a Mixpanel report, so your analysis lives on after our
  conversation.

  My Toolkit

  ┌────────────────────────┬──────────────────────────────────────────────────────────────────────────────┐
  │          Tool          │                                     Why                                      │
  ├────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
  │ mixpanel_data (Python) │ Typed, validated access to all four query engines + entity management        │
  ├────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
  │ pandas                 │ Every result is a DataFrame — filtering, pivoting, joining                   │
  ├────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
  │ networkx               │ Graph analysis on flow data — bottleneck detection, PageRank, shortest paths │
  ├────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
  │ anytree                │ Tree traversal on flow trees — branching analysis, path ranking              │
  ├────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
  │ scipy / numpy          │ Statistical testing — is this change significant or noise?                   │
  ├────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
  │ matplotlib / seaborn   │ Visualizations saved to files                                                │
  └────────────────────────┴──────────────────────────────────────────────────────────────────────────────┘

  Why Hire Me

  Because I turn "I wonder if..." into a running query in seconds, and "why did X drop?" into a structured multi-engine investigation that traces
  the problem from magnitude to root cause. I work directly against your live Mixpanel data, I know the API signatures cold, and I deliver answers
   — not instructions for how to find them yourself.

  Want to try it? Ask me something about your data.