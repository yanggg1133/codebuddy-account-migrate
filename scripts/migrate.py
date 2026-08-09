#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CodeBuddy 账号迁移工具
将旧账号的数据迁移到当前账号。

背景：
CodeBuddy 与 WorkBuddy 数据存储架构不同：
- WorkBuddy：Session / Memory / Connector 均按 user_id 隔离（workbuddy.db）
- CodeBuddy：Connector 为全局（mcp.json），
  Memory 按文件名隔离（~/.codebuddy/memery/{uid}_memery.md），
  对话历史按 user_id 隔离（%LOCALAPPDATA%/CodeBuddyExtension/Data/{uid}/CodeBuddyIDE/{uid}/history/）

因此，本工具迁移：
  1. Memory（~/.codebuddy/memery/）
  2. 本地对话历史（CodeBuddyExtension/Data/.../history/）

用法:
  python migrate.py                          # 交互式向导
  python migrate.py --diagnose               # 诊断：查看所有账号数据分布
  python migrate.py --source USER_ID         # 指定源账号迁移（Memory + 历史）
  python migrate.py --source USER_ID --yes   # 跳过确认
  python migrate.py --list-history USER_ID   # 查看指定账号的本地对话历史
  python migrate.py --rollback TIMESTAMP     # 回滚到指定备份
