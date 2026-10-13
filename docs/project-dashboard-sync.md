# Project Dashboard sync (independent of Stars sync)

This is a **separate** GitHub Actions workflow. It does not modify the existing Stars job or GitHub Stars collection.

## Status

Implementation is in `src/project_dashboard_sync.py`, with workflow `.github/workflows/sync-project-dashboard.yml`. The workflow becomes scheduled only after merging to the default branch **and configuring its secrets**. No live run has been verified yet.

## Requirements and permissions

1. Create a fine-grained GitHub PAT `GH_PROJECTS_TOKEN` scoped to repositories to monitor, including private repos. Minimum access: **Metadata: read**, **Contents: read**, **Pull requests: read**, **Actions: read**, **Checks: read**, **Commit statuses: read** (where supported). To discover Topic-marked private repositories, the token must also access the account's repo listing. Do not reuse a token with Stars write access unnecessarily.
2. Provide `NOTION_TOKEN` through GitHub Actions Secrets. A Notion integration needs read access to the **开发项目** and **代码仓库** data sources and update access to these plus the **代码管理** homepage and its statistic blocks. Existing Stars integration can be reused if permissions are expanded; otherwise use a separate token.
3. The data source IDs and homepage ID are already present in the workflow. Change them if the databases are recreated. No credentials are committed.
4. The workflow runs hourly (`23 * * * *`, UTC). GitHub Actions schedules are best-effort and only execute on the default branch. Manual runs default to **dry run**.

## Dynamic inclusion policy

* All existing managed Notion `代码仓库` rows remain in scope, **except** rows with `管理状态=忽略`.
* Add a GitHub URL (or multiple full URLs separated by whitespace, comma, or semicolon) to **开发项目 → 待关联仓库 URL**. The workflow will upsert by stable GitHub Repo ID and add a Relation to the project.
* Alternatively, add the repository Topic `notion-managed`. The workflow discovers it without automatically mapping it to an arbitrary similarly-named project.
* No blanket import of historical repositories or forks. Topic discovery excludes archived repositories.
* New unassociated repositories use `管理状态=待关联`.

## Synced fields

`仓库名称`, `仓库地址`, `GitHub Repo ID`, `可见性`, `默认分支`, `跟踪分支`, `最后 Push`, `最新分支提交`, `最新提交说明`, `最新提交链接`, `开放 PR 数`, `CI 状态`, `最后同步时间`, `同步状态`, `已归档`, `管理状态`, optional Relation.

The chosen **跟踪分支** is honoured (for example `refactor/postgres-background`). CI is based on the current branch commit's check runs and/or combined commit status; it is `未知` if neither provides a conclusive state. API errors do not clear prior data.

The three homepage counters are based on **Notion's actual database rows**, not on GitHub counts. The script looks for existing cards by their title and updates only their H1/H2/H3 number block and the P0–P3 summary text, leaving layout intact. It avoids rewriting human-controlled project status, importance, priority, or milestones.

## Test before enabling

Manual `workflow_dispatch` with `dry_run=true`, review job summary/log, then run again with `dry_run=false`. Verify all 10 known repository records, especially the tracked branch of `stockx-lite`; inspect homepage counters; then merge to main to enable the hourly schedule. If there are errors, existing data is preserved, and the job fails with a nonzero exit code.

Manual/local: `GH_PROJECTS_TOKEN=... NOTION_TOKEN=... DRY_RUN=1 python src/project_dashboard_sync.py`.

Do not expose tokens in logs, and avoid granting write access to source repositories.
