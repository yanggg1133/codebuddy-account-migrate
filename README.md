# workbuddy-account-migrate

> WorkBuddy 切换账号后对话记录不见了？一键恢复。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform: macOS | Windows | Linux](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows%20%7C%20Linux-blue.svg)](https://github.com/xiaoliuzhuan666/workbuddy-account-migrate)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-green.svg)](https://www.python.org/)
[![Version 1.4.0](https://img.shields.io/badge/Version-1.4.0-brightgreen.svg)](https://github.com/xiaoliuzhuan666/workbuddy-account-migrate)

**[English](#english) | [中文](#chinese)**

---

<h2 id="chinese">中文</h2>

### 你是不是遇到了这个问题？

WorkBuddy 切换账号 / 重新登录 / 换了腾讯云身份后，**之前的对话记录全没了**？长期记忆、MCP 连接器配置也看不到了？

**数据其实没丢**——它们还在磁盘上，只是 WorkBuddy 用 `user_id` 做了账号隔离，新账号的 UI 看不到旧账号的数据。

本工具一键把旧账号的数据合并到当前登录账号，**对话记录、记忆、连接器全部恢复可见**。

```
切换账号前：                       切换账号后：
┌──────────────────┐              ┌──────────────────┐
│  账号 A           │              │  账号 B           │
│  26 个对话 ✅     │    ──→      │  26 个对话 ❌     │ ← UI 看不到了
│  13KB 记忆 ✅     │              │  13KB 记忆 ❌     │ ← 文件还在磁盘上
│  17 个 MCP ✅     │              │  17 个 MCP ❌     │
└──────────────────┘              └──────────────────┘
                                         │
                                    运行迁移脚本
                                         │
                                         ▼
                                  ┌──────────────────┐
                                  │  账号 B           │
                                  │  26 个对话 ✅     │ ← 合并到当前账号
                                  │  13KB 记忆 ✅     │ ← 追加去重
                                  │  17 个 MCP ✅     │ ← 深度合并
                                  └──────────────────┘
```

### 功能特性

| 特性 | 说明 |
|:---|:---|
| ✅ 交互式向导 | 运行即用，列出所有账号，手动选择目标/源账号，无需知道 user_id |
| ✅ 跨平台路径适配 | v1.4：storage.json 路径自动适配 macOS / Windows / Linux |
| ✅ Session 对话记录迁移 | 修改 SQLite 数据库中的 `user_id` 字段，对话记录全部回归 |
| ✅ Memory 长期记忆合并 | 追加式去重合并，不会丢失当前账号已有记忆 |
| ✅ Connector MCP 连接器合并 | JSON 深度合并，目标账号已有配置保留不动 |
| ✅ 自动备份 + 回滚 | 迁移前自动备份数据库、记忆、连接器，支持一键回滚 |
| ✅ WAL 安全处理 | 迁移前后执行 SQLite checkpoint，确保数据持久化 |
| ✅ 登录态权威识别 | v1.4：以 storage.json 为当前账号权威来源，DB 按 session 数最多辅助验证 |
| ✅ 迁移结果验证 | v1.3：UPDATE 后验证源 user_id 归零，确认迁移成功 |
| ✅ 零依赖 | 仅需 Python 3.8+，无第三方包 |

### 快速开始

```bash
git clone https://github.com/xiaoliuzhuan666/workbuddy-account-migrate.git
cd workbuddy-account-migrate
python3 scripts/migrate.py
```

运行效果：

```
======================================================================
WorkBuddy 账号迁移向导
======================================================================

请选择迁移方向：先选【目标账号】（接收数据），再选【源账号】（被迁移）

  序号   user_id                                  Sessions     Memory   Connectors
  ------------------------------------------------------------------------
  1      abc12345-6789-...                              18     13.0KB  17mcp/6conn
  2      def67890-1234-...                               7      5.1KB  17mcp/4conn

请选择【目标账号】（接收数据的账号，输入序号）: 1
```

输入序号即可，全程不需要知道 user_id。

**其他模式：**

```bash
# 仅诊断 — 查看所有账号数据分布
python3 scripts/migrate.py --diagnose

# 指定源账号迁移（高级用户）
python3 scripts/migrate.py --source <USER_ID>

# 显式指定目标账号（不依赖当前登录态推断，v1.4 新增）
python3 scripts/migrate.py --source <USER_ID> --target <USER_ID>

# 回滚到指定备份
python3 scripts/migrate.py --rollback <TAG>
```

### 迁移内容

| 数据类型 | 存储位置 | 隔离方式 | 是否迁移 | 迁移策略 |
|:---|:---|:---|:---:|:---|
| Session 对话记录 | `workbuddy.db` sessions 表 | `user_id` 字段 | ✅ | UPDATE user_id |
| 长期记忆 Memory | `~/.workbuddy/memory/{uid}_memory.md` | 按文件名 | ✅ | 追加去重合并 |
| Connector 连接器配置 | `~/.workbuddy/connectors/{uid}/mcp.json` | 按子目录 | ✅ | JSON 深度合并 |
| Skills 技能 | `~/.workbuddy/skills/` | 无隔离 | ❌ | 全局共享，无需迁移 |
| Automations 定时任务 | `workbuddy.db` automations 表 | 无 user_id | ❌ | 全局共享，无需迁移 |
| Settings / MCP / Plugins | 全局配置文件 | 无隔离 | ❌ | 全局共享，无需迁移 |

### 工作原理

**Step 1：自动诊断** — 从数据库、Memory 文件、Connector 目录三个来源自动发现所有账号。当前登录账号以 **storage.json 的 genie.userId 为权威来源**，DB 中 session 数最多的 user_id 作为辅助验证，不一致时以 storage.json 为准并发出警告（v1.4 起；此前用"最新 session"推断，旧账号的最后一条 session 可能比当前账号更新，导致误判）。

**Step 2：安全备份** — 迁移前自动备份到 `~/.workbuddy/migrate_backups/{timestamp}_{uid}/`

**Step 3：执行迁移** — Session 用 `UPDATE user_id`，Memory 逐行去重追加，Connector JSON 深度合并

**Step 4：持久化 + 验证** — 迁移后执行 WAL checkpoint 确保数据落盘，验证源 user_id 归零确认迁移成功

**Step 5：重启提示** — 提示重启 WorkBuddy 客户端，UI 刷新缓存后数据可见

### 兼容性

| 平台 | 状态 |
|:---|:---|
| WorkBuddy (macOS) | ✅ 已测试 |
| WorkBuddy (Windows) | ✅ 已适配（v1.4，`%APPDATA%` 路径，欢迎实测反馈） |
| WorkBuddy (Linux) | ✅ 已适配（v1.4，`XDG_CONFIG_HOME` 路径，欢迎实测反馈） |
| CodeBuddy CLI | ❌ 不适用（见下方说明） |

**为什么不支持 CodeBuddy CLI？** CodeBuddy CLI 的记忆按项目维度隔离（`~/.codebuddy/memories/{project-id}/`），对话记录按 `{sessionId}.jsonl` 独立文件存储，不依赖 `user_id` 过滤，**不存在账号切换后数据丢失的问题**。如果你是 CodeBuddy 用户遇到类似问题，欢迎提 Issue。

### 安全规则

1. **必须先备份** — 迁移前自动创建备份，不可跳过
2. **源 ≠ 目标** — 防止自我覆盖
3. **Memory 追加不覆盖** — 不会丢失当前账号已有记忆
4. **Connector 深度合并** — 保留目标账号已有配置
5. **迁移后重启** — WorkBuddy 客户端有内存缓存
6. **备份 7 天可清** — 手动删除即可

### 回滚

```bash
ls ~/.workbuddy/migrate_backups/
python3 scripts/migrate.py --rollback 20260525170000_abc12345
```

### 竞品对比

| 项目 | 定位 | 同平台账号切换 | Session 迁移 | Memory 迁移 |
|:---|:---|:---:|:---:|:---:|
| **本项目** | 同平台账号切换数据合并 | ✅ | ✅ | ✅ |
| [ai-memory-sync](https://github.com/supercrzy/ai-memory-sync) | 跨设备记忆同步 | ❌ | ❌ | ✅ |
| [claw-migrate](https://github.com/citriac/claw-migrate) | 跨平台记忆迁移 | ❌ | ❌ | ✅ |
| [workbuddy-manager](https://github.com/starsss0416/workbuddy-manager) | 本地会话管理 | ❌ | ✅ 本地 | ❌ |

**本项目填补的空白**：跨平台迁移和跨设备同步都有人做了，但**同平台账号切换后的数据合并**是唯一没人覆盖的场景。

### FAQ

**Q: WorkBuddy 切换账号后对话记录 / 历史记录真的没丢吗？**

A: 没丢。数据文件全部还在磁盘上，只是 UI 按 `user_id` 过滤导致看不到。本工具把这些数据合并到当前账号下即可恢复可见。

**Q: 迁移后旧账号数据还在吗？**

A: Session 的 `user_id` 被改为新账号，所以在旧账号的 UI 下不可见了。Memory 和 Connector 的源文件仍然保留，可手动清理。

**Q: 支持双向迁移吗？**

A: 支持。从 B 迁到 A 后，可以登录 B 再执行 `--source <A的user_id>`，或者用 `--target` 直接指定目标账号、无需切换登录。Memory 按行去重、Connector 按 key 合并，反向迁移不会产生重复内容。注意：反向迁移会把 A 名下**所有** session 一起迁走（包括 A 原有的）；如果只是想撤销上一次迁移，用 `--rollback` 回滚更干净。

**Q: 支持 CodeBuddy CLI 吗？**

A: 暂不支持。CodeBuddy CLI 不存在账号切换数据丢失的问题。详见上方「兼容性」章节。

**Q: Windows / Linux 可以用吗？**

A: 可以。v1.4 起 storage.json 路径已按平台自动适配（macOS `~/Library/Application Support/...`、Windows `%APPDATA%`、Linux `XDG_CONFIG_HOME`）。

### 项目结构

```
workbuddy-account-migrate/
├── README.md                              # 本文档
├── LICENSE                                # MIT 许可证
├── .gitignore                             # 排除敏感文件
├── SKILL.md                               # WorkBuddy Skill 描述符
├── scripts/
│   └── migrate.py                         # 核心迁移脚本
└── references/
    └── data_isolation_map.md              # 数据隔离全景图
```

### 贡献

- Bug 报告 / 功能请求 → [Issues](https://github.com/xiaoliuzhuan666/workbuddy-account-migrate/issues)
- 代码贡献 → 提交 PR，请确保无硬编码的 user_id 或 Token
- Windows / Linux 实测反馈 → 欢迎 Issue

### 更新日志

#### v1.4.0 (2026-08-06)

**跨平台支持 + 当前账号识别修复**（感谢 [@yuren238](https://github.com/yuren238)，PR #1）

- **跨平台**：storage.json 路径自动适配 macOS / Windows / Linux，不再硬编码 macOS 路径
- **Bug 修复**：当前账号识别改为以 storage.json 为权威来源，DB 按 session 数最多做辅助验证。此前用"最新 session"推断，旧账号的最后一条 session 可能比当前账号更新，导致误把旧账号当成当前账号
- **新增**：`--target` 参数，可手动指定目标账号，无需切换登录
- **改进**：交互式向导改为手动选择目标/源账号，避免自动推断错误
- **Bug 修复**：Windows GBK 编码终端下 emoji 输出导致 UnicodeEncodeError 崩溃

#### v1.3.0 (2026-05-26)

**关键修复：账号切换后 storage.json 中 genie.userId 未同步，导致迁移被静默跳过**

- **Bug 修复**：`get_current_user_id()` 改为多源交叉验证——同时从 DB 最新 session 和 storage.json 读取 user_id，不一致时警告并优先使用 DB 值。此前仅依赖 `genie.userId`，账号切换后可能过时，导致 source=target 迁移被跳过。
- **Bug 修复**：`migrate_sessions()` 迁移后增加 WAL checkpoint + 验证源 user_id 归零。此前修改可能因 WAL 未落盘而在客户端重启后丢失。
- **文档更新**：SKILL.md 新增 AI 手动迁移最佳实践、3 条新踩坑记录。

#### v1.2.0 (2026-05-25)

- 新增历史任务恢复（`--list-tasks`、`--restore-tasks`）
- 新增交互式向导模式
- 新增 `--generate-commands` 生成 TaskCreate 命令

#### v1.1.0 (2026-05-25)

- 首次公开发布
- Session、Memory、Connector 迁移
- 自动备份 + 回滚

### License

[MIT](LICENSE) © 2026

---

<h2 id="english">English</h2>

### The Problem

After switching accounts in WorkBuddy (Tencent Cloud AI assistant desktop app), **all your previous conversation history, long-term memory, and MCP connector configs disappear from the UI**. The data is still on disk — just hidden by `user_id` isolation.

This tool merges old account data into your current account with a single command.

### Quick Start

```bash
git clone https://github.com/xiaoliuzhuan666/workbuddy-account-migrate.git
cd workbuddy-account-migrate
python3 scripts/migrate.py
```

Interactive wizard — just pick a number, no user_id knowledge required.

### What Gets Migrated

| Data | How | Strategy |
|:---|:---|:---|
| Session history | SQLite `user_id` field | UPDATE to new account |
| Long-term Memory | `~/.workbuddy/memory/{uid}_memory.md` | Append + deduplicate |
| MCP Connectors | `~/.workbuddy/connectors/{uid}/mcp.json` | JSON deep merge |

Skills, Automations, Settings are global (no user_id) — no migration needed.

### Features

- 🧙 Interactive wizard (pick target & source accounts by number, no user_id needed)
- 🖥️ Cross-platform: storage.json path auto-detected for macOS / Windows / Linux (v1.4)
- 🔒 Safe: append-only memory, deep-merge connectors, WAL checkpoint before & after
- 🔍 Authoritative login detection: storage.json first, DB session-count as cross-check (v1.4)
- ✅ Post-migration verification (source user_id must be zero)
- 🪶 Zero dependencies (Python 3.8+ only)

### Compatibility

- ✅ WorkBuddy macOS (tested)
- ✅ WorkBuddy Windows / Linux (paths adapted in v1.4, feedback welcome)
- ❌ CodeBuddy CLI (not needed — it uses project-level isolation, not user-level)

### Changelog

#### v1.4.0 (2026-08-06)

**Cross-platform support + current-account detection fix** (thanks [@yuren238](https://github.com/yuren238), PR #1)

- **Cross-platform**: storage.json path auto-adapts to macOS / Windows / Linux (no more hardcoded macOS path)
- **Bug fix**: current account is now detected from storage.json as the authoritative source, with the DB's most-frequent user_id as a cross-check. Previously the "latest session" heuristic could misidentify a stale old account as the current one
- **New**: `--target` flag to explicitly set the target account without switching logins
- **Improved**: interactive wizard now asks for target and source accounts explicitly, avoiding auto-inference errors
- **Bug fix**: emoji output no longer crashes on Windows GBK/CP936 terminals (UnicodeEncodeError)

#### v1.3.0 (2026-05-26)

**Critical fix: Migration was silently skipped due to stale user_id**

- **Bug fix**: `get_current_user_id()` now uses multi-source cross-validation — reads from both DB latest session and `storage.json`, warns when inconsistent, prioritizes DB value. Previously relied solely on `genie.userId` which could be stale after account switch, causing `source == target` and migration being skipped.
- **Bug fix**: `migrate_sessions()` now performs WAL checkpoint after UPDATE (not just before), and verifies source user_id is zero. Previously, modifications could be lost on client restart due to unflushed WAL logs.
- **SKILL.md**: Added AI manual migration best practices, 3 new troubleshooting entries.
- **README**: Updated feature list, workflow description, and version badge.

#### v1.2.0 (2026-05-25)

- Added task history recovery (`--list-tasks`, `--restore-tasks`)
- Added interactive wizard mode
- Added `--generate-commands` for TaskCreate tool

#### v1.1.0 (2026-05-25)

- Initial public release
- Session, Memory, Connector migration
- Auto-backup + rollback support

### License

[MIT](LICENSE) © 2026
