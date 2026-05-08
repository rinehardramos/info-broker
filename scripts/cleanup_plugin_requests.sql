-- Plugin Request Cleanup Script
-- Date: 2026-05-07
-- Based on analysis: 118 total, 40 to reject, 15 to approve, rest stay pending

BEGIN;

-- ============================================================
-- REJECT: Search engine duplicates (DDG/Bing overlap or low value)
-- ============================================================
UPDATE plugin_requests SET status = 'rejected', reviewed_at = now()
WHERE status = 'pending' AND spec->>'name' IN (
    'bing_search',
    'ecosia_search',
    'qwant_search',
    'mojeek_search',
    'startpage_search',
    'seznam_search',
    'brightdata_serp',
    'dataforseo_serp',
    'serpapi_search',
    'perplexity_search',
    'kagi_search',
    'jina_search',
    'firecrawl_search',
    'you_com_search',
    'phind_search'
);

-- REJECT: No API / paywalled / scraping-only
UPDATE plugin_requests SET status = 'rejected', reviewed_at = now()
WHERE status = 'pending' AND spec->>'name' IN (
    'pitchbook-private-financials',
    'synergy-research-cloud-share',
    'tracxn-api',
    'rotten-tomatoes-fetcher',
    'rotten-tomatoes-scraper',
    'justwatch-availability',
    'netflix-catalog-lookup',
    'netflix-catalog-api',
    'netflix-tudum-fetcher',
    'netflix-top10-tracker',
    'tiktok-search',
    'memory_system_local_bench',
    'imdb-fetcher',
    'imdb-title-detail'
);

-- REJECT: Duplicate of existing nodes
UPDATE plugin_requests SET status = 'rejected', reviewed_at = now()
WHERE status = 'pending' AND spec->>'name' IN (
    'apollo-email-finder'
);

-- REJECT: Too niche / speculative
UPDATE plugin_requests SET status = 'rejected', reviewed_at = now()
WHERE status = 'pending' AND spec->>'name' IN (
    'naver_search',
    'ph-business-intent-signals',
    'philsme-exhibitor-scraper',
    'parlon-classpass-pricing'
);

-- ============================================================
-- APPROVE: High-value plugins with clear APIs
-- ============================================================
UPDATE plugin_requests SET status = 'approved', reviewed_at = now()
WHERE status = 'pending' AND spec->>'name' IN (
    'serper_search',
    'github_search',
    'google-maps-places',
    'openalex_search',
    'semantic_scholar_search',
    'tmdb-lookup',
    'tmdb-search',
    'tmdb-tv-lookup',
    'exa_search',
    'tavily_search',
    'mcp_registry_search',
    'ph-fda-lto-registry',
    'ph_fda_lto_registry',
    'fda-ph-verification-scraper'
);

-- ============================================================
-- MERGE DUPLICATES: Keep newest, reject older for same name
-- ============================================================
-- For each duplicate name group, keep the row with the longest description
-- and reject the others
WITH ranked AS (
    SELECT id,
           spec->>'name' as name,
           ROW_NUMBER() OVER (
               PARTITION BY spec->>'name'
               ORDER BY LENGTH(spec->>'description') DESC, created_at DESC
           ) as rn
    FROM plugin_requests
    WHERE status IN ('pending', 'approved')
)
UPDATE plugin_requests
SET status = 'rejected', reviewed_at = now()
WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

-- ============================================================
-- Summary
-- ============================================================
-- SELECT status, count(*) FROM plugin_requests GROUP BY status ORDER BY count DESC;

COMMIT;
