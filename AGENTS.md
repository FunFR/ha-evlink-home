# AGENTS.md

Home Assistant custom integration for the Schneider EVlink Home Smart Wallbox, through the Wiser Home cloud service. Domain terms live in [GLOSSARY.md](GLOSSARY.md): use them in code, tests and docs.

## Public wording

Everything committed, and every issue, pull request or release note, is public. Present the integration as an unofficial client of the Wiser Home cloud service that acts for the user's own account, as the Wiser Home app does. Call it a cloud service, not an API, and describe what the integration does rather than how the service works. Claim no affiliation with Schneider Electric.

## Secrets and personal data

- The static app credential in `custom_components/evlink_home/api.py` stays a constant there, with no comment on its origin. Keep it out of logs, diagnostics, docs and chat.
- Fixtures, snapshots and examples carry placeholders (`REDACTED_*`, `123456`, `user@example.com`, all-zero UUIDs) in place of real ids, serials, tokens, emails or names.

## Tests

Tests run against recorded cloud answers in `tests/fixtures/` and stay offline. A Start or Stop sent to a real Wallbox needs its owner's go each time.

Recorded answers cannot see a change on the cloud side, so before a release, smoke-test in a real Home Assistant with a real account: `docker compose up -d` serves one on `127.0.0.1:8123` with the integration mounted from `custom_components/`. The release is ready when the coordinator logs `success: True` with no `ERROR` or traceback, and every `evlink_home` entity holds a value rather than `unavailable` or `unknown`.

## Releases

- A commit is breaking (`!`) only when it breaks an existing installation: an entity or `unique_id` removed or renamed, the domain changed, or a configuration step changed. release-drafter turns it into a major version.
- A fix for a bug a user reported ships as a pre-release, promoted to latest once the reporter confirms it on their Wallbox. HACS and the Marketplace offer pre-releases only to users who opt in.

## Maintenance

Renovate maintains the repository on its own, so every change stays valid for months without a human:

- Derive versions from a declared source. CI runs on the Python series of the `requires-python` floor, which follows Home Assistant's.
- For a problem owned upstream (a Home Assistant pin, a broken release), fix the cause or wait for the upstream fix. A pin or override that someone must remember to remove is rot.
- The `Audit` job runs `pip-audit` outside pull requests on purpose: a vulnerability in a version Home Assistant pins stays visible without holding dependency updates.

## Checks

`uv run pre-commit install` once, then `uv run pre-commit run --all-files` runs the local checks: ruff, mypy strict, pytest with coverage, zizmor and gitleaks. CI adds hassfest and the HACS validation.

When behaviour changes, keep `quality_scale.yaml` and the README true to the code.
