# Comprehensive Investigation Strategy — Design Spec

**Date:** 2026-05-07
**Status:** Draft
**Triggered by:** Query 04692dda lacking depth — shallow, cursory investigation strategy

## Problem Statement

The Intelligent Search (IS) brain performs shallow, cursory investigations. When investigating a person, it does a few web searches and LinkedIn lookups, then stops. It lacks:

1. **Strategic depth** — no guidance on what investigation domains to cover comprehensively
2. **Technical breadth** — missing capabilities for email verification (SMTP), breach lookups, username enumeration, facial recognition, messaging platform checks, etc.
3. **Intelligence classification** — no framework for assessing source reliability, information credibility, corroboration, or perishability
4. **Entity resolution** — findings about the same entity from different sources are not merged
5. **Selector-centric execution** — investigation should pivot on identifiers (selectors), not walk through sources sequentially
6. **Self-learning** — investigation strategies should evolve based on what works

## Architecture Overview

### Three-Layer Design

```
┌─────────────────────────────────────────────────────────┐
│ LAYER 1: COLLECTION                                      │
│ Pipeline nodes (existing + new) produce raw findings     │
│ + extracted selectors                                    │
└───────────────────────┬─────────────────────────────────┘
                        ↓ findings + selectors
┌─────────────────────────────────────────────────────────┐
│ LAYER 2: INTELLIGENCE FUSION (NEW)                       │
│ ├── Selector Extraction                                  │
│ ├── Entity Resolution (merge partial records)            │
│ ├── Relationship Graph (entity-relationship edges)       │
│ ├── Classification (Admiralty, corroboration, decay)     │
│ └── Completeness Assessment (domain checklist)           │
└───────────────────────┬─────────────────────────────────┘
                        ↓ unified entities + classified findings
┌─────────────────────────────────────────────────────────┐
│ LAYER 3: ANALYSIS                                        │
│ ├── Base: Synthesis + gap identification                 │
│ ├── Optional: ACH (competing hypotheses)                 │
│ └── Optional: PIR decomposition (intelligence reqs)      │
└─────────────────────────────────────────────────────────┘
```

### Integration with Existing Architecture

```
IS Brain Prompt:
  1. Base System Prompt (existing)
  2. Entity Strategy — selector-centric guidance (NEW)
  3. Suggested Strategies — from procedural memory (existing)
  4. Research Goal — from config (existing)
  5. Available Tools — auto-discovered nodes (existing + new nodes)

Post-Run Pipeline:
  1. create_skill_from_run()        (existing)
  2. analyze_run_pivots()           (NEW — maps tool calls to pivot patterns)
  3. update_strategy_overlays()     (NEW — reinforce/prune/discover/upgrade)
  4. User feedback → quality loop   (existing)
```

---

## Part 1: Selector-Centric Investigation Model

### Core Concept

Traditional OSINT investigation is **source-centric**: "search LinkedIn, then Facebook, then Hunter.io." This produces shallow, disconnected results.

Nation-state intelligence (derived from NSA architecture patterns: PRISM → XKeyscore → TIDE) is **selector-centric**: everything revolves around identifiers (selectors) that map to entities. Investigation is graph traversal from selector to selector.

### Selector Types

| Selector Type | Examples | Priority (Person) |
|--------------|---------|-------------------|
| `full_name` | "John Michael Doe" | Seed — always present |
| `email` | john.doe@gmail.com | High — pivots to many sources |
| `phone` | +63-917-XXX-XXXX | High — pivots to messaging, reverse lookup |
| `username` | johndoe42 | High — cross-platform identity linkage |
| `domain` | johndoe.com, employer.com | Medium — reveals ownership, colleagues |
| `address` | physical/mailing address | Medium — property records, neighbors |
| `employer` | Company name + role | Medium — professional network |
| `ip_address` | From email headers, website logs | Low — geolocation, infrastructure |
| `crypto_wallet` | 0x... / bc1... | Low (sentinel) — financial activity |
| `vehicle_id` | License plate, VIN | Low (sentinel) — location, ownership |
| `photo` | Profile picture, tagged photo | Medium — facial recognition pivot |
| `national_id` | SSN, TIN, passport number | Low (sentinel) — official records |

### Investigation Flow

```
1. SEED: Start with known selectors (name, maybe email or phone)
     ↓
2. EXPAND: Run pivot patterns for each selector → extract NEW selectors
     ↓
3. RESOLVE: Entity resolution — merge findings pointing to same entity
     ↓
4. GRAPH: Build relationship graph (entity → entity edges)
     ↓
5. HOP: For high-priority new selectors, recurse (configurable depth)
     ↓
6. ASSESS: Check completeness against domain checklist
     ↓
7. CLASSIFY: Apply Admiralty scoring, corroboration, decay
     ↓
8. REPORT: Synthesize unified profile with confidence metadata
```

---

## Part 2: Strategy, Tactics, Techniques (Reframed)

### Taxonomy

| Level | Definition | Selector-Centric Meaning |
|-------|-----------|--------------------------|
| **Strategy** | What selectors to pursue and completeness criteria | "For a Person: discover and pursue all email, phone, username, domain, address, wallet selectors. Investigation complete when selector graph exhausted to N hops or budget spent." |
| **Tactics** | Pivot patterns — given selector type X, what tools extract new selectors and relationships? | "email → smtp_verifier, hibp_lookup, reverse_lookup, messaging_check, web_search" |
| **Techniques** | Specific tool calls and parameter patterns | "run_smtp_verifier(email='...', timeout=10)" |

