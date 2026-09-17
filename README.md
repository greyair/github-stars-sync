# GitHub Stars Sync

将 GitHub Stars 与 Notion 数据库同步，并在 Notion 中完成分类、活跃度判断和清理管理。

## 功能

- GitHub → Notion：同步全部 starred repositories 元数据
- Notion → GitHub：通过 `同步操作` 执行 `Star` / `Unstar`
- 自动更新 `当前 Star`、`最后同步时间`、`活跃度`
- 根据 `config/categories.yml` 自动填充 `List`
- 保留人工维护字段：`建议`、`重复组`、`替代 / 更优项目`、`整理说明`
- GitHub 原生 Lists 暂不自动同步；Notion 的 `List` 为主分类

## 必需 Secrets

在仓库 Settings → Secrets and variables → Actions 中创建：

- `GH_STARS_TOKEN`：GitHub Fine-grained PAT，Account permissions → Starring: Read and write
- `NOTION_TOKEN`：Notion integration token，只授权目标数据库
- `NOTION_DATA_SOURCE_ID`：`a1e90c37-4400-4466-95e0-112ff6a88d77`

## 使用

Actions 中手动运行 `Sync GitHub Stars to Notion`，或等待每日定时同步。

### Notion → GitHub

不要直接把 `当前 Star` 当命令使用。要修改 GitHub 收藏状态，请设置：

- `同步操作 = Star`
- `同步操作 = Unstar`

同步成功后会自动把 `同步操作` 重置为 `无`，并刷新 `当前 Star`。

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
python src/sync.py
```

## 同步策略

1. 先读取 Notion 中待执行的 `同步操作`
2. 执行 GitHub Star / Unstar
3. 再读取 GitHub 当前 Stars 作为真实状态
4. 增量创建/更新 Notion 记录
5. GitHub 中已不再 Star 的历史记录不会删除，只将 `当前 Star` 设为 false

这样可避免 GitHub 与 Notion 双向覆盖冲突。
