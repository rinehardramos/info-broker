# Operations

Day-2 operations for an already-deployed Auto Marketer pipeline.

## Running the pipeline

The three long-running commands are idempotent and safe to run repeatedly:

```sh
uv run python ingest.py
uv run python research_agent.py --run
uv run python generate_emails.py --format csv --output targeted_campaign
```

`ingest.py` uses `INSERT ... ON CONFLICT (id) DO NOTHING`, so replaying it over the same Apify dataset will not duplicate profiles. `research_agent.py --run` selects up to 5 `research_status = 'pending'` rows per invocation, so to drain a large backlog loop it:

```sh
while uv run python research_agent.py --run | tee /tmp/run.log; do
    grep -q "No pending profiles" /tmp/run.log && break
done
```

## Scheduling

The scripts are plain CLIs with no daemon component. Drive them with `cron`, `launchd`, or `systemd-timers`:

```cron
# crontab -e
# Pull new profiles every hour
0  *  *  *  *  cd /srv/auto-marketer && /usr/local/bin/uv run python ingest.py >> logs/ingest.log 2>&1
# Research a batch every 15 minutes
*/15 * * * *   cd /srv/auto-marketer && /usr/local/bin/uv run python research_agent.py --run >> logs/research.log 2>&1
```

## Batch sizes and concurrency

- `research_agent.py --run` processes `LIMIT 5` profiles per call (`process_pending_profiles` in `research_agent.py`). Change it by editing the query literal.
- The ReAct loop allows up to 4 LLM turns per profile (3 searches + 1 final). See `analyze_profile_with_react`.
- The critic agent retries at most once when it rejects an analysis.
- There is no built-in worker pool. Redis-backed parallelism is still planned (see [architecture-and-agents.md](architecture-and-agents.md)). For now, run multiple shells against disjoint Postgres instances if you need horizontal scale.

## Retry / reset flags

There is no `--retry` flag. To re-run failed profiles, reset their status manually:

```sql
UPDATE linkedin_profiles SET research_status = 'pending' WHERE research_status = 'failed';
```

To re-grade a profile, null out its `user_grade` and run `research_agent.py --grade` again.

## Tagging

There is no tagging column in the current schema. If you need to segment campaigns, filter by `is_smb`, `user_grade`, or `search_queries_used` at export time, or by the Apify raw data keys when using `--mode full`.

## Monitoring Postgres

```sh
# Row counts by status
docker compose exec postgres psql -U user -d auto_marketer -c \
    "SELECT research_status, COUNT(*) FROM linkedin_profiles GROUP BY research_status;"

# Grading coverage
docker compose exec postgres psql -U user -d auto_marketer -c \
    "SELECT COUNT(*) FILTER (WHERE user_grade IS NOT NULL) AS graded, COUNT(*) AS total FROM linkedin_profiles;"
```

## Monitoring Qdrant

```sh
curl -s http://localhost:6335/collections | jq
curl -s http://localhost:6335/collections/linkedin_profiles | jq .result.points_count
curl -s http://localhost:6335/collections/user_feedback   | jq .result.points_count
```

## Backups

Postgres dump:

```sh
docker compose exec postgres pg_dump -U user -d auto_marketer -Fc \
    > backups/auto_marketer_$(date +%F).dump
```

Qdrant snapshot (one per collection):

```sh
curl -s -X POST http://localhost:6335/collections/linkedin_profiles/snapshots | jq
curl -s -X POST http://localhost:6335/collections/user_feedback/snapshots   | jq
```

Snapshots land inside the `qdrant_data` volume under `snapshots/`. Copy them out with `docker cp`.

## Supply-chain audit

```sh
uv sync --frozen         # refuses if uv.lock is stale or a hash mismatches
uv pip audit             # checks resolved deps against the PyPA advisory DB
```

See [../SECURITY.md](../SECURITY.md) for the full policy.

## Running the test suites

```sh
uv run pytest -v                                       # full suite
uv run pytest test_security.py -v                       # Phase 6 runtime hardening
uv run pytest test_no_sql_string_formatting.py -v       # AST guard against built SQL
uv run pytest test_episodic_memory.py -v                # Phase 2 memory
uv run pytest test_phases_345.py -v                     # Phase 3/4/5 (few-shot, critic, FT export)
uv run pytest test_grading.py -v                        # alignment metric
```

See [testing.md](testing.md) for what each suite covers.

## Ruff lint gate

```sh
uv run ruff check .
```

S608 (hardcoded-SQL-expression) is the load-bearing rule. Never silence it with `# noqa` without a security review — the AST test in `test_no_sql_string_formatting.py` also enforces the same rule at test time.