### Pivot Patterns (Tactics Layer)

#### Pivot: `full_name` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| web_search ("full name" + location) | Bio, employer, news mentions | employer, address, email (sometimes) |
| run_linkedin_profile (name search) | Professional profile, employment history | employer, email, phone, colleagues |
| run_facebook_pages (name search) | Personal profile, friends, check-ins | username, email, phone, family names |
| run_instagram_profile | Photos, bio, followers | username, photo |
| run_twitter_search | Tweets, bio, network | username, website/domain |
| run_ph_sec_dti / run_opencorporates | Corporate officer records | employer (as owner), address |
| run_apollo_zoominfo | Professional enrichment | email, phone, employer |
| web_search ("full name" filetype:pdf) | Documents authored by/mentioning subject | email, employer, address, co-authors |

#### Pivot: `email` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| run_smtp_verifier | Existence confirmation, MX host | (validates selector) |
| run_hibp_lookup | Breach exposure, breached services | other emails, usernames, passwords (service inference) |
| run_reverse_lookup | Linked identities, accounts | full_name, phone, address, usernames |
| run_username_enumerator (local-part) | Accounts using same username | platform profiles |
| run_hunter_io (domain-part) | Company info, colleagues | other emails at same domain |
| run_messaging_check | WhatsApp/Telegram/Signal presence | phone (from WhatsApp), username (from Telegram) |
| web_search ("email") | Forum posts, documents, mentions | any found in content |
| run_pep_sanctions_screen | Watchlist hits | (classification: sentinel) |

#### Pivot: `phone` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| run_phone_osint | Carrier, location, line type | (enrichment) |
| run_reverse_lookup | Name, address, other phones | full_name, address, other phones |
| run_messaging_check | WhatsApp profile, Telegram username | username, photo |
| web_search ("phone number") | Business listings, social profiles | employer, address |

#### Pivot: `username` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| run_username_enumerator | Confirmed platforms + profile URLs | platform-specific profiles |
| web_search ("username") | Forum posts, code repos, comments | email, full_name |
| follow_url (each confirmed profile) | Profile details, bio, links | email, phone, website/domain, photo |

#### Pivot: `domain` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| run_whois_lookup | Registrant info, dates | full_name, email, address, phone |
| run_shodan_search | Exposed services, infrastructure | ip_address |
| run_hunter_io (domain search) | All emails at domain | emails |
| web_crawl (domain) | Site content, team pages | full_name, email, phone, photos |

#### Pivot: `address` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| web_search (address) | Property records, business listings | full_name (other occupants), employer |
| run_opencorporates (address search) | Companies registered at address | employer |

#### Pivot: `photo` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| run_face_search | Matching photos across web | profile URLs, usernames |
| run_exif_extractor | GPS coordinates, device info, timestamps | address (from GPS), (metadata enrichment) |

#### Pivot: `crypto_wallet` → [SENTINEL]

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| run_crypto_tracer | Transactions, counterparties, balances | other wallets, exchange accounts |

### Completeness Checklist (Domains as Assessment, Not Execution)

After the selector graph is exhausted, assess coverage:

| Domain | What to Check | Completeness Criteria |
|--------|--------------|----------------------|
| 1. Identity | Full name, aliases, DOB, nationality, location | Name confirmed from 2+ sources |
| 2. Digital Footprint | Emails, phones, usernames, social accounts | At least 1 verified email, social media mapped |
| 3. Family & Social Network | Relatives, spouse, children, associates | Immediate family identified (if discoverable) |
| 4. Professional History | Employment timeline, education, skills | Current + 1 prior employer confirmed |
| 5. Financial & Assets | Property, business ownership, crypto | Business ownership checked |
| 6. Public Records | Court, regulatory, licenses | Checked (sentinel — may be empty) |
| 7. Visual Intelligence | Photos, geolocation from images | At least 1 photo obtained |
| 8. Communication Intel | Messaging platforms, phone metadata | Messaging presence checked |
| 9. Dark Web & Breach Intel | Breaches, leaks, stealer logs, paste sites | HIBP checked for all discovered emails |
| 10. Online Communities | Forums, Reddit, Discord, Telegram groups | Username searched across platforms |

---

## Part 3: New Pipeline Nodes

### 3.1 smtp_verifier

**Category:** enrich
**Purpose:** Verify email existence via SMTP probing without sending email.

**Technique chain (with fallback):**
1. MX record lookup (DNS)
2. SMTP RCPT TO probe (connect → HELO → MAIL FROM → RCPT TO)
   - 250 → exists
   - 550 → doesn't exist
   - Timeout/block → inconclusive
3. Catch-all detection (test random address at same domain)

**Config:**
```json
{
  "email": { "type": "string", "required": true },
  "timeout_seconds": { "type": "integer", "default": 10 }
}
```

**Output:**
```json
{
  "email": "john.doe@gmail.com",
  "exists": true | false | null,
  "mx_host": "gmail-smtp-in.l.google.com",
  "method": "smtp_rcpt_to",
  "catch_all": false
}
```

**Notes:** Gmail/Outlook often block RCPT TO → returns null (inconclusive). Rate-limited: 1 probe/second/domain.

### 3.2 email_enumerator

**Category:** enrich
**Purpose:** Generate candidate emails from name + verify.