"""

import argparse
import json
import os
import platform
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Windows 终端可能使用 GBK/CP936 编码，强制 stdout/stderr 为 UTF-8
# pytest 运行时 sys.stdout 已被 capture manager 接管，跳过包装
_IS_PYTEST = "PYTEST_CURRENT_TEST" in os.environ or "PYTEST_VERSION" in os.environ

if platform.system() == "Windows" and not _IS_PYTEST:
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── 路径配置（可被环境变量覆盖，便于测试） ────────────────────────────────

TEST_MODE = os.environ.get("CODEBUDDY_MIGRATE_TEST", "").lower() == "1"


def _path_from_env(env_var, default_factory):
    """从环境变量获取路径，否则用默认值。测试时用于覆盖路径。"""
    val = os.environ.get(env_var, "")
    if val:
        return Path(val)
    return default_factory()


# CodeBuddy 根目录（~/.codebuddy）
CODEBUDDY_DIR = _path_from_env(
    "CODEBUDDY_MIGRATE_HOME",
    lambda: Path.home() / ".codebuddy",
)

# CodeBuddy memory 目录（注意：官方拼写为 "memery" 非 "memory"）
MEMORY_DIR = _path_from_env(
    "CODEBUDDY_MIGRATE_MEMERY",
    lambda: CODEBUDDY_DIR / "memery",
)

# storage.json 路径：跨平台支持
def _get_storage_json_path():
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / "CodeBuddy" / "User" / "globalStorage" / "storage.json"
        return Path.home() / "AppData" / "Roaming" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"
    else:
        config_home = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        return Path(config_home) / "CodeBuddy" / "User" / "globalStorage" / "storage.json"

STORAGE_JSON = _path_from_env(
    "CODEBUDDY_MIGRATE_STORAGE",
    _get_storage_json_path,
)

# mcp.json（全局，不按 user_id 隔离）
MCP_JSON = _path_from_env(
    "CODEBUDDY_MIGRATE_MCP",
    lambda: CODEBUDDY_DIR / "mcp.json",
)

# 备份目录
BACKUP_DIR = _path_from_env(
    "CODEBUDDY_MIGRATE_BACKUP",
    lambda: CODEBUDDY_DIR / "migrate_backups",
)

# CodeBuddyExtension 本地数据根目录（对话历史按 user_id 隔离）
# Windows: %LOCALAPPDATA%\CodeBuddyExtension\Data\{uid}\CodeBuddyIDE\{uid}\history\
def _default_history_base():
    system = platform.system()
    if system == "Windows":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            return Path(local) / "CodeBuddyExtension" / "Data"
        return Path.home() / "AppData" / "Local" / "CodeBuddyExtension" / "Data"
    elif system == "Darwin":
        return Path.home() / "Library" / "Caches" / "CodeBuddyExtension" / "Data"
    else:
        return Path.home() / ".cache" / "CodeBuddyExtension" / "Data"

HISTORY_BASE = _path_from_env(
    "CODEBUDDY_MIGRATE_HISTORY_BASE",
    _default_history_base,
)


# CodeBuddy CN（中文版）根目录
# Windows: %APPDATA%\CodeBuddy CN
# macOS: ~/Library/Application Support/CodeBuddy CN
# Linux: ~/.config/CodeBuddy CN
def _default_cn_base():
    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / "CodeBuddy CN"
        return Path.home() / "AppData" / "Roaming" / "CodeBuddy CN"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "CodeBuddy CN"
    else:
        config_home = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        return Path(config_home) / "CodeBuddy CN"

CODEBUDDY_CN_BASE = _path_from_env(
    "CODEBUDDY_MIGRATE_CN_BASE",
    _default_cn_base,
)

# CodeBuddy CN 会话数据库
CN_SESSIONS_DB = CODEBUDDY_CN_BASE / "codebuddy-sessions.vscdb"


def _history_dir(uid):
    """返回指定 user_id 的本地对话历史目录"""
    return HISTORY_BASE / uid / "CodeBuddyIDE" / uid / "history"


# ── 当前 user_id 检测 ────────────────────────────────────────────────────


def get_current_user_id():
    """获取当前登录的 user_id

    策略：
    1. 从 storage.json 读取 genie.userId（登录态权威来源）
    2. 从 Memory 目录中最新修改的文件推断（辅助）
    3. 优先 storage.json
    """
    storage_uid = ""
    mem_uid = ""

    # 方法1：storage.json
    try:
        with open(STORAGE_JSON, encoding="utf-8") as f:
            data = json.load(f)
        storage_uid = data.get("genie.userId", "")
    except Exception:
        pass

    # 方法2：Memory 目录中最新修改的文件
    if MEMORY_DIR.exists():
        latest = None
        for f in MEMORY_DIR.glob("*_memery.md"):
            if latest is None or f.stat().st_mtime > latest.stat().st_mtime:
                latest = f
        if latest:
            mem_uid = latest.stem.replace("_memery", "")

    if storage_uid and mem_uid and storage_uid != mem_uid:
        print(f"⚠️  检测到 user_id 不一致！")
        print(f"   storage.json (genie.userId): {storage_uid}")
        print(f"   Memory 最新文件 user_id:     {mem_uid}")
        print(f"   → 优先使用 storage.json 的 user_id（登录态权威）: {storage_uid}")
        print()

    if storage_uid:
        return storage_uid
    if mem_uid:
        return mem_uid

    print("❌ 无法获取当前 user_id")
    return ""


# ── 扫描 ─────────────────────────────────────────────────────────────────


def get_all_user_ids():
    """扫描所有已知的 user_id（仅从 Memory 目录）"""
    user_ids = set()
    if MEMORY_DIR.exists():
        for f in MEMORY_DIR.glob("*_memery.md"):
            uid = f.stem.replace("_memery", "")
            user_ids.add(uid)
    return sorted(user_ids)


def get_memory_sizes():
    """获取各 user_id 的 memory 文件大小"""
    sizes = {}
    if MEMORY_DIR.exists():
        for f in MEMORY_DIR.glob("*_memery.md"):
            uid = f.stem.replace("_memery", "")
            sizes[uid] = f.stat().st_size
    return sizes


# ── 本地对话历史扫描 ─────────────────────────────────────────────────────


def get_all_history_uids():
    """扫描 CodeBuddyExtension Data 目录下所有有历史数据的 user_id"""
    uids = set()
    if HISTORY_BASE.exists():
        for entry in HISTORY_BASE.iterdir():
            if not entry.is_dir():
                continue
            uid = entry.name
            if uid in ("Public", "default"):
                continue
            hdir = _history_dir(uid)
            if hdir.exists() and any(hdir.iterdir()):
                uids.add(uid)
    return sorted(uids)


def get_history_counts():
    """获取各 user_id 的本地对话历史会话数"""
    counts = {}
    for uid in get_all_history_uids():
        hdir = _history_dir(uid)
        n = sum(1 for x in hdir.iterdir() if x.is_dir())
        counts[uid] = n
    return counts


def get_history_sessions(uid):
    """返回指定 user_id 的本地会话列表 [(id, title, last_message_at), ...]"""
    hdir = _history_dir(uid)
    sessions = []
    if not hdir.exists():
        return sessions
    for s in sorted(hdir.iterdir()):
        if not s.is_dir():
            continue
        idx = s / "index.json"
        title = ""
        last_at = ""
        if idx.exists():
            try:
                data = json.loads(idx.read_text(encoding="utf-8"))
                convs = data.get("conversations", [])
                if convs:
                    title = convs[0].get("name", "") or ""
                    last_at = convs[0].get("lastMessageAt", "") or ""
            except Exception:
                pass
        sessions.append((s.name, title, last_at))
    return sessions


# ── CodeBuddy CN（中文版）会话数据库 ─────────────────────────────────────
#
# ⚠️ 重要限制：CodeBuddy CN 是云端优先架构
# ────────────────────────────────────────────────────────────────
# genie-history/ 中的对话文件是 0B 空壳（CN 退出时删除），实际对话内容
# 存储在腾讯云服务端。codebuddy-sessions.vscdb 只存本地元数据（标题/状态）。
#
# 本工具的 CN 迁移（migrate_cn_sessions）只能修改本地 sessions DB 的
# userId，无法改变云端对话所有权。因此：
#   - 迁移后切换账号：CN 从云端拉取对话列表时，云端返回当前账号的对话
#   - 若云端对话仍属旧账号，CN 不显示
#   - 要查看历史对话，需登录原始创建账号
#
# 真正实现 CN 版完整迁移需要调用腾讯云 API（暂未实现）。
# ────────────────────────────────────────────────────────────────


def _cn_db_conn(db_path=None):
    """打开 CodeBuddy CN 会话数据库连接"""
    db = db_path or CN_SESSIONS_DB
    if not Path(db).exists():
        return None
    return sqlite3.connect(str(db))


def get_cn_session_rows(db_path=None):
    """读取 CodeBuddy CN 会话数据库的所有 session:* 行

    返回 [(key, value_json_dict), ...]
    """
    conn = _cn_db_conn(db_path)
    if conn is None:
        return []
    rows = []
    try:
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM ItemTable WHERE key LIKE 'session:%'")
        for k, v in cur.fetchall():
            try:
                rows.append((k, json.loads(v)))
            except Exception:
                pass
    finally:
        conn.close()
    return rows


def get_all_cn_uids(db_path=None):
    """扫描 CodeBuddy CN 会话数据库中的所有 user_id"""
    uids = set()
    for _, data in get_cn_session_rows(db_path):
        uid = data.get("userId", "")
        if uid:
            uids.add(uid)
    return sorted(uids)


def get_cn_session_counts(db_path=None):
    """统计 CodeBuddy CN 会话数据库中每个 user_id 的会话数"""
    counts = {}
    for _, data in get_cn_session_rows(db_path):
        uid = data.get("userId", "")
        if uid:
            counts[uid] = counts.get(uid, 0) + 1
    return counts


def migrate_cn_sessions(source_uid, target_uid, db_path=None):
    """迁移 CodeBuddy CN 会话数据库：把源账号的 session 记录 userId 改为目标账号

    对每个 session:* 行，若 value.userId == source_uid，则改为 target_uid。
    返回迁移的记录数。
    """
    db = db_path or CN_SESSIONS_DB
    if not Path(db).exists():
        print(f"  ⏭️  CodeBuddy CN 会话数据库不存在，跳过: {db}")
        return 0

    conn = sqlite3.connect(str(db))
    migrated = 0
    try:
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM ItemTable WHERE key LIKE 'session:%'")
        updates = []
        for k, v in cur.fetchall():
            try:
                data = json.loads(v)
            except Exception:
                continue
            if data.get("userId", "") == source_uid:
                data["userId"] = target_uid
                updates.append((k, json.dumps(data, ensure_ascii=False)))
        for k, v in updates:
            cur.execute("UPDATE ItemTable SET value=? WHERE key=?", (v, k))
        conn.commit()
        migrated = len(updates)
    finally:
        # 确保 WAL 落盘
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        conn.close()
    return migrated


# ── 诊断 ─────────────────────────────────────────────────────────────────


def diagnose():
    """诊断模式：展示所有账号数据分布"""
    current_uid = get_current_user_id()
    all_uids = get_all_user_ids()
    memory_sizes = get_memory_sizes()
    history_counts = get_history_counts()
    cn_counts = get_cn_session_counts()

    print("=" * 70)
    print("CodeBuddy 账号数据诊断")
    print("=" * 70)
    print(f"\n当前登录: {current_uid}\n")

    # 合并所有 user_id（memory + history + CN sessions）
    all_accounts = sorted(set(all_uids) | set(history_counts.keys()) | set(cn_counts.keys()))

    print(f"{'user_id':<40} {'Memory':>10} {'History':>8} {'CN会话':>8} {'当前':>4}")
    print("-" * 74)

    for uid in all_accounts:
        ms = memory_sizes.get(uid, 0)
        ms_str = f"{ms / 1024:.1f}KB" if ms > 0 else "-"
        hc = history_counts.get(uid, 0)
        hc_str = f"{hc} 会话" if hc > 0 else "-"
        cc = cn_counts.get(uid, 0)
        cc_str = f"{cc} 会话" if cc > 0 else "-"
        is_current = "✅" if uid == current_uid else ""
        print(f"{uid:<40} {ms_str:>10} {hc_str:>8} {cc_str:>8} {is_current:>4}")

    print(f"\n总计: {len(all_accounts)} 个账号")

    # 检查全局文件
    print(f"\n全局文件（不按 user_id 隔离，无需迁移）:")
    print(f"  mcp.json:   {'✅ 存在' if MCP_JSON.exists() else '❌ 不存在'}")
    print(f"  storage.json: {'✅ 存在' if STORAGE_JSON.exists() else '❌ 不存在'}")
    print(f"\nCodeBuddy CN 会话数据库:")
    print(f"  {CN_SESSIONS_DB}: {'✅ 存在' if CN_SESSIONS_DB.exists() else '❌ 不存在'}")

    if len(all_accounts) <= 1:
        print("\n⚠️  只发现一个账号，无需迁移。")
        return

    other_uids = [u for u in all_accounts if u != current_uid]
    if other_uids:
        print("\n💡 迁移建议（Memory + 本地对话历史 + CN 会话）:")
        for uid in other_uids:
            ms = memory_sizes.get(uid, 0)
            hc = history_counts.get(uid, 0)
            cc = cn_counts.get(uid, 0)
            parts = []
            if ms > 0:
                parts.append(f"{ms / 1024:.1f}KB memory")
            if hc > 0:
                parts.append(f"{hc} 个会话历史")
            if cc > 0:
                parts.append(f"{cc} 个 CN 会话")
            print(f"   {uid[:20]}... → 当前账号 ({', '.join(parts)})")
        print(f"\n   执行命令: python migrate.py --source {other_uids[0]}")


# ── 备份 ─────────────────────────────────────────────────────────────────


def create_backup(target_uid, timestamp):
    """创建备份（Memory + 本地对话历史 + mcp.json）"""
    BACKUP_DIR.mkdir(exist_ok=True)
    backup_tag = f"{timestamp}_{target_uid[:8]}"
    backup_path = BACKUP_DIR / backup_tag
    backup_path.mkdir(exist_ok=True)

    # 备份 Memory
    mem_file = MEMORY_DIR / f"{target_uid}_memery.md"
    if mem_file.exists():
        shutil.copy2(str(mem_file), str(backup_path / f"{target_uid}_memery.md"))
        print(f"  ✅ 已备份 Memory → {backup_path / f'{target_uid}_memery.md'}")

    # 备份本地对话历史（仅目标账号目录）
    src_hist = _history_dir(target_uid)
    if src_hist.exists():
        dst_hist = backup_path / "history"
        shutil.copytree(str(src_hist), str(dst_hist))
        print(f"  ✅ 已备份对话历史（{sum(1 for x in src_hist.iterdir() if x.is_dir())} 会话）")

    # 备份 mcp.json（全局，但备份以防万一）
    if MCP_JSON.exists():
        shutil.copy2(str(MCP_JSON), str(backup_path / "mcp.json"))
        print(f"  ✅ 已备份 mcp.json")

    # 备份 CodeBuddy CN 会话数据库
    if CN_SESSIONS_DB.exists():
        shutil.copy2(str(CN_SESSIONS_DB), str(backup_path / "codebuddy-sessions.vscdb"))
        # 同时备份 WAL/SHM（若存在）
        for suffix in ("-wal", "-shm"):
            f = Path(str(CN_SESSIONS_DB) + suffix)
            if f.exists():
                shutil.copy2(str(f), str(backup_path / f"codebuddy-sessions.vscdb{suffix}"))
        print(f"  ✅ 已备份 CodeBuddy CN 会话数据库")

    # 写入元数据
    meta = {
        "timestamp": timestamp,
        "target_uid": target_uid,
        "created_at": datetime.now().isoformat(),
    }
    with open(backup_path / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"  📦 备份标签: {backup_tag}")
    return backup_tag


# ── 迁移 ─────────────────────────────────────────────────────────────────


def migrate_memory(source_uid, target_uid):
    """迁移 Memory 文件（追加合并）"""
    src_file = MEMORY_DIR / f"{source_uid}_memery.md"
    dst_file = MEMORY_DIR / f"{target_uid}_memery.md"

    if not src_file.exists():
        print(f"  ⏭️  源账号无 Memory 文件，跳过")
        return

    src_content = src_file.read_text(encoding="utf-8").strip()

    if not src_content:
        print(f"  ⏭️  源账号 Memory 为空，跳过")
        return

    if not dst_file.exists():
        dst_file.write_text(src_content, encoding="utf-8")
        print(f"  ✅ 复制 Memory（目标为空，直接复制 {len(src_content)} 字符）")
        return

    # 追加去重
    dst_content = dst_file.read_text(encoding="utf-8").strip()
    src_lines = src_content.split("\n")
    dst_lines_set = set(dst_content.split("\n"))
    new_lines = [l for l in src_lines if l.strip() and l not in dst_lines_set]

    if not new_lines:
        print(f"  ⏭️  源账号 Memory 内容已存在于目标，跳过")
        return

    with open(dst_file, "a", encoding="utf-8") as f:
        f.write(f"\n\n---\n## 迁移自 {source_uid[:12]}...\n\n")
        f.write("\n".join(new_lines))
        f.write("\n")

    print(f"  ✅ 追加 {len(new_lines)} 行新内容到 Memory")


def migrate_history(source_uid, target_uid):
    """迁移本地对话历史（按会话目录复制，已存在则跳过）"""
    src_dir = _history_dir(source_uid)
    dst_dir = _history_dir(target_uid)

    if not src_dir.exists():
        print(f"  ⏭️  源账号无本地对话历史，跳过")
        return 0

    # 源账号会话目录列表
    src_sessions = [s for s in src_dir.iterdir() if s.is_dir()]
    if not src_sessions:
        print(f"  ⏭️  源账号对话历史为空，跳过")
        return 0

    # 目标已存在会话（按目录名去重）
    dst_existing = set()
    if dst_dir.exists():
        dst_existing = {s.name for s in dst_dir.iterdir() if s.is_dir()}

    copied = 0
    for s in src_sessions:
        if s.name in dst_existing:
            continue
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(s), str(dst_dir / s.name))
        copied += 1

    if copied:
        print(f"  ✅ 迁移 {copied} 个对话历史会话 → {dst_dir}")
    else:
        print(f"  ⏭️  对话历史已全部存在于目标，跳过")
    return copied


def migrate(source_uid, target_uid=None, skip_confirm=False):
    """执行完整迁移流程（Memory + 本地对话历史）"""
    if target_uid is None:
        target_uid = get_current_user_id()
    if not target_uid:
        print("❌ 无法获取目标账号 user_id，请确认 CodeBuddy 已登录")
        print("   也可使用 --target <USER_ID> 手动指定目标账号")
        sys.exit(1)

    if source_uid == target_uid:
        print("❌ 源账号和目标账号相同，无需迁移")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    print("=" * 70)
    print("CodeBuddy 账号迁移（Memory + 本地对话历史）")
    print("=" * 70)
    print(f"\n  源账号:   {source_uid}")
    print(f"  目标账号: {target_uid} (当前登录)")
    print()

    print("📊 Phase 1: 诊断数据分布...")
    memory_sizes = get_memory_sizes()
    history_counts = get_history_counts()
    cn_counts = get_cn_session_counts()
    src_memory = memory_sizes.get(source_uid, 0)
    tgt_memory = memory_sizes.get(target_uid, 0)
    src_history = history_counts.get(source_uid, 0)
    tgt_history = history_counts.get(target_uid, 0)
    src_cn = cn_counts.get(source_uid, 0)
    tgt_cn = cn_counts.get(target_uid, 0)
    print(f"  源账号: {src_memory / 1024:.1f}KB memory, {src_history} 个会话历史, {src_cn} 个 CN 会话")
    print(f"  目标账号: {tgt_memory / 1024:.1f}KB memory, {tgt_history} 个会话历史, {tgt_cn} 个 CN 会话")

    if src_memory == 0 and src_history == 0 and src_cn == 0:
        print("\n⚠️  源账号无 Memory 也无对话历史，无需迁移")
        return

    if not skip_confirm:
        print()
        answer = input("确认执行迁移？(y/N): ").strip().lower()
        if answer != "y":
            print("已取消")
            return

    print("\n📦 Phase 2: 创建备份...")
    backup_tag = create_backup(target_uid, timestamp)

    print("\n🔄 Phase 3: 执行迁移...")
    if src_memory > 0:
        print("\n  [Memory 迁移]")
        migrate_memory(source_uid, target_uid)
    if src_history > 0:
        print("\n  [对话历史迁移]")
        migrate_history(source_uid, target_uid)
    if src_cn > 0:
        print("\n  [CodeBuddy CN 会话迁移]")
        n = migrate_cn_sessions(source_uid, target_uid)
        if n > 0:
            print(f"  ✅ 迁移 {n} 个 CN 会话记录 → {target_uid[:12]}...")
        else:
            print(f"  ⏭️  CN 会话无需迁移")

    # 验证
    print("\n✅ Phase 4: 验证...")
    new_size = memory_sizes.get(target_uid, 0)
    dst_file = MEMORY_DIR / f"{target_uid}_memery.md"
    if dst_file.exists():
        new_size = dst_file.stat().st_size
    print(f"  目标账号 Memory: {tgt_memory / 1024:.1f}KB → {new_size / 1024:.1f}KB")
    new_hc = len(get_history_sessions(target_uid))
    print(f"  目标账号 对话历史: {tgt_history} → {new_hc} 个会话")
    new_cn = get_cn_session_counts().get(target_uid, 0)
    print(f"  目标账号 CN 会话: {tgt_cn} → {new_cn} 个会话")

    print("\n" + "=" * 70)
    print("迁移完成！")
    print("=" * 70)
    print(f"\n  📦 备份标签: {backup_tag}")
    print(f"\n  ⚠️  请重启 CodeBuddy 让变更生效！")
    print(f"  📁 备份位置: {BACKUP_DIR / backup_tag}")
    print(f"  🔙 回滚命令: python migrate.py --rollback {backup_tag}")


# ── 回滚 ─────────────────────────────────────────────────────────────────


def rollback(backup_tag):
    """回滚到指定备份"""
    backup_path = BACKUP_DIR / backup_tag
    if not backup_path.exists():
        print(f"❌ 备份不存在: {backup_tag}")
        sys.exit(1)

    meta_file = backup_path / "meta.json"
    target_uid = ""
    if meta_file.exists():
        with open(meta_file) as f:
            meta = json.load(f)
        target_uid = meta.get("target_uid", "")

    print("=" * 70)
    print("CodeBuddy 账号迁移回滚")
    print("=" * 70)
    print(f"\n  备份标签: {backup_tag}")
    print(f"  目标账号: {target_uid}")
    print()

    answer = input("确认回滚？这将覆盖当前数据！(y/N): ").strip().lower()
    if answer != "y":
        print("已取消")
        return

    if target_uid:
        mem_backup = backup_path / f"{target_uid}_memery.md"
        mem_target = MEMORY_DIR / f"{target_uid}_memery.md"
        if mem_backup.exists() and mem_target.exists():
            shutil.copy2(str(mem_backup), str(mem_target))
            print("  ✅ 已恢复 Memory")

        # 恢复对话历史（仅当备份里有 history 目录且目标存在时）
        hist_backup = backup_path / "history"
        hist_target = _history_dir(target_uid)
        if hist_backup.exists() and hist_target.exists():
            # 删除现有目标历史目录，恢复备份
            if hist_target.exists():
                shutil.rmtree(str(hist_target))
            shutil.copytree(str(hist_backup), str(hist_target))
            print("  ✅ 已恢复对话历史")

    mcp_backup = backup_path / "mcp.json"
    if mcp_backup.exists() and MCP_JSON.exists():
        shutil.copy2(str(mcp_backup), str(MCP_JSON))
        print("  ✅ 已恢复 mcp.json")

    # 恢复 CodeBuddy CN 会话数据库
    cn_backup = backup_path / "codebuddy-sessions.vscdb"
    if cn_backup.exists() and CN_SESSIONS_DB.exists():
        shutil.copy2(str(cn_backup), str(CN_SESSIONS_DB))
        # 恢复 WAL/SHM
        for suffix in ("-wal", "-shm"):
            f = backup_path / f"codebuddy-sessions.vscdb{suffix}"
            if f.exists():
                dst = Path(str(CN_SESSIONS_DB) + suffix)
                shutil.copy2(str(f), str(dst))
        print("  ✅ 已恢复 CodeBuddy CN 会话数据库")

    print("\n  ⚠️  请重启 CodeBuddy 让变更生效！")


# ── 交互式向导 ───────────────────────────────────────────────────────────


def interactive_migrate():
    """交互式迁移向导"""
    all_uids = get_all_user_ids()
    memory_sizes = get_memory_sizes()

    if len(all_uids) <= 1:
        print("⚠️  只发现一个账号，无需迁移。")
        return

    print("=" * 70)
    print("CodeBuddy 账号迁移向导（仅 Memory）")
    print("=" * 70)
    print("\n请选择迁移方向：先选【目标账号】，再选【源账号】\n")
    print(f"  {'序号':<4} {'user_id':<40} {'Memory':>10}")
    print("  " + "-" * 56)
    for i, uid in enumerate(all_uids, 1):
        ms = memory_sizes.get(uid, 0)
        ms_str = f"{ms / 1024:.1f}KB" if ms > 0 else "-"
        print(f"  {i:<4} {uid:<40} {ms_str:>10}")

    current_uid = get_current_user_id()
    print(f"\n  当前登录: {current_uid}")
    print(f"  ⚠️  如果「当前登录」显示有误，请按实际登录状态选择。\n")

    while True:
        try:
            choice = input("请选择【目标账号】（接收数据的账号，输入序号）: ").strip()
            if choice.lower() == "q":
                print("已取消")
                return
            idx = int(choice) - 1
            if 0 <= idx < len(all_uids):
                target_uid = all_uids[idx]
                print(f"  ✅ 目标账号: {target_uid[:20]}...")
                break
            else:
                print(f"⚠️  无效序号，请输入 1-{len(all_uids)}")
        except ValueError:
            print("⚠️  请输入数字或 q")
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            return

    other_uids = [u for u in all_uids if u != target_uid]
    print()
    print(f"  可迁移到 {target_uid[:20]}... 的源账号：\n")
    print(f"  {'序号':<4} {'user_id':<40} {'Memory':>10}")
    print("  " + "-" * 56)
    for i, uid in enumerate(other_uids, 1):
        ms = memory_sizes.get(uid, 0)
        ms_str = f"{ms / 1024:.1f}KB" if ms > 0 else "-"
        print(f"  {i:<4} {uid:<40} {ms_str:>10}")

    while True:
        try:
            choice = input("\n请选择【源账号】（要迁移出的账号，输入序号）: ").strip()
            if choice.lower() == "q":
                print("已取消")
                return
            idx = int(choice) - 1
            if 0 <= idx < len(other_uids):
                source_uid = other_uids[idx]
                break
            else:
                print(f"⚠️  无效序号，请输入 1-{len(other_uids)}")
        except ValueError:
            print("⚠️  请输入数字或 q")
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            return

    print(f"\n  源账号:   {source_uid[:20]}...")
    print(f"  目标账号: {target_uid[:20]}...")
    print()
    migrate(source_uid, target_uid=target_uid)


def list_history(uid):
    """列出指定账号的本地对话历史"""
    sessions = get_history_sessions(uid)
    if not sessions:
        print(f"❌ 账号 {uid[:20]}... 没有本地对话历史")
        return

    print("=" * 70)
    print(f"账号 {uid[:20]}... 的本地对话历史（{len(sessions)} 个会话）")
    print("=" * 70)
    for sid, title, last_at in sessions:
        ts = last_at[:10] if last_at else "?"
        t = title[:50] if title else "(无标题)"
        print(f"  {ts}  {t}")
    print(f"\n  📁 存储位置: {_history_dir(uid)}")


# ── Main ─────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="CodeBuddy 账号迁移工具（Memory + 本地对话历史）")
    parser.add_argument("--diagnose", "-d", action="store_true", help="诊断模式：查看所有账号数据分布")
    parser.add_argument("--source", "-s", type=str, help="源账号 user_id")
    parser.add_argument("--target", "-t", type=str, help="目标账号 user_id（默认从 storage.json 自动推断）")
    parser.add_argument("--yes", "-y", action="store_true", help="跳过确认直接迁移")
    parser.add_argument("--rollback", "-r", type=str, help="回滚到指定备份标签")
    parser.add_argument("--list-history", "-l", type=str, help="列出指定账号的本地对话历史")

    args = parser.parse_args()

    if args.diagnose:
        diagnose()
    elif args.rollback:
        rollback(args.rollback)
    elif args.list_history:
        list_history(args.list_history)
    elif args.source:
        migrate(args.source, target_uid=args.target, skip_confirm=args.yes)
    else:
        interactive_migrate()


if __name__ == "__main__":
    main()