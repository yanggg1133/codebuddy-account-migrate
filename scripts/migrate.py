#!/usr/bin/env python3
"""
WorkBuddy 账号迁移工具
将旧账号的 Session、Memory、Connector 数据迁移到当前登录账号

用法:
  python3 migrate.py                           # 交互式向导（推荐）
  python3 migrate.py --diagnose                # 诊断模式：查看所有账号数据分布
  python3 migrate.py --source USER_ID          # 指定源账号迁移（高级用户）
  python3 migrate.py --source USER_ID --yes    # 跳过确认直接迁移
  python3 migrate.py --rollback TIMESTAMP      # 回滚到指定备份
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

WORKBUDDY_DIR = Path.home() / ".workbuddy"
DB_PATH = WORKBUDDY_DIR / "workbuddy.db"
MEMORY_DIR = WORKBUDDY_DIR / "memory"
CONNECTORS_DIR = WORKBUDDY_DIR / "connectors"
STORAGE_JSON = Path.home() / "Library" / "Application Support" / "WorkBuddy" / "User" / "globalStorage" / "storage.json"

# 备份目录
BACKUP_DIR = WORKBUDDY_DIR / "migrate_backups"


def get_current_user_id():
    """获取当前登录的 user_id"""
    try:
        with open(STORAGE_JSON) as f:
            data = json.load(f)
        return data.get("genie.userId", "")
    except Exception as e:
        print(f"❌ 无法读取当前 user_id: {e}")
        return ""


def get_all_user_ids():
    """扫描所有已知的 user_id"""
    user_ids = set()

    # 从 DB
    if DB_PATH.exists():
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        try:
            cur.execute("SELECT DISTINCT user_id FROM sessions WHERE user_id IS NOT NULL")
            for row in cur.fetchall():
                user_ids.add(row[0])
        except sqlite3.OperationalError:
            pass
        conn.close()

    # 从 memory 文件
    if MEMORY_DIR.exists():
        for f in MEMORY_DIR.glob("*_memory.md"):
            uid = f.stem.replace("_memory", "")
            user_ids.add(uid)

    # 从 connectors 目录
    if CONNECTORS_DIR.exists():
        for d in CONNECTORS_DIR.iterdir():
            if d.is_dir() and d.name not in ("default", "skills") and not d.name.startswith("."):
                # 检查是否是 UUID 格式
                if "-" in d.name:
                    user_ids.add(d.name)

    return sorted(user_ids)


def get_session_counts():
    """获取各 user_id 的 session 数量"""
    counts = {}
    if DB_PATH.exists():
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        try:
            cur.execute("SELECT user_id, COUNT(*) FROM sessions WHERE user_id IS NOT NULL GROUP BY user_id")
            for row in cur.fetchall():
                counts[row[0]] = row[1]
        except sqlite3.OperationalError:
            pass
        conn.close()
    return counts


def get_memory_sizes():
    """获取各 user_id 的 memory 文件大小"""
    sizes = {}
    if MEMORY_DIR.exists():
        for f in MEMORY_DIR.glob("*_memory.md"):
            uid = f.stem.replace("_memory", "")
            sizes[uid] = f.stat().st_size
    return sizes


def get_connector_info():
    """获取各 user_id 的 connector 配置信息"""
    info = {}
    if CONNECTORS_DIR.exists():
        for d in CONNECTORS_DIR.iterdir():
            if d.is_dir() and d.name not in ("default", "skills") and "-" in d.name:
                mcp_file = d / "mcp.json"
                states_file = d / "connector-states.json"
                mcp_servers = 0
                states_count = 0
                if mcp_file.exists():
                    try:
                        with open(mcp_file) as f:
                            mcp_data = json.load(f)
                        mcp_servers = len(mcp_data.get("mcpServers", {}))
                    except:
                        pass
                if states_file.exists():
                    try:
                        with open(states_file) as f:
                            states_data = json.load(f)
                        states_count = len(states_data) if isinstance(states_data, dict) else 0
                    except:
                        pass
                info[d.name] = {"mcp_servers": mcp_servers, "connector_states": states_count}
    return info


def diagnose():
    """诊断模式：展示所有账号数据分布"""
    current_uid = get_current_user_id()
    all_uids = get_all_user_ids()
    session_counts = get_session_counts()
    memory_sizes = get_memory_sizes()
    connector_info = get_connector_info()

    print("=" * 70)
    print("WorkBuddy 账号数据诊断")
    print("=" * 70)
    print(f"\n当前登录: {current_uid}\n")

    print(f"{'user_id':<40} {'Sessions':>8} {'Memory':>10} {'Connectors':>12} {'当前':>4}")
    print("-" * 80)

    for uid in all_uids:
        sc = session_counts.get(uid, 0)
        ms = memory_sizes.get(uid, 0)
        ms_str = f"{ms / 1024:.1f}KB" if ms > 0 else "-"
        ci = connector_info.get(uid, {})
        conn_str = f"{ci.get('mcp_servers', 0)}mcp/{ci.get('connector_states', 0)}conn" if ci else "-"
        is_current = "✅" if uid == current_uid else ""
        print(f"{uid:<40} {sc:>8} {ms_str:>10} {conn_str:>12} {is_current:>4}")

    print(f"\n总计: {len(all_uids)} 个账号")
    print()

    if len(all_uids) <= 1:
        print("⚠️  只发现一个账号，无需迁移。")
        return

    # 建议迁移方向
    other_uids = [u for u in all_uids if u != current_uid]
    if other_uids:
        print("💡 迁移建议:")
        for uid in other_uids:
            sc = session_counts.get(uid, 0)
            ms = memory_sizes.get(uid, 0)
            print(f"   {uid[:20]}... → 当前账号 ({sc} sessions, {ms / 1024:.1f}KB memory)")
        print(f"\n   执行命令: python3 migrate.py --source {other_uids[0]}")


def create_backup(target_uid, timestamp):
    """创建备份"""
    BACKUP_DIR.mkdir(exist_ok=True)
    backup_tag = f"{timestamp}_{target_uid[:8]}"
    backup_path = BACKUP_DIR / backup_tag
    backup_path.mkdir(exist_ok=True)

    # 备份数据库
    if DB_PATH.exists():
        shutil.copy2(str(DB_PATH), str(backup_path / "workbuddy.db"))
        print(f"  ✅ 已备份数据库 → {backup_path / 'workbuddy.db'}")

    # 备份 Memory
    mem_file = MEMORY_DIR / f"{target_uid}_memory.md"
    if mem_file.exists():
        shutil.copy2(str(mem_file), str(backup_path / f"{target_uid}_memory.md"))
        print(f"  ✅ 已备份 Memory → {backup_path / f'{target_uid}_memory.md'}")

    # 备份 Connectors
    conn_dir = CONNECTORS_DIR / target_uid
    if conn_dir.exists():
        dst_dir = backup_path / target_uid
        if dst_dir.exists():
            shutil.rmtree(str(dst_dir))
        shutil.copytree(str(conn_dir), str(dst_dir))
        print(f"  ✅ 已备份 Connectors → {backup_path / target_uid}/")

    # 写入备份元数据
    meta = {
        "timestamp": timestamp,
        "target_uid": target_uid,
        "created_at": datetime.now().isoformat(),
    }
    with open(backup_path / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"  📦 备份标签: {backup_tag}")
    return backup_tag


def migrate_sessions(source_uid, target_uid):
    """迁移 Session 历史"""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # 先 checkpoint WAL
    cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # 统计
    cur.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (source_uid,))
    count = cur.fetchone()[0]

    if count == 0:
        print(f"  ⏭️  源账号无 session，跳过")
        conn.close()
        return 0

    # 执行迁移
    cur.execute("UPDATE sessions SET user_id = ? WHERE user_id = ?", (target_uid, source_uid))
    migrated = cur.rowcount
    conn.commit()
    conn.close()

    print(f"  ✅ 迁移 {migrated} 个 session（{source_uid[:12]}... → {target_uid[:12]}...）")
    return migrated


def migrate_memory(source_uid, target_uid):
    """迁移 Memory 文件（追加合并）"""
    src_file = MEMORY_DIR / f"{source_uid}_memory.md"
    dst_file = MEMORY_DIR / f"{target_uid}_memory.md"

    if not src_file.exists():
        print(f"  ⏭️  源账号无 Memory 文件，跳过")
        return

    src_content = src_file.read_text(encoding="utf-8").strip()

    if not src_content:
        print(f"  ⏭️  源账号 Memory 为空，跳过")
        return

    if not dst_file.exists():
        # 目标不存在，直接复制
        dst_file.write_text(src_content, encoding="utf-8")
        print(f"  ✅ 复制 Memory（目标为空，直接复制 {len(src_content)} 字符）")
        return

    # 目标已存在，追加去重
    dst_content = dst_file.read_text(encoding="utf-8").strip()

    # 按行去重
    src_lines = src_content.split("\n")
    dst_lines_set = set(dst_content.split("\n"))
    new_lines = [l for l in src_lines if l.strip() and l not in dst_lines_set]

    if not new_lines:
        print(f"  ⏭️  源账号 Memory 内容已存在于目标，跳过")
        return

    # 追加
    with open(dst_file, "a", encoding="utf-8") as f:
        f.write(f"\n\n---\n## 迁移自 {source_uid[:12]}...\n\n")
        f.write("\n".join(new_lines))
        f.write("\n")

    print(f"  ✅ 追加 {len(new_lines)} 行新内容到 Memory")


def deep_merge_dict(source, target):
    """深度合并字典，target 中已有的 key 保留不动"""
    for k, v in source.items():
        if k not in target:
            target[k] = v
        elif isinstance(v, dict) and isinstance(target[k], dict):
            deep_merge_dict(v, target[k])
    return target


def migrate_connectors(source_uid, target_uid):
    """迁移 Connector 配置（深度合并）"""
    src_dir = CONNECTORS_DIR / source_uid
    dst_dir = CONNECTORS_DIR / target_uid

    if not src_dir.exists():
        print(f"  ⏭️  源账号无 Connector 目录，跳过")
        return

    # 确保目标目录存在
    dst_dir.mkdir(exist_ok=True)

    for fname in ["mcp.json", "connector-states.json"]:
        src_file = src_dir / fname
        dst_file = dst_dir / fname

        if not src_file.exists():
            continue

        with open(src_file, encoding="utf-8") as f:
            src_data = json.load(f)

        if dst_file.exists():
            with open(dst_file, encoding="utf-8") as f:
                dst_data = json.load(f)

            if isinstance(src_data, dict) and isinstance(dst_data, dict):
                # 深度合并
                added_keys = [k for k in src_data if k not in dst_data]
                if added_keys:
                    deep_merge_dict(src_data, dst_data)
                    with open(dst_file, "w", encoding="utf-8") as f:
                        json.dump(dst_data, f, indent=2, ensure_ascii=False)
                    print(f"  ✅ 合并 {fname}（新增 {len(added_keys)} 个 key: {added_keys[:5]}...）")
                else:
                    print(f"  ⏭️  {fname} 无新增内容，跳过")
            else:
                print(f"  ⚠️  {fname} 类型冲突，跳过（源={type(src_data).__name__}, 目标={type(dst_data).__name__}）")
        else:
            with open(dst_file, "w", encoding="utf-8") as f:
                json.dump(src_data, f, indent=2, ensure_ascii=False)
            print(f"  ✅ 复制 {fname}（目标不存在）")


def migrate(source_uid, skip_confirm=False):
    """执行完整迁移流程"""
    target_uid = get_current_user_id()
    if not target_uid:
        print("❌ 无法获取当前登录 user_id，请确认 WorkBuddy 已登录")
        sys.exit(1)

    if source_uid == target_uid:
        print("❌ 源账号和目标账号相同，无需迁移")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    print("=" * 70)
    print("WorkBuddy 账号迁移")
    print("=" * 70)
    print(f"\n  源账号:   {source_uid}")
    print(f"  目标账号: {target_uid} (当前登录)")
    print()

    # Phase 1: 诊断
    print("📊 Phase 1: 诊断数据分布...")
    session_counts = get_session_counts()
    memory_sizes = get_memory_sizes()
    src_sessions = session_counts.get(source_uid, 0)
    src_memory = memory_sizes.get(source_uid, 0)
    print(f"  源账号: {src_sessions} sessions, {src_memory / 1024:.1f}KB memory")
    print(f"  目标账号: {session_counts.get(target_uid, 0)} sessions, {memory_sizes.get(target_uid, 0) / 1024:.1f}KB memory")

    if src_sessions == 0 and src_memory == 0:
        print("\n⚠️  源账号无任何数据，无需迁移")
        return

    # 确认
    if not skip_confirm:
        print()
        answer = input("确认执行迁移？(y/N): ").strip().lower()
        if answer != "y":
            print("已取消")
            return

    # Phase 2: 备份
    print("\n📦 Phase 2: 创建备份...")
    backup_tag = create_backup(target_uid, timestamp)

    # Phase 3: 迁移
    print("\n🔄 Phase 3: 执行迁移...")

    print("\n  [Session 迁移]")
    migrated_sessions = migrate_sessions(source_uid, target_uid)

    print("\n  [Memory 迁移]")
    migrate_memory(source_uid, target_uid)

    print("\n  [Connector 迁移]")
    migrate_connectors(source_uid, target_uid)

    # Phase 4: 验证
    print("\n✅ Phase 4: 验证...")
    new_session_counts = get_session_counts()
    new_target_sessions = new_session_counts.get(target_uid, 0)
    print(f"  当前账号 session 数: {session_counts.get(target_uid, 0)} → {new_target_sessions}")

    # Phase 5: 收尾
    print("\n" + "=" * 70)
    print("迁移完成！")
    print("=" * 70)
    print(f"\n  📦 备份标签: {backup_tag}")
    print(f"  🔄 已迁移: {migrated_sessions} sessions + memory + connectors")
    print(f"\n  ⚠️  请重启 WorkBuddy 客户端让变更生效！")
    print(f"  📁 备份位置: {BACKUP_DIR / backup_tag}")
    print(f"  🔙 回滚命令: python3 migrate.py --rollback {backup_tag}")


def rollback(backup_tag):
    """回滚到指定备份"""
    backup_path = BACKUP_DIR / backup_tag
    if not backup_path.exists():
        print(f"❌ 备份不存在: {backup_tag}")
        sys.exit(1)

    # 读取元数据
    meta_file = backup_path / "meta.json"
    if meta_file.exists():
        with open(meta_file) as f:
            meta = json.load(f)
        target_uid = meta.get("target_uid", "")
    else:
        # 从文件名推算
        target_uid = ""

    print("=" * 70)
    print("WorkBuddy 账号迁移回滚")
    print("=" * 70)
    print(f"\n  备份标签: {backup_tag}")
    print(f"  目标账号: {target_uid}")
    print()

    answer = input("确认回滚？这将覆盖当前数据！(y/N): ").strip().lower()
    if answer != "y":
        print("已取消")
        return

    # 恢复数据库
    db_backup = backup_path / "workbuddy.db"
    if db_backup.exists():
        shutil.copy2(str(db_backup), str(DB_PATH))
        print("  ✅ 已恢复数据库")

    # 恢复 Memory
    if target_uid:
        mem_backup = backup_path / f"{target_uid}_memory.md"
        mem_target = MEMORY_DIR / f"{target_uid}_memory.md"
        if mem_backup.exists() and mem_target.exists():
            shutil.copy2(str(mem_backup), str(mem_target))
            print("  ✅ 已恢复 Memory")

    # 恢复 Connectors
    conn_backup = backup_path / target_uid
    conn_target = CONNECTORS_DIR / target_uid
    if conn_backup.exists() and conn_target.exists():
        if conn_target.exists():
            shutil.rmtree(str(conn_target))
        shutil.copytree(str(conn_backup), str(conn_target))
        print("  ✅ 已恢复 Connectors")

    print("\n  ⚠️  请重启 WorkBuddy 客户端让变更生效！")


def interactive_migrate():
    """交互式迁移向导：自动诊断，用户选序号即可"""
    current_uid = get_current_user_id()
    if not current_uid:
        print("❌ 无法获取当前登录 user_id，请确认 WorkBuddy 已登录")
        sys.exit(1)

    all_uids = get_all_user_ids()
    session_counts = get_session_counts()
    memory_sizes = get_memory_sizes()
    connector_info = get_connector_info()

    print("=" * 70)
    print("WorkBuddy 账号迁移向导")
    print("=" * 70)
    print(f"\n当前登录: {current_uid}\n")

    if len(all_uids) <= 1:
        print("⚠️  只发现一个账号，无需迁移。")
        return

    # 列出可迁移的账号
    other_uids = [u for u in all_uids if u != current_uid]
    if not other_uids:
        print("⚠️  没有找到可迁移的其他账号。")
        return

    print("发现以下可迁移的账号：\n")
    print(f"  {'序号':<4} {'Sessions':>8} {'Memory':>10} {'Connectors':>12}")
    print("  " + "-" * 40)
    for i, uid in enumerate(other_uids, 1):
        sc = session_counts.get(uid, 0)
        ms = memory_sizes.get(uid, 0)
        ms_str = f"{ms / 1024:.1f}KB" if ms > 0 else "-"
        ci = connector_info.get(uid, {})
        conn_str = f"{ci.get('mcp_servers', 0)}mcp/{ci.get('connector_states', 0)}conn" if ci else "-"
        print(f"  {i:<4} {sc:>8} {ms_str:>10} {conn_str:>12}")

    print()

    # 用户选择
    while True:
        try:
            choice = input("请输入要迁移的账号序号（输入 q 取消）: ").strip()
            if choice.lower() == "q":
                print("已取消")
                return
            idx = int(choice) - 1
            if 0 <= idx < len(other_uids):
                source_uid = other_uids[idx]
                break
            else:
                print(f"⚠️  无效序号，请输入 1-{len(other_uids)} 之间的数字")
        except ValueError:
            print("⚠️  请输入数字或 q")
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            return

    print(f"\n已选择: {source_uid[:20]}... ({session_counts.get(source_uid, 0)} sessions)")
    migrate(source_uid)


def main():
    parser = argparse.ArgumentParser(description="WorkBuddy 账号迁移工具")
    parser.add_argument("--diagnose", "-d", action="store_true", help="诊断模式：查看所有账号数据分布")
    parser.add_argument("--source", "-s", type=str, help="源账号 user_id（要迁移出的账号）")
    parser.add_argument("--yes", "-y", action="store_true", help="跳过确认直接迁移")
    parser.add_argument("--rollback", "-r", type=str, help="回滚到指定备份标签")

    args = parser.parse_args()

    if args.diagnose:
        diagnose()
    elif args.rollback:
        rollback(args.rollback)
    elif args.source:
        migrate(args.source, skip_confirm=args.yes)
    else:
        # 无参数时进入交互式向导
        interactive_migrate()


if __name__ == "__main__":
    main()
