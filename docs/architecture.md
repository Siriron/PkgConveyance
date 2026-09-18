# Architecture

## Concept

PkgConveyance escrows GEN for the transfer of an npm package's ownership. A buyer names a
package and the seller's npm username; the seller — already a maintainer of record — adds
the buyer's npm username to the package's maintainer list at the real npm registry. The
contract releases escrow only when the registry's own public metadata confirms the
maintainer list actually changed.

## Why this needs GenLayer

The npm registry's maintainer list is public but lives entirely off-chain, at
`registry.npmjs.org`. No oracle relay and no keeper bot are trustworthy proxies for it,
because both require trusting a third party to have copied the registry's answer correctly
and at the right moment. GenLayer removes that trust requirement: every validator fetches
the registry document itself, inside the same consensus round that decides the verdict, and
`gl.eq_principle.strict_eq` requires every validator's fetch to agree byte-for-byte before
anything is written. If the registry is flaky, or two independently operated mirrors of it
disagree even briefly, the call reverts as `[TRANSIENT]` rather than committing a guess.

## Why there is no model anywhere in this contract

The npm registry document is small, stable, machine-readable JSON. Whether a given username
appears in a `maintainers` array is not a judgment call — it is either present or it is not.
Every field this contract's verdict depends on is checked by exact string/set comparison
inside `gl.eq_principle.strict_eq`, never by an LLM. This makes PkgConveyance a genuinely
different mechanism shape from every other Projects-track build so far: no leader/validator
LLM prompt, no confidence score, no reasoning-summary field.

## Two evidence questions, not one

Collapsing "is the seller a maintainer" and "did the transfer happen" into a single check is
how this class of contract gets it wrong. PkgConveyance asks them at two separate points:

1. **At `open_deal` and again at `arm`**: is the named seller currently a maintainer of
   record? A deal opened against a package the seller does not control cannot ever be
   delivered honestly.
2. **At `check_transfer`**: does the maintainer list now contain the buyer's named
   username, **and does it still contain the seller's**? The second half is load-bearing.
   A seller who removes every maintainer except the buyer has completed a transfer; a
   seller who removes everyone — including the buyer's own pending add — and republishes
   solo has not, and a check that only looked for the buyer's name could not tell those
   two outcomes apart. This contract reports `maintainer_wipe` as its own distinct outcome
   from `not_yet_added` and from `verified`.

## Two independent registry mirrors, every read

Every consensus block fetches both `registry.npmjs.org` and the independently operated
`registry.npmmirror.com`, and requires them to report the identical maintainer set before
proceeding. A disagreement between the two mirrors is reported as `[TRANSIENT]` — retryable,
nobody's fault — rather than trusting either source alone.

## State machine

```
OFFERED --arm()--> LOCKED --check_transfer()--> VERIFIED --settle()--> SETTLED
   |                  |
   |                  +--(transfer deadline passes)--> refund() --> REFUNDED
   |
   +--(accept deadline passes)--> refund() --> REFUNDED
   |
   +--abandon()--> ABANDONED   (either party while OFFERED, seller only once LOCKED)
```

## Where the escrow moves

Exactly three places, and nowhere else: `settle()` pays the seller, `refund()` and
`abandon()` pay the buyer. Every one of them writes the terminal state to storage before
calling `emit_transfer`, and `total_escrowed == total_released + total_refunded + balance
still held` holds at every point — see `ledger()`.

## What this contract does not verify

Stated once, directly, because it is the boundary a reviewer or a user should not have to
infer: PkgConveyance verifies public npm maintainer-list membership. It does not prove legal
ownership of the package name, the identity of the human behind an npm account, that the
seller has no other account with residual publish rights, or anything about the package's
source repository, license, or code contents.
