"""Philippine name variants generator — improves recall for PH person investigations.

Pure computation; no external API calls.
"""

from __future__ import annotations

import logging

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Filipino naming conventions — nicknames, married-name hyphenation, Hispanicized forms, "
    "middle-name initials — create many valid name spellings for the same person. "
    "Running this node first prevents missed records in PH searches."
)

# ---------------------------------------------------------------------------
# Nickname tables
# ---------------------------------------------------------------------------

PH_NICKNAMES: dict[str, list[str]] = {
    "jose": ["pepe", "joe", "jojo", "boy"],
    "joseph": ["joe", "jojo"],
    "maria": ["mary", "mayi", "marya", "marie", "mia"],
    "francisco": ["kiko", "paco", "frank", "franz"],
    "corazon": ["cory", "cora"],
    "ferdinand": ["ferdie", "bongbong", "bong"],
    "rodrigo": ["rody", "digong"],
    "benigno": ["noynoy", "ninoy"],
    "gloria": ["glo"],
    "imelda": ["meldy"],
    "roberto": ["bert", "robert", "bob", "bobby"],
    "eduardo": ["eddie", "ed", "boboy"],
    "antonio": ["tony", "toni", "tonet"],
    "juan": ["john", "johnny"],
    "miguel": ["mike", "michael", "migo"],
    "carlos": ["carl", "charlie", "carling"],
    "andres": ["andy", "andoy"],
    "manuel": ["manny", "manolo", "noel"],
    "christopher": ["chris", "topher", "kit"],
    "raymond": ["mon", "ray"],
    "mark": ["markus"],
    "ana": ["annie", "anita", "anya"],
    "angela": ["angel", "angie"],
    "elizabeth": ["beth", "betty", "bessie", "liz"],
    "grace": ["gracie"],
    "lorraine": ["lorie", "rain"],
    "kristine": ["kris", "tin", "tina"],
    "jennifer": ["jen", "jenny"],
    "jessica": ["jess", "jessie"],
    "michaela": ["mikay", "mika"],
}

# Reverse map: nickname → canonical first names
_REVERSE_NICKNAMES: dict[str, list[str]] = {}
for _canonical, _nicks in PH_NICKNAMES.items():
    for _nick in _nicks:
        _REVERSE_NICKNAMES.setdefault(_nick, []).append(_canonical)

# Hispanicized ↔ Anglicized equivalents (bidirectional)
_HISPANIC_ANGLO: dict[str, str] = {
    "roberto": "robert",
    "robert": "roberto",
    "juan": "john",
    "john": "juan",
    "miguel": "michael",
    "michael": "miguel",
    "jose": "joseph",
    "joseph": "jose",
    "antonio": "anthony",
    "anthony": "antonio",
    "manuel": "emmanuel",
    "emmanuel": "manuel",
    "francisco": "francis",
    "francis": "francisco",
    "carlos": "charles",
    "charles": "carlos",
    "andres": "andrew",
    "andrew": "andres",
    "pedro": "peter",
    "peter": "pedro",
    "pablo": "paul",
    "paul": "pablo",
}

# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

MAX_VARIANTS = 15


