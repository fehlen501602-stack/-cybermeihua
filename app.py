"""
app.py - CyberMeihua Streamlit 应用入口

布局：
  侧边栏  — 全局配置 + 起卦表单 + 占卜记录列表
  主区域  — 聊天界面（含模型切换下拉）
"""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

_LOCAL_TZ = ZoneInfo("Europe/Berlin")

import streamlit as st

import db
import llm_router
from scraper import fetch_divination_data

# ---------------------------------------------------------------------------
# 页面基础配置
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="赛博梅花 CyberMeihua",
    page_icon="🌸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# 数据库初始化（首次运行时建表）
# ---------------------------------------------------------------------------

db.init_db()

# ---------------------------------------------------------------------------
# Session State 初始化
# ---------------------------------------------------------------------------

if "active_session_id" not in st.session_state:
    st.session_state.active_session_id = None

if "active_model" not in st.session_state:
    st.session_state.active_model = llm_router.get_available_models()[0]

if "last_error" not in st.session_state:
    st.session_state.last_error = None

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _format_divination_result(data: dict) -> str:
    """将起卦结果格式化为 Markdown 字符串，作为会话初始消息。"""
    if not data.get("success"):
        return f"起卦失败：{data.get('error', '未知错误')}"

    hex_ = data.get("hexagram") or {}
    nuc  = data.get("nuclear_hexagram") or {}
    bia  = data.get("changing_hexagram") or {}
    line = data.get("changing_line", 0)

    parts = [
        f"## 🌸 起卦结果",
        f"**时间**：{data.get('note', '')}",
        f"**农历**：{data.get('eight', '')}",
        "",
        f"### 本卦：{hex_.get('name', '')}（{hex_.get('gua', '')}）",
        hex_.get("src", "")[:300] + ("…" if len(hex_.get("src", "")) > 300 else ""),
        "",
        f"### 动爻：第 {line} 爻",
        data.get("hexagram", {}).get("changing_line_text", "")[:300],
        "",
        f"### 互卦：{nuc.get('name', '')}（{nuc.get('gua', '')}）",
        f"### 变卦：{bia.get('name', '')}（{bia.get('gua', '')}）",
    ]
    return "\n".join(parts)


def _load_chat_history(session_id: int, model: str) -> list[dict]:
    return db.get_chat_history(session_id, model_used=model)


# ---------------------------------------------------------------------------
# 侧边栏
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🌸 赛博梅花")
    st.markdown("---")

    # ── API Key 配置 ─────────────────────────────────────────────
    with st.expander("🔑 API Keys", expanded=False):
        for label, key in [
            ("OpenAI",    "OPENAI_API_KEY"),
            ("Anthropic", "ANTHROPIC_API_KEY"),
            ("Google",    "GOOGLE_API_KEY"),
            ("DeepSeek",  "DEEPSEEK_API_KEY"),
        ]:
            saved = db.get_config_value(key) or ""
            val = st.text_input(
                label,
                value=saved,
                type="password",
                key=f"apikey_{key}",
            )
            if val != saved:
                db.set_config_value(key, val)

    # ── 全局配置 ────────────────────────────────────────────────
    with st.expander("⚙️ 全局指令", expanded=False):
        current_instructions = db.get_global_instructions()
        new_instructions = st.text_area(
            "全局 System Prompt（所有对话均自动注入）",
            value=current_instructions,
            height=120,
            key="global_instructions_input",
        )
        if st.button("保存全局指令", key="save_instructions"):
            db.update_global_instructions(new_instructions)
            st.success("已保存")

    st.markdown("---")

    # ── 起卦表单 ────────────────────────────────────────────────
    st.subheader("🎴 新建占卜")

    div_tab_time, div_tab_num = st.tabs(["⏰ 时间起卦", "🔢 数字起卦"])

    with div_tab_time:
        col1, col2 = st.columns(2)
        with col1:
            divination_date = st.date_input(
                "日期",
                value=datetime.now(tz=_LOCAL_TZ).date(),
                key="div_date",
            )
        with col2:
            divination_hour = st.number_input(
                "时辰（0-23）",
                min_value=0, max_value=23,
                value=datetime.now(tz=_LOCAL_TZ).hour,
                key="div_hour",
            )
        session_name_time = st.text_input(
            "会话名称（可留空）",
            placeholder="例：今日事业运势",
            key="session_name_time",
        )
        if st.button("🌸 时间起卦", use_container_width=True, key="start_time_div"):
            dt_str = f"{divination_date} {divination_hour:02d}"
            with st.spinner("起卦中…"):
                result = fetch_divination_data({"method": "time", "datetime": dt_str})
            formatted = _format_divination_result(result)
            name = session_name_time.strip() or (
                result.get("hexagram", {}).get("name", "新占卜") + " " +
                divination_date.strftime("%m/%d")
            )
            sid = db.create_session(name=name, initial_prompt_data=json.dumps(result, ensure_ascii=False))
            db.add_message(sid, "assistant", formatted, model_used=None)
            st.session_state.active_session_id = sid
            st.rerun()

    with div_tab_num:
        div_number = st.number_input(
            "起卦数字（任意正整数）",
            min_value=1, max_value=999999,
            value=8,
            key="div_number",
        )
        div_num_hour = st.number_input(
            "时辰（0-23，默认当前）",
            min_value=0, max_value=23,
            value=datetime.now(tz=_LOCAL_TZ).hour,
            key="div_num_hour",
        )
        session_name_num = st.text_input(
            "会话名称（可留空）",
            placeholder="例：数字 88 问财运",
            key="session_name_num",
        )
        if st.button("🌸 数字起卦", use_container_width=True, key="start_num_div"):
            with st.spinner("起卦中…"):
                result = fetch_divination_data({
                    "method": "number",
                    "number": div_number,
                    "hour": div_num_hour,
                })
            formatted = _format_divination_result(result)
            name = session_name_num.strip() or (
                result.get("hexagram", {}).get("name", "新占卜") + f" #{div_number}"
            )
            sid = db.create_session(name=name, initial_prompt_data=json.dumps(result, ensure_ascii=False))
            db.add_message(sid, "assistant", formatted, model_used=None)
            st.session_state.active_session_id = sid
            st.rerun()

    st.markdown("---")

    # ── 占卜记录列表 ────────────────────────────────────────────
    st.subheader("📜 占卜记录")

    sessions = db.get_all_sessions()
    if not sessions:
        st.caption("暂无记录，请先起卦。")
    else:
        for s in sessions:
            label = f"{'▶ ' if s['session_id'] == st.session_state.active_session_id else ''}{s['name']}"
            if st.button(label, key=f"session_{s['session_id']}", use_container_width=True):
                st.session_state.active_session_id = s["session_id"]
                st.rerun()

        # 重命名 / 删除当前会话
        if st.session_state.active_session_id:
            st.markdown("---")
            new_name = st.text_input(
                "重命名当前会话",
                placeholder="输入新名称后按 Enter",
                key="rename_input",
                label_visibility="collapsed",
            )
            col_rename, col_delete = st.columns(2)
            with col_rename:
                if st.button("✏️ 重命名", use_container_width=True, key="rename_session"):
                    if new_name.strip():
                        db.update_session_name(st.session_state.active_session_id, new_name.strip())
                        st.rerun()
                    else:
                        st.warning("名称不能为空")
            with col_delete:
                if st.button("🗑️ 删除", use_container_width=True, key="delete_session"):
                    db.delete_session(st.session_state.active_session_id)
                    st.session_state.active_session_id = None
                    st.rerun()


