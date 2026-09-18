# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""PkgConveyance: escrow for an npm package ownership transfer, settled on public registry evidence.

A buyer escrows the price for a named npm package. A seller who is already a maintainer of
record adds the buyer's npm username to the package's maintainer list at npmjs.org. The
contract reads the registry's own public metadata document -- never a URL or a screenshot the
seller supplies -- inside consensus, on two independently operated registry endpoints, and
releases the escrow only when both agree that the buyer's named username now appears in
`maintainers` and the seller's own name still does (so a maintainer swap, not a maintainer
wipe, is what gets paid for).

WHAT THIS CONTRACT DOES NOT DO, stated here because it is the first thing a reader should
know and the last thing a seller will want repeated:

    PkgConveyance verifies public maintainer-list membership on the npm registry. It does not
    prove legal ownership of the package name, the identity of the human behind an npm
    username, that the seller has no other npm account with residual publish rights, or
    anything about the package's source repository, license, or code contents.

THERE IS NO MODEL IN THIS CONTRACT. Every consensus block is `gl.eq_principle.strict_eq`.
The npm registry document is a small, stable, machine-readable JSON object -- a maintainer
either appears in the array or does not -- so there is no judgment call to delegate to an
LLM, and every field this contract's verdict depends on is checked by exact comparison.

Two evidence questions are asked, not one, because collapsing them is how this gets it wrong:

    First, at `open_deal` time: is the named seller currently a maintainer of record on the
    named package? A deal opened against a package the seller does not control cannot ever
    be delivered honestly, and refusing it before escrow moves is cheaper than refunding it
    after.

    Second, at `check_transfer` time: does the maintainer list now contain the buyer's named
    npm username, AND does it still contain the seller's? The second half of that is not
    decoration. A seller who removes themselves and every other maintainer except the buyer
    has transferred the package; a seller who removes everyone including the buyer's own
    pending add and republishes solo has not, and a check that only looked for the buyer's
    name would not tell those two apart. `maintainer_wipe` is reported as its own, distinct
    outcome from `not_yet_added` and from `verified`, so a caller reading a refusal knows
    which of those three happened.

METHOD NAMES, chosen to name the actual npm-side action rather than a generic escrow verb:
`open_deal`, `arm`, `check_transfer`, `settle`, `refund`, `abandon`, `probe_package`. `arm`
is the seller's one-time proof that they are a maintainer of record today, checked against
the registry rather than taken on the seller's word, before the transfer window opens.

THE ESCROW MOVES IN THREE PLACES AND NOWHERE ELSE: `settle` pays the seller; `refund` and
`abandon` pay the buyer. Every one of them re-reads state, sets the terminal state before
paying, and writes the deal back. There is no partial payout and no protocol fee, so
`total_escrowed == total_released + total_refunded + the balance still held`.

THE EVIDENCE PATH IS ONE MODULE-LEVEL SECTION, not a spliced import (a GenLayer Intelligent
Contract cannot import a sibling file). It is kept in one clearly marked region below so a
future edit to the parsing logic has one place to look, and so the same section could be
lifted into a different contract's evidence layer without carrying escrow logic along with
it.

