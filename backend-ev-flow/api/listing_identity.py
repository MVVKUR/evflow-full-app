"""Decide whether two rows *from the same source* are the same physical listing.

Background
----------
Dedup clusters every point within ``MERGE_RADIUS_M`` into one station and then
combines the members' connector lists. Taking the MAX count per
``(type, power_kw)`` is right when two *different* sources describe one site --
that is what ``connectors.merge_connectors`` documents -- but it is wrong when
one source lists a venue twice because the venue really has two separate
charger cabinets.

A hand-labelled audit of every same-source group where MAX actually discards
something (117 groups, out of 229 same-source groups in 2931 clusters) found the
population is genuinely mixed: separate chargers at one venue (a PLN office with
an HVT cabinet next to a DAYA+ cabinet, ``TRANSMART PEKANBARU A`` and ``... B``)
sit next to the same site imported twice (``(VOLTRON) Menara Era`` twice,
``Loop Graha Familly`` / ``Loop Graha Family`` at an identical coordinate). So
neither MAX-everywhere nor SUM-within-source is defensible on its own.

The separator
-------------
Reading the audit end to end, one signal splits the two populations far better
than any similarity threshold does:

* every genuinely distinct pair is marked as distinct **inside the name** -- an
  enumerator (``A``/``B``, ``1``/``2``/``3``, ``Tower 1``/``Tower 2``,
  ``6 A``/``6 B``) or a sub-location marker (``(B1)``/``(GF)``, ``Wing C``,
  ``Parking Area``, ``Gudang``, ``Shop House``, PLN's ``Center`` cabinet
  programme, a different vendor brand);
* every real duplicate differs only by *spelling*, *acronym*, *abbreviation* or
  *word order*, and carries no such marker.

So the rule is ordered, not weighted:

1. **Distinctness veto.** If the two names disagree on their enumerator /
   sub-location signature, or on their vendor brand, they are DISTINCT and
   nothing below can override it.
2. **Duplicate detectors.** Otherwise look for evidence of one name being a
   restatement of the other: token containment, an acronym expansion
   (``TKDN`` -> ``Teknologi Karya Digital Nusa``, ``KG`` -> ``Kompas Gramedia``),
   a prefix/abbreviation (``McD`` -> ``McDonald's``), a spelling variant within
   a small edit distance (``Citereup`` / ``Citeureup``), or plain token overlap.
3. **Corroboration, never decision.** Identical coordinates plus an identical
   connector profile can lift a *weak* name match over the line, but can never
   create a match on their own and can never beat step 1. 47 of the 117 audited
   groups sit at exactly 0.000 m and split roughly evenly between real
   duplicates and real multi-cabinet venues, so distance decides nothing.
4. **Ambiguity resolves to DISTINCT**, i.e. the counts get summed. Over-counting
   is the accepted direction; a duplicate that gets summed is not.

This is still a heuristic over dirty free-text. It is deliberately built out of
*general* shape rules (enumerators, acronyms, edit distance, brand tokens) so it
keeps working on the next data refresh -- no station name is hard-coded here.
The named audit cases live in ``tests/test_listing_identity.py`` as the oracle.
Pure / stdlib-only.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional, Sequence

# Minimum name-token overlap (Jaccard) for two brand-compatible rows to be
# judged one listing, once the distinctness veto has passed.
NAME_JACCARD_THRESHOLD = 0.5

# Same threshold applied to the *fuzzy* overlap, which additionally credits
# acronyms, abbreviations and spelling variants as matches.
FUZZY_MATCH_THRESHOLD = 0.5

# The floor a fuzzy overlap may drop to when identical coordinates AND an
# identical connector profile corroborate it. Never applied on its own.
CORROBORATED_MATCH_THRESHOLD = 0.2

# How close two rows must sit before their coordinates count as corroboration.
# Small on purpose: this is a "these are the same dot" test, not a merge radius.
COLOCATED_M = 20.0

_PUNCT = re.compile(r"[^a-z0-9+]+")
_POSSESSIVE = re.compile(r"['’]s\b")

# Tokens that carry no venue identity -- every other PLN row contains them, so
# leaving them in would inflate the overlap of unrelated sites. ``ulp``/``up3``/
# ``uid``/``uiw`` are PLN administrative-unit codes: they name the operating
# unit, not the site, and two different units sharing a (wrong) coordinate must
# not look similar just because both say "ULP".
_NOISE = {"spklu", "pln", "charging", "station", "ev", "charger", "kw", "the",
          "up", "to", "dc", "ac", "gedung", "jakarta",
          "ulp", "up3", "uid", "uiw"}

# Charging-network / cabinet-vendor tokens that appear inside the name field.
# Two rows carrying DIFFERENT brands at one venue are separate hardware and must
# never be collapsed (this is what makes the multi-cabinet PLN offices work).
# Ordered longest-prefix-first where one brand contains another
# ("utomo charge+" before "utomo").
_BRANDS = ("voltron", "terra charge", "terracharge", "utomo charge+", "utomo",
           "hvt", "niscala", "evcity", "daya+", "cse", "zora", "alvacharge",
           "uci beny", "travoy", "starvo", "dayagreen", "stroom ppi",
           "bluecharge", "arista power", "indomobil", "wuling",
           "astra otopower", "mobile")

# Words that name a *part* of a venue rather than the venue. When one name
# carries one of these and the other does not, the rows describe different
# hardware at one address -- a warehouse cabinet next to the office cabinet, a
# shop-house unit next to the apartment tower, PLN's "SPKLU Center" programme
# cabinet next to the plain one. Deliberately excludes words that merely vary
# between spellings of one venue ("apartment", "residence", "mall", "hotel",
# "retail", "arcade"), which is why "The Bellezza Retail & Apartment" and
# "The Bellezza Shopping Arcade" are still allowed to be one listing.
_SUBLOCATION_MARKERS = {
    "wing", "tower", "blok", "block", "lantai", "basement",
    "gf", "lg", "ug", "mezzanine", "parking", "parkir", "gudang", "warehouse",
    "ruko", "shophouse", "annex", "podium", "center", "centre",
}

# Building-type phrases that normalise to one marker token.
_PHRASES = ((re.compile(r"\bshop\s+house\b"), "shophouse"),
            (re.compile(r"\brumah\s+toko\b"), "ruko"))

# A unit code: "b1", "6a", "229b" -- a floor, a bay or a kilometre post.
_UNIT_CODE = re.compile(r"[a-z]{1,2}\d{1,3}|\d{1,4}[a-z]{1,2}")


def normalize_name(name: Optional[str]) -> str:
    """Lower-case, drop possessives, collapse building phrases, strip punctuation."""
    n = _POSSESSIVE.sub("", (name or "").lower())
    for pattern, replacement in _PHRASES:
        n = pattern.sub(replacement, n)
    return " ".join(_PUNCT.sub(" ", n).split())


def core_tokens(name: Optional[str]) -> set[str]:
    """Venue-identifying tokens: normalized, minus noise words and bare digits.

    Digits are dropped here because they are handled by ``enumerator_signature``
    instead, where a mismatch is a hard veto rather than a similarity penalty.
    """
    return {t for t in normalize_name(name).split()
            if t not in _NOISE and not t.isdigit()}


def brand_token(name: Optional[str]) -> str:
    """The charging-network brand embedded in a name, or ``""`` if none."""
    n = normalize_name(name)
    for b in _BRANDS:
        if b in n:
            return b
    return ""


def identity_tokens(name: Optional[str]) -> list[str]:
    """Core tokens with the vendor brand removed, in reading order.

    Order is kept because acronym expansion is order-sensitive: ``KG`` only
    expands against the adjacent run ``kompas gramedia``.
    """
    n = normalize_name(name)
    brand = brand_token(name)
    if brand:
        n = n.replace(brand, " ")
    seen: set[str] = set()
    out: list[str] = []
    for t in n.split():
        if t in _NOISE or t.isdigit() or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def enumerator_signature(name: Optional[str]) -> frozenset[str]:
    """Every token in a name that marks *which* unit at a venue is meant.

    Bare numbers ("Tower **1**"), bare letters ("PEKANBARU **A**"), unit codes
    ("(**B1**)", "KM 229**B**") and sub-location words ("**Wing** C",
    "**Gudang**"). Two names whose signatures differ are two different units --
    that is the veto in ``same_listing``.
    """
    sig: set[str] = set()
    for t in normalize_name(name).split():
        if t.isdigit() or (len(t) == 1 and t.isalpha()):
            sig.add(t)
        elif t in _SUBLOCATION_MARKERS:
            sig.add(t)
        elif t not in _BRANDS and _UNIT_CODE.fullmatch(t):
            sig.add(t)
    return frozenset(sig)


def name_jaccard(a: Optional[str], b: Optional[str]) -> float:
    """Jaccard overlap of two names' core tokens. 0.0 when both are empty."""
    ta, tb = core_tokens(a), core_tokens(b)
    union = ta | tb
    return len(ta & tb) / len(union) if union else 0.0


