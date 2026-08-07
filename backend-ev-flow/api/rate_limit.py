"""Tiny in-process rate limiter: a sliding window of hit timestamps per subject.

PER-PROCESS, NOT PER-DEPLOYMENT -- READ THIS BEFORE TRUSTING ANY NUMBER BELOW.
Every counter here lives in one uvicorn worker's memory. Nothing is shared
between workers, so the effective limit for the deployment is
(worker count x the constant), and which worker a connection lands on is not
predictable. The shipped default is NOT one worker: `Containerfile` runs
`uvicorn --workers ${WEB_CONCURRENCY:-2}` and `podman-compose.yml` passes
`${WEB_CONCURRENCY:-2}`, so a deploy without an explicit `.env` gets 2 processes
and **every limit in this module doubles**. Raising WEB_CONCURRENCY multiplies
them again. If a limit here ever has to be exact, it belongs in Redis or at the
edge, not in this file.

Three properties the callers depend on, each of which used to be missing:

* **It is thread-safe.** FastAPI runs sync `def` path operations on the AnyIO
  threadpool (40 threads by default), and every endpoint that calls into here
  except the two geocoding ones is sync. Without the lock the read-then-append
  in `_allow_locked` loses increments (measured: 2x the limit granted under 40
  concurrent callers) and `OrderedDict.move_to_end` can raise KeyError when
  another thread evicts the key mid-call -- which surfaces as a 500, not a 429.
* **Deployment-wide ceilings cannot be evicted.** Ceiling counters (subject
  `None`) are held in a separate table that eviction never touches. They used to
  be ordinary LRU entries, i.e. a ceiling that unrelated traffic on another
  endpoint could silently reset -- and it was the *least* recently touched key
  exactly while it was holding a lockout.
* **Eviction cannot cross namespaces.** Each namespace has its own LRU table and
  its own cap, so traffic on one endpoint can never evict another endpoint's
  counters. This is what makes a subject taken from caller input (the hashed
  email on /auth/forgot-password) safe to key on: see
  MAX_TRACKED_SUBJECTS_PER_NAMESPACE.

The window is a sliding log of individual timestamps, not a fixed bucket, so
there is no boundary burst: no 60s stretch can ever contain more than `limit`
hits. Only allowed hits are recorded, so denied attempts never extend a lockout.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from typing import Deque, Dict, Optional

# --------------------------------------------------------------------- geocoding
# Geocoding proxies OpenStreetMap's Nominatim, whose usage policy allows about
# 1 request/second per application. A human typing in the destination picker
# stays far below this; a script does not.
GEOCODING_RATE_LIMIT_REQUESTS = 30
GEOCODING_RATE_LIMIT_WINDOW_SECONDS = 60.0

# Ceiling for the whole deployment, not one caller. The per-caller budget above
# stops a single client looping; this stops many clients (or many demo accounts,
# since the demo password is public by design) from adding up to a volume that
# gets our egress IP banned. Nominatim's policy is ~1 request/second, and the
# response cache absorbs most repeats, so 60/minute leaves real headroom.
GEOCODING_GLOBAL_RATE_LIMIT_REQUESTS = 60

# --------------------------------------------------------------- support tickets
# The help desk turns one unauthenticated POST into one outbound email, which
# makes it an open relay unless it is budgeted. A human with a real problem sends
# one or two messages an hour; anything past a handful is either a stuck retry
# loop in the client or someone using our SMTP reputation to send mail.
SUPPORT_TICKET_RATE_LIMIT_WINDOW_SECONDS = 3600.0
SUPPORT_TICKET_RATE_LIMIT_REQUESTS = 5

# Ceiling for the whole deployment, same reasoning as the geocoding pair above:
# the per-caller budget stops one client looping, this stops many clients (or one
# client behind many addresses) adding up to a volume that gets the SMTP account
# suspended for spam -- which would take the password-reset email down with it.
SUPPORT_TICKET_GLOBAL_RATE_LIMIT_REQUESTS = 60

# ------------------------------------------------------------------------- login
# WHY A FAILURE COUNTER, NOT A REQUEST COUNTER. A successful sign-in costs no
# budget at all, so no amount of legitimate growth can trip this -- only wrong
# passwords count. That is what lets the number be this low.
#
# WHY 5 MINUTES. Long enough to make guessing pointless (60 per 5 min = 17,280
# per day against an 8-character minimum), short enough that a room full of
# people who have genuinely mistyped is unstuck before anyone files a ticket.
#
# REAL USAGE. JWT_EXPIRE_MINUTES defaults to 10080 (7 days), so a driver signs in
# about once a week. The worst legitimate burst we can construct is a ~40-person
# live demo where a third of the room fat-fingers the password inside the same
# 5 minutes: ~13 failures. 60 is ~4x that headroom.
#
# ATTACKER SIDE. Each failed login against an existing username costs one
# bcrypt(cost 12) verify, ~250-400 ms of a shared threadpool thread. 60 per
# 5 minutes caps that at ~18 s of CPU per window, ~6% of one core -- the point
# being that this endpoint is a CPU DoS primitive before it is a guessing one.
LOGIN_FAILURE_RATE_LIMIT_WINDOW_SECONDS = 300.0
LOGIN_FAILURE_RATE_LIMIT_REQUESTS = 60

# Deployment-wide failure ceiling. This is the bucket that actually catches
# credential stuffing (many usernames from one source), and it does so with zero
# lockout surface -- unlike a per-username counter, which would let anyone lock a
# named victim out for the price of one wrong password per window. Set equal to
# the per-IP figure on purpose: behind the Cloudflare tunnel + nginx every caller
# shares one apparent address, so the two are the same number today and the
# per-IP one only starts to bite once a real client address is available.
LOGIN_FAILURE_GLOBAL_RATE_LIMIT_REQUESTS = 60

# ---------------------------------------------------------------------- register
# WHAT THIS IS REALLY PROTECTING: `wallet.id` is a smallint and its primary key
# is `(SELECT COALESCE(MAX(id),0)+1)`, so account number 32,767 is the last one
# that can ever have a wallet -- after that both /wallet/topup and
# /charging/sessions raise for every future user, permanently, until someone
# ships a migration. Unauthenticated and unbudgeted that is ~3 hours of scripted
# signups to destroy the wallet feature for good.
#
# REAL USAGE. A person registers once, ever. This is sized for a classroom or a
# demo audience signing up in one session, not for one human: 20/hour is roughly
# a lecture hall, and it turns "3 hours to brick wallets" into ~68 days -- with a
# logged warning on every 429, so the operator gets months of notice instead of a
# silent Sunday. The rate limit only buys that time; the fix is the column type
# and the MAX(id)+1 primary key.
REGISTER_RATE_LIMIT_WINDOW_SECONDS = 3600.0
REGISTER_RATE_LIMIT_REQUESTS = 20
REGISTER_GLOBAL_RATE_LIMIT_REQUESTS = 40

# --------------------------------------------------------------- forgot password
# One POST here becomes one outbound email to an address the caller names, which
# is a mail bomb aimed at a third party and a way to burn the shared SMTP
# account's reputation until the provider suspends it -- taking password reset
# AND the help desk down together, i.e. both recovery paths for a locked-out
# user at once.
#
# WHY IT IS SAFE TO KEY ON THE VICTIM'S EMAIL HERE, WHEN /auth/login MUST NOT KEY
# ON THE VICTIM'S USERNAME. Exhausting this bucket denies the victim a *duplicate*
# email, not the reset: PASSWORD_RESET_TTL_MINUTES defaults to 60, so a victim
# whose hourly budget is spent already has a working link in their inbox for the
# same hour. A username bucket on /auth/login has no such property -- it would
# deny the account itself.
#
# REAL USAGE. A person asks once; twice if the first mail is slow to arrive.
# 3/hour is generous for that and bounds the mail bomb at 3 messages/hour/victim.
FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS = 3600.0
FORGOT_PASSWORD_EMAIL_RATE_LIMIT_REQUESTS = 3

# Per-caller and deployment-wide backstops for the same endpoint. The global one
# is doing two jobs: it caps total SMTP volume, and because it can never be
# evicted (see the module docstring) it is what makes the per-email bucket above
# unflushable -- filling this namespace's LRU takes thousands of requests and
# this ceiling only permits 30 an hour.
FORGOT_PASSWORD_IP_RATE_LIMIT_REQUESTS = 20
FORGOT_PASSWORD_GLOBAL_RATE_LIMIT_REQUESTS = 30

# ------------------------------------------------------------------ wallet topup
# Each accepted request creates a REAL invoice in the production Xendit merchant
# account and spends the merchant's API quota; it also pins one of the ~40 shared
# threadpool threads for up to XENDIT_TIMEOUT_SECONDS (default 30) on a
# synchronous outbound POST, so ~40 concurrent top-ups against a slow provider
# stall every other endpoint in the app, station lookups included.
#
# REAL USAGE. A driver tops up maybe weekly, and the frontend creates ONE invoice
# and then polls GET /wallet/topups/{id} -- a different endpoint -- so normal
# retry and polling traffic never touches this counter. 5 covers opening
# checkout, abandoning it, and retrying several times.
#
# WHY A 10-MINUTE WINDOW AND NOT AN HOUR. Everyone shares `demo.driver`, so on a
# live demo the whole room shares this bucket; a wedged audience should wait ten
# minutes, not an hour.
WALLET_TOPUP_RATE_LIMIT_WINDOW_SECONDS = 600.0
WALLET_TOPUP_RATE_LIMIT_REQUESTS = 5

# Deployment-wide ceiling: the resource being protected (Xendit's API quota and
# the merchant dashboard) belongs to the deployment, not to one user. 20 per ten
# minutes is four simultaneously-active top-up flows, well above anything this
# demo has ever seen.
WALLET_TOPUP_GLOBAL_RATE_LIMIT_REQUESTS = 20

# --------------------------------------------------------------- charging session
# Starting a session flips `connectors.status` to 'in_use' and NOTHING expires an
# abandoned one -- there is no sweeper and no operator-side release, so the
# connector stays occupied until that same user settles it. The attack is making
# the live map lie, and it is cheap: the seeded demo wallet holds 500,000 IDR and
# the minimum session costs the 2,500 IDR flat admin fee, so 200 connectors can
# be marked in_use by anyone holding the password that ships in the web bundle.
#
# BE HONEST ABOUT WHAT THIS BUYS: it slows that from a minute to ~7 hours. It
# does not fix it. The fix is a session TTL sweeper, which does not exist yet.
#
# REAL USAGE. A driver starts one session per charging stop; a heavy fleet user
# does 3-4 in a day. 5 per ten minutes is far above that, and the short window is
# again chosen because the demo account is shared.
#
# NO PER-STATION KEY, DELIBERATELY. It looks attractive, but it would let one
# caller deny a PHYSICAL asset to everyone else -- a worse weapon than the one it
# defends against -- and it buys nothing, because connectors_repo.occupy already
# returns None when no connector is free, so inventory bounds real occupancy on
# its own. This counter only needs to bound the rate of state churn.
CHARGING_SESSION_RATE_LIMIT_WINDOW_SECONDS = 600.0
CHARGING_SESSION_RATE_LIMIT_REQUESTS = 5
CHARGING_SESSION_GLOBAL_RATE_LIMIT_REQUESTS = 60

# ------------------------------------------------------------------------ storage
# Cap on distinct subjects tracked PER NAMESPACE, so the limiter cannot be used
# to grow the heap; oldest-touched subject in that namespace is evicted first.
# Namespaces are string literals in the handlers, never caller input, so the
# total is bounded: main.py declares 15 of them, 8 of which hold subjects at all
# (the other 7 are ceilings, one deque each). At roughly 1 KB per tracked subject
# -- an empty deque alone is ~760 bytes -- that is ~33 MB per worker in a worst
# case which first requires thousands of genuinely distinct callers on every one
# of those 8 endpoints.
#
# WHY PER-NAMESPACE AND WHY THIS BIG. With one shared table, 4096 requests to any
# endpoint evicted -- i.e. reset -- every other endpoint's counters, including
# the ones that had just locked an abuser out. Now eviction can only reach
# subjects of the same namespace, and each namespace's own ceiling bounds how
# fast that namespace can be filled: forgot:email admits 30/hour, so flushing
# 4096 of them takes ~136 hours against a 1-hour window; login:fail:ip admits
# 720/hour, ~5.7 hours against a 5-minute window. In every namespace the fill
# time is far longer than the window, so eviction can never reset a live counter.
# That is the property that makes it safe to key on a caller-supplied value.
MAX_TRACKED_SUBJECTS_PER_NAMESPACE = 4096

# One lock for the whole module. The critical sections are a few microseconds of
# deque work, so contention is irrelevant next to correctness: see the docstring.
_LOCK = threading.Lock()

# namespace -> LRU of subject -> hit timestamps. Evictable.
_SUBJECTS: Dict[str, "OrderedDict[str, Deque[float]]"] = {}

# namespace -> hit timestamps for the deployment-wide ceiling. NEVER evicted:
# a ceiling that traffic can flush is not a ceiling. Bounded because namespaces
# are literals in the code, not caller input.
_CEILINGS: Dict[str, Deque[float]] = {}


def _prune(hits: Deque[float], now: float, window_seconds: float) -> None:
    """Drop timestamps that have fallen out of the window."""
    cutoff = now - window_seconds
    while hits and hits[0] <= cutoff:
        hits.popleft()


def _peek_locked(namespace: str, subject: Optional[str]) -> Optional[Deque[float]]:
    """The bucket for (namespace, subject), or None. Creates nothing.

    Read-only on purpose, including the LRU order: a caller that only ever checks
    must not be able to keep a stale entry alive, and a check must not buy a
    table slot for a request that is about to be denied.
    """
    if subject is None:
        return _CEILINGS.get(namespace)
    return _SUBJECTS.get(namespace, {}).get(subject)


def _record_locked(namespace: str, subject: Optional[str], window_seconds: float) -> None:
    now = time.monotonic()
    if subject is None:
        hits = _CEILINGS.get(namespace)
        if hits is None:
            hits = _CEILINGS[namespace] = deque()
        _prune(hits, now, window_seconds)
        hits.append(now)
        return

    buckets = _SUBJECTS.get(namespace)
    if buckets is None:
        buckets = _SUBJECTS[namespace] = OrderedDict()
    hits = buckets.get(subject)
    if hits is None:
        hits = buckets[subject] = deque()
    buckets.move_to_end(subject)
    _prune(hits, now, window_seconds)
    hits.append(now)
    while len(buckets) > MAX_TRACKED_SUBJECTS_PER_NAMESPACE:
        buckets.popitem(last=False)


def _exceeded_locked(namespace: str, subject: Optional[str], limit: int,
                     window_seconds: float) -> bool:
    hits = _peek_locked(namespace, subject)
    if hits is None:
        # No bucket yet, so nothing can have been spent -- unless the limit is 0,
        # which means "never allow". Returning False there would turn a limit
        # misconfigured to 0 into no limit at all, silently.
        return limit <= 0
    _prune(hits, time.monotonic(), window_seconds)
    return len(hits) >= limit


def exceeded(namespace: str, subject: Optional[str], limit: int,
             window_seconds: float) -> bool:
    """Would the next hit exceed `limit` per window? Records nothing.

    Pair with `record()` for counters that must only charge *failures* (see
    /auth/login), so that legitimate traffic can never spend the budget.
    """
    with _LOCK:
        return _exceeded_locked(namespace, subject, limit, window_seconds)


def record(namespace: str, subject: Optional[str], window_seconds: float) -> None:
    """Charge one hit to (namespace, subject). `subject=None` is the ceiling."""
    with _LOCK:
        _record_locked(namespace, subject, window_seconds)


def allow(namespace: str, subject: Optional[str], limit: int,
          window_seconds: float) -> bool:
    """Record a hit; return False when it would exceed `limit` per window.

    `subject=None` addresses the namespace's deployment-wide ceiling.
    """
    with _LOCK:
        if _exceeded_locked(namespace, subject, limit, window_seconds):
            return False
        _record_locked(namespace, subject, window_seconds)
        return True


def tracked_subjects(namespace: str) -> int:
    """How many subjects the namespace is holding. Introspection for tests."""
    with _LOCK:
        return len(_SUBJECTS.get(namespace, ()))


def reset() -> None:
    """Drop all counters. Test helper -- not used by request handling."""
    with _LOCK:
        _SUBJECTS.clear()
        _CEILINGS.clear()