# ---------------------------------------------------------------------------
# 主区域：聊天界面
# ---------------------------------------------------------------------------

if st.session_state.active_session_id is None:
    # 未选中任何会话时的欢迎页
    st.markdown(
        """
        <div style='text-align:center; margin-top: 120px'>
            <h1>🌸 赛博梅花</h1>
            <p style='font-size:1.1rem; color:#888'>
                融合梅花易数与 AI 的占卜助手<br>
                在左侧填写时间，点击「开始起卦」开始新的占卜
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    session_id = st.session_state.active_session_id
    session_data = db.get_session_data(session_id)

    if session_data is None:
        st.warning("会话不存在，请重新选择。")
        st.session_state.active_session_id = None
        st.rerun()

    # ── 顶部栏：会话名 + 模型切换 ────────────────────────────────
    top_left, top_right = st.columns([3, 1])
    with top_left:
        st.subheader(f"🌸 {session_data['name']}")
        st.caption(f"创建于 {session_data['created_at']}")
    with top_right:
        models = llm_router.get_available_models()
        selected_model = st.selectbox(
            "模型",
            options=models,
            index=models.index(st.session_state.active_model)
                  if st.session_state.active_model in models else 0,
            key="model_selector",
            label_visibility="collapsed",
        )
        if selected_model != st.session_state.active_model:
            st.session_state.active_model = selected_model
            st.rerun()

    st.markdown("---")

    # ── 错误信息持久展示 ──────────────────────────────────────────
    if st.session_state.last_error:
        with st.expander("❌ 上次调用错误（点击展开）", expanded=True):
            st.code(st.session_state.last_error, language="text")
        if st.button("清除错误信息", key="clear_error"):
            st.session_state.last_error = None
            st.rerun()

    # ── 聊天记录展示 ──────────────────────────────────────────────
    history = _load_chat_history(session_id, st.session_state.active_model)

    chat_container = st.container()
    with chat_container:
        for msg in history:
            role = "user" if msg["sender"] == "user" else "assistant"
            with st.chat_message(role):
                st.markdown(msg["content"])
                if msg.get("model_used"):
                    st.caption(f"🤖 {msg['model_used']}")

    # ── 输入框 ────────────────────────────────────────────────────
    user_input = st.chat_input("输入你的问题…")

    if user_input:
        # 立刻展示用户消息
        with st.chat_message("user"):
            st.markdown(user_input)

        # 流式调用 LLM
        with st.chat_message("assistant"):
            try:
                st.write_stream(
                    llm_router.get_llm_response_stream(
                        session_id=session_id,
                        current_model=st.session_state.active_model,
                        user_message=user_input,
                    )
                )
                st.caption(f"🤖 {st.session_state.active_model}")
            except Exception as e:
                import traceback
                st.session_state.last_error = traceback.format_exc()

        st.rerun()