def run_ph_name_variants(
    first_name: str = "",
    last_name: str = "",
    middle_name: str = "",
    full_name: str = "",
) -> dict:
    """Generate all plausible Filipino name variants for a subject.

    Parameters
    ----------
    first_name:
        Given name (e.g. "Maria").
    last_name:
        Family name; may be hyphenated for married names (e.g. "Santos-Cruz").
    middle_name:
        Middle name, typically mother's maiden surname in PH convention.
    full_name:
        Alternative to first/last — parsed automatically if first/last are blank.

    Returns
    -------
    dict with keys:
        - ``variants``: deduplicated list of name strings (≤ MAX_VARIANTS)
        - ``search_queries``: list of one combined OR-search query string
        - ``input_parsed``: dict with ``first``, ``middle``, ``last`` as parsed
    """
    first, middle, last = _parse_inputs(first_name, last_name, middle_name, full_name)

    if not first and not last:
        return {
            "variants": [],
            "search_queries": [],
            "input_parsed": {"first": "", "middle": "", "last": ""},
            "error": "No name provided",
        }

    variants: list[str] = []
    first_key = first.lower()
    last_key = last.lower()

    # 1. Base forms
    if first and last:
        variants.append(f"{first} {last}")
    if last and first:
        variants.append(f"{last}, {first}")   # records-style Last, First
    if last and first:
        variants.append(f"{last} {first}")    # plain reversal without comma

    # 2. Middle name inclusion
    if middle and first and last:
        variants.append(f"{first} {middle} {last}")
        variants.append(f"{first} {middle[0].upper()}. {last}")

    # 3. Initials form: "F.M. Last" (used in PRC / professional licenses)
    if first and last:
        initials = first[0].upper() + "."
        if middle:
            initials += middle[0].upper() + "."
        variants.append(f"{initials} {last}")

    # 4. Nickname expansion — first_name → all its nicknames
    if first_key in PH_NICKNAMES:
        for nick in PH_NICKNAMES[first_key]:
            nick_proper = nick.capitalize()
            if last:
                variants.append(f"{nick_proper} {last}")
            if middle and last:
                variants.append(f"{nick_proper} {middle} {last}")
                variants.append(f"{nick_proper} {middle[0].upper()}. {last}")

    # 5. Reverse nickname — if first_name IS a known nickname, try canonical forms
    if first_key in _REVERSE_NICKNAMES:
        for canonical in _REVERSE_NICKNAMES[first_key]:
            canon_proper = canonical.capitalize()
            if last:
                variants.append(f"{canon_proper} {last}")

    # 6. Hispanicized ↔ Anglicized equivalent
    alt_first = _HISPANIC_ANGLO.get(first_key)
    if alt_first:
        alt_proper = alt_first.capitalize()
        if last:
            variants.append(f"{alt_proper} {last}")
        if middle and last:
            variants.append(f"{alt_proper} {middle[0].upper()}. {last}")

    # 7. Married name hyphenation — if last_name has a hyphen, try both orders
    if "-" in last:
        parts = last.split("-", 1)
        alt_last_a = f"{parts[1]}-{parts[0]}"  # reversed hyphen order
        alt_last_b = parts[0]                  # maiden only
        alt_last_c = parts[1]                  # married only
        for alt in (alt_last_a, alt_last_b, alt_last_c):
            if first:
                variants.append(f"{first} {alt}")
    elif first and last:
        # If no hyphen, offer a hyphenated married-name form
        # (only useful when middle_name looks like a surname — skip if absent)
        if middle:
            variants.append(f"{first} {last}-{middle}")

    # 8. De-prefixed variants: "dela Cruz" → "dela Cruz" and "Cruz"
    _de_prefixes = ("dela ", "de la ", "de los ", "de las ", "de ", "del ", "san ", "santa ")
    for prefix in _de_prefixes:
        if last_key.startswith(prefix):
            stripped_last = last[len(prefix):].strip()
            if stripped_last and first:
                variants.append(f"{first} {stripped_last}")
            break

    # Deduplicate while preserving order; drop blanks; cap at MAX_VARIANTS
    seen: set[str] = set()
    unique: list[str] = []
    for v in variants:
        v = v.strip()
        if v and v not in seen:
            seen.add(v)
            unique.append(v)
        if len(unique) >= MAX_VARIANTS:
            break

    # Build combined OR search query (quote each variant)
    search_query = " OR ".join(f'"{v}"' for v in unique) if unique else ""

    return {
        "variants": unique,
        "search_queries": [search_query] if search_query else [],
        "input_parsed": {"first": first, "middle": middle, "last": last},
        "source": "ph_name_variants",
        "reason": _REASON,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_inputs(
    first_name: str,
    last_name: str,
    middle_name: str,
    full_name: str,
) -> tuple[str, str, str]:
    """Normalise and return (first, middle, last)."""
    first = first_name.strip().title() if first_name else ""
    last = last_name.strip().title() if last_name else ""
    middle = middle_name.strip().title() if middle_name else ""

    # If first/last not provided, try to parse full_name
    if not first and not last and full_name:
        parts = full_name.strip().split()
        if len(parts) == 1:
            last = parts[0].title()
        elif len(parts) == 2:
            first, last = parts[0].title(), parts[1].title()
        elif len(parts) >= 3:
            first = parts[0].title()
            last = parts[-1].title()
            if not middle:
                middle = " ".join(p.title() for p in parts[1:-1])

    return first, middle, last


# ---------------------------------------------------------------------------
# Node class (pipeline integration)
# ---------------------------------------------------------------------------

class PhNameVariantsNode:
    node_type = "ph_name_variants"
    display_name = "PH Name Variants"
    category = "lookup"

    config_schema = {
        "type": "object",
        "properties": {
            "first_name": {
                "type": "string",
                "title": "First Name",
                "description": "Given name of the Filipino subject (e.g. 'Maria').",
                "default": "",
            },
            "last_name": {
                "type": "string",
                "title": "Last Name",
                "description": "Surname; hyphenated for married names (e.g. 'Santos-Cruz').",
                "default": "",
            },
            "middle_name": {
                "type": "string",
                "title": "Middle Name",
                "description": "Mother's maiden surname in PH convention (optional).",
                "default": "",
            },
            "full_name": {
                "type": "string",
                "title": "Full Name",
                "description": "Full name string — parsed automatically if first/last are blank.",
                "default": "",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        first = (config.get("first_name") or "").strip()
        last = (config.get("last_name") or "").strip()
        middle = (config.get("middle_name") or "").strip()
        full = (config.get("full_name") or "").strip()

        # Fall back to pipeline inputs if config is empty
        if not first and not last and not full:
            for item in inputs:
                first = (item.get("first_name") or "").strip()
                last = (item.get("last_name") or "").strip()
                middle = (item.get("middle_name") or "").strip()
                full = (
                    item.get("full_name") or item.get("name") or ""
                ).strip()
                if first or last or full:
                    break

        result = run_ph_name_variants(
            first_name=first,
            last_name=last,
            middle_name=middle,
            full_name=full,
        )
        return [result]


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from app.pipeline.nodes.ph_name_variants import run_ph_name_variants  # noqa: PLC0415

    result = run_ph_name_variants(
        first_name="Maria", last_name="Santos-Cruz", middle_name="Reyes"
    )
    import json
    print(json.dumps(result, indent=2))
