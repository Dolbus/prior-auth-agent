# Prior Auth AgentOps — Interview Prep & Project Narrative

Use this file when preparing to talk about this project in interviews, LinkedIn posts, or demos.
The story is structured as: problem found → dominant error → experiment → result → new errors → repeat.

---

## One-sentence summary
> Built a multi-agent AI system for healthcare prior authorization, then ran 10 controlled experiments on a locked evaluation dataset to systematically improve accuracy from a broken prototype to 70% — using structured audits and deterministic Python, not prompt tweaking.

---

## The architecture (what you built)

A LangGraph multi-agent workflow with 5 nodes and 4 supervisor gates:

1. **Eligibility gate** — rule-based lookup: does this drug/insurer combination even require prior auth?
2. **Research agent** — extracts diagnosis, medications, labs, prior treatment history from patient record
3. **Gate 2 check** — supervisor validates: did the research agent get all required fields?
4. **Rules checker agent** — matches patient case against insurer's coverage criteria (step therapy, lab thresholds, contraindications)
5. **Gate 3 check** — supervisor validates: were the correct rules applied? Step therapy checked?
6. **Writer agent** — generates the PA form and clinical justification document
7. **Gate 4 check** — supervisor validates: is the document complete? Guard rails passed?
8. **HITL gate** — human-in-the-loop review (auto mode or review mode)
9. **Payer decision handling** — APPROVED / DENIED / NEEDS_MORE_INFO, with downstream actions for each

The architecture evolved across the project. Three versions:
- **v1 (Baseline–Exp 5):** Pure LLM pipeline — everything goes through the model
- **v2 (Exp 6d.1+):** Python deterministic gate added before the LLM rules checker
- **v3 (Exp 10+):** Python gate extended to handle zero prior treatments → DENIED

---

## The full experiment story

### Phase 1: "The pipeline is broken. Nothing is reaching the Rules Checker."

**What we observed:**
35 out of 120 test cases returned UNKNOWN — no decision at all. The pipeline was failing at Gate 2 before the Rules Checker ever ran. 60% factual accuracy on the cases that did produce output — but this was a soft metric (does the reasoning make sense?) not an exact match score. Exact match was unmeasurable when 35/120 produced nothing.

**Why Gate 2 was blocking:**
Gate 2 checks: "did the Research Agent extract all required fields?" It required labs and clinical notes to be present. The synthetic test data often didn't include labs or notes by design. Gate 2 kept saying "incomplete, retry." After enough retries the case escalated to HITL as UNKNOWN.

**Experiment 1 — Fix Gate 2:**
Made labs/notes optional. "NOT FOUND" is an acceptable answer.
Result: 35 UNKNOWN → 22 UNKNOWN. 13 cases unblocked.

**New error found:** 22 cases still stuck at Gate 4. Gate 4 was demanding DOB, NPI, group ID — admin fields the synthetic data doesn't include.

**Experiment 2 — Fix Gate 4:**
Declared missing admin fields acceptable in a synthetic environment.
Result: 22 UNKNOWN → 0. All 120 cases now produce a decision. Pipeline working end to end for the first time.

**Experiment 3 — Intended: cost optimisation. Actual: nothing changed.**
Hypothesis: downgrade Writer Agent to GPT-4o-mini to reduce cost.
Discovery: Writer Agent was already on GPT-4o-mini via the global config. No real change occurred. Session logged, no learning extracted.

**Experiment 3b — Upgrade supervisor reasoning:**
Hypothesis: upgrading the four gate-check supervisors from GPT-4o-mini to GPT-4o will improve decision quality.
Result: cost spiked 7x ($0.20 → $1.44). Latency improved by 10 seconds. Decision distribution tightened.
Key finding from traces: the Rules Checker was hallucinating — inventing medical requirements not in the insurer's JSON file. This set up Exp 4.

---

### Phase 2: "The pipeline works. But the answers are wrong."

LangSmith locked dataset introduced. Exact match metric. Every case produces a decision. Question shifts from "is it running?" to "is it right?"

**Experiment 4 — Stop the hallucinations:**
Rules Checker was using general medical knowledge to fill gaps instead of sticking to the insurer's rules file.
Fix: strict mode — only use insurer_rules.json, nothing else. Missing data = NEEDS_MORE_INFO, no exceptions.
Result: 19.2% exact match.

