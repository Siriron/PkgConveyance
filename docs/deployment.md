# Deployment

## Contract

**Deployed** — StudioNet, `0x0E22e987cC239fAf76bf87Ba04d9289C596c1dab`
([explorer](https://explorer-studio.genlayer.com/address/0x0E22e987cC239fAf76bf87Ba04d9289C596c1dab)).
`frontend/src/config/chains.ts` already points at this address.

To redeploy or deploy a fresh instance:

1. Open [studio.genlayer.com](https://studio.genlayer.com/contracts) and deploy
   `contracts/PkgConveyance.py` to StudioNet.
2. Confirm line 1 is the pinned runner comment (`py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`) —
   Studio rejects an unpinned or `"test"` runner before the contract logic ever runs.
3. Use Studio's **Run and Debug** panel to exercise every write method against a real,
   currently-registered npm package before wiring up the frontend. This is the fastest way
   to confirm a nondet fix actually works — no wallet, no frontend redeploy needed.
4. Copy the deployed address into `frontend/src/config/chains.ts` as the
   `CONTRACT_ADDRESS` constant. This is the one place the address lives in this codebase.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Deploy to Vercel as a static Vite build; `vercel.json` already carries the SPA rewrite rule
so client-side routes (`/deals/:id`) resolve correctly on a hard refresh.

## Testing status — honest, not rounded up

**Executed in this repository:** `tests/test_direct.py` runs 28 direct-mode tests against the
real contract under the GenVM SDK (`pip install "genlayer-test==0.29.2"`, then
`pytest tests -q -p no:cacheprovider`), and `genvm-lint check contracts/PkgConveyance.py`
passes. Only the two npm registries are mocked. The tests include regression tests for the
three defects fixed after steward review (late verification past `transfer_deadline`, failed
checks losing their cooldown state to a storage rollback, and the seller-presence rule) and for
the HTTP-status handling fix; each was confirmed to fail against the pre-fix contract.

**Run live on StudioNet (Oct 1 2026), contract `0x0E22e987cC239fAf76bf87Ba04d9289C596c1dab`,
current code, 5 validators, 0 rotations, every transaction finalized:**
- `probe_package` (lodash; both mirrors agreed; empty stderr).
- `open_deal` (1 GEN escrowed, `OFFERED`; empty stderr).
- `arm` (`LOCKED`, transfer deadline 10 days out; empty stderr).
- `check_transfer` returning `not_yet_added`, after which `get_deal` showed `checks` = 1,
  `last_check_at` and `last_check_outcome` persisted (the rollback fix).
- A second `check_transfer` about three minutes later, which reverted with
  `[TRANSIENT] deal t1 was checked less than 300 seconds ago ... retry after the cooldown`
  (the cooldown, now actually enforced because the first check's state persisted).
- `abandon` (1 GEN returned to the buyer; the contract's refund transfer appears as a child
  transaction).
The live run used the public lodash package as a read-only target, so the deal could never
verify.

**Not proven live:** `VERIFIED` and `settle`, a buyer-present/seller-absent check, `refund`
past a deadline, the late-verification (`transfer_deadline`) rejection, and the
`maintainer_wipe` and `package_gone` branches. These are covered only by direct-mode tests with
mocked registries. Real multi-node behavior beyond the calls above is not proven.
