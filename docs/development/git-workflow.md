# Git 与 Pull Request 流程

## 分支和提交

- `main` 是集成分支；每项短期工作从最新 `main` 创建短生命周期分支。
- 分支名使用 `codex/<type>/<scope>`，例如 `codex/docs/ci-onboarding`、`codex/fix/ready-check`。
- 使用 Conventional Commits：`feat: ...`、`fix: ...`、`docs: ...`、`test: ...`、`chore: ...`；需要作用域时写作 `feat(api): ...`。
- 一个 PR 聚焦一个可审查目标，不混入格式化、锁文件升级或无关重构。

推荐命令：

```bash
git switch main
git pull --ff-only
git switch -c codex/docs/ci-onboarding
# edit, verify
git status --short
git diff --check
git add <intended-files>
git commit -m "docs: add CI and onboarding guidance"
```

## Pull Request

仓库提供 `.github/pull_request_template.md`。PR 必须说明摘要、实际执行过的测试命令、风险和回滚方案、迁移影响、安全/密钥影响，以及依赖、模型或网络行为变化。

评审意图是要求至少一次人工审阅，并要求与变更相符的 Backend CI、Frontend CI、Container CI 都通过。建议使用 squash merge，以一条清晰 Conventional Commit 记录集成结果。

这些内容是团队流程约定；仅添加工作流和文档**不会**在 GitHub 上实际启用分支保护、必需检查或审阅人数。管理员应在仓库设置中按该意图配置，并在规则生效后验证。

## 版本

发布标签采用 SemVer：`vMAJOR.MINOR.PATCH`。

- `MAJOR`：不兼容 API、数据或部署契约变更。
- `MINOR`：向后兼容的新功能。
- `PATCH`：向后兼容的缺陷修复或文档/构建修复。

是否发布和打标签仍是维护者决定；CI 不会自动创建发布或标签。

## Alembic 迁移规则

1. Schema 变更必须有新的、可审查的 Alembic revision，不能修改已在共享环境使用的 revision。
2. 在 PR 中列出 revision、升级影响、回滚/降级决策、数据回填计划和验证命令。
3. 在真实 PostgreSQL 副本上测试 `alembic upgrade head`；若降级安全且被支持，再测试 `alembic downgrade`。不可逆迁移必须明确写出恢复方案。
4. 不在 API 启动路径自动迁移。Compose 的 `migrate` 服务和生产运维步骤负责显式迁移。
5. 迁移不得包含生产凭据、真实客户数据或隐式网络副作用。