Why 19.2% is actually a success: the agent stopped making things up. But Gate 3 immediately caused a new problem.

**The Gate 3 paradox:**
Gate 3's scorecard said: "APPROVED or DENIED = good answer. NEEDS_MORE_INFO = unclear, failing grade."
So when the Rules Checker correctly said "labs not submitted, I need more info," Gate 3 rejected it as incomplete and forced a retry. The model was being punished for correct behaviour.

**Experiment 5 — Fix Gate 3 scorecard:**
Updated Gate 3 to accept NEEDS_MORE_INFO as a valid final answer.
Result: 11.7% — WORSE (−7.5%).

Why it got worse: the model overcorrected. Now that it was "allowed" to say needs-more-info, it said it for 114/120 cases. The underlying problem was exposed: the LLM couldn't reliably distinguish between "data is genuinely missing → NMI" and "data is present but shows criteria not met → DENIED."

**Experiments 6 → 6a → 6b → 6c → 6d (prompt attempts, all partial):**
Multiple attempts to fix this distinction via prompt engineering. Each version improved some cases but broke others. LLMs are probabilistic — they don't give the same answer every time for the same input. Prompts couldn't solve a determinism problem.

**Experiment 6d.1 — The architectural breakthrough (v1 → v2):**
Stop trying to teach the LLM this distinction. Write Python code instead.
Added a deterministic Python gate BEFORE the LLM Rules Checker:
- Contraindication found in patient record AND in insurer block list? → Python says DENIED. No LLM call.
- Lab value present AND below required threshold? → Python says DENIED. No LLM call.
- Step therapy drugs present AND criteria not met? → Python says DENIED. No LLM call.
- Everything genuinely ambiguous? → LLM path as before.

Result: +19.1%. Best return on investment in the project. Zero tokens for deterministic cases.

This is the architectural insight: **the LLM should only handle what Python can't.**

---

### Phase 3: "Architecture is right. The measurement is dirty."

**Experiment 7 — Fix the answer sheet:**
After the Python gate, the remaining errors looked wrong. Audit found 32 gold labels (expected answers in the eval dataset) were incorrect — the model was being penalised for correct predictions.

Gold labels = the answer key in the LangSmith dataset. Each of 120 cases has an expected_outcome field. 32 of those expected answers were wrong. Correcting them added +15.9%.

Important: the model didn't get smarter. The scoring got more accurate.

**Experiment 8 — Partial step therapy failure:**
Some patients had done SOME required drugs but not all. Model was outputting NMI instead of DENIED.
RULE 4A: if the patient record clearly shows a required drug was NOT taken, that is not missing information — that is failed criteria. → DENIED.
Supervisor wiring fix: ensured the DENIED decision propagated correctly through all gate checks to the final output.
Result: +16.7%. Largest genuine model improvement in the project.

**Experiment 9 — Final cleanup, lock the benchmark:**
9 more gold label corrections. Step-therapy sequence check (some insurers require drugs in a specific order).
Result: 70.0%. Locked as clean benchmark.

Post-run audit on remaining 24 errors: all DENIED→NMI. All share the same pattern — prior_treatments is empty. Model sees empty list → "I need more information." Every single one.

---

### Phase 4: "Targeted fix for the last dominant error pattern."

**The 4-layer audit (before writing any code):**
24 cases, same error type. Before touching code, categorised all 24:
- Pattern A (18/24): Same root cause — empty prior_treatments. One Python fix covers all 18.
- Pattern B (4/24): Model was correct. Gold label was wrong. Need relabeling, not code.
- Pattern C (2/24): Complex reasoning failure. Different fix needed. Planned for Exp 11.

If the audit had been skipped and a fix written for all 24: Pattern B cases would have broken, Pattern C effort would have been wasted.

**Experiment 10 — Extend the Python gate (v2 → v3):**
Two lines added to the existing Python gate: if prior_treatments is completely empty → step therapy definitively not done → DENIED. Never calls the LLM.

Run was contaminated: OpenAI API quota ran out at case ~95/120. Overall score (62.5%) is invalid as a benchmark.
Row-level CSV confirms: all 18 Pattern A cases correctly output DENIED. The fix works. The environment was dirty.

Projected clean score: 78–82%.

---

## The PA-057 example (alirocumab · Humana)

