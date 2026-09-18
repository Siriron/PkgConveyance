# Frontend

React + Vite, no framework beyond that. Hash-free path-based routing implemented by hand
(`App.tsx`) via `window.history.pushState` and `popstate` — small enough surface area that a
router dependency wasn't worth adding.

## Structure

- `src/config/chains.ts` — the one file to edit after redeploying the contract.
- `src/lib/genlayer/client.ts` — `ensureChain`, the write/read client constructors, and
  `TimeoutError` for a stuck `waitForTransactionReceipt`.
- `src/lib/genlayer/contract.ts` — `readView` / `writeMethod` wrappers used by every page.
- `src/lib/useWallet.ts` — wallet connection with `eth_accounts` silent reconnect on mount
  and `accountsChanged` sync.
- `src/pages/` — `DealsPage` (manifest list + the `probe_package` resolver hero),
  `NewDealPage` (`open_deal` form), `DealDetailPage` (the full state-machine action panel),
  `DocsPage`.
- `src/components/` — `Topbar`, `ErrorBoundary`, `PackageResolver`.

## Design system

A "manifest/ledger" register, distinct from every prior app in this project's tracker: a
warm paper background, a monospace type layer for every package name, npm username, address,
and timestamp (functional here, not decorative — this is a registry), and a serif display
face for headings. Deal list entries render as a lockfile-style vertical manifest with
hairline dividers, not shadowed cards. Accent palette: npm red `#B23A38` (grounded in npm's
own real brand color, desaturated), registry teal `#2B6E6E` for verified/success states,
amber `#A8732A` for locked/pending states — checked against this project's own accent-color
log and does not repeat any prior build's palette.

## Loading and error states

Every async view call (`readView`) and every write (`writeMethod`) has an explicit loading
state (`"Loading…"`, `"Resolving…"`, per-button pending labels) and a distinct error banner.
Any write shows a `pending-note` linking directly to the explorer transaction once submitted,
since GenLayer consensus genuinely takes minutes rather than seconds — a person should never
be staring at a spinner with no way to check whether it actually went through.

## Known gap

No automated end-to-end test suite for the frontend — every path was checked by hand against
the static audit in `docs/contracts.md`, not against a live deployment (see
`docs/deployment.md`'s testing-status section for the same honest framing applied there).
