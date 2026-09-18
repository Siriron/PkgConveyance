# Contract reference

Contract: `contracts/PkgConveyance.py`. Pinned runner: `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`.

## Write methods

| Method | Payable | Caller | Effect |
|---|---|---|---|
| `open_deal(deal_id, package_name, seller, seller_npm_username, buyer_npm_username)` | yes | anyone (buyer) | Escrows `gl.message.value`. Confirms today, via both registry mirrors, that `seller_npm_username` maintains the package and `buyer_npm_username` does not. Refunds and returns a `[TAG]`-prefixed string on any refusal — never reverts once value has been attached. |
| `arm(deal_id)` | no | seller only | Re-confirms the seller is still a maintainer, live. Moves `OFFERED -> LOCKED` and opens the transfer window. |
| `check_transfer(deal_id)` | no | anyone, rate-limited | Reads both mirrors. If both the buyer's and seller's usernames appear, moves to `VERIFIED`. If neither appears, reports `maintainer_wipe`. If only the seller's appears, reports `not_yet_added`. All non-`verified` outcomes are `[TRANSIENT]` reverts that leave the deal in `LOCKED`. |
| `settle(deal_id)` | no | anyone | Once `VERIFIED`, pays the full escrow to the seller. |
| `refund(deal_id)` | no | anyone | Once the accept deadline (`OFFERED`) or transfer deadline (`LOCKED`) has passed, returns escrow to the buyer. |
| `abandon(deal_id)` | no | either party (`OFFERED`) / seller only (`LOCKED`) | Cancels before delivery; escrow returns to the buyer. |
| `probe_package(package_name)` | no | anyone | Runs the same two-mirror consensus read with no storage write — lets a frontend show a package's current state before any value is committed. |

## Views

`get_deal(deal_id)`, `list_deals()`, `deal_for_package(package_name)`, `ledger()`,
`parameters()` — all read-only, all return JSON-serializable dicts/lists per GenVM's view
convention.

## Refusal taxonomy

Every refusal string in this contract is prefixed with one of four tags:

- `[EXPECTED]` — a real rule fired; this is a decision (e.g. the seller does not currently
  maintain the package).
- `[EXTERNAL]` — a registry mirror answered with an error status; nothing was decided.
- `[TRANSIENT]` — nothing was decided and the same call may succeed on retry (e.g. the two
  mirrors currently disagree, or a rate-limit cooldown is still active).
- `[LLM_ERROR]` — kept for taxonomy parity with this project's other evidence-arbitration
  contracts, even though this contract calls no model. Used when a registry that claims to
  speak JSON returns a body that does not parse as JSON.

## Evidence sources

- `https://registry.npmjs.org/<package>` — npm's own public registry API.
- `https://registry.npmmirror.com/<package>` — an independently operated mirror serving the
  identical document shape.

Both are read inside every `gl.eq_principle.strict_eq` block. A disagreement between them
about whether a package exists, or about its maintainer set, is a `[TRANSIENT]` refusal —
never resolved by picking one source over the other.

## Nondet safety audit, applied in full

Every item in this project's mandatory pre-deploy checklist was run against this contract
before writing this document:

- No `.send()` anywhere; the contract moves value only via `emit_transfer(value=...)`.
- Zero `self.`-prefixed references inside any `def work():` closure passed to
  `gl.eq_principle.strict_eq` — including indirectly through a bound helper method. A real
  bug of exactly this shape (`self._join_sorted(...)` called from inside two `work()`
  bodies) was found and fixed during development by moving the helper to module level as
  `_join_sorted_names`.
- Every class-body attribute with a type annotation is genuine, mutable, per-instance
  contract storage — no constants declared inside the class body.
- `json.loads()` is called only on a raw HTTP response body inside `_decode_json`, never on
  a `strict_eq` return value or a `leaders_res`-derived value (this contract does not use
  `run_nondet_unsafe`, so there is no `leaders_res` wrapper at all — `strict_eq` returns the
  plain agreed value directly).
- `float()` does not appear anywhere in the contract's executable code.
- `gl.eq_principle.strict_eq(work)` is called positionally in both of its two call sites.
- `DynArray[str]` (`deal_ids`) is declared directly on the top-level `gl.Contract` class,
  never on a nested `@allow_storage` dataclass, and is only ever `.append()`'d to — the
  confirmed-safe pattern from this project's own Bug 7 catalog.
- Every value in the four-outcome verdict set (`verified`, `not_yet_added`,
  `maintainer_wipe`, `package_gone`) is traced to an explicit, reachable branch inside
  `work()` — an exhaustive four-way partition on package existence and each username's
  membership, with no disclosed-but-unreachable value.
- Timestamp handling uses the confirmed hand-rolled `_now_epoch_seconds()` parser (never
  `datetime.now()`, never `int()` on the raw ISO string).
- Escrow conservation: exactly three payout sites (`settle`, `refund`, `abandon`), each
  writing the terminal state to storage before calling `_pay`, with no protocol fee —
  `total_escrowed == total_released + total_refunded + balance held` at every point.

## Deliberate gaps

- No support for scoped-package transfer where the scope itself (not just the package
  within it) changes ownership — npm scopes are organizations, not individual maintainer
  lists, and are out of scope for this contract's first version.
- No partial/installment escrow — a deal is all-or-nothing on the full named price.
- No automated cancellation on a compromised-account signal (e.g. npm's own account
  security flags) — this contract only ever reads the maintainer list, never account
  security metadata.