PA-057 is the poster child for all 18 Pattern A cases. Used in the dashboard to make the fix concrete.

Patient: requesting alirocumab (Praluent), a cholesterol drug.
Humana requires: patient must have tried ezetimibe AND simvastatin first (step therapy).
PA-057 record: prior_treatments = [] — never tried either drug. LDL = 101 (labs fine, above threshold).

**Exp 9 (before fix):** Rules Checker sees empty list → "I need more information about prior treatments" → NEEDS_MORE_INFO. Wrong. The data is there. It says nothing was done.

**Exp 10 (after fix):** Python gate checks: prior_treatments is empty → step therapy definitively not done → DENIED. Correct. Zero LLM tokens. $0.000 cost.

This case validates that even though the overall Exp 10 run was contaminated, the specific class of error targeted was correctly fixed.

---

## What's next

| Experiment | Goal | Expected result |
|---|---|---|
| Exp 10b | Same code, clean API credits | Validate 78–82% projection |
| Exp 10c | Fix 4 over-deny regressions (PA-032/112/037/117) | Cases where zero-steps→DENIED was too aggressive |
| Exp 11 | Fix Pattern C (2 cases) + 4 Pattern B relabels | Projected ceiling: 85–88% |
| Pilot | Short batch on new synthetic data | Validate generalisation before real-world test |

---

## Key talking points for interviews

**On why eval-first:**
"Most people build an agent, see a bad number, and tweak the prompt. I set up a locked evaluation dataset and session tracking before making any changes. That meant every experiment had a receipt — you could see exactly what changed and what it did to the score."

**On the Python gate (the biggest insight):**
"The biggest score jump came from removing the LLM from decisions it shouldn't be making. Python is deterministic. If a patient has a contraindication, you don't need GPT-4o to tell you that — you need a dictionary lookup. Moving those cases out of the LLM path gave +19.1% and cut cost per case."

**On the contaminated run:**
"Exp 10 came back at 62.5% — worse than Exp 9. I could have hidden that. Instead it's on the dashboard with a full breakdown: 18 quota kills, 4 over-deny regressions, 8 LLM nondeterminism cases. The row-level CSV confirms the fix worked for all 18 target cases. Showing the contaminated run honestly is more valuable than hiding it."

**On the 4-layer audit:**
"Before writing any code for the fix, I categorised all 24 remaining errors. 18 were the same root cause. 4 were wrong gold labels — the model was already right. 2 needed a completely different approach. If I'd skipped the audit and written a fix for all 24, I'd have broken 4 cases the model already had correct."

**On architecture evolution:**
"The architecture changed twice — both times because the evaluation data told me to change it. The Python gate wasn't in the original design. The data showed the LLM was wrong on cases that had deterministic answers, so I moved those cases out. That's what eval-driven development looks like in practice."

**On cost:**
"$0.012 per case average. Manual prior auth review costs $8–12 per case in human labour. The deterministic path runs at $0.000 — no LLM call at all."

---

---

## Every architectural decision + the tradeoff

**Decision 1: LangGraph StateGraph over a simple chain**
*Triggered by:* Initial design — prior auth has conditional paths (retry, escalate, reroute on failure).
*Why:* A linear chain can't handle retry logic, escalation, or routing to different paths based on gate results. LangGraph's graph structure lets you define conditional edges — "if Gate 2 fails, loop back to the Research Agent; if it fails twice, route to human review." Sequential chains can't do this.
*Tradeoff:* More complex to build and debug. State management requires care — if two nodes both write to the same field, you need typed list fields to prevent overwrites. The complexity is justified because the routing logic is core to the system's reliability, not optional.

**Decision 2: 4 supervisor gates instead of one final quality check**
*Triggered by:* Initial design — needed to know WHICH agent failed, not just that something failed.
*Why:* Catching errors early is cheaper than catching them late. If the Research Agent extracts bad data and you only check at the end, the Rules Checker and Writer Agent both run on corrupt input — wasted tokens, wrong output, harder to diagnose. A gate after each step means errors are caught where they originate.
*Tradeoff:* Each gate is an additional LLM call on GPT-4o. 4 gates adds ~$1.20/run. Justified because catching a bad research extraction early saves downstream LLM calls that would have run on corrupted data. Also makes debugging trivial — you know exactly which node failed.