**Technique:**
1. Generate permutations: `first.last@`, `firstlast@`, `f.last@`, `flast@`, `first_last@`, `lastfirst@`, `last.first@`
2. Cross with providers: gmail.com, yahoo.com, hotmail.com, outlook.com, icloud.com, protonmail.com, aol.com + custom domains
3. Verify each via smtp_verifier internally
4. Optional: Hunter.io API for professional patterns

**Config:**
```json
{
  "first_name": { "type": "string", "required": true },
  "last_name": { "type": "string", "required": true },
  "domain_hints": { "type": "array", "items": { "type": "string" } },
  "providers": { "type": "array", "default": ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "protonmail.com"] },
  "max_candidates": { "type": "integer", "default": 50 }
}
```

**Output:** List of `{ "email", "exists", "source": "generated+smtp_verified" }`

### 3.3 hibp_lookup

**Category:** enrich
**Purpose:** Check email/username against breach databases.

**Technique chain:**
1. HaveIBeenPwned API (if key configured)
2. Dehashed API (if key configured)
3. Fallback: web search `"email" site:haveibeenpwned.com`

**Config:**
```json
{
  "email": { "type": "string", "required": true },
  "include_pastes": { "type": "boolean", "default": false }
}
```

**Output:**
```json
{
  "email": "...",
  "breached": true,
  "breaches": [{ "name": "LinkedIn2021", "date": "2021-06-22", "data_classes": ["email", "password", "name"] }],
  "source": "hibp_api"
}
```

### 3.4 reverse_lookup

**Category:** enrich
**Purpose:** Reverse-lookup email, phone, or username to find linked identities.

**Technique chain:**
1. API-backed: Pipl, FullContact, Spokeo (if keys configured)
2. Web search fallback: quoted exact-match searches across platforms
3. Social media profile URL probing (for usernames)

**Config:**
```json
{
  "query": { "type": "string", "required": true },
  "query_type": { "type": "string", "enum": ["email", "phone", "username", "auto"], "default": "auto" }
}
```

**Output:** `{ "query", "identities": [{ "name", "platform", "url", "confidence" }] }`

### 3.5 username_enumerator

**Category:** enrich
**Purpose:** Check username existence across 400+ platforms.

**Technique:** Sherlock/WhatsMyName library integration, or HTTP probing of known profile URL patterns.

**Config:**
```json
{
  "username": { "type": "string", "required": true },
  "platforms": { "type": "array", "description": "Limit to specific platforms (optional)" }
}
```

**Output:** List of `{ "platform", "url", "exists": true/false }`

### 3.6 face_search

**Category:** enrich
**Purpose:** Reverse facial recognition search.

**Technique chain:**
1. PimEyes API (if key configured)
2. FaceCheck.ID (if key configured)
3. Yandex reverse image search (free fallback)

**Config:**
```json
{
  "image_url": { "type": "string" },
  "image_base64": { "type": "string" },
  "max_results": { "type": "integer", "default": 20 }
}
```

**Output:** List of `{ "match_url", "source_platform", "confidence", "thumbnail_url" }`

### 3.7 exif_extractor

**Category:** enrich
**Purpose:** Extract metadata from images and documents.

**Technique:** exiftool wrapper — extract GPS, timestamps, author, device info, software.

**Config:**
```json
{
  "file_url": { "type": "string" },
  "file_path": { "type": "string" }
}
```

**Output:**
```json
{
  "gps": { "lat": 14.5995, "lon": 120.9842 },
  "timestamp": "2025-03-15T14:30:00",
  "device": "iPhone 15 Pro",
  "author": "John Doe",
  "software": "Microsoft Word 16.0"
}
```

### 3.8 document_search

**Category:** source
**Purpose:** Google Dorking + document metadata extraction.

**Technique:**
1. Google Custom Search API (or DuckDuckGo) with filetype operators
2. Download discovered documents
3. Extract metadata via exif_extractor

**Config:**
```json
{
  "query": { "type": "string", "required": true },
  "filetypes": { "type": "array", "default": ["pdf", "docx", "xlsx", "pptx"] },
  "site": { "type": "string", "description": "Limit to specific domain" },
  "max_results": { "type": "integer", "default": 10 }
}
```

**Output:** List of `{ "url", "filename", "filetype", "metadata": {...}, "snippet" }`

### 3.9 phone_osint

**Category:** enrich
**Purpose:** Phone number reconnaissance.

**Technique chain:**
1. PhoneInfoga (open source — carrier, line type, region)
2. NumVerify API (if key configured — validation, active status)
3. Truecaller API (if key configured — caller ID, name)

**Config:**
```json
{
  "phone": { "type": "string", "required": true },
  "country_code": { "type": "string" }
}
```

**Output:** `{ "phone", "carrier", "line_type", "region", "active", "caller_name" }`

### 3.10 messaging_check

**Category:** enrich
**Purpose:** Check presence on messaging platforms.

**Technique:**
1. Telegram: Bot API phone number check → username, display name
2. WhatsApp: Contact registration check → profile photo, about text
3. Signal: Phone number registration check (limited)

**Config:**
```json
{
  "phone": { "type": "string" },
  "email": { "type": "string" }
}
```

**Output:** `{ "telegram": { "exists", "username", "display_name" }, "whatsapp": { "exists", "has_photo" }, "signal": { "exists" } }`

### 3.11 pep_sanctions_screen [SENTINEL]

**Category:** enrich
**Purpose:** Screen against PEP (Politically Exposed Persons) and sanctions lists.

**Technique chain:**
1. OpenSanctions API (free, comprehensive — OFAC, EU, UN, Interpol, PEP lists)
2. Web search fallback: `"name" site:sanctionssearch.ofac.treas.gov`

