"""
db.py - 数据库交互层
封装所有 SQLite CRUD 操作。
"""

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from config import DB_PATH, DEFAULT_GLOBAL_INSTRUCTIONS


# ---------------------------------------------------------------------------
# 连接管理
# ---------------------------------------------------------------------------

@contextmanager
def get_conn():
    """线程安全的数据库连接上下文管理器。"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row          # 让查询结果支持列名访问
    conn.execute("PRAGMA foreign_keys = ON") # 启用外键约束
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------

def init_db() -> None:
    """创建所有表（幂等），并写入默认全局配置。"""
    ddl = """
    CREATE TABLE IF NOT EXISTS divination_sessions (
        session_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        name             TEXT    NOT NULL DEFAULT 'New Divination',
        created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        initial_prompt_data TEXT
    );

    CREATE TABLE IF NOT EXISTS chat_history (
        message_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id   INTEGER NOT NULL,
        message_uuid TEXT    UNIQUE NOT NULL,
        sender       TEXT    NOT NULL CHECK (sender IN ('user', 'assistant')),
        content      TEXT    NOT NULL,
        timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        model_used   TEXT,
        FOREIGN KEY (session_id) REFERENCES divination_sessions(session_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS global_config (
        config_key   TEXT PRIMARY KEY,
        config_value TEXT NOT NULL
    );
    """
    with get_conn() as conn:
        conn.executescript(ddl)
        # 只在 key 不存在时插入默认值
        conn.execute(
            "INSERT OR IGNORE INTO global_config (config_key, config_value) VALUES (?, ?)",
            ("global_instructions", DEFAULT_GLOBAL_INSTRUCTIONS),
        )


# ---------------------------------------------------------------------------
# 占卜会话 CRUD
# ---------------------------------------------------------------------------

def create_session(name: str = "New Divination", initial_prompt_data: str = "") -> int:
    """
    创建新的占卜会话。
    返回新建 session 的 session_id。
    """
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO divination_sessions (name, initial_prompt_data) VALUES (?, ?)",
            (name, initial_prompt_data),
        )
        return cur.lastrowid


def get_session_data(session_id: int) -> Optional[dict]:
    """获取单个会话的完整元数据，不存在则返回 None。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM divination_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None


def get_all_sessions() -> list[dict]:
    """返回所有会话，按创建时间降序排列（最新在前）。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM divination_sessions ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def update_session_name(session_id: int, name: str) -> None:
    """重命名会话。"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE divination_sessions SET name = ? WHERE session_id = ?",
            (name, session_id),
        )


def delete_session(session_id: int) -> None:
    """删除会话（CASCADE 会同时删除关联的 chat_history 记录）。"""
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM divination_sessions WHERE session_id = ?",
            (session_id,),
        )


# ---------------------------------------------------------------------------
# 聊天记录 CRUD
# ---------------------------------------------------------------------------

def add_message(
    session_id: int,
    sender: str,
    content: str,
    model_used: Optional[str] = None,
) -> dict:
    """
    向指定会话写入一条聊天记录。
    sender: 'user' 或 'assistant'
    返回写入后的完整记录 dict。
    """
    msg_uuid = str(uuid.uuid4())
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO chat_history
               (session_id, message_uuid, sender, content, timestamp, model_used)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, msg_uuid, sender, content, ts, model_used),
        )
        return {
            "message_id": cur.lastrowid,
            "session_id": session_id,
            "message_uuid": msg_uuid,
            "sender": sender,
            "content": content,
            "timestamp": ts,
            "model_used": model_used,
        }


def get_chat_history(
    session_id: int,
    model_used: Optional[str] = None,
) -> list[dict]:
    """
    获取某会话的聊天记录，按时间升序。
    如果指定 model_used，则只返回该模型产生的消息（用户消息不区分模型，全部返回）。

    隔离规则（用户消息也绑定模型，彻底隔离各模型对话线程）：
    - model_used IS NULL → 返回所有记录（初始卦象等全局消息）
    - model_used 指定    → 只返回该模型的消息（含用户和助手）
                           以及 model_used IS NULL 的助手消息（初始卦象）
    """
    with get_conn() as conn:
        if model_used is None:
            rows = conn.execute(
                "SELECT * FROM chat_history WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM chat_history
                   WHERE session_id = ?
                     AND (model_used = ? OR model_used IS NULL)
                   ORDER BY timestamp ASC""",
                (session_id, model_used),
            ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 全局配置 CRUD
# ---------------------------------------------------------------------------

def get_global_instructions() -> str:
    """读取全局指令字符串。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT config_value FROM global_config WHERE config_key = 'global_instructions'"
        ).fetchone()
        return row["config_value"] if row else ""


def update_global_instructions(instructions: str) -> None:
    """更新（或插入）全局指令。"""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO global_config (config_key, config_value) VALUES ('global_instructions', ?)
               ON CONFLICT(config_key) DO UPDATE SET config_value = excluded.config_value""",
            (instructions,),
        )


def get_config_value(key: str) -> Optional[str]:
    """通用读取任意配置项。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT config_value FROM global_config WHERE config_key = ?",
            (key,),
        ).fetchone()
        return row["config_value"] if row else None


def set_config_value(key: str, value: str) -> None:
    """通用写入任意配置项（UPSERT）。"""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO global_config (config_key, config_value) VALUES (?, ?)
               ON CONFLICT(config_key) DO UPDATE SET config_value = excluded.config_value""",
            (key, value),
        )


# ---------------------------------------------------------------------------
# 快速自测（直接运行此文件时执行）
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    print("[db] 数据库初始化完成，路径:", DB_PATH)

    sid = create_session("测试会话", "初始卦象数据")
    print("[db] 新建会话 session_id:", sid)

    add_message(sid, "user", "帮我解读一下这一卦", None)
    add_message(sid, "assistant", "此卦为乾卦，刚健有为……", "gpt-4o")
    add_message(sid, "user", "用心理学角度呢？", None)
    add_message(sid, "assistant", "从荣格分析心理学来看……", "claude-sonnet-4-6")

    print("[db] gpt-4o 历史:", get_chat_history(sid, "gpt-4o"))
    print("[db] claude 历史:", get_chat_history(sid, "claude-sonnet-4-6"))
    print("[db] 全局指令:", get_global_instructions())
    print("[db] 所有会话:", get_all_sessions())