**Decision 3: GPT-4o for supervisor gates, GPT-4o-mini for task agents**
*Triggered by:* Experiment 3b — ran same pipeline at two model tiers, compared traces.
*Why:* Task agents follow structured templates — extraction, matching, drafting. These don't require deep reasoning, just careful instruction-following. Supervisor gates make judgement calls about logical soundness and clinical completeness. The cost-performance tradeoff lands differently for each job.
*Tradeoff:* Gates running on GPT-4o spike cost 7x vs running everything on mini ($0.20 → $1.44/run). Offset by two unexpected benefits: GPT-4o is 10 seconds faster on reasoning tasks (better model, faster throughput), and gate accuracy improved enough to surface the Rules Checker hallucination problem in Exp 3b traces — which was the discovery that drove the entire Exp 4–6 arc.
*Interview note:* The Exp 3 / 3b experiments looked like a distraction — you thought you were testing cost optimisation but Exp 3 was a non-event (model was already on mini). Exp 3b's real value wasn't the results, it was the traces revealing the hallucination problem. Frame it as: "the experiment I thought I was running wasn't the valuable one — the one I actually ran surfaced the next problem."

**Decision 4: Deterministic Python gate before the LLM Rules Checker (v1 → v2)**
*Triggered by:* 5 failed prompt iterations (Exp 6 → 6a → 6b → 6c → 6d) trying to fix the "missing vs not-met" distinction.
*Why:* An LLM is probabilistic. For the question "is ezetimibe in this patient's prior treatments list?" the answer is deterministic — it's either there or it isn't. Running an LLM on that question costs tokens, adds latency, and introduces nondeterminism. Python is always right, always free, always instant on binary presence checks.
*Tradeoff:* Python rules require string matching. Implemented three layers to handle this: (1) normalization — lowercases and strips whitespace so "Simvastatin" matches "simvastatin 20mg"; (2) substring matching — "ezetimibe" matches "ezetimibe 10mg"; (3) lab key alias map — "LDL_min" also looks for "LDL", "ldl". Drug name resolution tries brand name → generic → CPT code in order.
*Known production gap:* Brand/generic drug synonyms in step therapy matching. If the insurer rule says "simvastatin" and the patient record says "Zocor" (same drug, brand name), Python misses it. In production this is solved with RxNorm (free NIH drug API). The synthetic data uses consistent generic names so this gap doesn't surface in the test results — but knowing it exists is important.
*Result:* +19.1% — best single return on investment in the project.

**Decision 5: Extend Python gate to cover zero prior treatments → DENIED (v2 → v3)**
*Triggered by:* Post-Exp 9 audit of 24 DENIED→NMI errors, all sharing empty prior_treatments.
*Why:* An empty prior_treatments list IS information — it means step therapy was definitively not done. Treating it as "missing data" (and therefore NMI) was wrong. This was a 2-line Python addition to the existing gate.
*Tradeoff:* The zero-steps→DENIED rule needs to be conditional on insurer policy. Not all insurers require step therapy for all drugs. The Exp 10 implementation applied it too broadly — 4 cases (PA-032/112/037/117) were over-denied because their insurer/drug combination didn't require step therapy at all. Exp 10c will add the conditional check.

**Decision 6: HITL gate before any submission**
*Triggered by:* Initial design — healthcare decisions have real consequences.
*Why:* No AI system should submit prior auth forms without a human checkpoint in production. HITL gate exists as a configurable safety layer. `hitl_enabled = False` for testing (auto mode), `True` for production intent (review mode).
*Tradeoff:* Auto mode removes the safety net for speed. Review mode adds latency and human cost. The flag makes this environment-dependent rather than hardcoded.

**Decision 7: Locked evaluation dataset, one evaluator, session IDs from Exp 4 onwards**
*Triggered by:* Recognising that score improvements meant nothing without a stable baseline.
*Why:* Without a locked dataset, you can't tell if a score change is because your code improved or because different cases were sampled. Without session IDs, you can't replay a run to verify a number. Without a single evaluator (exact_match), different experiments are measuring different things.
*Tradeoff:* A locked dataset can develop its own biases — 32 wrong gold labels proved this. The dataset needs its own audit process to stay honest. Exp 7 and Exp 9 were partly doing this alongside accuracy improvements.
*What you'd do earlier:* Set up LangSmith and the locked dataset before Exp 1, not Exp 4. Exp 1–3 were fixing problems that would have been discovered earlier if the measurement harness had been in place from the start.

