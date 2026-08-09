---
name: 账号迁移工具
description: CodeBuddy / CodeBuddy CN 账号切换后一键同步数据，将旧账号的 Memory 记忆、本地对话历史、CN 会话索引迁移到当前账号。触发关键词：切账号、迁移、同步数据、账号切换、数据丢失、记录没了、CodeBuddy。
version: 2.2.0
agent_created: true
---

# 账号迁移工具（CodeBuddy 版）

CodeBuddy 切换账号后，数据按 `user_id` 隔离，旧账号的 Memory、对话历史在新账号下不可见。本工具实现一键迁移，将所有历史数据合并到当前登录账号。

## 快速使用

```bash
# 交互式向导（推荐）
python3 scripts/migrate.py

# 仅诊断，查看数据分布
python3 scripts/migrate.py --diagnose

# 指定源账号迁移
python3 scripts/migrate.py --source <USER_ID>

# 回滚到指定备份
python3 scripts/migrate.py --rollback <TAG>
```

## 问题背景

CodeBuddy 数据存储：**本地优先 + 账号隔离**，迁移脚本以 `migrate.py` 为核心，自动处理三种数据源。

### 数据隔离全景

| 数据类型 | 存储位置 | 隔离方式 | 切账号后 | 迁移策略 |
|:---|:---|:---|:---:|:---|
| 长期记忆 Memory | `~/.codebuddy/memery/{uid}_memery.md` | 按文件名（`{uid}_` 前缀） | ❌ 不可见 | 追加去重合并 |
| 对话历史（英文版） | `%LOCALAPPDATA%\CodeBuddyExtension\Data\{uid}\CodeBuddyIDE\{uid}\history\` | 按 user_id 目录 | ❌ 不可见 | 会话目录复制，已存在跳过 |
| 会话索引（CN 中文版） | `%APPDATA%\CodeBuddy CN\codebuddy-sessions.vscdb` | SQLite 记录 userId 字段 | ⚠️ 有限 | UPDATE userId（仅本地索引，云端所有权不变） |
| Connector 连接器 | `~/.codebuddy/mcp.json` | 全局共享 | ✅ 可见 | 无需迁移 |
| Settings / Skills | 全局配置文件 | 无隔离 | ✅ 可见 | 无需迁移 |
| 工作空间 Memory | `{workspace}/.workbuddy/memory/` | 绑定工作空间 | ✅ 可见 | 无需迁移 |

### 账号发现机制

脚本通过以下路径扫描所有账号：

1. **Memory 文件**：扫描 `~/.codebuddy/memery/` 下的 `*_memery.md` 文件，提取文件名前缀的 user_id
2. **英文版历史目录**：扫描 `CodeBuddyExtension\Data\` 下的子目录名
3. **CN 版会话数据库**：查询 `codebuddy-sessions.vscdb` 的 `ItemTable` 表，提取 `session:*` 行中的 `userId` 字段

### 当前登录账号识别

脚本优先从 `~/.codebuddy/storage.json` 的 `genie.userId` 字段读取当前账号，若不存在则回退到 Memory 文件推断。

**⚠️ 已知问题**：CodeBuddy 切换账号后 `storage.json` 中的 `genie.userId` 可能**没有同步更新**，仍为旧 ID。如果脚本误读旧 ID 作为 target，会导致"源=目标，无需迁移"的假象。当前版本已增加交叉验证，但手动执行时需要注意。

## 迁移执行流程

### Phase 1：环境诊断（`--diagnose`）

```bash
python3 scripts/migrate.py --diagnose
```

输出示例：
```
user_id                                      Memory  History     CN会话   当前
--------------------------------------------------------------------------
9bc620d6-c54d-40f8-b258-79914d5cd500         15.5KB    88 会话        -    ✅
f7080610-9553-4df8-81c6-0b1a572a98bd         15.4KB    80 会话    40 会话
...
```

各列含义：
- **Memory**：`~/.codebuddy/memery/{uid}_memery.md` 文件大小
- **History**：英文版本地对话历史（文件夹数）
- **CN会话**：中文版 CodeBuddy CN 会话数
- **当前**：✅ 标记当前登录账号

### Phase 2：备份（自动）

运行 `migrate.py --source <UID>` 后自动备份：
1. Memory 目录 `~/.codebuddy/memery/` → `migrate_backups/{tag}/memery/`
2. 英文版历史目录 → `migrate_backups/{tag}/history/`
3. CN 会话数据库 `codebuddy-sessions.vscdb` → `migrate_backups/{tag}/`（含 WAL/SHM）

### Phase 3：执行迁移（三通道合并）

#### 3.1 Memory 迁移（追加去重合并）

```python
# 核心逻辑（migrate.py 的 migrate_memory()）
# 目标已有内容：追加去重，加上 "## Migrated from {source_uid}" 标记
# 目标为空：直接复制
```

#### 3.2 英文版对话历史迁移（目录复制）

```python
# 核心逻辑（migrate.py 的 migrate_history()）
# 遍历源账号 history/ 下所有会话目录
# 若目标目录不存在同名会话，则复制整个目录
# 若目标已存在同名会话，跳过（不覆盖）
```

#### 3.3 CN 中文版会话迁移（UPDATE userId）

```python
# 核心逻辑（migrate.py 的 migrate_cn_sessions()）
# 查询 codebuddy-sessions.vscdb 的 ItemTable
# 对每个 session:* 行，若 value.userId == source_uid，则改为 target_uid
# 事务提交后执行 PRAGMA wal_checkpoint(TRUNCATE) 确保落盘
```

### Phase 4：验证

```bash
python3 scripts/migrate.py --diagnose
# 确认源账号的 Memory/History/CN会话 已归零
# 确认目标账号的数据量已增加
```

### Phase 5：收尾

- 告知用户**重启 CodeBuddy 客户端**让变更生效
- 备份文件保留在 `~/.codebuddy/migrate_backups/{tag}/`，可手动删除
- 回滚命令：`python3 scripts/migrate.py --rollback <TAG>`

## 实际案例

```
迁移前：
  f7080610... → 15.4KB memory, 80 会话历史, 40 CN 会话
  9bc620d6... → 15.5KB memory, 10 会话历史, 0 CN 会话  ✅ 当前