**Config:**
```json
{
  "name": { "type": "string", "required": true },
  "dob": { "type": "string" },
  "nationality": { "type": "string" }
}
```

**Output:** `{ "name", "matched": true/false, "matches": [{ "list", "reason", "since", "confidence" }] }`

### 3.12 adverse_media

**Category:** enrich
**Purpose:** Systematic negative news monitoring across crime/fraud/corruption categories.

**Technique:**
1. Web search with category-specific queries: `"name" (fraud OR corruption OR lawsuit OR arrest OR scandal OR investigation)`
2. Google News search with date filtering
3. Categorize hits: financial_crime, regulatory, fraud, corruption, violence, other

**Config:**
```json
{
  "name": { "type": "string", "required": true },
  "categories": { "type": "array", "default": ["fraud", "corruption", "lawsuit", "arrest", "scandal", "investigation", "sanction"] }
}
```

**Output:** List of `{ "title", "url", "date", "category", "snippet", "source" }`

### 3.13 crypto_tracer [SENTINEL]

**Category:** enrich
**Purpose:** Blockchain wallet analysis.

**Technique chain:**
1. Etherscan API (Ethereum — free tier)
2. Blockchain.com API (Bitcoin — free)
3. Blockchair API (multi-chain — free tier)

**Config:**
```json
{
  "wallet_address": { "type": "string", "required": true },
  "chain": { "type": "string", "enum": ["ethereum", "bitcoin", "auto"], "default": "auto" }
}
```

**Output:** `{ "address", "chain", "balance", "tx_count", "first_seen", "last_seen", "top_counterparties": [...] }`

---

## Part 4: Intelligence Fusion Layer

### 4.1 Selector Extraction

Every pipeline node output is post-processed to extract selectors:

```python
@dataclass
class ExtractedSelector:
    type: str          # email, phone, username, domain, address, etc.
    value: str         # the actual identifier
    source_node: str   # which pipeline node produced this
    source_finding: str # which finding it was extracted from
    confidence: float  # 0-1 confidence this is a real selector
    entity_ref: str    # which entity this selector belongs to (if known)
```

**Extraction rules** (deterministic, not LLM):
- Email: regex `[\w.-]+@[\w.-]+\.\w+`
- Phone: regex for international formats + local formats
- Username: from profile URLs using platform-specific patterns
- Domain: from email domain-parts, website URLs
- Address: NER or structured field extraction

### 4.2 Entity Resolution

Multiple findings about the same real-world entity must be merged.

**Entity model:**
```python
@dataclass
class Entity:
    id: str                          # UUID
    type: str                        # person, company, etc.
    canonical_name: str              # best-known name
    selectors: list[ExtractedSelector]  # all known identifiers
    attributes: dict[str, list[AttributeValue]]  # name→values with provenance
    relationships: list[Relationship]  # edges to other entities
```

**Resolution algorithm:**
1. **Exact selector match:** Two findings sharing an identical email/phone/username → same entity
2. **Fuzzy name match + context:** "John Doe at Company X" and "J. Doe, CompanyX Inc." → likely same entity (confirm via shared selectors)
3. **Transitive linkage:** Finding A shares email with Finding B; Finding B shares phone with Finding C → A, B, C are same entity

**Deduplication rules:**
- Same selector type + same value → merge (high confidence)
- Same name + same employer → merge (moderate confidence, flag for review)
- Conflicting attributes on merged entity → keep both with provenance, mark as competing

### 4.3 Relationship Graph

Build an entity-relationship graph as findings accumulate:

```python
@dataclass
class Relationship:
    source_entity: str          # entity UUID
    target_entity: str          # entity UUID
    type: str                   # works_at, family_of, associates_with, owns, etc.
    confidence: str             # confirmed, suspected, possible
    evidence: list[str]         # finding IDs supporting this relationship
    first_seen: datetime
    last_seen: datetime
```

**Relationship types:**
- `works_at` / `worked_at` (person → company)
- `family_of` (person → person, with subtype: spouse, parent, child, sibling)
- `associates_with` (person → person)
- `owns` (person → company/property/domain)
- `registered_at` (person/company → address)
- `uses` (person → email/phone/username)

**Graph operations:**
- **N-hop traversal:** Given entity E, find all entities within N relationship hops
- **Path finding:** What connects Entity A to Entity B?
- **Cluster detection:** Which entities form tight clusters?

### 4.4 Storage

The relationship graph is stored in PostgreSQL (for durability and querying) with optional Qdrant indexing for semantic search:

```sql
CREATE TABLE entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL REFERENCES pipeline_runs(id),
    type            VARCHAR(50) NOT NULL,
    canonical_name  TEXT NOT NULL,
    selectors       JSONB NOT NULL DEFAULT '[]',
    attributes      JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE relationships (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL REFERENCES pipeline_runs(id),
    source_entity   UUID NOT NULL REFERENCES entities(id),
    target_entity   UUID NOT NULL REFERENCES entities(id),
    type            VARCHAR(50) NOT NULL,
    confidence      VARCHAR(20) NOT NULL DEFAULT 'possible',
    evidence        JSONB NOT NULL DEFAULT '[]',
    first_seen      TIMESTAMPTZ,
    last_seen       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_entities_run ON entities(run_id);
CREATE INDEX idx_entities_selectors ON entities USING GIN (selectors);
CREATE INDEX idx_relationships_source ON relationships(source_entity);
CREATE INDEX idx_relationships_target ON relationships(target_entity);
```

