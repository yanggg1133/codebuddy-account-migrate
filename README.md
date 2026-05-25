# workbuddy-account-migrate

> WorkBuddy 切换账号后对话记录不见了？一键恢复。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform: macOS](https://img.shields.io/badge/Platform-macOS-blue.svg)](https://www.apple.com/macos)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-green.svg)](https://www.python.org/)
[![Version 1.1.0](https://img.shields.io/badge/Version-1.1.0-brightgreen.svg)](https://github.com/yourname/workbuddy-account-migrate)

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
| ✅ 交互式向导 | 运行即用，自动诊断、列出账号、输入序号选择，无需知道 user_id |
| ✅ Session 对话记录迁移 | 修改 SQLite 数据库中的 `user_id` 字段，对话记录全部回归 |
| ✅ Memory 长期记忆合并 | 追加式去重合并，不会丢失当前账号已有记忆 |
| ✅ Connector MCP 连接器合并 | JSON 深度合并，目标账号已有配置保留不动 |
| ✅ 自动备份 + 回滚 | 迁移前自动备份数据库、记忆、连接器，支持一键回滚 |
| ✅ WAL 安全处理 | 迁移前执行 SQLite checkpoint，避免数据不一致 |
| ✅ 零依赖 | 仅需 Python 3.8+，无第三方包 |

### 快速开始

```bash
git clone https://github.com/yourname/workbuddy-account-migrate.git
cd workbuddy-account-migrate
python3 scripts/migrate.py
```

运行效果：

```
======================================================================
WorkBuddy 账号迁移向导
======================================================================

当前登录: abc12345-6789-...

发现以下可迁移的账号：

  序号   Sessions     Memory   Connectors
  ----------------------------------------
  1           7      5.1KB  17mcp/4conn
  2          18     13.0KB  17mcp/6conn

请输入要迁移的账号序号（输入 q 取消）: 2
```

输入序号即可，全程不需要知道 user_id。

**其他模式：**

```bash
# 仅诊断 — 查看所有账号数据分布
python3 scripts/migrate.py --diagnose

# 指定源账号迁移（高级用户）
python3 scripts/migrate.py --source <USER_ID>

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

**Step 1：自动诊断** — 从数据库、Memory 文件、Connector 目录三个来源自动发现所有账号，当前登录账号通过读取 `storage.json` 自动获取。

**Step 2：安全备份** — 迁移前自动备份到 `~/.workbuddy/migrate_backups/{timestamp}_{uid}/`

**Step 3：执行迁移** — Session 用 `UPDATE user_id`，Memory 逐行去重追加，Connector JSON 深度合并

**Step 4：验证 + 重启提示** — 迁移后验证 session 数量变化，提示重启 WorkBuddy 客户端

### 兼容性

| 平台 | 状态 |
|:---|:---|
| WorkBuddy (macOS) | ✅ 已测试 |
| WorkBuddy (Windows) | ⚠️ 路径需适配（`%APPDATA%`），欢迎 PR |
| WorkBuddy (Linux) | ⚠️ 路径需适配（`~/.config`），欢迎 PR |
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

A: 支持。从账号 A 迁到 B 后，也可以再从 B 迁回 A。但注意 Memory 是追加合并，多次迁移可能产生重复内容。

**Q: 支持 CodeBuddy CLI 吗？**

A: 暂不支持。CodeBuddy CLI 不存在账号切换数据丢失的问题。详见上方「兼容性」章节。

**Q: Windows / Linux 可以用吗？**

A: 脚本中的 `STORAGE_JSON` 路径目前硬编码为 macOS 路径。Windows 和 Linux 需要适配路径，欢迎提 PR。

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

- Bug 报告 / 功能请求 → [Issues](https://github.com/yourname/workbuddy-account-migrate/issues)
- 代码贡献 → 提交 PR，请确保无硬编码的 user_id 或 Token
- 平台适配（Windows/Linux）→ 欢迎 PR

### License

[MIT](LICENSE) © 2026

---

<h2 id="english">English</h2>

### The Problem

After switching accounts in WorkBuddy (Tencent Cloud AI assistant desktop app), **all your previous conversation history, long-term memory, and MCP connector configs disappear from the UI**. The data is still on disk — just hidden by `user_id` isolation.

This tool merges old account data into your current account with a single command.

### Quick Start

```bash
git clone https://github.com/yourname/workbuddy-account-migrate.git
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

- 🧙 Interactive wizard (no user_id needed)
- 💾 Auto-backup before migration + rollback support
- 🔒 Safe: append-only memory, deep-merge connectors, WAL checkpoint
- 🪶 Zero dependencies (Python 3.8+ only)

### Compatibility

- ✅ WorkBuddy macOS (tested)
- ⚠️ Windows/Linux (path adaptation needed, PRs welcome)
- ❌ CodeBuddy CLI (not needed — it uses project-level isolation, not user-level)

### License

[MIT](LICENSE) © 2026