迁移后：
  ✅ 78 个会话复制到目标账号
  ✅ 15.4KB 记忆追加到目标账号
  ✅ 40 个 CN 会话索引更新到目标账号
  目标账号: 15.5KB → 30.9KB, 10 会话 → 88 会话, 0 CN → 40 CN
```

## 踩坑记录

| 坑 | 说明 | 解决 |
|:---|:---|:---|
| **英文版 vs 中文版存储不同** | 英文版用 `history/` 目录，CN 版用 `codebuddy-sessions.vscdb` SQLite | 脚本自动检测并分通道处理 |
| **Memory 文件名冲突** | `{uid}_memery.md` 命名绑定账号 | 追加去重合并，非覆盖 |
| **storage.json 的 userId 过时** | 切账号后可能未更新，仍为旧 ID | 脚本读取 `genie.userId` 并交叉验证 |
| **CN 会话 DB 有 WAL 模式** | SQLite WAL 日志可能导致数据不一致 | 迁移后执行 `PRAGMA wal_checkpoint(TRUNCATE)` |
| **迁移后需重启** | CodeBuddy 客户端有内存缓存 | 迁移后提示重启 |
| **会话目录名非 UUID** | 历史目录名是 base64 编码的 workspace 路径 | 按 `index.json` 中的 `conversationId` 去重 |
| **CN 版云端优先架构** | 实际对话在腾讯云，genie-history 文件为 0B 空壳，CN 退出即删除，按云端 userId 隔离 | 本地 sessions DB 迁移只改标题索引，云端所有权不变。查看历史对话需用原始创建账号登录 CN |
| **CN 版 migrate_cn_sessions 的局限** | 仅 UPDATE sessions DB，云端对话仍属旧账号；跨账号无法显示 | 若要真正实现跨账号可见，需调用腾讯云 API 转交对话所有权（待实现） |

## 安全规则

1. **必须先备份**，Phase 2 由脚本自动执行
2. **源和目标 user_id 必须不同**，防止自我覆盖
3. **Memory 合并用追加而非覆盖**，避免丢失目标账号已有记忆
4. **历史复制用跳过而非覆盖**，已存在的会话不重复复制
5. **CN 会话用 UPDATE 而非 DELETE**，原子化事务 + WAL checkpoint
6. **迁移完成后提示重启**，确保 UI 刷新缓存

## 参考文件

- `scripts/migrate.py` — 主迁移脚本（CLI 入口）
- `tests/test_migrate.py` — pytest 33 测试用例
- `README.md` — 完整使用文档