---

## Part 5: Intelligence Classification

### 5.1 Default Classification (Always On)

Every finding carries this metadata envelope:

```python
@dataclass
class IntelligenceMetadata:
    # NATO Admiralty System (two independent axes)
    source_reliability: str    # A-F (see table below)
    info_credibility: int      # 1-6 (see table below)

    # Unified confidence (STIX 2.1 scale, 0-100)
    confidence_score: int      # Maps to Admiralty, WEP, and DNI scales

    # Corroboration
    corroboration_level: str   # uncorroborated, corroborated, multi_source, conflicting
    corroborating_sources: list[str]  # finding IDs that confirm this

    # Timeliness
    collected_at: datetime     # when this data was collected
    data_as_of: datetime       # when the underlying data was current
    shelf_life: str            # perishable (days), semi_perishable (months), durable (years)
    decay_function: str        # exponential, linear, step

    # Deception risk
    deception_risk: float      # 0-1, composite score
    deception_flags: list[str] # specific indicators if any

    # Provenance
    source_node: str           # which pipeline node produced this
    source_url: str            # original data URL
    extraction_method: str     # api, scrape, search, inference
```

### 5.2 Source Reliability Ratings (Rule-Based Baseline)

| Source Type | Default Rating | Rationale |
|------------|---------------|-----------|
| Government registries (SEC, DTI, OpenCorporates) | A (Completely Reliable) | Official records, verified data |
| Major professional platforms (LinkedIn verified) | B (Usually Reliable) | Self-reported but platform-verified |
| Breach databases (HIBP) | B (Usually Reliable) | Data confirmed from actual breaches |
| Major social media (Facebook, Instagram) | C (Fairly Reliable) | Self-reported, can be fabricated |
| Web search results | C-D (Fairly to Not Usually Reliable) | Varies wildly by source |
| SMTP verification | B (Usually Reliable) | Technical verification, deterministic |
| Forum posts / comments | D (Not Usually Reliable) | Anonymous, unverified |
| Dark web / paste sites | D-E (Not Usually to Unreliable) | High deception risk |
| Generated / inferred | F (Cannot Be Judged) | No source to evaluate |

The IS brain can **override** the baseline when it has context (e.g., a government website returning a 404 should be downgraded).

### 5.3 Information Credibility Scoring (Hybrid: Rule + LLM)

**Rule-based component:**
- Single source, no corroboration → 3 (Possibly True) max
- Two independent sources agree → 2 (Probably True)
- Three+ independent sources agree → 1 (Confirmed)
- Sources actively conflict → 4 (Doubtful) or 5 (Improbable)

**LLM adjustment:** The IS brain can adjust ±1 based on contextual assessment (e.g., two sources agree but one is clearly copying the other → not truly independent → stay at 3).

### 5.4 Confidence Score Mapping (STIX 2.1)

| STIX Score | Admiralty Credibility | Words of Estimative Probability | IC Confidence |
|-----------|---------------------|---------------------------------|---------------|
| 0-14 | 6 - Cannot judge | Almost certainly not | Low |
| 15-39 | 5 - Improbable | Unlikely | Low |
| 40-59 | 4 - Doubtful | Even chance | Moderate |
| 60-79 | 3 - Possibly true | Likely | Moderate |
| 80-89 | 2 - Probably true | Very likely | High |
| 90-100 | 1 - Confirmed | Almost certain | High |

### 5.5 Perishability Model

| Data Type | Shelf Life | Decay Function | Example |
|-----------|-----------|----------------|---------|
| Current phone/email | 6 months | Exponential | People change numbers |
| Social media profile | 3 months | Linear | Profiles get updated |
| Employment status | 12 months | Step (cliff at ~18mo) | Jobs last ~2 years avg |
| Company registration | 5 years | Linear (slow) | Entities persist |
| Criminal records | 10+ years | None (durable) | Permanent record |
| Physical address | 12 months | Linear | People move |
| Breach data | Permanent | None (durable) | Historical fact |
| Sanctions/PEP status | 6 months | Exponential | Lists get updated |
| Financial data | 3 months | Exponential | Markets change fast |

**Current confidence calculation:**
```
current_confidence = base_confidence × decay_function(age / shelf_life)
```

### 5.6 Deception Detection (Automated Flags)

| Indicator | Detection Method | Risk Level |
|-----------|-----------------|------------|
| Profile too perfect | All fields filled, no inconsistencies, stock photo | Medium |
| Recent creation | Social media account < 6 months old | Low-Medium |
| Copied content | Same bio text across multiple platforms (exact match) | Medium |
| Metadata stripping | Photos with all EXIF removed (deliberate) | Low |
| Temporal anomaly | Claimed activity date impossible (before platform existed) | High |
| Source echo | Two "independent" sources share identical text | High |
| Contradiction | Conflicting facts from same source (internal inconsistency) | High |

---

## Part 6: Analysis Layer (Optional Modes)

### 6.1 Base Analysis (Always On)

The existing Analyzer node behavior enhanced with:
- Entity extraction → entity resolution
- Relationship mapping → graph building
- Gap identification against completeness checklist
- Synthesis with confidence metadata

### 6.2 ACH Mode (Toggleable)

When findings conflict, the system can invoke Analysis of Competing Hypotheses:

**Trigger:** Two or more findings for the same attribute of the same entity have conflicting values (e.g., two different employers listed as "current").

