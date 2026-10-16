# Delta for per-user-isolation

Issue #117 (Fase F4, Ola 4): the drawings `PUT` update path is a NEW write verb
on an owned model and MUST carry the same cross-user denial evidence as the
existing `for_user` reads/deletes. R14.1–R14.5 stay in force and unmodified.

## ADDED Requirements

### Requirement: R14.6 — Cross-user update denied (PUT)

The `PUT /market/api/drawings/<id>` path MUST resolve the row through
`Drawing.for_user(request.user)` and MUST NOT use an id-only lookup. A PUT that
targets another user's `id` MUST resolve to nothing (404) with no existence leak
and MUST NOT modify the row. The denial MUST be proven by a committed assertion
in `tests/web/test_market_api.py` (A≠B PUT → 404, A's row unchanged).

#### Scenario: B's PUT of an A id is 404

- GIVEN A's drawing `d`
- WHEN B PUTs `/market/api/drawings/<d.id>` with a valid body
- THEN 404 and A's `points`/`style` are unchanged

#### Scenario: for_user scopes the update target

- GIVEN a `Drawing` owned by A
- WHEN the PUT path calls `Drawing.for_user(B).get(pk=d.pk)` (or `.filter(...).first()`)
- THEN it resolves to nothing for B

#### Scenario: Owner's own PUT succeeds

- GIVEN A's drawing `d`
- WHEN A PUTs `/market/api/drawings/<d.id>`
- THEN 200 with the updated row scoped to A