def _edit_distance(x: str, y: str, cap: int = 3) -> int:
    """Levenshtein distance, saturating at ``cap`` (we never care past it)."""
    if abs(len(x) - len(y)) > cap:
        return cap + 1
    prev = list(range(len(y) + 1))
    for i, cx in enumerate(x, 1):
        cur = [i]
        for j, cy in enumerate(y, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (cx != cy)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def _tokens_match(x: str, y: str) -> bool:
    """One token is a spelling variant / abbreviation of the other."""
    if x == y:
        return True
    short, long = sorted((x, y), key=len)
    if len(short) < 3:
        return False           # two-letter tokens only ever match exactly
    if long.startswith(short):
        return True            # "mcd" -> "mcdonald", "springhill" -> "springhills"
    if len(short) >= 4 and short in long:
        return True            # "nine" inside "thamrinine"
    if len(short) >= 4:
        return _edit_distance(x, y) <= (1 if len(long) <= 8 else 2)
    return False


def _acronym_run(token: str, tokens: Sequence[str]) -> Optional[tuple[int, int]]:
    """Find a run of ``tokens`` whose initials spell ``token``, order-insensitive.

    Order-insensitive because the feeds transpose them: ``Mega Glodok
    Kemayoran`` is listed as ``MKG``. Requires one initial per word, so a run of
    length ``len(token)``.
    """
    n = len(token)
    if not (2 <= n <= 5) or not token.isalpha():
        return None
    target = sorted(token)
    for i in range(len(tokens) - n + 1):
        run = tokens[i:i + n]
        if sorted(w[0] for w in run) == target:
            return (i, i + n)
    return None


def fuzzy_overlap(a: Optional[str], b: Optional[str]) -> float:
    """Jaccard overlap of two names' identity tokens, with fuzzy matching.

    A token counts as shared when it matches the other side exactly, as a
    spelling variant, as an abbreviation, or through an acronym expansion. The
    shared count is the mean of the two sides' matched counts (an acronym
    matches one token against several, so the two sides disagree), and the
    union is ``len_a + len_b - shared``. Same 0..1 scale as ``name_jaccard``,
    so the two thresholds are directly comparable.
    """
    ta, tb = identity_tokens(a), identity_tokens(b)
    if not ta or not tb:
        return 0.0
    matched_a: set[str] = set()
    matched_b: set[str] = set()
    for x in ta:
        for y in tb:
            if _tokens_match(x, y):
                matched_a.add(x)
                matched_b.add(y)
    for src, dst, m_src, m_dst in ((ta, tb, matched_a, matched_b),
                                   (tb, ta, matched_b, matched_a)):
        for token in src:
            run = _acronym_run(token, dst)
            if run:
                m_src.add(token)
                m_dst.update(dst[run[0]:run[1]])
    shared = (len(matched_a) + len(matched_b)) / 2
    return shared / (len(ta) + len(tb) - shared)


def _profile_key(conns: Optional[Iterable[dict]]) -> frozenset:
    """The set of (type, power_kw) a row offers -- counts deliberately ignored.

    Two imports of one listing routinely disagree on the count while agreeing on
    exactly which plug kinds stand there.
    """
    return frozenset((c.get("type"), c.get("power_kw")) for c in (conns or []))


def _brand_is_the_only_difference(a: Optional[str], b: Optional[str]) -> bool:
    """True when one row is the other row plus a vendor brand.

    ``SPKLU ALOHA PIK 2`` / ``SPKLU HVT ALOHA PIK 2`` and ``SPKLU PLN UP3 PONDOK
    GEDE`` / ``SPKLU EVCITY PLN UP3 PONDOK GEDE`` are the signature of a venue
    that grew a second cabinet from a second vendor: the site name is untouched
    and the vendor is bolted on. Those must never collapse. A branded row whose
    name *also* differs elsewhere (``Hotel LePolonia - Medan`` vs ``(STARVO)
    LePolonia Hotel & Convention``) is just the same site re-imported.
    """
    ta, tb = set(identity_tokens(a)), set(identity_tokens(b))
    return bool(ta or tb) and (ta <= tb or tb <= ta)


def same_listing(a: Optional[str], b: Optional[str], *,
                 distance_m: Optional[float] = None,
                 connectors_a: Optional[Iterable[dict]] = None,
                 connectors_b: Optional[Iterable[dict]] = None) -> bool:
    """True when two same-source names look like one listing imported twice.

    ``distance_m`` and the two connector lists are optional CORROBORATION only:
    supplying them can rescue a weak name match, never create one, and never
    beat the distinctness veto. Omitting them keeps the pure-name behaviour.
    """
    # --- 1. distinctness veto -------------------------------------------------
    if enumerator_signature(a) != enumerator_signature(b):
        return False

    ba, bb = brand_token(a), brand_token(b)
    if ba and bb and ba != bb:
        return False
    if bool(ba) != bool(bb) and _brand_is_the_only_difference(a, b):
        return False

    # --- 2. duplicate detectors ----------------------------------------------
    ta, tb = set(identity_tokens(a)), set(identity_tokens(b))
    if not ta or not tb:
        return False                     # no identity left; summing is the safe way
    if ta <= tb or tb <= ta:
        return True                      # one name is a truncation of the other
    if name_jaccard(a, b) >= NAME_JACCARD_THRESHOLD:
        return True
    score = fuzzy_overlap(a, b)
    if score >= FUZZY_MATCH_THRESHOLD:
        return True

    # --- 3. corroboration (cannot decide alone) ------------------------------
    if score < CORROBORATED_MATCH_THRESHOLD:
        return False
    if distance_m is None or distance_m > COLOCATED_M:
        return False
    profile = _profile_key(connectors_a)
    return bool(profile) and profile == _profile_key(connectors_b)
