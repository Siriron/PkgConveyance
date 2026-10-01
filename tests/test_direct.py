"""
tests/test_direct.py -- direct-mode tests that EXECUTE the real PkgConveyance contract
under GenVM (genlayer-test==0.29.2, which installs the `gltest`/`gltest.direct` package),
per this project's repository-only review requirement.

CONFIRMED API SURFACE (read directly from the installed gltest.direct source, Sep 2026 --
this project's own template guessed a different, older-looking API; that guess is NOT
followed here):
    direct_vm.sender = <bytes | Address>      -- setting the caller
    direct_vm.value  = <int>                  -- wei attached to the next call
    direct_vm.warp(iso_string)                -- set the block timestamp read via
                                                  gl.message_raw["datetime"]
    direct_vm.mock_web(url_regex, {"status":.., "body":..})  -- re.search-matched
    direct_vm.expect_revert(message=None)     -- CONTEXT MANAGER, not a raises() helper:
                                                  `with direct_vm.expect_revert("text"): ...`
    direct_vm.check_pickling = True           -- validates run_nondet closures are
                                                  picklable (this contract uses strict_eq /
                                                  run_nondet_unsafe.lazy under the hood, not
                                                  run_nondet, so this is a light sanity check
                                                  here rather than the primary safety net)
    gltest.direct.loader.create_address(seed) -- deterministic address, returned as raw
                                                  bytes in this environment (Address import
                                                  falls back); hex-encode with '0x'+b.hex()
                                                  for any str-typed contract argument.
There is no `run_validator` applicability here: this contract calls
`gl.eq_principle.strict_eq`, never `run_nondet`/`run_nondet_unsafe` directly, so there is no
captured validator closure to re-run -- every disagreement path is exercised instead by
mocking the two mirrors to disagree with each other directly.

WHAT THIS PROVES: the deterministic guards in open_deal/arm/check_transfer/settle/refund/
abandon; the strict_eq evidence-agreement logic in _lookup_block/_delivery_block, including
the corrected seller-presence rule (buyer AND seller must both be observed present in the
SAME read for `verified`) and the fixed `.status` (not `.status_code`) HTTP-error handling;
the transfer_deadline guard added to check_transfer; that non-verified check_transfer
outcomes persist their cooldown/outcome state rather than being rolled back by a revert; and
escrow conservation across settle/refund/abandon.
WHAT THIS DOES NOT PROVE: real npm registry behavior, real multi-node consensus timing, or
genuinely adversarial validator disagreement beyond what direct mode can simulate by mocking
two mirrors differently.

Run: pip install "genlayer-test==0.29.2"; pytest tests -q -p no:cacheprovider
Do not run with -s.
"""
import json
import pytest

from gltest.direct.loader import create_address

CONTRACT = "contracts/PkgConveyance.py"

NPMJS_PATTERN = r"registry\.npmjs\.org/"
NPMMIRROR_PATTERN = r"registry\.npmmirror\.com/"

PKG = "left-pad-fake"
SELLER_USER = "seller_ada"
BUYER_USER = "buyer_bob"
ESCROW_WEI = 10 ** 18

_seller_bytes = create_address("seller")
_seller2_bytes = create_address("seller2")
_buyer_bytes = create_address("buyer")


def hexaddr(b: bytes) -> str:
    return "0x" + b.hex()


SELLER_ADDR = hexaddr(_seller_bytes)
SELLER2_ADDR = hexaddr(_seller2_bytes)
BUYER_ADDR = hexaddr(_buyer_bytes)


def doc(maintainers, latest="1.0.0", modified="2026-01-01T00:00:00.000Z"):
    return json.dumps({
        "name": PKG,
        "maintainers": [{"name": n, "email": "%s@example.invalid" % n} for n in maintainers],
        "dist-tags": {"latest": latest},
        "time": {"modified": modified},
    })


def warp(direct_vm, iso):
    """direct_vm.warp() only updates datetime.now(); this contract reads
    gl.message_raw["datetime"], which the harness does not refresh, so set both."""
    import genlayer.gl as gl
    direct_vm.warp(iso)
    gl.message_raw["datetime"] = iso


def mock_both_mirrors(direct_vm, maintainers, status=200, **doc_kwargs):
    # mock_web APPENDS and the first match wins, so always clear before re-mocking.
    direct_vm.clear_mocks()
    body = doc(maintainers, **doc_kwargs)
    direct_vm.mock_web(NPMJS_PATTERN, {"status": status, "body": body})
    direct_vm.mock_web(NPMMIRROR_PATTERN, {"status": status, "body": body})