**Process:**
1. Identify competing hypotheses (H1: works at Company A, H2: works at Company B, H3: works at both)
2. List all evidence related to this question
3. Score each evidence item against each hypothesis: ++ (strongly supports), + (supports), 0 (neutral), - (contradicts), -- (strongly contradicts)
4. Select hypothesis with LEAST disconfirming evidence (not most confirming — this counters confirmation bias)
5. Output: winning hypothesis with diagnostic evidence highlighted

**Implementation:** Add `analysis_mode` config to Analyzer node with `ach: true` option. The ACH matrix is constructed by the LLM and included in the output.

### 6.3 PIR Mode (Toggleable)

Decompose the investigation into structured intelligence requirements:

**Trigger:** User enables `pir_mode: true` in Analyzer config, or investigation is flagged as "due diligence" or "risk assessment."

**Process:**
1. Decompose query into PIRs (Priority Intelligence Requirements):
   - PIR 1: "Is this person who they claim to be?" (Identity verification)
   - PIR 2: "What are their business interests?" (Professional/financial)
   - PIR 3: "Do they pose any risk?" (Adverse media, sanctions, legal)
2. Each PIR decomposes into SIRs (Specific Intelligence Requirements)
3. Each SIR decomposes into EEIs (Essential Elements of Information)
4. Map findings to EEIs → SIRs → PIRs
5. Report: "PIR 1 answered with HIGH confidence (8/10 EEIs resolved). PIR 3 has GAPS (sanctions checked, court records unavailable)."

---

## Part 7: Self-Learning Strategy Evolution

### 7.1 Architecture: Seed + Learned Overlays

```
SEED STRATEGY (static file)          ← Initial baseline, version-controlled
  app/pipeline/strategies/person.py
         +
STRATEGY OVERLAYS (database)         ← Learned modifications from experience
  investigation_strategy_overlays
         =
COMPILED STRATEGY (runtime)          ← Merged for IS brain prompt injection
```

### 7.2 The Learning Loop

After every research run completes:

**Step 1: Run Analysis** (`analyze_run_pivots()`)
- Map each tool call to its pivot pattern
- Calculate per-pivot yield: `new_selectors_extracted / tool_calls_used`
- Calculate per-pivot intel value: `user_feedback_score × uniqueness × completeness_impact`
- Identify tool calls that produced zero findings

**Step 2: Signal Classification**
- **Reinforce:** Pivot pattern produced high yield OR high intel value in N+ runs
- **Prune:** Pivot pattern produced zero yield AND zero intel value in N+ consecutive runs
- **Discover:** A pivot sequence not in seed strategy produced significant results
- **Upgrade:** A new technique consistently outperforms existing one for same pivot

**Step 3: Tactic Classification (4-Quadrant Model)**

```
                │ High Intel Value (when hit)
                │
  SENTINEL      │  HIGH PRIORITY
  (always run)  │  (always run, boost)
                │
────────────────┼────────────────
                │
  PRUNE         │  SITUATIONAL
  (remove)      │  (budget permitting)
                │
                │ Low Intel Value (when hit)

  Low Yield ────────────── High Yield
```

**Sentinel detection:**
```
IF yield_rate < 0.2 AND (
    any_hit_positive_feedback OR
    any_hit_filled_empty_domain OR
    any_hit_triggered_cross_reference
):
    category = "sentinel"
```

### 7.3 Overlay Database

```sql
CREATE TABLE investigation_strategy_overlays (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     VARCHAR(50) NOT NULL,
    selector_type   VARCHAR(50) NOT NULL,       -- email, phone, username, etc.
    pivot_pattern   VARCHAR(200) NOT NULL,       -- e.g., "email → hibp_lookup"
    overlay_type    VARCHAR(20) NOT NULL,        -- reinforce, prune, discover, upgrade
    content         TEXT,                        -- description for discovered pivots
    technique_ref   VARCHAR(100),               -- tool name for upgrades
    yield_rate      FLOAT DEFAULT 0.0,
    intel_value     FLOAT DEFAULT 0.5,
    category        VARCHAR(20) DEFAULT 'situational',
    confidence      FLOAT DEFAULT 0.0,
    run_count       INT DEFAULT 0,
    pinned          BOOLEAN DEFAULT FALSE,       -- human override
    last_validated  TIMESTAMPTZ DEFAULT now(),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_overlays_entity ON investigation_strategy_overlays(entity_type);
CREATE INDEX idx_overlays_category ON investigation_strategy_overlays(category);
```

### 7.4 Guardrails

- **Minimum run count:** Overlays require N >= 3 runs before activating
- **Confidence decay:** Overlays not validated in 30 days get confidence reduced 10%/week
- **Human override:** User can pin (prevent pruning) or force-prune (override reinforcement)
- **Seed immutability:** Seed strategy files are never auto-modified — only overlays change

---

## Part 8: Person Entity Strategy (Seed)

This is the seed strategy file injected into the IS brain prompt.

