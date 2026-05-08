"""Historical archival research retrieval sub-strategy module."""

CATEGORY = "retrieval"
NAME = "historical_archival"
DISPLAY_NAME = "Historical & Archival Research"
DESCRIPTION = (
    "Recovers and contextualizes historical facts from primary archival sources, "
    "digitized collections, and contemporaneous records. Applies historical-critical "
    "method to evaluate source authenticity, provenance, and bias."
)
SELECTORS = [
    "historical_event",
    "time_period",
    "historical_figure",
    "archive_collection",
    "primary_source",
    "geographic_region",
    "historical_context",
]

STRATEGY = """
=== HISTORICAL & ARCHIVAL RESEARCH STRATEGY ===

This strategy guides the recovery and contextualization of historical facts from
primary sources, digitized archives, and contemporaneous records. It applies the
historical-critical method: evaluate source provenance, authenticity, and bias
before accepting any account. Secondary and tertiary sources are used for context
but never as substitutes for primary evidence. Validate coverage using the
completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step historical archival research process:

1. TEMPORAL AND GEOGRAPHIC SCOPING — Establish the research frame:
   - Time period: define start and end dates; note periodization conventions
   - Geographic scope: country, region, locality; note historical boundary changes
   - Subject scope: event, figure, institution, or social phenomenon
   - Research question: what specific historical question is being answered?
   Historical administrative boundaries often differ from modern ones;
   research the appropriate historical jurisdiction for records.

2. SECONDARY SOURCE ORIENTATION — Use secondary sources to map the historical landscape:
   - Survey academic histories, reference works, and encyclopedias for factual baseline
   - Identify the major interpretive schools and historiographical debates
   - Note which primary sources established historians rely on
   - Extract citations to primary sources for Step 3 follow-up
   Secondary sources reveal what is known and contested — they do not replace primary evidence.

3. PRIMARY SOURCE IDENTIFICATION & LOCATION — Find the original records:
   - Digitized archives: HathiTrust, Internet Archive, Google Books, Chronicling America
   - Government archives: NARA (US), National Archives (UK), Bundesarchiv (Germany)
   - University special collections and manuscript libraries
   - Newspaper archives: ProQuest Historical Newspapers, Newspapers.com, BNF Gallica
   - Contemporaneous publications: pamphlets, government reports, personal correspondence
   For each primary source, document: repository, collection name, box/folder/item,
   date, author/creator, and any known publication or digitization status.

4. SOURCE CRITICISM (HISTORICAL-CRITICAL METHOD) — Evaluate every source:
   - External criticism: Is the source authentic? Has it been altered or forged?
     Check handwriting, paper, ink, typography for period consistency.
   - Internal criticism: Is the author credible? Were they an eyewitness?
     What was their position, motivation, and potential bias?
   - Corroboration: Does the account align with other contemporaneous sources?
     Isolated accounts require higher scrutiny.
   - Provenance: Has custody of the document been documented (chain of custody)?
   Apply these checks before drawing historical conclusions.

5. CONTEXTUAL SYNTHESIS — Place findings in historical context:
   - Situate events within broader political, economic, social, and cultural forces
   - Account for what contemporaries knew vs. what is known with hindsight
   - Distinguish between what sources say happened and what historians interpret happened
   - Identify historiographical consensus and ongoing scholarly debates
   - Flag anachronistic interpretations (applying modern frameworks to historical actors)

--- PRIORITY SELECTORS (Historical & Archival Research) ---

Ordered by research leverage (highest first):

1. historical_event    — anchor event; scopes all other research
2. time_period         — temporal frame; determines which archives and records are relevant
3. primary_source      — specific document or collection; highest evidentiary value
4. historical_figure   — person-based anchor; enables biographical and associational research
5. geographic_region   — locality anchor; points to jurisdiction-specific archives
6. archive_collection  — named collection; enables targeted repository requests
7. historical_context  — interpretive frame for situating findings

--- KEY PIVOT PATTERNS ---

historical_event + time_period:
  - Chronicling America (loc.gov/collections/chronicling-america) for US newspaper archives
  - Internet Archive (archive.org/texts) for digitized historical texts
  - HathiTrust (hathitrust.org) for digitized books and periodicals
  - ddg_search "[event] primary source" OR "[event] archive" OR "[event] documents"
  - Wikipedia "References" and "Further reading" sections — follow citations to primary sources

historical_figure:
  - Biography databases: Oxford Dictionary of National Biography, American National Biography
  - Finding aids: ArchiveGrid (archivegrid.org) for manuscript collections
  - Google Scholar for biographical studies and document editions
  - Presidential libraries (US) for government official papers
  - ddg_search "[figure name] papers collection" OR "[figure] archive finding aid"

primary_source (newspaper):
  - Chronicling America (free, 1770–1963 US newspapers)
  - ProQuest Historical Newspapers (subscription; major US papers)
  - BNF Gallica (gallica.bnf.fr) for French-language historical newspapers
  - Newspapers.com and GenealogyBank for US and international archives

primary_source (government records):
  - NARA (archives.gov) for US federal records; catalog.archives.gov for online search
  - National Archives UK (nationalarchives.gov.uk) for British government records
  - Fold3 (fold3.com) for US military and pension records
  - Digital Public Library of America (dp.la) for aggregated US digital collections

archive_collection:
  - ArchiveGrid (archivegrid.org) for finding aids across 1000+ repositories
  - Repository website direct search for named collections
  - WorldCat for library holdings of primary source editions
  - web_search_fetch [archive name] finding aid [collection name]

--- COMPLETENESS CHECKLIST ---

Before closing a historical archival research task, confirm coverage in each area:

1. Scope Definition    — time period, geography, and research question precisely defined
2. Secondary Survey    — historiographical landscape mapped; major interpretations noted
3. Primary Sources     — at least one contemporaneous primary source located per key claim
4. Source Criticism    — authenticity, bias, and corroboration evaluated for each source
5. Contextual Frame    — findings situated within appropriate historical context
6. Gaps Documented     — unavailable or unlocated sources noted; gaps acknowledged

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
