"""Development-assistant fact corrections after checking executed code and raw CSVs."""
from pathlib import Path
import shutil
import sys

root = Path(sys.argv[1]).resolve()
sections = root / "paper" / "sections"
backup = root / "validation" / "pre-fact-review"
backup.mkdir(parents=True, exist_ok=True)
texts = {}
texts["00_abstract.tex"] = r"""Research agents can resume a durable graph while their external evidence is duplicated, incomplete, or changed. We examine this distinction with a small, reproducible process-crash benchmark. A scripted LangGraph harness imports the Store and RunStore classes from a pinned PaperScientist working-tree snapshot; it does not execute the full research agent or measure LLM reasoning. Four policies share synthetic keyed-record workloads of 8, 24, and 64 actions: checkpoint replay, conservative receipts, effect reconciliation, and reconciliation with a final evidence audit. The 228 designed configurations comprise 12 fault-free controls, 180 primary crash cases, and 36 stress cases. Every injected crash exits a real Python process and resumes from SQLite checkpoints in a new process. Among 45 primary cases per policy, checkpoint replay falsely declares completion in 18; receipts avoid those duplicates but block 18 cases; reconciliation and the full contract verify all 45. In nine stress cases per policy, receipts and reconciliation each block six but falsely complete three cases where evidence changes after a done receipt. The final audit blocks all nine and produces no false completion in the tested matrix. A separate reader reproduces all 228 outcome labels. We contribute an inspectable application-level evidence contract and a narrow empirical case study, building on established recovery and idempotency techniques. These counts describe enumerated failure configurations, not population reliability; the observation rule depends on an exclusive, readable local effect store. Two separate DeepSeek web-interface fixtures demonstrate durable human answers without establishing autonomous scientific capability.
"""
texts["03_method.tex"] = r"""\section{Problem and Recovery Policies}
\label{sec:method}
\subsection{State and effects}
The experiment distinguishes graph progress $C$, receipt state $R$, and external evidence $E$.
The graph stores progress in \texttt{graph.db}; the imported RunStore stores running/done receipts
in a separate SQLite database; \texttt{effects.jsonl} contains non-idempotent append effects.
For seed $s$ and action index $i$, the harness constructs a deterministic value from the
SHA-256 digest of the canonical JSON list $[s,i,\texttt{cpu-record}]$.
Its record is \texttt{\{id, value, sha256\}}, where \texttt{id} is \texttt{op-}$i$ and
the final field hashes the canonical JSON object containing just \texttt{id} and \texttt{value}.
Canonical JSON sorts keys and uses compact separators. These are independent record hashes,
not a cryptographically linked hash chain. No adversarial authenticity guarantee is claimed.

Each tool effect appends one complete JSON line, flushes it, and calls \texttt{fsync}.
It does not atomically rename the effect file. Separate configuration, fault-marker and
outcome JSON files use temporary-file replacement. Neither the effect append nor its receipt
is atomic with the graph checkpoint. A crash between these writes is therefore informative.

\subsection{Completion contract}
Let $\mathrm{Req}(s,n)$ be the ordered sequence of $n$ expected records. Verified completion means
\begin{equation}
 \mathrm{ReportedComplete}\ \land\ \mathrm{Valid}(E)\ \land\ E=\mathrm{Req}(s,n).
 \label{eq:contract}
\end{equation}
Validity checks parseability, exact record keys, and per-record hashes. Sequence equality checks
order, payloads, multiplicity and completeness. A false completion is a positive completion
report that fails this predicate. A blocked run is explicitly incomplete, regardless of how
many correct records already exist. Thus reducing false completion by refusing every task
would not improve verified success.

The contract concerns evidence at audit time. Subsequent mutation is outside its guarantee.
A generic research task rarely has a fully known expected output; in deployment, a task-specific
validator would replace this synthetic exact-sequence oracle. Whether such a validator is
scientifically adequate is a separate problem.

\subsection{Policies and observations}
\paragraph{\policy{checkpoint}.}
The graph resumes from its last synchronized checkpoint and re-executes an unfinished action.
There are no application tool receipts. A crash after an append but before a graph checkpoint
can therefore duplicate that append. This is a deliberately minimal baseline, not an optimized
LangGraph deployment using idempotent tasks.

\paragraph{\policy{receipt}.}
The imported RunStore inserts a \texttt{running} row before the effect and commits a
\texttt{done} result afterward. A done receipt can replay the saved next-index result without
repeating the effect. A running receipt on recovery is ambiguous: this policy blocks with
\texttt{uncertain\_effect}, leaves the graph at the interrupted index and executes no later actions.
It does not erase an existing record or advance past uncertainty. Its incomplete traces may
therefore lack the interrupted action and/or later actions that were never executed.

\paragraph{\policy{reconcile}.}
An ambiguous running receipt invokes an observer. It returns \emph{applied} when a readable,
valid effect log has exactly one record with the expected ID and exact payload; \emph{absent}
when the valid log has none; and \emph{unknown} for opaque observation, invalid data,
duplicate matches or a conflicting payload. Applied commits the result without another append;
absent retries the append; unknown blocks. Done receipts still bypass observation.
This absence test is justified only by this fixture's exclusive writer, complete local log
and absence of delayed/background effects. It is unsound for a generally eventually consistent
or opaque remote service.

\paragraph{\policy{contract}.}
This policy adds a final whole-log audit to reconciliation. It reports completion only if
the current evidence satisfies Equation~\ref{eq:contract}'s validity and equality conditions;
otherwise it blocks with \texttt{evidence\_mismatch}. The audit catches changes after a done
receipt that reconciliation alone will not revisit. It never converts an unknown result into success.

\subsection{Questions and scope}
The experiment asks where checkpoint-only replay duplicates effects; whether conservative
receipts trade duplicates for incomplete runs; when observable effects resolve that uncertainty;
and whether final auditing detects post-receipt evidence changes. It also records elapsed execution
cost. The tri-state decision and idempotency principles are established techniques; the contribution
here is their explicit evidence predicate, matched ablations and reproducible failure accounting.
No proof of arbitrary external exactly-once execution is offered.
"""
texts["04_experimental_setup.tex"] = r"""\section{Experimental Setup}
\label{sec:setup}
\subsection{Implementation and provenance}
The benchmark imports only \texttt{Store} and \texttt{RunStore} from an unmodified snapshot
of the PaperScientist working tree. The manifest covers 28 files; independent re-hashing found
28 matches. The recorded git base is \texttt{c72b9da5c13d7bfc10581a786cbb4b200d2b8392};
the snapshot also contains uncommitted implementation, so that revision alone does not reproduce it.
\texttt{verified\_bench/common.py}, \texttt{worker.py} and \texttt{run\_matrix.py} implement
the synthetic planner, graph and process driver separately. They are not the production
RunManager and do not run an LLM. The development assistant supplied and reviewed this compact
harness after earlier agent-generated drafts proved incomplete; those drafts are excluded from evidence.

The graph uses the installed LangGraph 1.2.1 and \texttt{langgraph-checkpoint-sqlite} 3.1.0,
with \texttt{AsyncSqliteSaver} and \texttt{durability="sync"}. LangChain Core is 1.4.8.
Execution used Python 3.12.0 on Windows 11 build 26300, an Intel processor reported as
Family 6 Model 183, with 28 logical CPUs. Four independent cases ran concurrently.
Every case owns fresh files and databases; benchmark processes do not contact the production service.

\subsection{Synthetic traces and real exits}
Trace lengths are $n\in\{8,24,64\}$ keyed-record actions, not three real scientific domains.
Payloads are deterministic; primary-case seeds are $n+\text{target}$, while controls and stress
cases use $n$. All policies receive the same case parameters. The driver runs a fresh Python process,
injects one \texttt{os.\_exit(73)}, and launches a new process against the same databases.
A flushed marker prevents repeated injection. The five boundaries are:
\begin{description}[leftmargin=1.2em,itemsep=2pt]
\item[Before intent] before any receipt for the selected action.
\item[After intent] after a running receipt, before the effect.
\item[After effect] after the append has been flushed and fsynced, before a done receipt.
\item[After receipt] after committing the tool result, before the graph checkpoint.
\item[After checkpoint] after state inspection confirms the synchronized next-index checkpoint.
\end{description}
The checkpoint policy has no receipts: its after-intent and after-receipt injection locations
are the corresponding positions in the common code path, without those writes. In particular,
after-effect and after-receipt are equivalent failure windows for that baseline, an intentional
factorial redundancy rather than independent mechanisms. Each lifetime has a 70-second limit;
at most three are allowed. Nonzero exit codes other than 73 abort the case.

\subsection{Mutually exclusive matrix}
For each length and policy, one no-fault control, 15 primary cases (five boundaries times
first/middle/last targets $0,\lfloor n/2\rfloor,n-1$), and three stress cases are run.
The stress cases all target the middle action: an opaque observer after-effect; a torn JSON
fragment appended after-effect; and a value changed after-receipt without updating its record hash.
Thus each length contributes $4(1+15+3)=76$ cases and all lengths contribute 228.
Across lengths, every policy has 3 controls, 45 primary cases, and 9 stress cases.
An opaque observer is a controlled unavailable-observation interface; it is not an OS permission test.
The value perturbation is controlled data inconsistency, not an adversarial attack evaluation.

\subsection{Measurement}
The recorded outcomes are verified success, false completion, blocked state/reason, duplicate
record counts, absent record IDs, wrong payloads, process lifetimes and elapsed time.
Absent IDs in a stopped trace include actions never reached; they must not be described as
loss of previously durable data. The parent evaluator and final-audit policy share the
exact-sequence specification and initial audit helper. A separate implementation later reads
raw files, reconstructs expected records, and checks outcome labels without importing that helper.

Elapsed times include interpreter start-up, imports and restarts. Comparisons are descriptive:
policies that stop early perform less work, and four concurrent workers contend for resources.
These runs provide neither isolated latency estimates nor evidence of a statistically significant
speed difference. Cases are deliberately enumerated, not sampled; no population reliability
estimate, confidence interval or significance test is inferred from their counts.
"""
texts["05_results.tex"] = r"""\section{Results}
\label{sec:results}
Table~\ref{tab:summary} reports the mutually exclusive outcome groups. Every case produced
an outcome with exit codes 0 or 73 and no timeout; each of the 216 injected cases records
a real exited process and a distinct subsequent process. This means the driver terminated,
not that all tasks completed: blocked cases retain unresolved effects or an evidence mismatch.
\input{sections/05a_table_summary}

\subsection{Primary crash cases}
Checkpoint replay verifies 27 of 45 primary cases and falsely completes 18, each with
one duplicated record. These 18 cover after-effect and after-receipt (nine each).
It succeeds at before-intent, after-intent and after-checkpoint (nine each). The exact
location of the crash therefore matters more than the fact that a restart occurred.

Conservative receipts also verify 27 of 45, but replace erroneous completion with 18
explicit blocks and produce no duplicate effect. The ambiguous boundaries are now after-intent
and after-effect (nine each). This is not a one-to-one repair of the baseline's failures:
receipts recover after-receipt cases but conservatively block after-intent cases that checkpoint
replay can execute safely. Fifteen blocked primary traces lack some expected record IDs.
After-effect at the last action, all records may already exist, yet the policy still blocks
because it cannot establish that the unfinished receipt denotes an applied effect.

Reconciliation and the full contract each verify all 45 primary cases, with zero duplicates
and no missing expected records. In this exclusive local store, the observer can distinguish
an absent interrupted append from an already-applied one. These results test the stated
observation assumptions; they do not establish recovery of opaque remote side effects.
Figure~\ref{fig:boundary} shows the nine cases at each boundary per policy.

\subsection{Stress cases and the final-audit ablation}
Each policy has nine stress cases. Checkpoint replay falsely completes all nine.
Receipts and reconciliation each block six (opaque and torn-log cases), but falsely
complete all three post-receipt value-tampering cases. Their done receipt bypasses effect
observation, while the final artifact has changed. This is the separating example for
the final-audit component, not a benefit of adding more restart attempts.

The full contract blocks all nine: six as \texttt{uncertain\_effect} and three as
\texttt{evidence\_mismatch}. It achieves no verified stress-case success. Refusal to certify
contradictory or unavailable evidence is the intended behavior, but it still requires later
repair or human resolution. Across all 57 cases per policy, checkpoint, receipt, reconcile
and contract yield respectively $(30,27,0)$, $(30,3,24)$, $(48,3,6)$ and $(48,0,9)$ for
(verified success, false completion, blocked).

\subsection{Trace length and execution cost}
The primary correctness profile is unchanged at lengths 8, 24 and 64: checkpoint has
9 successes and 6 false completions at each length; receipts have 9 successes and 6 blocks;
reconciliation and the contract have 15 successes. This regularity follows the tested
boundary structure rather than a sampled robustness rate. The mean primary case times
are 2.753, 3.685, 4.144 and 4.113 seconds in policy order. The full contract's mean is
approximately 1.49 times the checkpoint baseline in this mixed workload. Fault-free control
means are 1.919, 2.694, 2.854 and 2.862 seconds. We do not interpret the slight timing
difference between reconciliation and the contract as an optimization result.
Figure~\ref{fig:cost} and Table~\ref{tab:cost} give the length-dependent measurements.
All timings include process overhead and concurrent contention, and different completion
outcomes change how much work is performed.

\subsection{Independent recomputation}
\label{sec:results-indep}
The separate reader checks all 228 cases and finds zero disagreements in completion,
verified-success, false-completion and blocked labels, and in duplicate counts. It also
checks the expected number of hard-exit trace events and changed process IDs. The original
28-file runtime snapshot matches its manifest. These checks increase confidence that the
reported data correspond to executed files; they do not prove the scientific adequacy of
the workload or independence of its expected-output specification.
\input{sections/05b_table_cost}
\input{sections/05c_figures}
"""
texts["01_introduction.tex"] = r"""\section{Introduction}
\label{sec:intro}
A research assistant may spend hours collecting literature, executing analyses and building a
manuscript. Resuming its conversation or control graph is useful only if the files it cites
still support its claims. A graph checkpoint, a tool-completion receipt and an evidence artifact
are different objects, with different failure windows. A process may exit after appending a
result but before recording progress. Conversely, a valid completion receipt may survive while
its corresponding evidence is subsequently changed.

Persistent workflow systems already address replay and idempotency~\cite{langgraph2026durable,temporal2024idempotency}.
Recent agent-runtime research studies resume contracts, sandbox restoration and scientific-state
recovery~\cite{khan2026resume,wu2026crab,ma2026guardrail}. We build on these ideas rather than
claiming a new durability primitive. Our question is narrower: under which observable conditions
may an application honestly certify that resumed execution produced its required evidence?

We compare four application policies in one controlled graph. Checkpoint replay trusts graph
progress. Conservative receipts distinguish begun from completed effects and block ambiguous
replays. Reconciliation inspects an exclusive local effect store to resolve some of those
ambiguities. A final contract additionally checks the complete artifact before declaring success.
The final distinction matters: verifying a receipt at recovery time does not validate the
current evidence at reporting time.

The contributions are (1) an explicit completion predicate separating correct evidence,
false completion and unresolved outcomes; (2) a small executable matrix of actual process exits
over LangGraph/SQLite and a pinned application receipt implementation; and (3) matched ablations
and independent raw-file recomputation exposing both useful recovery and justified abstention.
The workload is intentionally synthetic, with a known expected sequence. Its 228 configurations
illustrate mechanisms and counterexamples; they neither measure LLM research competence nor
establish state-of-the-art recovery performance. Product-level human-interaction fixtures are
reported separately from the deterministic benchmark.
"""
texts["02_related_work.tex"] = r"""\section{Related Work}
\label{sec:related}
\paragraph{Workflow persistence and idempotency.}
LangGraph provides persistent thread checkpoints and application stores, while its interrupt API
supports pausing and resuming the same thread with external input~\cite{langgraph2026durable,langgraph2026interrupts}.
Temporal explains why retries of non-idempotent activities can repeat side effects and recommends
idempotency-aware designs~\cite{temporal2024idempotency}. Our running/done receipts and conservative
handling of ambiguous outcomes follow established principles. They are not an exactly-once guarantee
for an arbitrary external system. MongoDB's durable LangGraph adapter also distinguishes stable
activity identities from attempt-local interrupt identities~\cite{mongodb2026durableinterrupts};
our single-server functional tests do not evaluate that adapter or its distributed semantics.

\paragraph{Directly related recovery studies.}
Khan's \emph{Resume Means Resume} specifies and checks multiple persistence-API conformance
properties and evaluates pinned framework versions under faults~\cite{khan2026resume}. Its scope
and formal guarantees exceed this report's small application-level matrix. We complement that
perspective with a terminal evidence predicate and explicit artifact-observation stress cases;
we do not reproduce or claim to outperform its systems. Wu et al.'s \emph{Crab} bridges agent
turns and OS-visible effects using a sandbox checkpoint/restore runtime~\cite{wu2026crab}.
Our harness restores graph metadata and inspects local records; it does not restore process memory,
containers or microVMs. These are distinct recovery layers and no direct comparison is measured.

\emph{Guardrailed Meta-Agent Loops} separates scientific-state recovery from repeated execution
in a deterministic simulation testbed~\cite{ma2026guardrail}. This directly motivates caution
about interpreting recovered outcomes as exactly-once execution. Our study uses real process exits
and filesystem/SQLite writes, but a much smaller synthetic task model. Neither setting establishes
general autonomous research reliability. These recent works limit novelty claims: this report is
an inspectable engineering case study, not the first recovery contract or agent fault benchmark.

\paragraph{Scientific and interactive agent evaluation.}
ScienceAgentBench assesses agents on scientific programming tasks extracted from published
research~\cite{chen2025scienceagentbench}. $\tau$-bench uses tool-user interaction and final database
state as evaluation targets, while $\tau^2$-bench introduces a shared environment controlled by
both user and agent~\cite{yao2024taubench,barres2025tau2bench}. Those task capabilities are outside
our measured comparison. We borrow the discipline of checking outputs against explicit requirements,
while isolating recovery mechanics with a scripted policy. A scripted benchmark and two live
DeepSeek fixtures should not be conflated with success on those external benchmarks.
"""
texts["05b_table_cost.tex"] = r"""\begin{table}[t]
\centering\small
\caption{Descriptive whole-case time. Primary means cover 45 cases per policy and control
means cover three. Times include process startup, imports and restarts under four concurrent
workers. Different policies can execute different amounts of work before blocking.}
\label{tab:cost}
\begin{tabular}{@{}lrrr@{}}\toprule
Policy & Primary mean (s) & Control mean (s) & Primary ratio\\\midrule
\policy{checkpoint} & 2.753 & 1.919 & 1.00\\
\policy{receipt} & 3.685 & 2.694 & 1.34\\
\policy{reconcile} & 4.144 & 2.854 & 1.51\\
\policy{contract} & 4.113 & 2.862 & 1.49\\\bottomrule
\end{tabular}\end{table}
"""
texts["05c_figures.tex"] = r"""\begin{figure}[t]\centering
\includegraphics[width=0.86\linewidth]{figures/fig1_primary_outcomes.pdf}
\caption{Primary outcomes: 45 designed cases per policy. Receipts trade incorrect completion
for explicit blocking at ambiguous boundaries; reconciliation resolves those boundaries under
the tested local observation assumptions. These counts are not population reliability estimates.}
\label{fig:outcomes}\end{figure}
\begin{figure}[t]\centering
\includegraphics[width=0.96\linewidth]{figures/fig2_boundary_success.pdf}
\caption{Verified successes by primary fault boundary: nine cases per policy and boundary.
After-receipt has no receipt write in the checkpoint baseline. Stress cases are excluded.}
\label{fig:boundary}\end{figure}
\begin{figure}[t]\centering
\includegraphics[width=0.94\linewidth]{figures/fig3_cost_vs_length.pdf}
\caption{Mean whole-case time by synthetic trace length, 15 primary configurations per policy
and length. One execution of each configuration does not quantify timing variation; no uncertainty
bars or significance claims are supplied. Startup, restarts and shared-machine contention are included.}
\label{fig:cost}\end{figure}
"""
for name, text in texts.items():
    path = sections / name
    if path.exists() and not (backup / name).exists():
        shutil.copy2(path, backup / name)
    path.write_text(text, encoding="utf-8", newline="\n")
