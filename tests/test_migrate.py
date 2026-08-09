"""
CodeBuddy 账号迁移工具 — pytest 测试套件

测试策略：
- 使用 tempfile 创建隔离的临时目录，避免触碰真实数据
- 通过 CODEBUDDY_MIGRATE_* 环境变量覆盖所有路径
- 覆盖：user_id 检测、扫描、Memory 迁移（5 种场景）、备份、诊断、回滚、完整流程
"""

import json
import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# 模块路径
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

# 环境变量先设，再导入模块（模块 import 时会读这些变量）
_TMP_ENV = {}


def _set_env(key, val):
    _TMP_ENV[key] = os.environ.get(key, None)
    os.environ[key] = val


def _unset_env(key):
    if _TMP_ENV.get(key) is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = _TMP_ENV[key]


@pytest.fixture(autouse=True)
def clean_env():
    """确保测试前无残留环境变量"""
    for k in list(os.environ):
        if k.startswith("CODEBUDDY_MIGRATE_"):
            os.environ.pop(k, None)
    yield
    for k in list(os.environ):
        if k.startswith("CODEBUDDY_MIGRATE_"):
            os.environ.pop(k, None)


@pytest.fixture
def tmp_home(tmp_path):
    """创建临时 HOME 目录，模拟 ~/.codebuddy/ 结构"""
    codebuddy = tmp_path / ".codebuddy"
    memery = codebuddy / "memery"
    memery.mkdir(parents=True)

    # 创建全局 mcp.json
    mcp = codebuddy / "mcp.json"
    mcp.write_text(json.dumps({"mcpServers": {"test": {}}}), encoding="utf-8")

    # 创建 storage.json（模拟 Windows 路径）
    appdata_dir = tmp_path / "AppData"
    appdata_dir.mkdir(parents=True)
    storage_dir = appdata_dir / "CodeBuddy" / "User" / "globalStorage"
    storage_dir.mkdir(parents=True)
    storage = storage_dir / "storage.json"
    storage.write_text(json.dumps({"genie.userId": "user-current-000"}), encoding="utf-8")

    # 创建 CodeBuddyExtension Data 目录（模拟本地对话历史）
    data_dir = tmp_path / "Local" / "CodeBuddyExtension" / "Data"
    data_dir.mkdir(parents=True)

    yield tmp_path


def _write_history(tmp_home, uid, session_id, title="Test Session"):
    """创建模拟的本地对话历史会话目录"""
    hdir = (tmp_home / "Local" / "CodeBuddyExtension" / "Data" / uid
            / "CodeBuddyIDE" / uid / "history" / session_id)
    hdir.mkdir(parents=True)
    conv_dir = hdir / "conv-1"
    conv_dir.mkdir()
    (conv_dir / "messages").mkdir()
    (conv_dir / "messages" / "msg1.json").write_text(
        json.dumps({"role": "user", "message": "hello"}), encoding="utf-8")
    idx = {
        "conversations": [{
            "id": "conv-1",
            "name": title,
            "lastMessageAt": "2026-08-08T10:00:00.000Z",
        }],
        "current": "conv-1",
    }
    (hdir / "index.json").write_text(json.dumps(idx), encoding="utf-8")
    return hdir


def _write_memory(dir_path: Path, uid: str, content: str):
    f = dir_path / f"{uid}_memery.md"
    f.write_text(content, encoding="utf-8")
    return f


