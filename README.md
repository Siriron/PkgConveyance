<div align="center">

<img src="./docs/assets/mark.svg" width="88" alt="PkgConveyance logo" />

# PkgConveyance

### Escrow for an npm package ownership transfer, settled on public registry evidence — no model, no oracle.

<br />

![Status](https://img.shields.io/badge/status-deployed-brightgreen?style=flat-square)
![Networks](https://img.shields.io/badge/networks-StudioNet-blue?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)
![Stack](https://img.shields.io/badge/stack-React%20%2B%20Vite%20%2B%20GenVM-B23A38?style=flat-square)
![Consensus](https://img.shields.io/badge/consensus-strict__eq%20%28no%20LLM%29-2B6E6E?style=flat-square)

<br />

**[Documentation](./docs/architecture.md)** &nbsp;·&nbsp; **[Smart Contract](./contracts/PkgConveyance.py)** &nbsp;·&nbsp; **[Explorer](https://explorer-studio.genlayer.com/address/0x88DcFBA04A8FE6277e2343CcF41E3E4F69460566)**

</div>

<br />

---

## What this is

A buyer escrows GEN to buy a named npm package's maintainer access. A seller who currently
maintains it adds the buyer's npm username to the package's maintainer list on the real npm
registry. The contract fetches the registry's own public metadata — never a screenshot or a
claim — inside consensus, on two independently operated mirrors, and pays the seller only
when both agree the buyer is now listed and the seller hasn't wiped every other maintainer
on the way out.

<br />

<div align="center">

| | |
|---|---|
| **Concept** | Escrowed npm package ownership transfer |
| **Consensus need** | A seller who never transfers keeps the escrow if trusted on their word; a buyer who claims non-delivery falsely keeps the package unpaid for. Neither can be resolved by either party's own say-so. |
| **Evidence source** | The npm registry's own public `maintainers` array — never a URL or description the parties supply |
| **Consensus mechanism** | `gl.eq_principle.strict_eq` — deterministic, no LLM anywhere in this contract |
| **Network** | StudioNet |

</div>

<br />

---

## How it works

1. Buyer escrows the price via `open_deal`, naming the package, the seller's npm username,
   and their own. The contract confirms today that the seller maintains it and the buyer
   does not, on both `registry.npmjs.org` and `registry.npmmirror.com`.
2. Seller calls `arm` once ready — re-confirmed live, not trusted from the baseline —
   opening the transfer window.
3. Seller adds the buyer's npm username as a maintainer, off-chain, on npm itself.
4. Anyone calls `check_transfer`. The contract reads both mirrors again: if the buyer now
   appears **and** the seller still does, it moves to `VERIFIED`.
5. Anyone calls `settle` to release the escrow.

If the seller never arms, or the transfer never happens before its deadline, `refund`
returns the escrow to the buyer — no dispute, no arbitration, just a clock and a public
registry.

<br />

<details>
<summary><b>Why two names are checked at delivery, not one</b></summary>
<br />

A seller who removes every other maintainer except the buyer has transferred the package —
reported as `verified`. A seller who removes everyone, including the buyer's own pending
add, and republishes solo has not — reported as `maintainer_wipe`, a distinct outcome from
`not_yet_added`. Checking only for the buyer's name would not tell these two apart.

</details>

<br />

---

## Deployed contracts

<div align="center">

| Network | Address | Explorer |
|---|---|---|
| StudioNet | `0x88DcFBA04A8FE6277e2343CcF41E3E4F69460566` | [View](https://explorer-studio.genlayer.com/address/0x88DcFBA04A8FE6277e2343CcF41E3E4F69460566) |

</div>

<br />

---

## Quick start

```bash
cd frontend
npm install
npm run dev
```

Full deployment instructions: [`docs/deployment.md`](./docs/deployment.md)

<br />

---

## Project structure

```
contracts/PkgConveyance.py    The GenVM contract — no LLM, strict_eq consensus only
frontend/                      React + Vite app
docs/                          architecture.md, deployment.md, frontend.md, contracts.md
LICENSE                        MIT
```

<br />

---

## Status

<div align="center">

![Audited](https://img.shields.io/badge/nondet%20safety%20audit-passed-brightgreen?style=flat-square)
![Deployed](https://img.shields.io/badge/StudioNet%20deploy-confirmed-brightgreen?style=flat-square)
![Untested](https://img.shields.io/badge/full%20lifecycle-not%20yet%20live--tested-yellow?style=flat-square)

</div>

The contract has been checked against every item in this project's mandatory nondet safety
audit (see `docs/contracts.md`) — one real bug was found and fixed during that process (a
bound-method call leaking into a `strict_eq` closure). It is **deployed to StudioNet** at
`0x88DcFBA04A8FE6277e2343CcF41E3E4F69460566`. The full `open_deal → arm → check_transfer →
settle` lifecycle, and the `refund`/`abandon` paths, have **not yet been exercised live**
against that deployment — a deployed contract and a live-tested one are different claims,
and this section will be updated once the lifecycle has actually been run, not before. See
`docs/deployment.md`'s testing-status section for the exact current state.

<br />

---

<div align="center">

Built on [GenLayer](https://genlayer.com) · [Portal submission](https://portal.genlayer.foundation/)

</div>
