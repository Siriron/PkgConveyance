# Deployment

## Contract

**Deployed** — StudioNet, `0x88DcFBA04A8FE6277e2343CcF41E3E4F69460566`
([explorer](https://explorer-studio.genlayer.com/address/0x88DcFBA04A8FE6277e2343CcF41E3E4F69460566)).
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

**Live-verified as of this writing:** the contract-level static nondet safety audit (see
`docs/contracts.md`) and a confirmed StudioNet deployment at
`0x88DcFBA04A8FE6277e2343CcF41E3E4F69460566`. That is not the same claim as a verified
lifecycle: `open_deal → arm → check_transfer → settle`, and the `refund`/`abandon` paths,
have **not yet been exercised against this deployment**. Anyone picking this up should run
the full lifecycle in Run and Debug (or the live frontend) against at least one real,
currently unclaimed-by-the-tester npm package before treating any path as proven end-to-end.

**Known untested edge case worth checking live:** the `maintainer_wipe` branch requires a
package that starts with exactly one maintainer (the seller) and is then republished with a
completely different maintainer set. This is straightforward to construct on a disposable
test package but was not exercised during development, since doing so against a real
package on the public npm registry has real, live side effects on that package.