def mock_mirror_disagreement(direct_vm, maintainers_a, maintainers_b):
    direct_vm.clear_mocks()
    direct_vm.mock_web(NPMJS_PATTERN, {"status": 200, "body": doc(maintainers_a)})
    direct_vm.mock_web(NPMMIRROR_PATTERN, {"status": 200, "body": doc(maintainers_b)})


@pytest.fixture
def opened(direct_vm, direct_deploy):
    """A deal opened with the seller as sole maintainer (buyer not yet added)."""
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = _buyer_bytes
    mock_both_mirrors(direct_vm, [SELLER_USER])
    direct_vm.value = ESCROW_WEI
    out = contract.open_deal("deal-1", PKG, SELLER_ADDR, SELLER_USER, BUYER_USER)
    assert "OFFERED" in out, out
    direct_vm.value = 0
    return contract


@pytest.fixture
def locked(opened, direct_vm):
    """An opened deal, armed by the seller into LOCKED."""
    direct_vm.sender = _seller_bytes
    mock_both_mirrors(direct_vm, [SELLER_USER])
    out = opened.arm("deal-1")
    assert "LOCKED" in out, out
    return opened


# ---------------------------------------------------------------- open_deal
def test_open_deal_escrows_and_records_baseline(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = _buyer_bytes
    mock_both_mirrors(direct_vm, [SELLER_USER])
    direct_vm.value = ESCROW_WEI
    out = contract.open_deal("d1", PKG, SELLER_ADDR, SELLER_USER, BUYER_USER)
    assert "OFFERED" in out
    deal = contract.get_deal("d1")
    assert deal["state"] == "OFFERED"
    assert deal["escrow"] == str(ESCROW_WEI)
    assert deal["seller_npm_username"] == SELLER_USER
    assert deal["buyer_npm_username"] == BUYER_USER
    ledger = contract.ledger()
    assert ledger["total_escrowed"] == str(ESCROW_WEI)


def test_open_deal_declines_and_refunds_when_seller_not_maintainer(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = _buyer_bytes
    mock_both_mirrors(direct_vm, ["someone_else"])
    direct_vm.value = ESCROW_WEI
    out = contract.open_deal("d1", PKG, SELLER_ADDR, SELLER_USER, BUYER_USER)
    assert "[EXPECTED]" in out
    assert contract.list_deals() == []
    ledger = contract.ledger()
    assert ledger["total_escrowed"] == "0"  # value was declined, never escrowed


def test_open_deal_declines_when_buyer_already_maintainer(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = _buyer_bytes
    mock_both_mirrors(direct_vm, [SELLER_USER, BUYER_USER])
    direct_vm.value = ESCROW_WEI
    out = contract.open_deal("d1", PKG, SELLER_ADDR, SELLER_USER, BUYER_USER)
    assert "[EXPECTED]" in out


def test_open_deal_rejects_zero_value(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = _buyer_bytes
    direct_vm.value = 0
    out = contract.open_deal("d1", PKG, SELLER_ADDR, SELLER_USER, BUYER_USER)
    assert "[EXPECTED]" in out and "escrow" in out  # declined via return, never reverts
    assert contract.list_deals() == []


def test_open_deal_rejects_duplicate_id(opened, direct_vm):
    direct_vm.sender = _seller2_bytes
    mock_both_mirrors(direct_vm, [SELLER_USER])
    direct_vm.value = ESCROW_WEI
    out = opened.open_deal("deal-1", PKG, SELLER2_ADDR, SELLER_USER, BUYER_USER)
    assert "[EXPECTED]" in out


# ---------------------------------------------------------------- arm
def test_arm_moves_to_locked_and_sets_transfer_deadline(opened, direct_vm):
    direct_vm.sender = _seller_bytes
    mock_both_mirrors(direct_vm, [SELLER_USER])
    out = opened.arm("deal-1")
    assert "LOCKED" in out
    deal = opened.get_deal("deal-1")
    assert deal["state"] == "LOCKED"
    assert deal["transfer_deadline"] != ""


def test_arm_rejects_non_seller_caller(opened, direct_vm):
    direct_vm.sender = _buyer_bytes
    mock_both_mirrors(direct_vm, [SELLER_USER])
    with direct_vm.expect_revert("only the named seller"):
        opened.arm("deal-1")


def test_arm_rejects_if_seller_no_longer_maintainer(opened, direct_vm):
    direct_vm.sender = _seller_bytes
    mock_both_mirrors(direct_vm, ["someone_else"])
    with direct_vm.expect_revert("no longer maintains"):
        opened.arm("deal-1")


# ---------------------------------------------------------------- check_transfer: outcomes
def test_check_transfer_verified_when_both_present(locked, direct_vm):
    mock_both_mirrors(direct_vm, [SELLER_USER, BUYER_USER])
    out = locked.check_transfer("deal-1")
    assert "VERIFIED" in out
    deal = locked.get_deal("deal-1")
    assert deal["state"] == "VERIFIED"
    assert deal["checks"] == "1"


def test_check_transfer_not_yet_added_when_only_seller_present(locked, direct_vm):
    mock_both_mirrors(direct_vm, [SELLER_USER])
    out = locked.check_transfer("deal-1")
    assert "[TRANSIENT]" in out
    deal = locked.get_deal("deal-1")
    assert deal["state"] == "LOCKED"  # unchanged
    assert deal["last_check_outcome"] == "not_yet_added"
    assert deal["checks"] == "1"  # persisted, not rolled back by the tagged return


def test_check_transfer_not_yet_added_when_only_buyer_present_is_not_verified(locked, direct_vm):
    """Regression test for the corrected seller-presence rule: a seller who has already
    removed themselves once the buyer is present must NOT be reported as verified -- both
    names must be observed present in the same read."""
    mock_both_mirrors(direct_vm, [BUYER_USER])
    out = locked.check_transfer("deal-1")
    assert "[TRANSIENT]" in out
    assert "VERIFIED" not in out
    deal = locked.get_deal("deal-1")
    assert deal["state"] == "LOCKED"
    assert deal["last_check_outcome"] == "not_yet_added"


def test_check_transfer_maintainer_wipe_when_neither_present(locked, direct_vm):
    mock_both_mirrors(direct_vm, ["nobody_relevant"])
    out = locked.check_transfer("deal-1")
    assert "[EXPECTED]" in out  # a wipe is reported as an expected, non-retryable-by-waiting outcome
    deal = locked.get_deal("deal-1")
    assert deal["state"] == "LOCKED"
    assert deal["last_check_outcome"] == "maintainer_wipe"


def test_check_transfer_package_gone(locked, direct_vm):
    direct_vm.clear_mocks()
    direct_vm.mock_web(NPMJS_PATTERN, {"status": 404, "body": ""})
    direct_vm.mock_web(NPMMIRROR_PATTERN, {"status": 404, "body": ""})
    out = locked.check_transfer("deal-1")
    assert "[TRANSIENT]" in out
    deal = locked.get_deal("deal-1")
    assert deal["last_check_outcome"] == "package_gone"


# ---------------------------------------------------------------- check_transfer: fixed bugs
def test_check_transfer_persists_cooldown_state_on_failed_check(locked, direct_vm):
    """Regression test for the storage-rollback bug: a non-verified outcome must not
    revert (which would roll back last_check_at/checks), or the advertised cooldown never
    actually throttles anything."""
    mock_both_mirrors(direct_vm, [SELLER_USER])
    locked.check_transfer("deal-1")
    deal = locked.get_deal("deal-1")
    assert deal["last_check_at"] != ""
    assert deal["checks"] == "1"
    ledger = locked.ledger()
    assert ledger["checks_run"] == "1"
    # Cooldown must now actually be enforced on an immediate second call.
    mock_both_mirrors(direct_vm, [SELLER_USER, BUYER_USER])
    with direct_vm.expect_revert("cooldown"):
        locked.check_transfer("deal-1")
    deal2 = locked.get_deal("deal-1")
    assert deal2["state"] == "LOCKED"  # still not verified -- cooldown blocked the retry
    assert deal2["checks"] == "1"  # the throttled call did not re-run the check


def test_check_transfer_rejects_after_transfer_deadline(locked, direct_vm):
    """Regression test for the missing transfer_deadline guard."""
    deal = locked.get_deal("deal-1")
    warp(direct_vm, deal["transfer_deadline"])
    mock_both_mirrors(direct_vm, [SELLER_USER, BUYER_USER])
    with direct_vm.expect_revert("transfer_deadline"):
        locked.check_transfer("deal-1")
    # state must remain LOCKED, not silently VERIFIED past the deadline
    assert locked.get_deal("deal-1")["state"] == "LOCKED"


def test_check_transfer_rejects_wrong_state(opened, direct_vm):
    with direct_vm.expect_revert("requires state"):
        opened.check_transfer("deal-1")  # still OFFERED, never armed


def test_http_error_on_both_mirrors_becomes_transient_not_evidence(locked, direct_vm):
    """Regression guard for the status_code bug: SDK Response has .status, never
    .status_code. The 500 body here is a VALID registry document showing a completed
    transfer, so if the helper ignores the status the deal would wrongly verify."""
    direct_vm.clear_mocks()
    body = doc([SELLER_USER, BUYER_USER])
    direct_vm.mock_web(NPMJS_PATTERN, {"status": 500, "body": body})
    direct_vm.mock_web(NPMMIRROR_PATTERN, {"status": 500, "body": body})
    with direct_vm.expect_revert():
        locked.check_transfer("deal-1")
    deal = locked.get_deal("deal-1")
    assert deal["state"] == "LOCKED"
    assert deal["last_check_outcome"] == ""


def test_mirror_disagreement_reverts_transient(locked, direct_vm):
    mock_mirror_disagreement(direct_vm, [SELLER_USER, BUYER_USER], [SELLER_USER])
    with direct_vm.expect_revert():
        locked.check_transfer("deal-1")
    deal = locked.get_deal("deal-1")
    assert deal["state"] == "LOCKED"
    assert deal["last_check_outcome"] == ""  # genuinely nothing decided, nothing stored


# ---------------------------------------------------------------- settle / refund / abandon
def test_settle_pays_seller_and_conserves_escrow(locked, direct_vm):
    mock_both_mirrors(direct_vm, [SELLER_USER, BUYER_USER])
    locked.check_transfer("deal-1")
    out = locked.settle("deal-1")
    assert "SETTLED" in out
    deal = locked.get_deal("deal-1")
    assert deal["state"] == "SETTLED"
    assert deal["paid_to_seller"] == str(ESCROW_WEI)
    ledger = locked.ledger()
    assert ledger["total_released"] == str(ESCROW_WEI)
    assert int(ledger["held"]) == 0


def test_settle_rejects_before_verified(locked, direct_vm):
    with direct_vm.expect_revert("requires state"):
        locked.settle("deal-1")


def test_refund_after_transfer_deadline_returns_buyer(locked, direct_vm):
    deal = locked.get_deal("deal-1")
    warp(direct_vm, deal["transfer_deadline"])
    out = locked.refund("deal-1")
    assert "REFUNDED" in out
    ledger = locked.ledger()
    assert ledger["total_refunded"] == str(ESCROW_WEI)
    assert int(ledger["held"]) == 0


def test_refund_rejects_before_deadline(locked, direct_vm):
    with direct_vm.expect_revert("has not lapsed"):
        locked.refund("deal-1")


def test_refund_after_accept_deadline_while_offered(opened, direct_vm):
    deal = opened.get_deal("deal-1")
    warp(direct_vm, deal["accept_deadline"])
    out = opened.refund("deal-1")
    assert "REFUNDED" in out


def test_abandon_while_offered_by_either_party(opened, direct_vm):
    direct_vm.sender = _buyer_bytes
    out = opened.abandon("deal-1")
    assert "ABANDONED" in out


def test_abandon_while_locked_seller_only(locked, direct_vm):
    direct_vm.sender = _buyer_bytes
    with direct_vm.expect_revert("only the seller"):
        locked.abandon("deal-1")
    direct_vm.sender = _seller_bytes
    out = locked.abandon("deal-1")
    assert "ABANDONED" in out


def test_escrow_conservation_across_lifecycle(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = _buyer_bytes
    mock_both_mirrors(direct_vm, [SELLER_USER])
    direct_vm.value = ESCROW_WEI
    contract.open_deal("d1", PKG, SELLER_ADDR, SELLER_USER, BUYER_USER)
    direct_vm.value = 0
    direct_vm.sender = _seller_bytes
    contract.arm("d1")
    mock_both_mirrors(direct_vm, [SELLER_USER, BUYER_USER])
    contract.check_transfer("d1")
    contract.settle("d1")
    ledger = contract.ledger()
    assert (int(ledger["total_escrowed"])
            == int(ledger["total_released"]) + int(ledger["total_refunded"]) + int(ledger["held"]))
    assert int(ledger["held"]) == 0


# ---------------------------------------------------------------- storage / nondet safety
def test_no_storage_object_crosses_into_the_strict_eq_closure(direct_vm, direct_deploy):
    """check_pickling makes direct mode warn on storage-backed/unpicklable values leaking
    into a strict_eq closure (this project's Bug 4/5/6 class, applied to strict_eq's
    underlying run_nondet_unsafe.lazy machinery instead of a raw run_nondet_unsafe call)."""
    direct_vm.check_pickling = True
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = _buyer_bytes
    mock_both_mirrors(direct_vm, [SELLER_USER])
    direct_vm.value = ESCROW_WEI
    contract.open_deal("d1", PKG, SELLER_ADDR, SELLER_USER, BUYER_USER)
    direct_vm.value = 0
    direct_vm.sender = _seller_bytes
    contract.arm("d1")
    mock_both_mirrors(direct_vm, [SELLER_USER, BUYER_USER])
    contract.check_transfer("d1")


def test_probe_package_is_storage_free(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    mock_both_mirrors(direct_vm, [SELLER_USER])
    out = contract.probe_package(PKG)
    assert out["found"] == "True"
    assert contract.list_deals() == []
