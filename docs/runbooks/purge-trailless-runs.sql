-- Purge pipeline_runs that have no research_trails row.
--
-- Context: the Path B / IS-loop substrate (default since 6d02595) marked
-- runs succeeded via post_process without writing a trail. The UI's Results
-- panel calls /v3/runs/{id}/replay, which reads research_trails, so these
-- runs always render empty.
--
-- The forward fix is in app/temporal/activities/post_process.py (adds the
-- INSERT). This script removes the orphans created before that fix.
--
-- USAGE (preview first):
--   psql $DATABASE_URL -f docs/runbooks/purge-trailless-runs.sql
--
-- The script wraps everything in a transaction and ends with ROLLBACK by
-- default. Change the final ROLLBACK to COMMIT once you've reviewed the
-- preview output.

BEGIN;

-- 1. Preview what will be deleted ------------------------------------------
\echo '=== Runs without research_trails (purge candidates) ==='

SELECT pr.id,
       pr.status,
       pr.user_id,
       pr.started_at,
       left(coalesce(pr.query, ''), 60) AS query_preview
  FROM pipeline_runs pr
  LEFT JOIN research_trails rt ON rt.run_id = pr.id
 WHERE rt.id IS NULL
 ORDER BY pr.started_at DESC;

\echo ''
\echo '=== Dependent rows that will cascade or be detached ==='

SELECT 'pipeline_step_runs'     AS table, count(*) FROM pipeline_step_runs WHERE run_id IN (
    SELECT pr.id FROM pipeline_runs pr LEFT JOIN research_trails rt ON rt.run_id = pr.id WHERE rt.id IS NULL
) UNION ALL
SELECT 'run_share_links',      count(*) FROM run_share_links WHERE run_id IN (
    SELECT pr.id FROM pipeline_runs pr LEFT JOIN research_trails rt ON rt.run_id = pr.id WHERE rt.id IS NULL
) UNION ALL
SELECT 'webhook_deliveries',   count(*) FROM webhook_deliveries WHERE run_id IN (
    SELECT pr.id FROM pipeline_runs pr LEFT JOIN research_trails rt ON rt.run_id = pr.id WHERE rt.id IS NULL
) UNION ALL
SELECT 'budget_ledger_entries (SET NULL)', count(*) FROM budget_ledger_entries WHERE run_id IN (
    SELECT pr.id FROM pipeline_runs pr LEFT JOIN research_trails rt ON rt.run_id = pr.id WHERE rt.id IS NULL
) UNION ALL
SELECT 'research_skills (SET NULL manual)', count(*) FROM research_skills WHERE run_id IN (
    SELECT pr.id FROM pipeline_runs pr LEFT JOIN research_trails rt ON rt.run_id = pr.id WHERE rt.id IS NULL
);

-- 2. Detach FK rows that don't have ON DELETE CASCADE / SET NULL -----------
UPDATE research_skills
   SET run_id = NULL
 WHERE run_id IN (
    SELECT pr.id FROM pipeline_runs pr
    LEFT JOIN research_trails rt ON rt.run_id = pr.id
    WHERE rt.id IS NULL
);

-- 3. Delete the trailless runs ---------------------------------------------
WITH deleted AS (
    DELETE FROM pipeline_runs pr
    USING (
        SELECT pr2.id
          FROM pipeline_runs pr2
     LEFT JOIN research_trails rt ON rt.run_id = pr2.id
         WHERE rt.id IS NULL
    ) t
    WHERE pr.id = t.id
    RETURNING pr.id
)
SELECT count(*) AS rows_deleted FROM deleted;

-- 4. End: ROLLBACK by default; change to COMMIT to apply -------------------
ROLLBACK;
-- COMMIT;
