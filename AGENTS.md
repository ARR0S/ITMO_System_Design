# AGENTS.md

## Project context

This repository contains a four-hour admission-exam Proof-of-Concept
for an AI/ML System Design Case.

The system automates support-ticket processing for a large online service.

The primary goal is to demonstrate:

- clear architectural reasoning;
- separation of fast and slow paths;
- separation of model predictions and business policy;
- safe handling of high-risk and low-confidence tickets;
- graceful degradation when the LLM is unavailable;
- a minimal locally runnable vertical slice.

This is not a production-ready system.

## Sources of truth

Before making any changes, read:

1. `docs/task_analysis.md`
2. `docs/architecture.md`
3. `docs/ml.md`
4. `docs/monitoring.md`
5. `docs/risks-and-ops.md`
6. `AI_USAGE.md`
7. `README.md`, if it exists

The approved decisions in these files must not be silently changed.

## Ownership

The user is the system designer and final decision-maker.

Do not independently change:

- product requirements;
- scope or out of scope;
- architecture;
- happy, risky, or failure scenarios;
- ML approach;
- confidence thresholds;
- risk categories;
- fallback behaviour;
- dependencies;
- external integrations.

When required information is missing, report the ambiguity instead
of making a substantial architectural assumption.

## Approved PoC scenarios

### Happy path

A valid low-risk FAQ ticket:

1. passes validation;
2. contains no unsafe PII;
3. receives a high-confidence category;
4. retrieves a relevant knowledge-base fragment;
5. receives a deterministic mock-LLM answer;
6. receives `AUTO_ANSWER`;
7. is recorded in the audit log.

### Risky path

A valid high-risk ticket:

1. is classified successfully;
2. is marked as high risk;
3. receives `HUMAN_REVIEW` regardless of confidence;
4. is added to the review repository;
5. is recorded in the audit log.

### Failure path

A valid low-risk ticket when the mock LLM fails:

1. remains saved;
2. remains classified and routed;
3. does not receive an automatic answer;
4. receives `ROUTE_ONLY`;
5. receives status `DEGRADED`;
6. records the failure and fallback in the audit log.

## Approved PoC constraints

The PoC must use:

- Python;
- a modular monolith;
- explicit interfaces for replaceable components;
- deterministic mock components;
- a local knowledge base;
- a simple lexical retriever;
- an in-memory repository;
- a CLI or demo script;
- pytest smoke tests.

The PoC must not require:

- real API keys;
- external network access;
- PostgreSQL;
- Redis;
- Kafka or another message broker;
- a production vector database;
- Kubernetes;
- a real LLM API;
- a real model-training pipeline;
- a frontend;
- a production monitoring stack.

## Architecture rules

- Domain logic must not directly depend on infrastructure implementations.
- Model prediction and Policy Engine decisions must remain separate.
- Business risk and classifier confidence must remain separate.
- High-risk tickets must always go to human review.
- Low-confidence tickets must not be closed automatically.
- The original ticket must not be lost when an external component fails.
- LLM failure must not stop classification or routing.
- External services must be accessed through explicit interfaces.
- Mock implementations must preserve the intended production contracts.
- The in-memory queue or repository is a PoC substitute, not a production claim.
- The knowledge-base source must be identifiable in the final result.
- Audit events must contain the reason for the final decision.

## Scope control

Do not:

- broaden the task;
- add optional infrastructure;
- create microservices;
- add abstractions not needed by the three approved scenarios;
- add a framework only for visual completeness;
- implement speculative future functionality;
- rewrite unrelated files;
- generate large amounts of boilerplate.

Prefer the smallest design that clearly demonstrates the approved architecture.

## Code quality

- Use clear English names.
- Add type hints to public functions and domain models.
- Use small functions with one explicit responsibility.
- Use concise docstrings for public interfaces and non-obvious components.
- Comments must explain why a rule or limitation exists.
- Do not comment obvious syntax.
- Remove unused imports and dead code.
- Avoid hidden global mutable state where a repository object can be explicit.
- Do not swallow exceptions silently.
- Use deterministic test data.

Examples of useful comments:

- why a high-risk ticket is never automatically closed;
- why an external service is mocked;
- why a fallback returns `ROUTE_ONLY`;
- which PoC component would be replaced in production.

Examples of unnecessary comments:

- “return result”;
- “increment counter”;
- “check confidence”.

## Testing requirements

At minimum, the repository must contain tests for:

1. happy path → `AUTO_ANSWER`;
2. high-risk path → `HUMAN_REVIEW`;
3. LLM failure → `ROUTE_ONLY` and `DEGRADED`.

Tests must verify business outcomes, not only internal implementation details.

The full test command must be documented and executed after every
meaningful implementation stage.

## Documentation rules

Documentation must distinguish clearly between:

- functionality implemented in the PoC;
- target production architecture;
- assumptions;
- known limitations.

Do not claim that a production component is implemented
when it exists only in documentation.

## AI usage

The repository contains `AI_USAGE.md`.

After each approved implementation stage, report:

- what was implemented;
- assumptions made;
- deviations from the specification;
- tests executed;
- known limitations;
- proposed commit message.

Do not edit `AI_USAGE.md` unless explicitly requested.

## Git rules

Do not create a commit until the user has reviewed:

- the implementation plan;
- changed files;
- diff;
- test results;
- assumptions;
- proposed commit message.

Each commit must represent one logical responsibility.

Do not rewrite existing Git history.

## Required workflow before editing

Before modifying files:

1. Read all approved documentation.
2. Summarize your understanding.
3. List the exact files you intend to create or modify.
4. List proposed dependencies.
5. State assumptions and ambiguities.
6. Identify anything excessive for the four-hour PoC.
7. Wait for user approval when the prompt requests planning only.

## Required completion report

After each implementation task, return:

1. Summary.
2. Files created or changed.
3. Architectural decisions implemented.
4. Assumptions made.
5. Commands run.
6. Test results.
7. Known limitations.
8. Git diff summary.
9. Proposed commit message.

Do not commit unless explicitly instructed.