```
=== PERSON INVESTIGATION STRATEGY ===

You are conducting a comprehensive investigation of a person using a
SELECTOR-CENTRIC approach. Your goal is to discover all identifiers
(selectors) associated with this person and build a complete profile
by following every selector to its investigative endpoints.

## EXECUTION MODEL

1. Start with SEED SELECTORS (name, and any provided email/phone/etc.)
2. For each selector, run the PIVOT PATTERNS below to extract NEW selectors
3. Feed new selectors back into the loop (up to configured hop depth)
4. After the selector graph is exhausted, check the COMPLETENESS CHECKLIST
5. Rate every finding using the classification metadata

## PRIORITY SELECTORS (Person)

Discover and pursue these selector types in priority order:
1. full_name (always known — seed)
2. email (highest pivot value — connects to breach, social, messaging)
3. phone (high pivot value — connects to messaging, reverse lookup)
4. username (high pivot value — cross-platform identity)
5. employer/domain (medium — professional network, colleagues)
6. address (medium — property, neighbors, co-residents)
7. photo (medium — facial recognition cross-reference)
8. crypto_wallet (sentinel — low frequency, high value when found)
9. national_id (sentinel — rarely discoverable, critical when found)
10. vehicle_id (sentinel — rarely discoverable, critical when found)

## PIVOT PATTERNS

Note: The strategy compiler (strategies/compiler.py) injects the full pivot
pattern tables from Part 2 of this spec here at runtime. The tables are not
hardcoded in the seed file — they are assembled from the seed + learned
overlays. See Part 2 for the complete pivot pattern definitions.

## INVESTIGATION PRINCIPLES

- EXHAUSTIVE: Don't stop at first results. Follow every lead.
- CROSS-REFERENCING: A finding in one domain should trigger searches in others.
  Found an employer? Search for their email at that domain. Found an email?
  Check it against breach databases. Found a username? Search it everywhere.
- CORROBORATION: Every claim should ideally be confirmed from 2+ sources.
  Mark single-source findings accordingly.
- FAMILY EXPANSION: When you discover a family member, investigate them
  one level deep (name, basic digital footprint, relationship confirmation).
- SENTINEL AWARENESS: Always run low-yield/high-value checks (sanctions,
  court records, breach databases) even if they usually return nothing.
- DECEPTION AWARENESS: Be skeptical of too-perfect profiles, recently
  created accounts, and information that confirms a narrative too neatly.

## COMPLETENESS CHECKLIST

Before finishing, verify you've attempted coverage of:
□ Identity (full name, aliases, DOB, nationality, location)
□ Digital footprint (emails, phones, usernames, social accounts)
□ Family & social network (immediate family, key associates)
□ Professional history (employment timeline, education)
□ Financial & assets (business ownership, property)
□ Public records (court, regulatory, sanctions) [SENTINEL]
□ Visual intelligence (photos, geolocation)
□ Communication intel (messaging platform presence)
□ Dark web & breach intel (breach exposure, paste sites) [SENTINEL]
□ Online communities (forums, Reddit, Discord, Telegram)

Mark any uncovered domain as a gap in your final report.
```

---

## Part 9: Research Findings — Intelligence Frameworks Reference

This section documents the intelligence classification frameworks researched during design. These inform the classification layer and optional analysis modes.

### 9.1 NATO Admiralty System

Two independent axes:

**Source Reliability (A-F):**
- A: Completely Reliable — no doubt of authenticity, history of complete reliability
- B: Usually Reliable — valid information most of the time
- C: Fairly Reliable — has provided valid information in the past
- D: Not Usually Reliable — significant doubt
- E: Unreliable — history of invalid information
- F: Cannot Be Judged — no basis for evaluation

**Information Credibility (1-6):**
- 1: Confirmed by independent sources
- 2: Probably True — not confirmed but logical and consistent
- 3: Possibly True — not confirmed, reasonably logical
- 4: Doubtful — not confirmed, possible but not logical
- 5: Improbable — contradicts other information
- 6: Cannot Be Judged — no basis for evaluation

Key insight: These axes are INDEPENDENT. A reliable source (A) can report unconfirmed information (3). A new source (F) can provide confirmed facts (1).

### 9.2 Words of Estimative Probability (Sherman Kent / CIA)

| Term | Probability Range |
|------|-------------------|
| Almost Certain | ~93% (±6%) |
| Probable / Likely | ~75% (±12%) |
| Chances About Even | ~50% (±10%) |
| Probably Not / Unlikely | ~30% (±10%) |
| Almost Certainly Not | ~7% (±5%) |

### 9.3 STIX 2.1 Confidence Scale (0-100)

Bridges all major frameworks into a single integer. See Section 5.4 for mapping table.

### 9.4 Analysis of Competing Hypotheses (ACH)

CIA's flagship technique for resolving conflicting evidence:
1. List all plausible hypotheses
2. List all significant evidence
3. Score evidence against each hypothesis (++, +, 0, -, --)
4. Eliminate hypotheses with MOST disconfirming evidence
5. Winner = hypothesis with LEAST negative evidence (counters confirmation bias)

### 9.5 Intelligence Requirements Hierarchy

IR → PIR → SIR → EEI → Collection Plan → Tasking

### 9.6 Information Quality Dimensions (Wang & Strong 1996)

Core dimensions: Accuracy, Completeness, Consistency, Timeliness, Believability, Relevance.

### 9.7 Evidence Grading (Medical/Legal Analogs)

- GRADE framework: High → Moderate → Low → Very Low certainty
- Legal standards: Reasonable suspicion (~42%) → Probable cause (~50%) → Preponderance (~54%) → Clear and convincing (~73%) → Beyond reasonable doubt (~90%)

### 9.8 Counter-Intelligence / Deception Categories

- Disinformation: Deliberately false
- Misinformation: Inaccurate, shared without malice
- Malinformation: True but shared to cause harm
- Manipulated: Originally true, altered
- Fabricated: Entirely invented

### 9.9 NSA Architecture Patterns (from leaked documents)

