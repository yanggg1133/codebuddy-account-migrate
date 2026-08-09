# codebuddy-account-migrate

> CodeBuddy 切换账号后对话历史不见了？数据没丢，一键合并回当前账号。

> 本项目基于 [xiaoliuzhuan666/workbuddy-account-migrate](https://github.com/xiaoliuzhuan666/workbuddy-account-migrate) 改造，将 WorkBuddy 账号迁移工具适配为 **CodeBuddy IDE** 专用版本。核心差异：WorkBuddy 需迁移 Session（SQLite 数据库）+ Memory + Connector，CodeBuddy 需迁移**对话历史（本地目录）** + Memory。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform: macOS | Windows | Linux](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows%20%7C%20Linux-blue.svg)](https://github.com/xiaoliuzhuan666/workbuddy-account-migrate)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-green.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/Tests-33%20passed-brightgreen.svg)](https://github.com/xiaoliuzhuan666/workbuddy-account-migrate)

**[English](#english) | [中文](#chinese)**

---

<h2 id="chinese">中文</h2>

### 你是不是遇到了这个问题？

CodeBuddy IDE 切换账号 / 重新登录 / 换了腾讯云身份后，**之前的对话历史全没了**？长期记忆（Memory）也看不到了？

**数据其实没丢**——它们还在磁盘上，只是 CodeBuddy 用 `user_id` 做了账号隔离，新账号的 UI 看不到旧账号的数据。

```
切换账号前：                       切换账号后：
┌──────────────────┐              ┌──────────────────┐
│  账号 A           │              │  账号 B           │
│  80 个对话 ✅     │    ──→      │  80 个对话 ❌     │ ← UI 看不到了
│  15KB 记忆 ✅     │              │  15KB 记忆 ❌     │ ← 文件还在磁盘上
└──────────────────┘              └──────────────────┘
                                         │
                                    运行迁移脚本
                                         │
                                         ▼
                                  ┌──────────────────┐
                                  │  账号 B           │
                                  │  80 个对话 ✅     │ ← 合并到当前账号
                                  │  15KB 记忆 ✅     │ ← 追加去重
                                  └──────────────────┘
```

本工具一键把旧账号的 **对话历史 + 长期记忆** 合并到当前登录账号，重启 CodeBuddy 后即可看见。

### 功能特性

| 特性 | 说明 |
|:---|:---|
| ✅ 交互式向导 | 运行即用，列出所有账号，手动选择目标/源账号，无需知道 user_id |
| ✅ 对话历史迁移 | 按会话目录复制合并（已存在跳过），对话记录全部回归 |
| ✅ Memory 长期记忆合并 | 追加式去重合并，不会丢失当前账号已有记忆 |
| ✅ 自动备份 + 回滚 | 迁移前自动备份记忆 + 对话历史，支持一键回滚 |
| ✅ 登录态权威识别 | 以 storage.json 的 genie.userId 为当前账号权威来源，Memory 最新文件辅助验证 |
| ✅ 历史预览 | `--list-history` 查看任意账号的本地对话标题，确认后再迁移 |
| ✅ 跨平台 | macOS / Windows / Linux 路径自动适配 |
| ✅ 零依赖 | 仅需 Python 3.8+，无第三方包 |

### 快速开始

```bash
cd codebuddy-account-migrate
python scripts/migrate.py
```

运行效果：

```
======================================================================
CodeBuddy 账号迁移向导
======================================================================

请选择迁移方向：先选【目标账号】（接收数据），再选【源账号】（被迁移）

  序号   user_id                                  Memory   History
  ------------------------------------------------------------------------
  1      9bc620d6-c54d-40f8-b258-79914d5cd500    15.5KB   88 会话   ← 当前
  2      f7080610-9553-4df8-81c6-0b1a572a98bd    15.4KB   80 会话
  3      fa6abb06-a882-40c8-9266-290076c81613    14.3KB   17 会话
  4      c089215e-74ff-4b3d-a937-e7a5cfa532b5    12.2KB    7 会话
  5      a10c91d2-e7d8-481c-8dbb-05565e9e8341     8.8KB    8 会话
  6      8791e828-438e-4386-a991-9a26060648c4     7.4KB    4 会话
  7      0354eea6-5fa8-420b-9c00-4168546ea039     7.3KB    9 会话
  8      c9f790f4-3a29-4265-9f7a-d457a199ac6a         -    9 会话

请选择【目标账号】（接收数据的账号，输入序号）: 1
请选择【源账号】（被迁移的账号，输入序号）: 2
确认执行迁移？(y/N): y
```

输入序号即可，全程不需要知道 user_id。

**其他模式：**

```bash
# 诊断 — 查看所有账号的 Memory + 对话历史分布
python scripts/migrate.py --diagnose

# 指定源账号迁移（Memory + 对话历史）
python scripts/migrate.py --source <USER_ID>

# 指定目标账号（不依赖当前登录态推断）
python scripts/migrate.py --source <USER_ID> --target <USER_ID>

# 跳过确认直接迁移
python scripts/migrate.py --source <USER_ID> --yes

# 查看某个账号的本地对话历史标题
python scripts/migrate.py --list-history <USER_ID>

# 回滚到指定备份
python scripts/migrate.py --rollback <TAG>
```

### 实际迁移案例

把旧账号 `f7080610`（80 会话 + 15.4KB 记忆）合并到当前账号 `9bc620d6`：

```bash
$ python scripts/migrate.py --source f7080610-9553-4df8-81c6-0b1a572a98bd --target 9bc620d6-c54d-40f8-b258-79914d5cd500 --yes

======================================================================
CodeBuddy 账号迁移（Memory + 本地对话历史）
======================================================================

  源账号:   f7080610-9553-4df8-81c6-0b1a572a98bd
  目标账号: 9bc620d6-c54d-40f8-b258-79914d5cd500 (当前登录)

📊 Phase 1: 诊断数据分布...
  源账号: 15.4KB memory, 80 个会话历史
  目标账号: 0.0KB memory, 10 个会话历史

📦 Phase 2: 创建备份...
  ✅ 已备份对话历史（10 会话）
  ✅ 已备份 mcp.json
  📦 备份标签: 20260808201737_9bc620d6

🔄 Phase 3: 执行迁移...
  [Memory 迁移]
  ✅ 复制 Memory（目标为空，直接复制 8750 字符）
  [对话历史迁移]
  ✅ 迁移 78 个对话历史会话 → .../history

✅ Phase 4: 验证...
  目标账号 Memory: 0.0KB → 15.5KB
  目标账号 对话历史: 10 → 88 个会话

======================================================================
迁移完成！
======================================================================
```

### 迁移内容

| 数据类型 | 存储位置 | 隔离方式 | 是否迁移 | 迁移策略 |
|:---|:---|:---|:---:|:---|
| 对话历史（英文版） | `%LOCALAPPDATA%\CodeBuddyExtension\Data\{uid}\CodeBuddyIDE\{uid}\history\` | 按 user_id 目录 | ✅ | 会话目录复制，已存在跳过 |
| 会话索引（CN 中文版） | `%APPDATA%\CodeBuddy CN\codebuddy-sessions.vscdb` | SQLite 记录 userId 字段 | ✅ | UPDATE userId 字段 |
| 长期记忆 Memory | `~/.codebuddy/memery/{uid}_memery.md` | 按文件名 | ✅ | 追加去重合并（空行对齐） |
| Connector 连接器 | `~/.codebuddy/mcp.json` | 全局 | ❌ | 全局共享，无需迁移 |
| Settings / Skills | 全局配置文件 | 无隔离 | ❌ | 全局共享，无需迁移 |

> ⚠️ **CodeBuddy CN（中文版）重要限制**：CN 版是**云端优先架构**，实际对话内容存储在腾讯云服务端（按 userId 隔离）。`codebuddy-sessions.vscdb` 只存本地元数据（标题/状态），本工具只能 UPDATE 本地索引的 userId，**无法改变云端对话所有权**。因此迁移后切换账号可能仍看不到历史——需要用**原始创建账号登录 CN 才能查看**。完整迁移需要调用腾讯云 API（待实现）。英文版不受此限制（历史数据全在本地 `history/` 目录）。

### 工作原理

**Step 1：自动诊断** — 从 Memory 目录（`~/.codebuddy/memery/`）+ CodeBuddyExtension Data 目录（`%LOCALAPPDATA%\CodeBuddyExtension\Data\`）自动发现所有账号。当前登录账号以 **storage.json 的 genie.userId 为权威来源**，Memory 最新文件做辅助验证，不一致时以 storage.json 为准并发出警告。

**Step 2：安全备份** — 迁移前自动备份到 `~/.codebuddy/migrate_backups/{timestamp}_{uid}/`（含 Memory + 对话历史 + mcp.json + 元数据）

**Step 3：执行迁移** — 对话历史按会话目录复制（已存在跳过），Memory 逐行去重追加（保留空行结构，多行段落不拆散）

**Step 4：验证** — 迁移后对比目标账号 Memory 大小与历史会话数，确认增量

**Step 5：重启提示** — 提示重启 CodeBuddy，UI 刷新缓存后数据可见

### 安全规则

1. **必须先备份** — 迁移前自动创建备份，不可跳过
2. **源 ≠ 目标** — 防止自我覆盖
3. **Memory 追加不覆盖** — 不会丢失当前账号已有记忆
4. **历史已存在跳过** — 不会覆盖目标账号已有会话
5. **迁移后重启** — CodeBuddy 客户端有内存缓存，重启后生效
6. **备份可回滚** — 支持 `--rollback` 一键恢复迁移前状态

### 回滚

```bash
# 查看所有备份
ls ~/.codebuddy/migrate_backups/

# 回滚到指定备份
python scripts/migrate.py --rollback 20260808201737_9bc620d6
```

### 兼容性

| 平台 | 状态 |
|:---|:---|
| Windows | ✅ 已实测（C:\Python\Python312，28 测试通过） |
| macOS | ✅ 已适配（路径自动推断） |
| Linux | ✅ 已适配（路径自动推断） |

### 项目结构

```
codebuddy-account-migrate/
├── README.md                              # 本文档
├── LICENSE                                # MIT 许可证
├── .gitignore                             # 排除敏感文件
├── SKILL.md                               # WorkBuddy Skill 描述符
├── pytest.ini                             # pytest 配置
├── scripts/
│   └── migrate.py                         # 核心迁移脚本（零依赖）
├── tests/
│   └── test_migrate.py                    # pytest 测试（33 用例）
└── references/
    └── data_isolation_map.md              # 数据隔离全景图
```

### FAQ

**Q: CodeBuddy 切换账号后对话历史真的没丢吗？**

A: 没丢。数据文件全部还在磁盘上（`%LOCALAPPDATA%\CodeBuddyExtension\Data\`），只是 UI 按 `user_id` 过滤导致看不到。本工具把这些数据合并到当前账号下即可恢复可见。

**Q: 切换账号后，旧账号的数据会丢吗？**

A: 不会。每个账号的数据在独立目录下，切换账号不会删除任何文件。只是新账号的 UI 看不到旧账号的数据。

**Q: 迁移后旧账号数据还在吗？**

A: 在。对话历史是**复制**（非移动），旧账号目录保持不变；Memory 是追加合并，源文件保留。可随时删除。

**Q: 为什么之前说"不支持 CodeBuddy"？**

A: 早期版本未发现 CodeBuddy 的本地对话历史存储位置（`CodeBuddyExtension\Data\{uid}\`），以为对话历史全在服务端。实测发现 CodeBuddy IDE 的对话历史同样按 user_id 目录隔离，因此本版本已全面支持。

**Q: 支持双向迁移吗？**

A: 支持。从 B 迁到 A 后，可以登录 B 再执行 `--source <A的user_id>`，或者用 `--target` 直接指定目标账号、无需切换登录。Memory 按行去重、历史按目录去重，反向迁移不会产生重复内容。如果只是想撤销上一次迁移，用 `--rollback` 回滚更干净。

**Q: Windows / Linux 可以用吗？**

A: 可以。storage.json 路径已按平台自动适配（macOS `~/Library/Application Support/...`、Windows `%APPDATA%`、Linux `XDG_CONFIG_HOME`），CodeBuddyExtension Data 路径同理。

### 贡献

- Bug 报告 / 功能请求 → [Issues](https://github.com/xiaoliuzhuan666/workbuddy-account-migrate/issues)
- 代码贡献 → 提交 PR，请确保无硬编码的 user_id 或 Token
- Windows / Linux 实测反馈 → 欢迎 Issue

### 更新日志

#### v2.1.0 (2026-08-08)

**CodeBuddy CN（中文版）全面支持**

- **新增**：CodeBuddy CN 中文版会话索引迁移（`codebuddy-sessions.vscdb`），支持切换账号后 CN 版对话历史恢复
- **新增**：`get_cn_session_rows()` / `get_all_cn_uids()` / `get_cn_session_counts()` / `migrate_cn_sessions()` 全套 CN 会话数据库操作
- **新增**：`CODEBUDDY_MIGRATE_CN_BASE` 环境变量，支持所有路径覆盖，跨平台（macOS / Windows / Linux）
- **新增**：备份/回滚扩展至 CN 会话数据库（含 WAL/SHM 文件）
- **新增**：`--diagnose` 增加 CN 会话列，同时显示英文版历史 + 中文版会话
- **新增**：pytest 测试 5 个新用例，覆盖 CN 会话读取、迁移、备份、诊断、完整流程
- **测试**：33/33 通过

#### v2.0.0 (2026-08-08)

**CodeBuddy 全面适配 + 对话历史迁移**

- **重大发现**：CodeBuddy IDE 的对话历史以 `user_id` 目录隔离存储在本地（`%LOCALAPPDATA%\CodeBuddyExtension\Data\{uid}\CodeBuddyIDE\{uid}\history\`），"切账号丢历史"实为 UI 过滤，数据未丢
- **新增**：对话历史迁移（`migrate_history()`），按会话目录复制合并，已存在跳过
- **新增**：`--list-history <uid>` 命令，查看任意账号的本地对话标题
- **新增**：`--diagnose` 增加 History 列，显示每个账号的本地会话数
- **新增**：备份/回滚机制扩展至对话历史目录
- **新增**：`CODEBUDDY_MIGRATE_*` 环境变量体系，支持全部路径覆盖（便于测试）
- **新增**：pytest 测试套件（28 用例），覆盖 memory 迁移、history 迁移、备份、回滚、诊断、完整流程
- **改进**：Memory 去重逻辑保留空行，避免多行段落被拆散
- **改进**：Windows GBK 编码检测，pytest 下跳过 stdout 包装避免崩溃
- **测试**：Windows C:\Python\Python312 实测 28/28 通过

---

<h2 id="english">English</h2>

> This project is a fork of [xiaoliuzhuan666/workbuddy-account-migrate](https://github.com/xiaoliuzhuan666/workbuddy-account-migrate), adapted for **CodeBuddy IDE**. Key difference: WorkBuddy requires migrating Session (SQLite DB) + Memory + Connector; CodeBuddy requires migrating **conversation history (local directories)** + Memory.

### The Problem

After switching accounts in CodeBuddy IDE, **all your previous conversation history and long-term memory disappear from the UI**. The data is still on disk — just hidden by `user_id` isolation.

| Data | Location | Isolation |
|:---|:---|:---|
| Conversation history | `%LOCALAPPDATA%\CodeBuddyExtension\Data\{uid}\CodeBuddyIDE\{uid}\history\` | Per-user directory |
| Long-term Memory | `~/.codebuddy/memery/{uid}_memery.md` | Per-file naming |

This tool merges old account data (history + memory) into your current account with a single command.

### Quick Start

```bash
cd codebuddy-account-migrate
python scripts/migrate.py
```

Interactive wizard — just pick a number, no user_id knowledge required.

**Other modes:**

```bash
# Diagnose — view all accounts' memory + history distribution
python scripts/migrate.py --diagnose

# Migrate with source and optional target
python scripts/migrate.py --source <USER_ID>
python scripts/migrate.py --source <USER_ID> --target <USER_ID>

# Skip confirmation
python scripts/migrate.py --source <USER_ID> --yes

# Preview conversation titles for an account
python scripts/migrate.py --list-history <USER_ID>

# Rollback to a backup
python scripts/migrate.py --rollback <TAG>
```

### What Gets Migrated

| Data | Location | Strategy |
|:---|:---|:---|
| Conversation history | `%LOCALAPPDATA%\CodeBuddyExtension\Data\{uid}\...\history\` | Copy session dirs, skip existing |
| Long-term Memory | `~/.codebuddy/memery/{uid}_memery.md` | Append + deduplicate |

Connectors, Settings, and Skills are global (no user_id) — no migration needed.

### Features

- 🧙 Interactive wizard (pick target & source accounts by number)
- 🗂️ Conversation history migration (session-by-session copy, existing skipped)
- 🧠 Memory merge (append-only, deduplicated, preserves structure)
- 🔒 Auto-backup before migration + one-command rollback
- 🔍 Authoritative login detection: storage.json first, memory file as cross-check
- 👁️ Preview history with `--list-history` before committing
- 🖥️ Cross-platform: macOS / Windows / Linux paths auto-detected
- 🪶 Zero dependencies (Python 3.8+ only)

### Real Migration Example

Migrating 80 sessions + 15.4KB memory from `f7080610` to the current account `9bc620d6`:

```
📊 Phase 1: Diagnose...
  Source: 15.4KB memory, 80 sessions
  Target: 0.0KB memory, 10 sessions

📦 Phase 2: Backup...
  ✅ Backed up history (10 sessions) + mcp.json

🔄 Phase 3: Migrate...
  ✅ Copied Memory (8750 chars)
  ✅ Migrated 78 history sessions

✅ Phase 4: Verify...
  Memory: 0.0KB → 15.5KB
  History: 10 → 88 sessions
```

### Rollback

```bash
ls ~/.codebuddy/migrate_backups/
python scripts/migrate.py --rollback 20260808201737_9bc620d6
```

### Project Structure

```
codebuddy-account-migrate/
├── README.md                              # This file
├── LICENSE                                # MIT License
├── .gitignore                             # Sensitive file exclusion
├── SKILL.md                               # WorkBuddy Skill descriptor
├── pytest.ini                             # pytest configuration
├── scripts/
│   └── migrate.py                         # Core migration script (zero deps)
├── tests/
│   └── test_migrate.py                    # pytest suite (33 tests)
└── references/
    └── data_isolation_map.md              # Data isolation full map
```

### Compatibility

| Platform | Status |
|:---|:---|
| Windows | ✅ Tested (C:\Python\Python312, 33 tests passed) |
| macOS | ✅ Adapted (paths auto-detected) |
| Linux | ✅ Adapted (paths auto-detected) |

### Changelog

#### v2.1.0 (2026-08-08)

**CodeBuddy CN (Chinese version) full support**

- **New**: CodeBuddy CN session index migration (`codebuddy-sessions.vscdb`) — recover conversation history after switching accounts in the Chinese version
- **New**: `get_cn_session_rows()` / `get_all_cn_uids()` / `get_cn_session_counts()` / `migrate_cn_sessions()` — full CN session DB API
- **New**: `CODEBUDDY_MIGRATE_CN_BASE` env var for cross-platform path override (macOS / Windows / Linux)
- **New**: Backup/rollback extended to CN session DB (including WAL/SHM files)
- **New**: `--diagnose` now shows CN session column alongside English history
- **New**: 5 new pytest test cases covering CN session read, migration, backup, diagnose, full flow
- **Tested**: 33/33 passing

#### v2.0.0 (2026-08-08)

**Full CodeBuddy support + conversation history migration**

- **Major discovery**: CodeBuddy IDE stores conversation history locally per user_id (`%LOCALAPPDATA%\CodeBuddyExtension\Data\{uid}\CodeBuddyIDE\{uid}\history\`). "Lost history after switching accounts" = UI filtering, data never lost
- **New**: `migrate_history()` — copy session directories, skip existing
- **New**: `--list-history <uid>` — preview conversation titles
- **New**: `--diagnose` now shows History column with session counts
- **New**: Backup/rollback extended to history directory
- **New**: `CODEBUDDY_MIGRATE_*` environment variables for all path overrides
- **New**: pytest test suite (28 tests) covering memory, history, backup, rollback, diagnose, full flow
- **Improved**: Memory dedup preserves blank lines and multi-line sections
- **Improved**: Windows GBK encoding detection, skip stdout wrapping in pytest
- **Tested**: 33/33 passing on Windows C:\Python\Python312

### License

[MIT](LICENSE) © 2026