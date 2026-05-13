"""Academic researcher investigation strategy module."""

ENTITY_TYPE = "researcher"

STRATEGY = """
=== ACADEMIC RESEARCH STRATEGY ===

goal: Complete scholarly identity — publication record, institutional affiliations, research network (co-authors/advisors/students), citation impact.
execution_model: seed → anchor(canonical_identity) → expand(publications+co_authors+cited_by) → gap_fill

PRIORITY SELECTORS: full_name | employer | domain | orcid_id | scholar_id | openalex_id

pivots:
full_name → Google_Scholar(site:scholar.google.com "[name]" "[institution]") | run_openalex_search(name+institution) | run_semantic_scholar(author+papers)
orcid_id → direct_ORCID_API(employment+education+works) | OpenAlex_cross_reference
employer → faculty_page_scrape(run_multi_search: site:[institution] "[name]") | lab_affiliation
publications(DOI) → CrossRef_API | Unpaywall(OA_PDF)

tools: run_openalex_search | run_semantic_scholar | run_multi_search | run_web_crawl

principles: DISAMBIGUATION-FIRST(common_names→institution+field) | CITATION-GRAPH-DEPTH(1_level_deep_top_10) | INSTITUTIONAL-CORROBORATION(2_sources) | CO-AUTHOR-NETWORK(top_10_cited_works)

COMPLETENESS CHECKLIST: identity(name+variants+ORCID) | publications(complete_works+venues+DOIs) | affiliations(current+past) | research_network(co-authors+institutions)
"""
