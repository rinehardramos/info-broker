"""Genealogical research retrieval sub-strategy module."""

CATEGORY = "retrieval"
NAME = "genealogical"
DISPLAY_NAME = "Genealogical Research"
DESCRIPTION = (
    "Traces family lineages using vital records, census data, immigration records, "
    "and DNA evidence. Source citation is mandatory for every genealogical fact. "
    "Conflicting records are documented and evaluated rather than resolved arbitrarily."
)
SELECTORS = [
    "ancestor_name",
    "birth_date",
    "birth_place",
    "death_date",
    "marriage_record",
    "immigration_record",
    "census_entry",
]

STRATEGY = """
=== GENEALOGICAL RESEARCH STRATEGY ===

This strategy guides family lineage research using vital records, census data,
immigration records, and DNA evidence. Every genealogical assertion requires a
source citation. Conflicting records are documented and evaluated, not arbitrarily
resolved. Research progresses from the known to the unknown — starting with the
subject and working backward. Validate coverage using the completeness checklist
before concluding.

--- EXECUTION MODEL ---

A 5-step genealogical research process:

1. KNOWN-TO-UNKNOWN PROGRESSION — Begin with fully documented living or recent
   individuals and trace backward:
   - Start: subject's birth certificate, vital records, and personal knowledge
   - Step back one generation at a time; do not skip generations
   - Each generation requires corroborated vital events (birth, marriage, death)
   - Document the research trail: what was searched, when, and what was found

2. VITAL RECORDS SEARCH — For each ancestor, locate:
   - Birth record (certificate, church baptismal register, civil registration)
   - Marriage record (certificate, church register, announcements)
   - Death record (certificate, church burial register, obituary, gravestone)
   - Cross-reference: a birth record names parents; a marriage record names both families
   Note name spelling variants — surnames were frequently anglicized or misspelled.

3. CENSUS & POPULATION RECORDS — Census records reveal household composition
   and provide corroborating data:
   - Ages and birth years (note: self-reported ages vary across census years)
   - Birthplace: country, state, or county of birth
   - Household members: parents, siblings, boarders, servants
   - Occupation, property value, and immigration year
   US: 1790–1940 census (Ancestry, FamilySearch); cross-reference across decades.

4. IMMIGRATION & NATURALIZATION — For immigrant ancestors:
   - Passenger manifests: name, age, occupation, last residence, US contact
   - Naturalization papers: declaration of intent, petition, certificate
   - Ellis Island, Castle Garden, and other port records
   - Home country records: parish registers, military conscription, passports
   Note: pre-1906 naturalization may exist in any US court, not just federal.

5. DNA EVIDENCE INTEGRATION — Use DNA results to break through brick walls:
   - Autosomal DNA (AncestryDNA, 23andMe, MyHeritage): confirms close relationships;
     useful up to ~4th cousins
   - Y-DNA (FTDNA): traces direct paternal line; useful for surname research
   - mtDNA (FTDNA): traces direct maternal line
   - Compare matches to known family; triangulate shared segments to common ancestors
   - DNA does not replace documentary evidence; it corroborates and redirects research

--- PRIORITY SELECTORS (Genealogical Research) ---

Ordered by research leverage (highest first):

1. ancestor_name      — primary anchor; note all spelling variants
2. birth_date + birth_place — combined anchor; distinguishes same-name individuals
3. marriage_record    — connects two family lines; reveals maiden names
4. census_entry       — household snapshot with ages, birthplaces, and family members
5. immigration_record — critical for immigrant ancestors; links to origin country
6. death_date         — death records and obituaries often list surviving family
7. birth_place        — geographic anchor for civil and church record searches

--- KEY PIVOT PATTERNS ---

ancestor_name + birth_place:
  - FamilySearch (familysearch.org) — free; largest genealogical database
  - Ancestry (ancestry.com) — census, vital records, immigration, military records
  - FindMyPast — strong UK, Ireland, and Australian records
  - MyHeritage — strong European records; DNA database
  - ddg_search "[ancestor full name] [birth year] [birthplace] genealogy"

birth_place (locality research):
  - Identify which county/parish/district the location fell in historically
  - Local historical societies and genealogical societies for unpublished records
  - Church records for baptisms, marriages, and burials (pre-civil registration)
  - web_search_fetch local GenWeb pages for locality-specific research guides

immigration_record:
  - Ellis Island database (libertyellisfoundation.org) for 1892–1957 arrivals
  - Ancestry passenger lists for arrivals to all US ports
  - Statue of Liberty–Ellis Island Foundation for restored manifests
  - FamilySearch immigration records collection (free)
  - ddg_search "[ancestor name] [approximate arrival year] passenger list"

census_entry:
  - US Federal Census: FamilySearch (free 1940+) and Ancestry for all years
  - State censuses: many states conducted separate censuses between federal years
  - Note age discrepancies across census years; calculate birth year range
  - Head-of-household transcription errors: search by first name + birthplace if
    surname search fails

marriage_record:
  - County courthouse for civil marriage licenses and certificates
  - Church register transcriptions on FamilySearch and Ancestry
  - Newspaper announcement archives: Newspapers.com, Chronicling America (LOC)
  - ddg_search "[name] married [name] [location] [approximate year] newspaper"

--- COMPLETENESS CHECKLIST ---

Before closing a genealogical research task, confirm coverage in each area:

1. Vital Records       — birth, marriage, and death records located for each generation;
                         all sources cited; conflicting records documented
2. Census Coverage     — subject appears in census records across available decades;
                         household members identified and cross-referenced
3. Immigration         — for immigrant ancestors: arrival record and naturalization
                         located; origin country and locality identified
4. Church Records      — parish records consulted for pre-civil registration periods
5. DNA Corroboration   — DNA evidence assessed where available; matches cross-referenced
6. Brick Walls         — unresolved research problems documented with attempted strategies

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