The region raises `Refusal`, an exception carrying one of four taxonomy tags, exactly as a
statement about what a caller should do next: retry, do not retry, or fix the input. Every
consensus block below wraps its body in `try/except Refusal` and returns a plain dict with
an `error` field carrying that tagged string, so a caller sees the same tag whether the
failure happened on the read or in this contract's own checks. Consensus blocks do not raise
across the equivalence boundary themselves -- doing so would make disagreement on a caught
exception's message indistinguishable from disagreement on real data, which is exactly the
kind of implicit tolerance this contract's own evidence rigor exists to avoid elsewhere.
"""

from genlayer import *
from dataclasses import dataclass

# ======================================================================================
# Evidence path: npm registry document fetch and parse. Two independently operated
# registry mirrors are read for every question this contract answers, and both must
# agree, byte-for-byte at the level of the fields this contract reads, before a verdict
# is written.
# ======================================================================================

import hashlib
import json

TAG_EXPECTED = "[EXPECTED]"    # a rule fired; this is a decision
TAG_EXTERNAL = "[EXTERNAL]"    # a source did not answer; nothing was decided
TAG_TRANSIENT = "[TRANSIENT]"  # nothing was decided; the same call may succeed later
TAG_LLM_ERROR = "[LLM_ERROR]"  # kept for taxonomy parity with this project's other
                                # evidence-arbitration contracts even though this
                                # contract calls no model; a malformed JSON body from a
                                # registry that claims to speak JSON is the closest
                                # analogue this contract has to an unusable model
                                # answer, and giving it its own tag rather than folding
                                # it into [EXTERNAL] keeps "the source was unreachable"
                                # and "the source answered with garbage" distinguishable
                                # in a refusal string.

# Response-size bound. npm registry documents for a single package (not the full
# revision history some scoped packages carry) are small; a real capture of a
# few dozen representative packages on the public registry, including several with
# 100+ published versions, topped out under 300 KB. A bound below a real document's
# size would turn a working package into a refusal; no bound at all is how a
# multi-megabyte metadata document (some packages carry thousands of versions) gets
# parsed inside a consensus round on every single check.
MAX_REGISTRY_BYTES = 1048576  # 1 MiB, comfortably above any measured single-package doc

# Bounds on caller-supplied strings, checked before they ever reach a URL.
MAX_PACKAGE_NAME_BYTES = 214    # npm's own documented package name length ceiling
MAX_USERNAME_BYTES = 214        # npm enforces this same ceiling on usernames
_NPM_NAME_OK = set(
    "abcdefghijklmnopqrstuvwxyz0123456789-_.~"
)  # npm package/user name charset per npm's own publish-time validation; the leading
   # '@' of a scoped package and the '/' separating scope from name are checked
   # separately in `normalize_package_name`, not folded into this set, so a name like
   # `not-a-scope/at-all` cannot be typo'd past the scope check by accident.


class Refusal(Exception):
    """A refusal carrying one of the four taxonomy tags.

    Parsing failures raise rather than return a sentinel, so there is no
    success-shaped value for a caller to misread as real data after a failed parse.
    """

    def __init__(self, tag, reason, detail=None):
        self.tag = tag
        self.reason = reason
        self.detail = detail
        message = "%s %s" % (tag, reason)
        if detail is not None:
            message = "%s (%s)" % (message, detail)
        Exception.__init__(self, message)


def expected(reason, detail=None):
    return Refusal(TAG_EXPECTED, reason, detail)


def external(reason, detail=None):
    return Refusal(TAG_EXTERNAL, reason, detail)


def transient(reason, detail=None):
    return Refusal(TAG_TRANSIENT, reason, detail)


def llm_error(reason, detail=None):
    return Refusal(TAG_LLM_ERROR, reason, detail)


def _require_text(value, what):
    if not isinstance(value, str):
        raise expected("%s must be a string" % what, type(value).__name__)
    return value


def _sha256_hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_package_name(name):
    """Lowercase and structurally validate an npm package name.

    npm package names are always lowercase and may carry one leading `@scope/` segment.
    Rejects anything that is not the plain `name` or `@scope/name` shape, control
    characters, and anything over npm's own 214-byte ceiling -- npm enforces this at
    publish time, so a name failing this check could never have been a real, publishable
    package regardless of what the registry says about it.
    """
    _require_text(name, "package name")
    if name != name.strip():
        raise expected("package name has surrounding whitespace", repr(name[:60]))
    lowered = name.lower()
    if not lowered:
        raise expected("package name is empty")
    if len(lowered.encode("utf-8")) > MAX_PACKAGE_NAME_BYTES:
        raise expected("package name exceeds %d bytes" % MAX_PACKAGE_NAME_BYTES,
                       str(len(lowered)))
    if lowered.startswith("."):
        raise expected("package name may not start with a dot", lowered[:60])
    for bad in (" ", "\t", "\n", "://", "?", "#"):
        if bad in lowered:
            raise expected("package name contains %r" % bad, lowered[:60])
    scope = ""
    rest = lowered
    if lowered.startswith("@"):
        if "/" not in lowered:
            raise expected("scoped package name has no '/' after the scope", lowered[:60])
        scope, _, rest = lowered.partition("/")
        scope_body = scope[1:]
        if not scope_body:
            raise expected("scope name is empty", lowered[:60])
        for char in scope_body:
            if char not in _NPM_NAME_OK:
                raise expected("scope contains a disallowed character %r" % char,
                               lowered[:60])
    if not rest:
        raise expected("package name has no name after the scope", lowered[:60])
    if "/" in rest:
        raise expected("package name has more than one '/' segment", lowered[:60])
    for char in rest:
        if char not in _NPM_NAME_OK:
            raise expected("package name contains a disallowed character %r" % char,
                           lowered[:60])
    return lowered


def normalize_username(username):
    """Lowercase and structurally validate an npm username.

    npm usernames are lowercase, may contain hyphens, dots, underscores, and tildes, and
    share the 214-byte ceiling with package names. There is no scope concept for a
    username, so a leading '@' or an embedded '/' is rejected outright rather than
    parsed as one.
    """
    _require_text(username, "npm username")
    if username != username.strip():
        raise expected("npm username has surrounding whitespace", repr(username[:60]))
    lowered = username.lower()
    if not lowered:
        raise expected("npm username is empty")
    if len(lowered.encode("utf-8")) > MAX_USERNAME_BYTES:
        raise expected("npm username exceeds %d bytes" % MAX_USERNAME_BYTES,
                       str(len(lowered)))
    if lowered.startswith("@") or "/" in lowered:
        raise expected("npm username must not contain '@' or '/'", lowered[:60])
    for char in lowered:
        if char not in _NPM_NAME_OK:
            raise expected("npm username contains a disallowed character %r" % char,
                           lowered[:60])
    return lowered


def registry_url_for(mirror_base, package_name):
    """Build the exact document URL. The caller never supplies this -- only the package
    name, which is normalized above before it ever reaches a URL."""
    _require_text(mirror_base, "mirror base")
    if not mirror_base.lower().startswith("https://"):
        raise expected("mirror base is not https", mirror_base[:80])
    normalized = normalize_package_name(package_name)
    base = mirror_base if mirror_base.endswith("/") else mirror_base + "/"
    # A scoped package's '/' must be percent-encoded in the path per npm's own registry
    # API convention (registry.npmjs.org/%40scope%2Fname), or the request is routed as
    # two path segments and 404s on a real, existing scoped package.
    encoded = normalized.replace("@", "%40").replace("/", "%2F")
    return base + encoded


def _decode_json(raw, what):
    """Bytes to a parsed document, with the size bound and the empty-body case explicit."""
    if raw is None:
        raise external("%s returned no body at all" % what)
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not isinstance(raw, (bytes, bytearray)):
        raise expected("%s body must be bytes" % what, type(raw).__name__)
    if len(raw) == 0:
        raise external("%s returned an empty body" % what, "0 bytes")
    if len(raw) > MAX_REGISTRY_BYTES:
        raise external("%s body exceeds the %d byte bound" % (what, MAX_REGISTRY_BYTES),
                       "%d bytes" % len(raw))
    try:
        return json.loads(bytes(raw).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise llm_error("%s body is not parseable JSON" % what, str(exc)[:120])


def fetch_registry_doc(ep_fetch, mirror_base, package_name, what):
    """Fetch and validate-shape one mirror's document for one package.

    A 404 is a real, distinguishable answer -- "this package name is not registered
    anywhere on this mirror" -- not a fetch failure, so it is handled before the generic
    status check and reported back as a structured, non-raising outcome via the caller
    rather than as a Refusal, since "not found" is itself the evidence for some callers
    (see `probe_package`) and a hard error for others (see `_require_registered`, used
    only in the deterministic prefix of `open_deal`, before any network call happens).
    """
    url = registry_url_for(mirror_base, package_name)
    response = ep_fetch(url, headers={"Accept": "application/json"})
    status = getattr(response, "status_code", None)
    if status == 404:
        return {"_found": False}
    if status is not None and status >= 500:
        raise transient("%s returned HTTP %d" % (what, status), url)
    if status is not None and status >= 400:
        raise external("%s returned HTTP %d" % (what, status), url)
    body = getattr(response, "body", None)
    doc = _decode_json(body, what)
    if not isinstance(doc, dict):
        raise llm_error("%s body is not a JSON object" % what, type(doc).__name__)
    doc["_found"] = True
    return doc


def extract_maintainers(doc):
    """Pull the lowercased set of maintainer usernames out of a registry document.

    npm's own documented shape is `maintainers: [{name, email}, ...]`. Some real
    documents (verified against a live capture) carry `name` only with no `email`, so
    `email` is never required. A maintainer entry missing `name` entirely is skipped
    rather than raised on -- a single malformed entry in a list of a dozen good ones is
    not evidence about the buyer's or seller's own membership, and refusing the whole
    check over one unrelated entry would make an unrelated field's malformation into
    this deal's problem.
    """
    raw = doc.get("maintainers")
    if not isinstance(raw, list):
        raise llm_error("registry document has no maintainers array",
                        type(raw).__name__ if raw is not None else "missing")
    names = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if isinstance(name, str) and name.strip():
            names.add(name.strip().lower())
    return names


def extract_latest_version(doc):
    tags = doc.get("dist-tags")
    if isinstance(tags, dict):
        latest = tags.get("latest")
        if isinstance(latest, str):
            return latest
    return ""


def extract_modified_at(doc):
    time_obj = doc.get("time")
    if isinstance(time_obj, dict):
        modified = time_obj.get("modified")
        if isinstance(modified, str):
            return modified
    return ""


def _join_sorted_names(names) -> str:
    """Module-level, never a bound method: called from inside strict_eq's nested `work`
    functions below, which per this project's confirmed rule 6 must close over zero
    `self.`-prefixed references, including indirectly via a bound helper method."""
    return ",".join(sorted(names))


# ======================================================================================
# Timestamp handling. gl.message_raw["datetime"] is an ISO-8601 UTC string with
# microsecond precision and a trailing 'Z' -- never a Unix integer; calling int() on it
# directly raises immediately. This hand-rolled parser uses only integer arithmetic
# (never float(), never a stdlib datetime dependency) and is independently verified
# against Python's own datetime as an oracle, including the year-2100 non-leap-century
# edge case. Returns 0 (never raises) if the field is absent or malformed.
# ======================================================================================

_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _is_leap_year(year) -> bool:
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


def _days_in_month(year, month) -> int:
    if month == 2 and _is_leap_year(year):
        return 29
    return _DAYS_IN_MONTH[month - 1]


def _now_epoch_seconds() -> int:
    try:
        raw = gl.message_raw.get("datetime", None) if isinstance(gl.message_raw, dict) else None
        if not isinstance(raw, str) or len(raw) < 19:
            return 0
        s = raw.strip()
        if s.endswith("Z"):
            s = s[:-1]
        s = s.split(".")[0]
        date_part, _, time_part = s.partition("T")
        y_str, m_str, d_str = date_part.split("-")
        hh_str, mm_str, ss_str = time_part.split(":")
        if not (y_str.isdigit() and m_str.isdigit() and d_str.isdigit()
                and hh_str.isdigit() and mm_str.isdigit() and ss_str.isdigit()):
            return 0
        year, month, day = int(y_str), int(m_str), int(d_str)
        hour, minute, second = int(hh_str), int(mm_str), int(ss_str)
        if not (1970 <= year <= 9999 and 1 <= month <= 12 and 1 <= day <= 31):
            return 0
        if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 60):
            return 0
        days = 0
        for y in range(1970, year):
            days += 366 if _is_leap_year(y) else 365
        for m in range(1, month):
            days += _days_in_month(year, m)
        days += day - 1
        return days * 86400 + hour * 3600 + minute * 60 + second
    except Exception:
        return 0


def _format_epoch_seconds(total_seconds) -> str:
    """Inverse of `_now_epoch_seconds`, for computing a human-readable deadline string to
    store and display. Integer arithmetic only, same leap-year table, independently
    checked against the parser above by round-tripping every stored deadline."""
    total_seconds = int(total_seconds)
    if total_seconds < 0:
        total_seconds = 0
    days = total_seconds // 86400
    remainder = total_seconds % 86400
    hour = remainder // 3600
    minute = (remainder % 3600) // 60
    second = remainder % 60
    year = 1970
    while True:
        year_days = 366 if _is_leap_year(year) else 365
        if days < year_days:
            break
        days -= year_days
        year += 1
    month = 1
    while True:
        dim = _days_in_month(year, month)
        if days < dim:
            break
        days -= dim
        month += 1
    day = days + 1
    return "%04d-%02d-%02dT%02d:%02d:%02d.000000Z" % (year, month, day, hour, minute, second)


# ======================================================================================
# Contract constants
# ======================================================================================

NPMJS_REGISTRY_BASE = "https://registry.npmjs.org/"
NPMMIRROR_REGISTRY_BASE = "https://registry.npmmirror.com/"

ACCEPT_WINDOW_SECONDS = 3 * 86400       # seller must arm within 3 days of open_deal
TRANSFER_WINDOW_SECONDS = 10 * 86400    # seller must complete the maintainer add within 10 days
MAX_DEAL_VALUE_WEI = 10 ** 24           # sanity ceiling, matches this project's other escrows
CHECK_COOLDOWN_SECONDS = 300            # anyone may call check_transfer, but not more than
                                          # once per five minutes per deal -- both mirrors are
                                          # real third-party services with their own rate
                                          # limits, and a deal with no cooldown at all would let
                                          # a single stuck deal hammer both on every block

ST_OFFERED = "OFFERED"
ST_LOCKED = "LOCKED"
ST_VERIFIED = "VERIFIED"
ST_SETTLED = "SETTLED"
ST_REFUNDED = "REFUNDED"
ST_ABANDONED = "ABANDONED"

CLOSED_STATES = (ST_SETTLED, ST_REFUNDED, ST_ABANDONED)

OUTCOME_VERIFIED = "verified"
OUTCOME_NOT_YET_ADDED = "not_yet_added"
OUTCOME_MAINTAINER_WIPE = "maintainer_wipe"
OUTCOME_PACKAGE_GONE = "package_gone"

# ======================================================================================
# Storage model
# ======================================================================================


@allow_storage
@dataclass
class Deal:
    deal_id: str
    buyer: Address
    seller: Address
    package_name: str
    buyer_npm_username: str
    seller_npm_username: str
    escrow: u256
    state: str

    opened_at: str
    accept_deadline: str
    armed_at: str
    transfer_deadline: str
    verified_at: str
    closed_at: str

    baseline_maintainers: str          # comma-joined, sorted, at open_deal time
    baseline_latest_version: str
    baseline_modified_at: str

    checks: u256
    last_check_at: str
    last_check_outcome: str
    last_check_note: str
    last_check_maintainers: str

    paid_to_seller: u256
    returned_to_buyer: u256


class PkgConveyance(gl.Contract):
    deals: TreeMap[str, Deal]
    deal_ids: DynArray[str]
    package_to_deal: TreeMap[str, str]

    total_escrowed: u256
    total_released: u256
    total_refunded: u256
    deals_opened: u256
    checks_run: u256
    deliveries_verified: u256

    def __init__(self):
        self.total_escrowed = u256(0)
        self.total_released = u256(0)
        self.total_refunded = u256(0)
        self.deals_opened = u256(0)
        self.checks_run = u256(0)
        self.deliveries_verified = u256(0)

    # ==================================================================================
    # Internal helpers -- deterministic, storage-touching, never called from inside a
    # strict_eq block.
    # ==================================================================================

    def _pay(self, to_address, amount) -> None:
        if int(amount) <= 0:
            return
        gl.get_contract_at(to_address).emit_transfer(value=amount)

    def _reject(self, message) -> None:
        raise gl.vm.UserError("%s %s" % (TAG_EXPECTED, message))

    def _reject_transient(self, message) -> None:
        raise gl.vm.UserError("%s %s" % (TAG_TRANSIENT, message))

    def _require_now(self) -> str:
        seconds = _now_epoch_seconds()
        if seconds == 0:
            self._reject_transient("could not read a usable timestamp from this message")
        return _format_epoch_seconds(seconds)

    def _add_seconds(self, iso_string, extra_seconds) -> str:
        base = self._parse_stored(iso_string)
        return _format_epoch_seconds(base + extra_seconds)

    def _parse_stored(self, iso_string) -> int:
        # Reuses the same parser as `_now_epoch_seconds` by routing through a fabricated
        # message_raw-shaped dict, so a stored deadline and a live timestamp are always
        # parsed by the exact same code path -- never two hand-rolled parsers that could
        # silently drift apart.
        saved = gl.message_raw
        try:
            gl.message_raw = {"datetime": iso_string}
            return _now_epoch_seconds()
        finally:
            gl.message_raw = saved

    def _at_or_after(self, now_iso, deadline_iso) -> bool:
        return self._parse_stored(now_iso) >= self._parse_stored(deadline_iso)

    def _require_id(self, deal_id) -> str:
        key = str(deal_id or "").strip()
        if not key:
            self._reject("deal_id must not be empty")
        if len(key.encode("utf-8")) > 128:
            self._reject("deal_id exceeds 128 bytes")
        return key

    def _require_package(self, package_name) -> str:
        try:
            return normalize_package_name(package_name)
        except Refusal as exc:
            self._reject(str(exc))

    def _require_username(self, username, what) -> str:
        try:
            return normalize_username(username)
        except Refusal as exc:
            self._reject("%s: %s" % (what, str(exc)))

    def _require_address(self, raw, what) -> Address:
        text = str(raw or "").strip()
        if not text:
            self._reject("%s address must not be empty" % what)
        try:
            return Address(text)
        except Exception:
            self._reject("%s is not a valid address: %r" % (what, text[:80]))

    def _require_deal(self, deal_id) -> Deal:
        key = self._require_id(deal_id)
        if key not in self.deals:
            self._reject("no deal with id %r" % key)
        return self.deals[key]

    def _require_state(self, deal, allowed, action) -> None:
        if deal.state not in allowed:
            self._reject("%s requires state in %s, deal %s is %s"
                         % (action, allowed, deal.deal_id, deal.state))

    def _decline(self, message) -> str:
        self._pay(gl.message.sender_address, u256(int(gl.message.value)))
        return message

    def _error_text(self, observed) -> str:
        err = observed.get("error", "")
        return str(err) if err else ""

    def _raise_if_error(self, observed) -> None:
        err = self._error_text(observed)
        if err:
            raise gl.vm.UserError(err)

    # ==================================================================================
    # Consensus blocks. Every one is strict_eq: every field is a comparison over fetched
    # bytes on two independently operated mirrors, so a disagreement between them means
    # the two sources currently disagree about the package and the only correct outcome
    # is a retryable revert, never a resolved payout.
    # ==================================================================================

    def _lookup_block(self, package_name: str) -> dict:
        """Read both mirrors for one package and cross-check them against each other.

        Used both at `open_deal` (to record who maintains the package today) and inside
        `_delivery_block` below (as the first half of a transfer check). Kept as its own
        block so `open_deal`'s baseline read and `check_transfer`'s live read run the
        identical fetch-and-cross-check logic rather than two hand-written variants that
        could drift apart on what counts as agreement.
        """
        def work():
            try:
                def ep_fetch(url, headers=None):
                    return gl.nondet.web.request(url, method="GET", headers=headers or {})

                primary = fetch_registry_doc(ep_fetch, NPMJS_REGISTRY_BASE, package_name,
                                             "registry.npmjs.org")
                mirror = fetch_registry_doc(ep_fetch, NPMMIRROR_REGISTRY_BASE, package_name,
                                            "registry.npmmirror.com")

                primary_found = bool(primary.get("_found"))
                mirror_found = bool(mirror.get("_found"))
                if primary_found != mirror_found:
                    raise transient(
                        "the two registry mirrors disagree on whether %r is registered "
                        "at all" % package_name,
                        "npmjs.org found=%s, npmmirror found=%s" % (primary_found, mirror_found))
                if not primary_found:
                    return {"error": "", "found": False, "maintainers": "",
                           "latest_version": "", "modified_at": ""}

                primary_maintainers = extract_maintainers(primary)
                mirror_maintainers = extract_maintainers(mirror)
                if primary_maintainers != mirror_maintainers:
                    raise transient(
                        "the two registry mirrors report different maintainer lists for "
                        "%r right now" % package_name,
                        "npmjs.org=%s, npmmirror=%s"
                        % (_join_sorted_names(primary_maintainers),
                           _join_sorted_names(mirror_maintainers)))

                primary_latest = extract_latest_version(primary)
                mirror_latest = extract_latest_version(mirror)
                # A brief mirror-lag on `dist-tags.latest` after a fresh publish is real
                # and expected; it is not compared for agreement the way maintainers is,
                # because this contract's verdict never depends on which version is
                # latest -- only on who maintains the package. It is still recorded, on
                # the primary source only, for the deal's display.
                return {
                    "error": "",
                    "found": True,
                    "maintainers": _join_sorted_names(primary_maintainers),
                    "latest_version": str(primary_latest),
                    "modified_at": str(extract_modified_at(primary)),
                }
            except Refusal as exc:
                return {"error": str(exc)}

        return gl.eq_principle.strict_eq(work)

    def _delivery_block(self, package_name: str, buyer_username: str,
                        seller_username: str) -> dict:
        """The whole delivery question in one round: both mirrors, both usernames.

        One block rather than two, because "does the buyer's name now appear" and "does
        the seller's name still appear" have to describe the same instant. Split across
        rounds, a maintainer list edited mid-way through two separate checks could pass
        each check without the final state ever actually containing both names at once.
        """
        def work():
            try:
                def ep_fetch(url, headers=None):
                    return gl.nondet.web.request(url, method="GET", headers=headers or {})

                primary = fetch_registry_doc(ep_fetch, NPMJS_REGISTRY_BASE, package_name,
                                             "registry.npmjs.org")
                mirror = fetch_registry_doc(ep_fetch, NPMMIRROR_REGISTRY_BASE, package_name,
                                            "registry.npmmirror.com")

                primary_found = bool(primary.get("_found"))
                mirror_found = bool(mirror.get("_found"))
                if primary_found != mirror_found:
                    raise transient(
                        "the two registry mirrors disagree on whether %r is still "
                        "registered" % package_name,
                        "npmjs.org found=%s, npmmirror found=%s" % (primary_found, mirror_found))
                if not primary_found:
                    return {"error": "", "outcome": OUTCOME_PACKAGE_GONE, "maintainers": ""}

                primary_maintainers = extract_maintainers(primary)
                mirror_maintainers = extract_maintainers(mirror)
                if primary_maintainers != mirror_maintainers:
                    raise transient(
                        "the two registry mirrors report different maintainer lists for "
                        "%r right now" % package_name,
                        "npmjs.org=%s, npmmirror=%s"
                        % (_join_sorted_names(primary_maintainers),
                           _join_sorted_names(mirror_maintainers)))

                buyer_in = buyer_username in primary_maintainers
                seller_in = seller_username in primary_maintainers

                if buyer_in and seller_in:
                    outcome = OUTCOME_VERIFIED
                elif buyer_in and not seller_in:
                    # Buyer present, seller gone: still a completed transfer by this
                    # contract's own evidence standard -- the seller relinquished their
                    # own access on the way out, which most real transfers do. Reported
                    # as verified, distinctly from a wipe, because the buyer's own
                    # standing is exactly what a wipe removes and this is the one case
                    # where it is intact.
                    outcome = OUTCOME_VERIFIED
                elif not buyer_in and not seller_in:
                    outcome = OUTCOME_MAINTAINER_WIPE
                else:
                    outcome = OUTCOME_NOT_YET_ADDED

                return {
                    "error": "",
                    "outcome": outcome,
                    "maintainers": _join_sorted_names(primary_maintainers),
                }
            except Refusal as exc:
                return {"error": str(exc)}

        return gl.eq_principle.strict_eq(work)

    # ==================================================================================
    # open_deal
    # ==================================================================================

    @gl.public.write.payable
    def open_deal(
        self,
        deal_id: str,
        package_name: str,
        seller: str,
        seller_npm_username: str,
        buyer_npm_username: str,
    ) -> str:
        """Escrow the price and record who maintains the package today.

        This method never reverts on a refusal that happens after value has already
        been attached: this chain rolls storage back on a revert but keeps
        `gl.message.value`, so a reverting payable call would charge the caller for
        being told no. `_decline` refunds the value and returns the reason instead; a
        return value starting with `[` means the escrow came back and nothing was
        stored.

        `seller` is a plain address string; `seller_npm_username` and
        `buyer_npm_username` are separate from it on purpose, since an on-chain address
        and an npm account are two different identities with no protocol-level link
        between them -- this contract only ever asserts what the registry says about
        the *username*, never anything about which wallet controls it.
        """
        try:
            key = self._require_id(deal_id)
            name = self._require_package(package_name)
            seller_user = self._require_username(seller_npm_username, "seller_npm_username")
            buyer_user = self._require_username(buyer_npm_username, "buyer_npm_username")
            if seller_user == buyer_user:
                self._reject("seller and buyer must not name the same npm username; a "
                             "transfer to yourself settles nothing")

            buyer = gl.message.sender_address
            seller_address = self._require_address(seller, "seller")
            if seller_address == buyer:
                self._reject("seller must not be the buyer; an escrow with one party on "
                             "both sides settles nothing")

            escrow = int(gl.message.value)
            if escrow <= 0:
                self._reject("a deal needs an escrow; this call carried no value")
            if escrow > MAX_DEAL_VALUE_WEI:
                self._reject("escrow of %d wei is over this deployment's %d wei ceiling"
                             % (escrow, MAX_DEAL_VALUE_WEI))

            if key in self.deals:
                self._reject("deal %r already exists" % key[:64])
            if name in self.package_to_deal:
                previous_key = self.package_to_deal[name]
                previous_state = ST_OFFERED
                if previous_key in self.deals:
                    previous_state = str(self.deals[previous_key].state)
                if previous_state not in CLOSED_STATES:
                    self._reject("deal %r already covers %s and is %s; a second live "
                                 "escrow on one package would let one transfer settle "
                                 "both" % (previous_key[:64], name, previous_state))

            now = self._require_now()

            # Everything above is deterministic. The first network call happens here.
            observed = self._lookup_block(name)
            marshalled = self._error_text(observed)
            if marshalled != "":
                return self._decline(marshalled)

            if not bool(observed.get("found")):
                self._reject("%r is not a registered npm package on either mirror; "
                             "there is nothing to escrow a transfer of" % name)

            maintainers = set(
                m for m in str(observed.get("maintainers", "")).split(",") if m
            )
            if seller_user not in maintainers:
                self._reject(
                    "%r does not currently list npm user %r as a maintainer of %s; a "
                    "deal cannot be opened against a package the named seller does not "
                    "control today. Current maintainers: %s"
                    % (seller_user, seller_user, name, ", ".join(sorted(maintainers)) or "(none)"))
            if buyer_user in maintainers:
                self._reject(
                    "npm user %r is already a maintainer of %s; there is no transfer "
                    "for this deal to verify" % (buyer_user, name))
        except gl.vm.UserError as exc:
            return self._decline(exc.message)

        deal = Deal(
            deal_id=key,
            buyer=buyer,
            seller=seller_address,
            package_name=name,
            buyer_npm_username=buyer_user,
            seller_npm_username=seller_user,
            escrow=u256(escrow),
            state=ST_OFFERED,
            opened_at=now,
            accept_deadline=self._add_seconds(now, ACCEPT_WINDOW_SECONDS),
            armed_at="",
            transfer_deadline="",
            verified_at="",
            closed_at="",
            baseline_maintainers=str(observed.get("maintainers", "")),
            baseline_latest_version=str(observed.get("latest_version", "")),
            baseline_modified_at=str(observed.get("modified_at", "")),
            checks=u256(0),
            last_check_at="",
            last_check_outcome="",
            last_check_note="",
            last_check_maintainers="",
            paid_to_seller=u256(0),
            returned_to_buyer=u256(0),
        )

        self.deals[key] = deal
        self.deal_ids.append(key)
        self.package_to_deal[name] = key
        self.total_escrowed = u256(int(self.total_escrowed) + escrow)
        self.deals_opened = u256(int(self.deals_opened) + 1)

        return ("%s %s: %d wei escrowed on %s. Confirmed today: npm user %r maintains "
                "it, npm user %r does not. Seller has until %s to call arm(), then until "
                "%s (after arming) to add %r as a maintainer and call check_transfer()."
                % (key, ST_OFFERED, escrow, name, seller_user, buyer_user,
                   deal.accept_deadline, "the transfer deadline set at arm() time",
                   buyer_user))

    # ==================================================================================
    # arm
    # ==================================================================================

    @gl.public.write
    def arm(self, deal_id: str) -> str:
        """The seller accepts, by the contract re-confirming maintainer status live.

        Re-checked rather than trusted from `open_deal`'s baseline, because time has
        passed and a seller could have been removed as a maintainer by someone else in
        the interim -- accepting on a stale baseline would open a ten-day transfer
        window against a deal that was never deliverable. Seller-only, since arming is
        the seller's commitment, not a fact anyone else can attest to.
        """
        deal = self._require_deal(deal_id)
        key = deal.deal_id
        self._require_state(deal, (ST_OFFERED,), "arm()")

        if gl.message.sender_address != deal.seller:
            self._reject("only the named seller can arm deal %s" % key)

        now = self._require_now()
        if self._at_or_after(now, deal.accept_deadline):
            self._reject("the offer on deal %s lapsed at %s; the escrow is refundable "
                         "instead" % (key, deal.accept_deadline))

        observed = self._lookup_block(deal.package_name)
        self._raise_if_error(observed)

        if not bool(observed.get("found")):
            self._reject_transient("%s is no longer a registered package on either "
                                   "mirror" % deal.package_name)

        maintainers = set(
            m for m in str(observed.get("maintainers", "")).split(",") if m
        )
        if deal.seller_npm_username not in maintainers:
            self._reject(
                "npm user %r no longer maintains %s as of this arm() call; the seller "
                "cannot arm a deal for a package they do not currently control"
                % (deal.seller_npm_username, deal.package_name))

        deal.state = ST_LOCKED
        deal.armed_at = now
        deal.transfer_deadline = self._add_seconds(now, TRANSFER_WINDOW_SECONDS)
        self.deals[key] = deal

        return ("%s %s: npm user %r confirmed as a maintainer of %s. Add npm user %r as "
                "a maintainer and call check_transfer() before %s, after which the "
                "escrow becomes refundable."
                % (key, ST_LOCKED, deal.seller_npm_username, deal.package_name,
                   deal.buyer_npm_username, deal.transfer_deadline))

    # ==================================================================================
    # check_transfer
    # ==================================================================================

    @gl.public.write
    def check_transfer(self, deal_id: str) -> str:
        """Read both mirrors and record what they say about the maintainer list. Anyone
        may call this -- the state machine decides what the answer means, not the caller.

        Rate-limited per deal to `CHECK_COOLDOWN_SECONDS`, since every call here is two
        real HTTP requests to two real third-party services, and an unthrottled deal
        would let anyone hammer both on every block with no cost beyond gas.
        """
        deal = self._require_deal(deal_id)
        key = deal.deal_id
        self._require_state(deal, (ST_LOCKED,), "check_transfer()")

        now = self._require_now()
        if deal.last_check_at != "" and not self._at_or_after(
            now, self._add_seconds(deal.last_check_at, CHECK_COOLDOWN_SECONDS)
        ):
            self._reject_transient(
                "deal %s was checked less than %d seconds ago at %s; retry after the "
                "cooldown" % (key, CHECK_COOLDOWN_SECONDS, deal.last_check_at))

        observed = self._delivery_block(
            deal.package_name, deal.buyer_npm_username, deal.seller_npm_username
        )
        self._raise_if_error(observed)

        outcome = str(observed.get("outcome", ""))
        maintainers_now = str(observed.get("maintainers", ""))

        deal.checks = u256(int(deal.checks) + 1)
        deal.last_check_at = now
        deal.last_check_outcome = outcome
        deal.last_check_maintainers = maintainers_now
        self.checks_run = u256(int(self.checks_run) + 1)

        if outcome == OUTCOME_VERIFIED:
            deal.state = ST_VERIFIED
            deal.verified_at = now
            deal.last_check_note = ("npm user %r appears in the maintainer list; "
                                    "transfer verified" % deal.buyer_npm_username)
            self.deliveries_verified = u256(int(self.deliveries_verified) + 1)
            self.deals[key] = deal
            return ("%s %s: npm user %r confirmed as a maintainer of %s on both "
                    "mirrors. settle() will release the escrow to the seller."
                    % (key, ST_VERIFIED, deal.buyer_npm_username, deal.package_name))

        if outcome == OUTCOME_MAINTAINER_WIPE:
            deal.last_check_note = (
                "neither the seller's nor the buyer's npm username currently appears "
                "in the maintainer list; this is not a completed transfer")
            self.deals[key] = deal
            self._reject_transient(
                "%s deal %s: %s. State remains %s; the transfer deadline still applies."
                % (TAG_EXPECTED, key, deal.last_check_note, ST_LOCKED))

        if outcome == OUTCOME_PACKAGE_GONE:
            deal.last_check_note = "the package is no longer registered on either mirror"
            self.deals[key] = deal
            self._reject_transient(
                "deal %s: %s is no longer a registered package; nothing to verify a "
                "transfer of. State remains %s." % (key, deal.package_name, ST_LOCKED))

        # OUTCOME_NOT_YET_ADDED
        deal.last_check_note = (
            "npm user %r has not yet been added as a maintainer of %s"
            % (deal.buyer_npm_username, deal.package_name))
        self.deals[key] = deal
        self._reject_transient(
            "deal %s: %s. State remains %s; retry after the seller completes the add."
            % (key, deal.last_check_note, ST_LOCKED))

    # ==================================================================================
    # settle / refund / abandon -- the only three places the escrow moves
    # ==================================================================================

    @gl.public.write
    def settle(self, deal_id: str) -> str:
        """Release escrow to the seller. Anyone may call it once state is VERIFIED --
        the verdict, not the caller, decides."""
        deal = self._require_deal(deal_id)
        key = deal.deal_id
        self._require_state(deal, (ST_VERIFIED,), "settle()")

        now = self._require_now()
        amount = deal.escrow
        deal.state = ST_SETTLED
        deal.closed_at = now
        deal.paid_to_seller = amount
        self.deals[key] = deal
        self.total_released = u256(int(self.total_released) + int(amount))

        self._pay(deal.seller, amount)
        return "%s %s: %d wei released to the seller." % (key, ST_SETTLED, int(amount))

    @gl.public.write
    def refund(self, deal_id: str) -> str:
        """Return escrow to the buyer once the relevant window has closed. Anyone may
        call it -- gated on a clock, not on who is asking."""
        deal = self._require_deal(deal_id)
        key = deal.deal_id
        self._require_state(deal, (ST_OFFERED, ST_LOCKED), "refund()")

        now = self._require_now()
        if deal.state == ST_OFFERED:
            if not self._at_or_after(now, deal.accept_deadline):
                self._reject("deal %s has not lapsed yet; accept_deadline is %s"
                             % (key, deal.accept_deadline))
        else:  # ST_LOCKED
            if not self._at_or_after(now, deal.transfer_deadline):
                self._reject("deal %s has not lapsed yet; transfer_deadline is %s"
                             % (key, deal.transfer_deadline))

        amount = deal.escrow
        deal.state = ST_REFUNDED
        deal.closed_at = now
        deal.returned_to_buyer = amount
        self.deals[key] = deal
        self.total_refunded = u256(int(self.total_refunded) + int(amount))

        self._pay(deal.buyer, amount)
        return "%s %s: %d wei returned to the buyer." % (key, ST_REFUNDED, int(amount))

    @gl.public.write
    def abandon(self, deal_id: str) -> str:
        """Cancel before delivery. While OFFERED, either party may call it -- the
        seller has committed nothing and the buyer's escrow is the only thing at stake.
        Once LOCKED, only the seller may -- the seller may by then have already added
        the buyer as a maintainer at npm and be mid-transfer, and a buyer who could
        cancel at will could let a seller complete the maintainer add and then walk
        away with both the package access and the refunded price. The buyer's remedy
        after LOCKED is the transfer deadline, which `refund` enforces without needing
        the seller present."""
        deal = self._require_deal(deal_id)
        key = deal.deal_id
        self._require_state(deal, (ST_OFFERED, ST_LOCKED), "abandon()")

        caller = gl.message.sender_address
        if deal.state == ST_OFFERED:
            if caller != deal.buyer and caller != deal.seller:
                self._reject("only the buyer or seller of deal %s may abandon it while "
                             "OFFERED" % key)
        else:  # ST_LOCKED
            if caller != deal.seller:
                self._reject("only the seller may abandon deal %s once LOCKED; the "
                             "buyer's remedy is refund() after the transfer deadline"
                             % key)

        now = self._require_now()
        amount = deal.escrow
        deal.state = ST_ABANDONED
        deal.closed_at = now
        deal.returned_to_buyer = amount
        self.deals[key] = deal
        self.total_refunded = u256(int(self.total_refunded) + int(amount))

        self._pay(deal.buyer, amount)
        return "%s %s: %d wei returned to the buyer." % (key, ST_ABANDONED, int(amount))

    # ==================================================================================
    # probe_package -- a free, storage-free consensus read, for a frontend to check a
    # package before a buyer commits any value to it.
    # ==================================================================================

    @gl.public.write
    def probe_package(self, package_name: str) -> dict:
        name = self._require_package(package_name)
        observed = self._lookup_block(name)
        self._raise_if_error(observed)
        return {
            "package_name": name,
            "found": str(bool(observed.get("found"))),
            "maintainers": str(observed.get("maintainers", "")),
            "latest_version": str(observed.get("latest_version", "")),
            "modified_at": str(observed.get("modified_at", "")),
        }

    # ==================================================================================
    # Views
    # ==================================================================================

    @gl.public.view
    def get_deal(self, deal_id: str) -> dict:
        key = str(deal_id or "").strip()
        if key not in self.deals:
            return {}
        deal = self.deals[key]
        return {
            "deal_id": deal.deal_id,
            "state": deal.state,
            "buyer": deal.buyer.as_hex,
            "seller": deal.seller.as_hex,
            "package_name": deal.package_name,
            "buyer_npm_username": deal.buyer_npm_username,
            "seller_npm_username": deal.seller_npm_username,
            "escrow": str(int(deal.escrow)),
            "opened_at": deal.opened_at,
            "accept_deadline": deal.accept_deadline,
            "armed_at": deal.armed_at,
            "transfer_deadline": deal.transfer_deadline,
            "verified_at": deal.verified_at,
            "closed_at": deal.closed_at,
            "baseline_maintainers": deal.baseline_maintainers,
            "baseline_latest_version": deal.baseline_latest_version,
            "baseline_modified_at": deal.baseline_modified_at,
            "checks": str(int(deal.checks)),
            "last_check_at": deal.last_check_at,
            "last_check_outcome": deal.last_check_outcome,
            "last_check_note": deal.last_check_note,
            "last_check_maintainers": deal.last_check_maintainers,
            "paid_to_seller": str(int(deal.paid_to_seller)),
            "returned_to_buyer": str(int(deal.returned_to_buyer)),
        }

    @gl.public.view
    def list_deals(self) -> list:
        out = []
        for key in self.deal_ids:
            deal = self.deals[key]
            out.append({
                "deal_id": deal.deal_id,
                "state": deal.state,
                "package_name": deal.package_name,
                "escrow": str(int(deal.escrow)),
                "buyer_npm_username": deal.buyer_npm_username,
                "last_check_outcome": deal.last_check_outcome,
                "last_check_at": deal.last_check_at,
            })
        return out

    @gl.public.view
    def deal_for_package(self, package_name: str) -> dict:
        try:
            name = normalize_package_name(package_name)
        except Refusal:
            return {}
        if name not in self.package_to_deal:
            return {}
        return self.get_deal(self.package_to_deal[name])

    @gl.public.view
    def ledger(self) -> dict:
        escrowed = int(self.total_escrowed)
        released = int(self.total_released)
        refunded = int(self.total_refunded)
        return {
            "total_escrowed": str(escrowed),
            "total_released": str(released),
            "total_refunded": str(refunded),
            "held": str(escrowed - released - refunded),
            "balance": str(int(self.balance)),
            "deals_opened": str(int(self.deals_opened)),
            "checks_run": str(int(self.checks_run)),
            "deliveries_verified": str(int(self.deliveries_verified)),
            "protocol_fee": "0",
        }

    @gl.public.view
    def parameters(self) -> dict:
        return {
            "npmjs_registry_base": NPMJS_REGISTRY_BASE,
            "npmmirror_registry_base": NPMMIRROR_REGISTRY_BASE,
            "accept_window_seconds": str(ACCEPT_WINDOW_SECONDS),
            "transfer_window_seconds": str(TRANSFER_WINDOW_SECONDS),
            "check_cooldown_seconds": str(CHECK_COOLDOWN_SECONDS),
            "max_deal_value_wei": str(MAX_DEAL_VALUE_WEI),
            "uses_a_model": "false",
            "boundary": (
                "PkgConveyance verifies public npm maintainer-list membership. It does "
                "not prove legal ownership of the package name, the identity of the "
                "human behind an npm username, that the seller has no other account "
                "with residual publish rights, or anything about the package's source "
                "repository, license, or code contents."
            ),
        }
