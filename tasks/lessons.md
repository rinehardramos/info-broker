# Lessons Learned

## [docker] NEVER modify container config after asking user for manual steps
**Trigger**: User runs interactive auth/setup inside a container.
**Rule**: ALWAYS finalize docker-compose.yml, Dockerfile, volumes, and env vars BEFORE asking the user to perform any manual step (auth, config, etc). Container recreation destroys ephemeral state.
**Why**: User had to re-authenticate Claude Code 3 times because container was recreated after each docker-compose.yml change.

## [docker] `setup-token` / keychain auth does not work in Docker containers
**Trigger**: Trying to authenticate Claude Code in a Docker container.
**Rule**: NEVER rely on OS keychain (macOS Keychain, Linux Secret Service) inside Docker. Tokens stored via `claude setup-token` are in the host keychain, inaccessible to containers.
**How to apply**: Extract the OAuth token from the host keychain and pass it as `ANTHROPIC_API_KEY`:
```bash
export CLAUDE_OAUTH_TOKEN=$(security find-generic-password -s "Claude Code-credentials" -w | python3 -c "import sys,json;print(json.load(sys.stdin)['claudeAiOauth']['accessToken'])")
```
Then use `--bare` flag so Claude Code reads `ANTHROPIC_API_KEY` directly.

## [auth] Claude Code subscription != ANTHROPIC_API_KEY
**Trigger**: Requiring `ANTHROPIC_API_KEY` when the user has a Claude Code subscription.
**Rule**: NEVER gate features on `ANTHROPIC_API_KEY` when Claude Code subscription auth is valid. The subscription uses OAuth tokens, not API keys. Only use `--bare` when an API key is explicitly available.
**How to apply**: Check both auth methods: `claude auth status` for subscription, `ANTHROPIC_API_KEY` env var for API key. Either is sufficient.

## [docker] OpenBao secrets can conflict with Docker Compose env vars
**Trigger**: OpenBao `secret/shared` or `secret/<project>` contains keys that overlap with Docker Compose env vars (e.g. `POSTGRES_HOST=localhost` vs Docker's `POSTGRES_HOST=postgres`).
**Rule**: Even though `os.environ.setdefault()` should not override, verify that OpenBao vault paths don't contain Docker-internal env vars. The vault should only store secrets (API keys, tokens), not infrastructure config.
**How to apply**: Audit vault contents before enabling OpenBao in Docker. Keep infra vars (hostnames, ports) out of the vault.

## [process] Verify the full lifecycle before suggesting architecture
**Trigger**: Suggesting `setup-token` without verifying it persists in Docker.
**Rule**: ALWAYS trace the complete lifecycle of any suggested approach: where data is stored, what survives container restart, what gets destroyed on recreate, what needs manual steps.
**How to apply**: Before recommending a setup: (1) check where state is stored, (2) verify it survives the operations you'll perform, (3) sequence manual steps LAST.

## [process] Don't conflate research with workarounds
**Trigger**: Spending time on OpenBao integration when the actual blocker was keychain access.
**Rule**: When hitting a blocker, identify the root cause first. Don't start solving adjacent problems (OpenBao, API keys) when the real issue is different (keychain not available in Docker).