print("Corrected four sections against the actual implementation and 228 raw outcomes.")

table = sections / "05a_table_summary.tex"
if table.exists():
    table.write_text(table.read_text().replace("No case is unresolved.", "All driver executions terminate; blocked tasks remain incomplete."), encoding="utf-8")

bib = root / "paper" / "references.bib"
if not (backup / "references.bib").exists():
    shutil.copy2(bib, backup / "references.bib")
text = bib.read_text(encoding="utf-8")
# Remove unrelated/unchecked entries: these are not needed for the revised related work.
import re
text = re.sub(r'@(?:misc|inproceedings)\{(?:xu2025crab|chen2026cordon|chang2025sagallm),.*?\n\}\s*', '', text, flags=re.S)
text = re.sub(r'@misc\{temporal2024idempotency,.*?\n\}', lambda _: r'''@misc{temporal2024idempotency,
  author={Keith Tenzer and Joshua Smith},
  title={What is idempotency? And why it matters for durable systems},
  year={2024},
  howpublished={\url{https://temporal.io/blog/idempotency-and-durable-execution}},
  note={Published 2024-02-27; accessed 2026-10-23}
}''', text, flags=re.S)
text = re.sub(r'@misc\{mongodb2026durableinterrupts,.*?\n\}', lambda _: r'''@misc{mongodb2026durableinterrupts,
  author={{MongoDB}}, title={Durable LangGraph interrupt and resume}, year={2026},
  howpublished={\url{https://www.mongodb.com/docs/agentengine/sdk/python/packages/agent-engine-sdk-langgraph/docs/durable-interrupts/}},
  note={Official documentation; accessed 2026-10-23}
}''', text, flags=re.S)
for key, entry in {
 "wu2026crab": r'''@misc{wu2026crab,
 author={Tianyuan Wu and Chaokun Chang and Lunxi Cao and Wei Gao and Wei Wang},
 title={Crab: A Semantics-Aware Checkpoint/Restore Runtime for Agent Sandboxes},
 year={2026}, eprint={2604.28138}, archivePrefix={arXiv},
 doi={10.48550/arXiv.2604.28138}
}''',
 "ma2026guardrail": r'''@misc{ma2026guardrail,
 author={Qinzhen Ma and Jialin Wu},
 title={Guardrailed Meta-Agent Loops: Stress-Testing Policy Pinning, Budget Bounds, and Crash Recovery},
 year={2026}, eprint={2609.12216}, archivePrefix={arXiv},
 doi={10.48550/arXiv.2609.12216}
}'''
}.items():
    if "{" + key + "," not in text:
        text += "\n" + entry + "\n"
bib.write_text(text, encoding="utf-8")