def _set_all_env(tmp_home):
    """设置所有 CODEBUDDY_MIGRATE_* 环境变量指向临时目录"""
    _set_env("CODEBUDDY_MIGRATE_STORAGE",
             str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
    _set_env("CODEBUDDY_MIGRATE_MEMERY", str(tmp_home / ".codebuddy" / "memery"))
    _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
    _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
    _set_env("CODEBUDDY_MIGRATE_HISTORY_BASE",
             str(tmp_home / "Local" / "CodeBuddyExtension" / "Data"))
    _set_env("CODEBUDDY_MIGRATE_CN_BASE", str(tmp_home / "AppData" / "CodeBuddy CN"))


def _read_memory(dir_path: Path, uid: str) -> str:
    f = dir_path / f"{uid}_memery.md"
    return f.read_text(encoding="utf-8")


def _create_cn_db(db_path: Path, sessions):
    """创建模拟的 CodeBuddy CN 会话数据库

    sessions: [(conversation_id, user_id, title), ...]
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
    for cid, uid, title in sessions:
        value = json.dumps({
            "conversationId": cid,
            "cwd": "e:/download/test",
            "userId": uid,
            "title": title,
            "status": "Completed",
            "createdAt": 1770000000000,
            "updatedAt": 1770000000000,
        }, ensure_ascii=False)
        conn.execute("INSERT INTO ItemTable (key, value) VALUES (?, ?)",
                     (f"session:{cid}", value))
    conn.commit()
    conn.close()
    return db_path


def _import_mod():
    """动态导入模块（环境变量已设好后）"""
    import importlib
    # 清除缓存
    for key in list(sys.modules):
        if key == "migrate":
            del sys.modules[key]
    return importlib.import_module("migrate")


# ── 测试：get_current_user_id ─────────────────────────────────────────────


class TestGetCurrentUserId:

    def test_from_storage_json(self, tmp_home):
        _set_env("CODEBUDDY_MIGRATE_STORAGE",
                  str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(tmp_home / ".codebuddy" / "memery"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        uid = mod.get_current_user_id()
        assert uid == "user-current-000"

    def test_storage_and_memory_conflict(self, tmp_home):
        memery_dir = tmp_home / ".codebuddy" / "memery"
        _write_memory(memery_dir, "user-old-111", "# Old content")
        _set_env("CODEBUDDY_MIGRATE_STORAGE",
                  str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(memery_dir))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        # 当前登录账号优先，即使 Memory 文件更新
        uid = mod.get_current_user_id()
        assert uid == "user-current-000"

    def test_no_storage_falls_back_to_memory(self, tmp_home):
        memery_dir = tmp_home / ".codebuddy" / "memery"
        _write_memory(memery_dir, "user-only-999", "# Only this user")
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_path := tmp_home / "nonexistent.json"))
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(memery_dir))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        uid = mod.get_current_user_id()
        assert uid == "user-only-999"


# ── 测试：扫描 ────────────────────────────────────────────────────────────


class TestScan:

    def test_scan_all_user_ids(self, tmp_home):
        memery_dir = tmp_home / ".codebuddy" / "memery"
        _write_memory(memery_dir, "uid-aaa", "# A")
        _write_memory(memery_dir, "uid-bbb", "# B")
        _write_memory(memery_dir, "uid-ccc", "# C")
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(memery_dir))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        uids = mod.get_all_user_ids()
        assert set(uids) == {"uid-aaa", "uid-bbb", "uid-ccc"}

    def test_memory_sizes(self, tmp_home):
        memery_dir = tmp_home / ".codebuddy" / "memery"
        _write_memory(memery_dir, "uid-small", "x")
        _write_memory(memery_dir, "uid-large", "y" * 10000)
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(memery_dir))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        sizes = mod.get_memory_sizes()
        assert sizes["uid-small"] == 1
        assert sizes["uid-large"] == 10000

    def test_empty_dir(self, tmp_home):
        memery_dir = tmp_home / ".codebuddy" / "memery"
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(memery_dir))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        uids = mod.get_all_user_ids()
        assert uids == []


# ── 测试：migrate_memory ──────────────────────────────────────────────────


class TestMigrateMemory:

    def test_source_not_exists(self, tmp_home):
        memery_dir = tmp_home / ".codebuddy" / "memery"
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(memery_dir))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        mod.migrate_memory("uid-nonexistent", "uid-target")
        assert not (memery_dir / "uid-target_memery.md").exists()

    def test_source_empty_content(self, tmp_home):
        memery_dir = tmp_home / ".codebuddy" / "memery"
        _write_memory(memery_dir, "uid-empty", "   \n\n  ")
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(memery_dir))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        mod.migrate_memory("uid-empty", "uid-target")
        assert not (memery_dir / "uid-target_memery.md").exists()

    def test_target_not_exists_copy(self, tmp_home):
        memery_dir = tmp_home / ".codebuddy" / "memery"
        content = "# User Profile\n> Last updated: 2026-01-01\n\n## Skills\n- Python"
        _write_memory(memery_dir, "uid-src", content)
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(memery_dir))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        mod.migrate_memory("uid-src", "uid-tgt")
        result = _read_memory(memery_dir, "uid-tgt")
        assert result == content

    def test_target_exists_append_dedup(self, tmp_home):
        memery_dir = tmp_home / ".codebuddy" / "memery"
        tgt = "# User Profile\n> Last updated: 2026-01-01\n\n## Skills\n- Python"
        _write_memory(memery_dir, "uid-tgt", tgt)
        src = "# User Profile\n> Last updated: 2026-01-01\n\n## Skills\n- Python\n- New Skill"
        _write_memory(memery_dir, "uid-src", src)
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(memery_dir))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        mod.migrate_memory("uid-src", "uid-tgt")
        result = _read_memory(memery_dir, "uid-tgt")
        assert "# User Profile" in result
        assert "- New Skill" in result
        # 去重：- Python 只出现一次
        assert result.count("- Python") == 1

    def test_target_already_has_all_content(self, tmp_home):
        memery_dir = tmp_home / ".codebuddy" / "memery"
        content = "# User Profile\n> Last updated: 2026-01-01"
        _write_memory(memery_dir, "uid-tgt", content)
        _write_memory(memery_dir, "uid-src", content)
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(memery_dir))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        mod.migrate_memory("uid-src", "uid-tgt")
        result = _read_memory(memery_dir, "uid-tgt")
        assert result.strip() == content

    def test_append_with_migration_marker(self, tmp_home):
        memery_dir = tmp_home / ".codebuddy" / "memery"
        _write_memory(memery_dir, "uid-tgt", "# Existing")
        _write_memory(memery_dir, "uid-src", "# New Section\n- Item 1")
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(memery_dir))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        mod.migrate_memory("uid-src", "uid-tgt")
        result = _read_memory(memery_dir, "uid-tgt")
        assert "迁移自 uid-src" in result
        assert "- Item 1" in result


# ── 测试：create_backup ───────────────────────────────────────────────────


class TestCreateBackup:

    def test_creates_backup_directory_and_files(self, tmp_home):
        memery_dir = tmp_home / ".codebuddy" / "memery"
        _write_memory(memery_dir, "user-current-000", "# Test Memory")
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(memery_dir))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        tag = mod.create_backup("user-current-000", "20260808180000")
        assert tag == "20260808180000_user-cur"

        backup_dir = tmp_home / ".codebuddy" / "migrate_backups" / tag
        assert backup_dir.exists()
        assert (backup_dir / "user-current-000_memery.md").exists()
        assert (backup_dir / "mcp.json").exists()
        assert (backup_dir / "meta.json").exists()

        meta = json.loads((backup_dir / "meta.json").read_text())
        assert meta["target_uid"] == "user-current-000"
        assert meta["timestamp"] == "20260808180000"

    def test_backup_content_matches(self, tmp_home):
        memery_dir = tmp_home / ".codebuddy" / "memery"
        content = "# Test Content 中文测试"
        _write_memory(memery_dir, "user-current-000", content)
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(memery_dir))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        tag = mod.create_backup("user-current-000", "20260808180000")
        backup_dir = tmp_home / ".codebuddy" / "migrate_backups" / tag
        backed_up = (backup_dir / "user-current-000_memery.md").read_text(encoding="utf-8")
        assert backed_up == content


# ── 测试：diagnose ────────────────────────────────────────────────────────


class TestDiagnose:

    def test_diagnose_output(self, tmp_home, capsys):
        memery_dir = tmp_home / ".codebuddy" / "memery"
        _write_memory(memery_dir, "user-current-000", "x" * 100)
        _write_memory(memery_dir, "user-old-111", "y" * 2000)
        _set_all_env(tmp_home)
        mod = _import_mod()

        mod.diagnose()
        captured = capsys.readouterr()
        assert "CodeBuddy 账号数据诊断" in captured.out
        assert "user-current-000" in captured.out
        assert "user-old-111" in captured.out
        assert "✅" in captured.out
        assert "迁移建议" in captured.out

    def test_diagnose_single_account(self, tmp_home, capsys):
        memery_dir = tmp_home / ".codebuddy" / "memery"
        _write_memory(memery_dir, "user-current-000", "# Only one")
        _set_all_env(tmp_home)
        mod = _import_mod()

        mod.diagnose()
        captured = capsys.readouterr()
        assert "只发现一个账号" in captured.out


# ── 测试：rollback ────────────────────────────────────────────────────────


class TestRollback:

    def test_rollback_restores_files(self, tmp_home):
        memery_dir = tmp_home / ".codebuddy" / "memery"
        tag = "20260808180000_user-cur"
        backup_dir = tmp_home / ".codebuddy" / "migrate_backups" / tag
        backup_dir.mkdir(parents=True)
        (backup_dir / "user-current-000_memery.md").write_text("# Original Memory", encoding="utf-8")
        (backup_dir / "mcp.json").write_text(json.dumps({"old": "config"}), encoding="utf-8")
        (backup_dir / "meta.json").write_text(
            json.dumps({"target_uid": "user-current-000", "timestamp": "20260808180000"}), encoding="utf-8")

        _write_memory(memery_dir, "user-current-000", "# Migrated Content")
        mcp = tmp_home / ".codebuddy" / "mcp.json"
        mcp.write_text(json.dumps({"new": "config"}), encoding="utf-8")

        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(memery_dir))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(mcp))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        with patch("builtins.input", return_value="y"):
            mod.rollback(tag)

        assert _read_memory(memery_dir, "user-current-000") == "# Original Memory"
        assert json.loads(mcp.read_text()) == {"old": "config"}

    def test_rollback_nonexistent(self, tmp_home, capsys):
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(tmp_home / ".codebuddy" / "memery"))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        with pytest.raises(SystemExit):
            mod.rollback("nonexistent_tag")
        captured = capsys.readouterr()
        assert "备份不存在" in captured.out


# ── 测试：history 扫描 ───────────────────────────────────────────────────


class TestHistoryScan:

    def test_get_all_history_uids(self, tmp_home):
        _write_history(tmp_home, "uid-aaa", "sess-1", "Session A")
        _write_history(tmp_home, "uid-bbb", "sess-2", "Session B")
        _set_all_env(tmp_home)
        mod = _import_mod()
        uids = mod.get_all_history_uids()
        assert set(uids) == {"uid-aaa", "uid-bbb"}

    def test_get_history_counts(self, tmp_home):
        _write_history(tmp_home, "uid-aaa", "sess-1", "A")
        _write_history(tmp_home, "uid-aaa", "sess-2", "B")
        _write_history(tmp_home, "uid-bbb", "sess-3", "C")
        _set_all_env(tmp_home)
        mod = _import_mod()
        counts = mod.get_history_counts()
        assert counts["uid-aaa"] == 2
        assert counts["uid-bbb"] == 1

    def test_get_history_sessions_titles(self, tmp_home):
        _write_history(tmp_home, "uid-aaa", "sess-1", "我的会话")
        _set_all_env(tmp_home)
        mod = _import_mod()
        sessions = mod.get_history_sessions("uid-aaa")
        assert len(sessions) == 1
        sid, title, last_at = sessions[0]
        assert sid == "sess-1"
        assert title == "我的会话"
        assert last_at.startswith("2026-08-08")

    def test_no_history_dir_returns_empty(self, tmp_home):
        _set_all_env(tmp_home)
        mod = _import_mod()
        assert mod.get_history_sessions("uid-nobody") == []
        assert mod.get_history_counts() == {}


# ── 测试：migrate_history ────────────────────────────────────────────────


class TestMigrateHistory:

    def test_copy_sessions_to_target(self, tmp_home):
        _write_history(tmp_home, "uid-src", "sess-1", "A")
        _write_history(tmp_home, "uid-src", "sess-2", "B")
        _set_all_env(tmp_home)
        mod = _import_mod()

        copied = mod.migrate_history("uid-src", "uid-tgt")
        assert copied == 2
        dst = tmp_home / "Local" / "CodeBuddyExtension" / "Data" / "uid-tgt" / "CodeBuddyIDE" / "uid-tgt" / "history"
        assert (dst / "sess-1" / "index.json").exists()
        assert (dst / "sess-2" / "index.json").exists()

    def test_skip_existing_sessions(self, tmp_home):
        _write_history(tmp_home, "uid-src", "sess-1", "A")
        _write_history(tmp_home, "uid-src", "sess-2", "B")
        _write_history(tmp_home, "uid-tgt", "sess-1", "A-dup")
        _set_all_env(tmp_home)
        mod = _import_mod()

        copied = mod.migrate_history("uid-src", "uid-tgt")
        assert copied == 1
        dst = tmp_home / "Local" / "CodeBuddyExtension" / "Data" / "uid-tgt" / "CodeBuddyIDE" / "uid-tgt" / "history"
        # 已存在的 sess-1 不被覆盖
        idx = json.loads((dst / "sess-1" / "index.json").read_text(encoding="utf-8"))
        assert idx["conversations"][0]["name"] == "A-dup"

    def test_source_no_history_returns_zero(self, tmp_home):
        _set_all_env(tmp_home)
        mod = _import_mod()
        assert mod.migrate_history("uid-empty", "uid-tgt") == 0


# ── 测试：migrate 主流程 ─────────────────────────────────────────────────


class TestMigrate:

    def test_same_source_target_exits(self, tmp_home, capsys):
        memery_dir = tmp_home / ".codebuddy" / "memery"
        _write_memory(memery_dir, "user-current-000", "# Test")
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(memery_dir))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        with pytest.raises(SystemExit):
            mod.migrate("user-current-000", "user-current-000", skip_confirm=True)

    def test_source_empty_returns_early(self, tmp_home, capsys):
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(tmp_home / ".codebuddy" / "memery"))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        mod.migrate("uid-nonexistent", "user-current-000", skip_confirm=True)
        captured = capsys.readouterr()
        assert "源账号无" in captured.out or "无需迁移" in captured.out

    def test_full_migration_flow(self, tmp_home, capsys):
        memery_dir = tmp_home / ".codebuddy" / "memery"
        _write_memory(memery_dir, "user-current-000", "# Current\n- Existing")
        _write_memory(memery_dir, "user-old-111", "# Old\n- Old item 1\n- Old item 2")
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(memery_dir))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        mod.migrate("user-old-111", "user-current-000", skip_confirm=True)
        captured = capsys.readouterr()

        assert "迁移完成" in captured.out
        assert "备份标签" in captured.out
        assert "CodeBuddy" in captured.out

        result = _read_memory(memery_dir, "user-current-000")
        assert "# Current" in result
        assert "- Existing" in result
        assert "- Old item 1" in result
        assert "- Old item 2" in result


# ── 测试：CodeBuddy CN 会话迁移 ──────────────────────────────────────────


class TestMigrateCnSessions:

    def test_cn_db_read(self, tmp_home):
        """CN 会话数据库读取"""
        cn_base = tmp_home / "AppData" / "CodeBuddy CN"
        db_path = cn_base / "codebuddy-sessions.vscdb"
        _create_cn_db(db_path, [
            ("conv-1", "user-old-111", "First session"),
            ("conv-2", "user-old-111", "Second session"),
            ("conv-3", "user-current-000", "Current session"),
        ])
        _set_env("CODEBUDDY_MIGRATE_CN_BASE", str(cn_base))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(tmp_home / ".codebuddy" / "memery"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        rows = mod.get_cn_session_rows()
        assert len(rows) == 3

        uids = mod.get_all_cn_uids()
        assert "user-old-111" in uids
        assert "user-current-000" in uids

        counts = mod.get_cn_session_counts()
        assert counts.get("user-old-111") == 2
        assert counts.get("user-current-000") == 1

    def test_migrate_cn_sessions(self, tmp_home):
        """CN 会话迁移：userId 更新"""
        cn_base = tmp_home / "AppData" / "CodeBuddy CN"
        db_path = cn_base / "codebuddy-sessions.vscdb"
        _create_cn_db(db_path, [
            ("conv-1", "user-old-111", "First"),
            ("conv-2", "user-old-111", "Second"),
            ("conv-3", "user-current-000", "Current"),
        ])
        _set_env("CODEBUDDY_MIGRATE_CN_BASE", str(cn_base))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(tmp_home / ".codebuddy" / "memery"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        n = mod.migrate_cn_sessions("user-old-111", "user-current-000")
        assert n == 2

        # 验证迁移后结果
        counts = mod.get_cn_session_counts()
        assert counts.get("user-old-111", 0) == 0
        assert counts.get("user-current-000") == 3

    def test_migrate_cn_sessions_no_db(self, tmp_home, capsys):
        """CN 数据库不存在时跳过"""
        cn_base = tmp_home / "AppData" / "CodeBuddy CN"
        _set_env("CODEBUDDY_MIGRATE_CN_BASE", str(cn_base))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(tmp_home / ".codebuddy" / "memery"))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        n = mod.migrate_cn_sessions("user-old-111", "user-current-000")
        assert n == 0

    def test_cn_sessions_in_diagnose(self, tmp_home, capsys):
        """诊断输出包含 CN 会话统计"""
        cn_base = tmp_home / "AppData" / "CodeBuddy CN"
        _create_cn_db(cn_base / "codebuddy-sessions.vscdb", [
            ("conv-1", "user-old-111", "Old session"),
        ])
        _set_all_env(tmp_home)
        _set_env("CODEBUDDY_MIGRATE_CN_BASE", str(cn_base))
        mod = _import_mod()

        mod.diagnose()
        captured = capsys.readouterr()
        # 诊断输出应包含 CN 会话列
        assert "CN会话" in captured.out
        assert "CodeBuddy CN 会话数据库" in captured.out

    def test_cn_sessions_in_migrate_flow(self, tmp_home, capsys):
        """完整迁移流程中包含 CN 会话迁移"""
        memery_dir = tmp_home / ".codebuddy" / "memery"
        _write_memory(memery_dir, "user-current-000", "# Current")
        _write_memory(memery_dir, "user-old-111", "# Old")
        cn_base = tmp_home / "AppData" / "CodeBuddy CN"
        _create_cn_db(cn_base / "codebuddy-sessions.vscdb", [
            ("conv-1", "user-old-111", "Old session"),
            ("conv-2", "user-old-111", "Another old"),
        ])
        _set_env("CODEBUDDY_MIGRATE_CN_BASE", str(cn_base))
        _set_env("CODEBUDDY_MIGRATE_STORAGE", str(tmp_home / "AppData" / "CodeBuddy" / "User" / "globalStorage" / "storage.json"))
        _set_env("CODEBUDDY_MIGRATE_MEMERY", str(memery_dir))
        _set_env("CODEBUDDY_MIGRATE_MCP", str(tmp_home / ".codebuddy" / "mcp.json"))
        _set_env("CODEBUDDY_MIGRATE_BACKUP", str(tmp_home / ".codebuddy" / "migrate_backups"))
        mod = _import_mod()

        mod.migrate("user-old-111", "user-current-000", skip_confirm=True)
        captured = capsys.readouterr()

        assert "迁移完成" in captured.out
        assert "CN 会话" in captured.out
        # 验证 CN 会话已迁移
        counts = mod.get_cn_session_counts()
        assert counts.get("user-old-111", 0) == 0
        assert counts.get("user-current-000") == 2