Key patterns applicable to OSINT fusion:
1. **Selector-centric pivoting** — everything revolves around identifiers
2. **Staged pipeline** — collection → routing → separation → filtering → storage → indexing → query
3. **Entity resolution** (TIDE pattern) — nominations → merge → unified profiles → export
4. **Precomputed relationship graph** (MAINWAY pattern) — build adjacency index at ingest, query at analysis
5. **Federated search** (ICREACH pattern) — unified query across source-specific stores
6. **Plugin-based extraction** (XKeyscore pattern) — DSL for extraction rules + heavyweight plugins for complex cases
7. **Microservices decomposition** (TURBULENCE vs. Trailblazer) — small composable pieces beat monoliths

### 9.10 OSINT-Specific Gap Analysis

Sources researched: OSINT Framework, Bellingcat Toolkit, Michael Bazzell (IntelTechniques, 11th edition), Trace Labs CTF methodology, SANS SEC487/SEC587, SCIP competitive intelligence, KYC/AML/EDD frameworks.

High-priority gaps identified and incorporated:
- Username enumeration (cross-platform pivot)
- Image/facial recognition search
- Document OSINT (Google Dorking + metadata)
- Communication metadata (messaging platforms, phone OSINT)
- Geolocation (EXIF + chronolocation)
- Dark web / paste sites / stealer logs (3 distinct channels)
- PEP/Sanctions/Watchlist screening
- Adverse media screening
- Cryptocurrency/blockchain tracing

---

## Part 10: New Files Summary

| File | Purpose |
|------|---------|
| `app/pipeline/strategies/__init__.py` | Strategy loader + compiler |
| `app/pipeline/strategies/person.py` | Person entity seed strategy |
| `app/pipeline/strategies/compiler.py` | Merges seed + overlays → compiled strategy |
| `app/pipeline/strategies/analyzer.py` | Post-run pivot analysis → signal generation |
| `app/pipeline/fusion/__init__.py` | Intelligence Fusion Layer entry |
| `app/pipeline/fusion/selectors.py` | Selector extraction from findings |
| `app/pipeline/fusion/entities.py` | Entity resolution + merging |
| `app/pipeline/fusion/graph.py` | Relationship graph building + traversal |
| `app/pipeline/fusion/classification.py` | Admiralty scoring, corroboration, decay |
| `app/pipeline/nodes/smtp_verifier.py` | SMTP RCPT TO email verification |
| `app/pipeline/nodes/email_enumerator.py` | Name-based email generation + verification |
| `app/pipeline/nodes/hibp_lookup.py` | HaveIBeenPwned + Dehashed breach lookup |
| `app/pipeline/nodes/reverse_lookup.py` | Email/phone/username reverse identity lookup |
| `app/pipeline/nodes/username_enumerator.py` | Cross-platform username search |
| `app/pipeline/nodes/face_search.py` | Reverse facial recognition |
| `app/pipeline/nodes/exif_extractor.py` | Image/document metadata extraction |
| `app/pipeline/nodes/document_search.py` | Google Dorking + metadata extraction |
| `app/pipeline/nodes/phone_osint.py` | Phone number reconnaissance |
| `app/pipeline/nodes/messaging_check.py` | Messaging platform presence check |
| `app/pipeline/nodes/pep_sanctions_screen.py` | PEP/Sanctions/Watchlist screening |
| `app/pipeline/nodes/adverse_media.py` | Systematic negative news monitoring |
| `app/pipeline/nodes/crypto_tracer.py` | Blockchain wallet analysis |

### Modified Files

| File | Change |
|------|--------|
| `app/is_prompt.py` | Add `{entity_strategy}` placeholder |
| `app/pipeline/nodes/intelligent_search.py` | Load compiled strategy, extract selectors from results |
| `app/pipeline/nodes/analyzer.py` | Add ACH and PIR optional modes |
| `app/routers/v3/research_api.py` | Add post-run pivot analysis hook |
| Schema migration | Add `entities`, `relationships`, `investigation_strategy_overlays` tables |

### Database Tables

| Table | Purpose |
|-------|---------|
| `entities` | Resolved entity profiles with selectors and attributes |
| `relationships` | Entity-to-entity edges with evidence |
| `investigation_strategy_overlays` | Learned strategy modifications |

---

## Part 11: Implementation Phases

### Entity Type Extensibility

This spec focuses on Person entity type. The architecture is extensible to other entity types (Company, Product, Location, Event) by:
1. Creating new seed strategy files (e.g., `strategies/company.py`)
2. Defining entity-specific selector types (e.g., Company: `domain`, `ticker_symbol`, `registration_number`)
3. Defining entity-specific pivot patterns
4. Entity-specific completeness checklists

The fusion layer, classification, and learning loop are entity-type-agnostic.

### Phase 1: Collection Enhancement
- New pipeline nodes (13 nodes)
- Seed person strategy file
- Strategy injection into IS brain prompt
- Integration with procedural memory (existing SUGGESTED STRATEGIES)

### Phase 2: Intelligence Fusion Layer
- Selector extraction from findings
- Entity resolution and merging
- Relationship graph building and storage
- Classification metadata envelope (Admiralty + STIX + corroboration + decay)

### Phase 3: Analysis Enhancement
- Completeness assessment against domain checklist
- ACH mode for conflicting evidence
- PIR decomposition mode
- Deception detection scoring

### Phase 4: Self-Learning Loop
- Post-run pivot analysis
- Strategy overlay system (reinforce/prune/discover/upgrade)
- 4-quadrant tactic classification (high priority / sentinel / situational / prune)
- Confidence decay and human override