---

## Drug alias and normalization — what's implemented

**What exists in the code:**
- `_normalize_contra()` — lowercases, strips whitespace. Handles capitalisation variants.
- Substring matching in step therapy (`if req in pv or pv in req`) — handles dosage suffixes like "ezetimibe 10mg".
- Lab key alias map in `_lab_value_for_threshold_key` — "LDL_min" also checks "LDL", "ldl"; "A1C_min" checks "A1C", "HbA1c"; "BMI_min" checks "BMI", "bmi"; etc.
- Drug name resolution — tries brand name → generic_name → cpt_code in sequence in both eligibility and rules checker.

**Known production gap:**
Brand/generic drug synonyms in step therapy matching. The insurer rule might say "simvastatin" and the patient record might say "Zocor" (same drug). Python can't match these without a drug synonym database. The synthetic data uses consistent generic names throughout, so this gap doesn't appear in test results.

**How to close it in production:** Integrate RxNorm (free NIH API) or a drug formulary to resolve brand ↔ generic equivalences before the Python matching step. This is a known, scoped problem with a known solution.

---

## Likely interview questions and answers

**Q: Why prior auth specifically?**
A: High-stakes, high-volume, rules-heavy domain. Every insurer has different criteria. The rules are in structured JSON — perfectly suited to a deterministic-first approach. And the consequences of a wrong decision (approving something that shouldn't be approved, or denying something that should) are real, which meant evaluation discipline mattered from day one.

**Q: What was the hardest part?**
A: Figuring out when NOT to use an LLM. The instinct when a score is bad is to improve the prompt. The right answer was often to remove the LLM from that decision entirely and write Python.

**Q: What would you do differently?**
A: Set up the evaluation harness before writing a single agent node. I spent Exp 1–3 fixing infrastructure problems that wouldn't have existed if I'd validated the data and pipeline in isolation first.

**Q: How do you know the 70% is real?**
A: Every run has a LangSmith session ID. The dataset is locked — same 120 cases, same evaluator, every time. You can replay any session and get the same number. The CHANGELOG has the session ID for every experiment.

**Q: What's the ceiling?**
A: Based on the audit: 85–88% is achievable with Exp 10b (clean re-run), Exp 10c (fix 4 regressions), and Exp 11 (Pattern C + relabels). Beyond that you need more synthetic data diversity or real-world cases to find the next error bucket.

**Q: Why did prompt engineering fail to fix the Rules Checker hallucination? Was that a failure on your part?**
A: It's two separate problems that got tangled together. The first — the model inventing requirements not in the insurer's JSON file — was a genuine prompting problem, and prompting fixed it. Exp 4's strict adherence mode largely solved it. The second — confusing "data is missing" with "data is present but shows failure" — is where it gets more nuanced. The LLM was doing two jobs simultaneously in one call: interpreting ambiguous clinical language (what LLMs are good at) and doing exact binary comparisons on structured data (what Python is good at). Mixing them gave mediocre performance on both. The 5 prompt iterations (Exp 6→6d) weren't wasted — they were the evidence needed to prove the problem wasn't a language problem before justifying the architectural change. If I'd jumped straight to Python without trying prompts first, that would have been premature. The iterations proved the case. The +19.1% came from recognising that distinction, not from writing a better prompt.

**Q: Why LangGraph specifically and not LangChain or a simpler framework?**
A: LangGraph is built for stateful, cyclic workflows — where you need to loop back, retry, and route conditionally based on what happened at each step. LangChain chains are linear. My workflow needs to loop the Research Agent back on a Gate 2 failure, escalate to human review after too many retries, and route differently based on the payer's decision (APPROVED/DENIED/NMI all have different downstream paths). LangGraph's graph structure with conditional edges handles all of that natively.

**Q: Your Exp 3 was a non-event — how do you explain that?**
A: I thought I was testing whether a cheaper model could handle the Writer Agent. I discovered the model was already on GPT-4o-mini via the global config — nothing changed. I documented it rather than deleting it. Null results that get documented honestly show you ran a controlled test and didn't reverse-engineer the narrative. Exp 3b — the corrected test — revealed the hallucination problem in the Rules Checker, which drove the entire Exp 4–6 improvement arc. The valuable finding didn't come from the experiment I thought I was running.

**Q: How do you handle the brand/generic drug name problem in production?**
A: Currently the Python step therapy matching uses normalization and substring matching, which works for the synthetic data because it uses consistent generic names. The known gap is brand/generic synonyms — "Zocor" vs "simvastatin" would fail. In production I'd integrate RxNorm (the NIH drug database, free API) to resolve brand/generic equivalences before the Python matching step. I know the gap, I know the solution, and I know it doesn't affect the current synthetic benchmark because the data is consistent.

**Q: Why synthetic data and not real patient data?**
A: Two reasons. First, HIPAA — real patient records can't be used without a compliance framework that's out of scope for a solo project. Second, synthetic data lets you control the ground truth — you know exactly what the right answer is for each case, which makes the evaluation clean. The tradeoff is generalisability — synthetic data may not capture the full variability of real records. The pilot phase (after Exp 11) would validate on a new synthetic batch with different distributions before any real-world test.

**Q: What does $0.012 per case actually mean in context?**
A: Manual prior auth review costs $8–12 per case in human staff time — that's the industry figure. At $0.012 per case, the AI path is roughly 1000x cheaper per decision. The deterministic Python cases run at $0.000 — no API call at all. Cost per case could drop further as more cases are routed to the Python path.

---

## DeepMind-Level Probe Questions — Phase 1 vs Phase 2 Failures

**Q: How did you know the gate was over-strict vs the data being genuinely ambiguous?**
A: LangSmith traces showed Gate 2 firing with a specific rejection reason — it was flagging cases as incomplete because `labs` and `clinical_notes` fields were empty or null. But when I looked at the actual patient records, those fields weren't missing by error — the synthetic data was designed without mandatory lab results for every case. The gate was treating "field not present" as "incomplete submission" rather than "not applicable." That's an observable pattern in the traces — every single UNKNOWN had the same Gate 2 rejection string, not a distribution of different reasons. If it had been genuine data ambiguity, you'd expect varied rejection reasons across cases.

**Q: What changed between Phase 1 and your locked baseline?**
A: Two gate configuration changes across Exps 1 and 2. Exp 1: made labs and clinical notes optional in Gate 2 — NOT FOUND is a valid extraction result, not a failure. That dropped UNKNOWNs from 35 to 22. Exp 2: declared missing admin fields — DOB, NPI, group ID — acceptable in a synthetic environment at Gate 4. That cleared the remaining 22. Once all 120 cases were producing decisions end to end, I introduced LangSmith as the eval harness, locked the dataset, and switched the primary metric from factual accuracy to exact match. That became the baseline — 19.2% on Exp 4, the first run under controlled conditions.

**Q: Why 120 cases specifically?**
A: Practical constraint first — at $0.012 per case running 10+ experiments, 120 cases kept the full cohort eval cost under $2 per run, which meant I could run it repeatedly without thinking about budget. The composition was intentional though: 72 DENIED, 36 APPROVED, 12 NEEDS_MORE_INFO — reflecting the real-world distribution where denials dominate PA decisions. And 4 payers × 6 drug categories gave enough combinatorial variety to stress-test the rules engine across different insurer criteria. It's not a statistically powered sample size by research standards — I'd say that directly if asked. What it is is a controlled, repeatable cohort where every run is comparable because nothing changes between experiments.

**Context note — 35 UNKNOWNs vs 18 misclassifications (keep these straight):**
These are two different failure modes from two different phases. The 35 UNKNOWNs (Phase 1) were pipeline failures — the system couldn't complete a prediction at all because supervisor gates had over-strict configuration for synthetic data. Fixed in Exps 1–2 before any accuracy measurement was possible. The 18 misclassifications (Phase 4, Exp 10 audit) were accuracy failures — the system ran and produced a decision, but the wrong one. Specifically: empty prior_treatments list → model said NEEDS_MORE_INFO instead of DENIED. That's a logic failure on a deterministic case, traced and fixed via LangSmith. If an interviewer asks about the 35 UNKNOWNs: "That was Phase 1 — the pipeline wasn't completing runs at all. Gate configuration was over-strict for synthetic data. Fixed in the first two experiments before we had a meaningful baseline to evaluate against."
