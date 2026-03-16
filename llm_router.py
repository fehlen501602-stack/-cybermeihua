"""
llm_router.py - LLM 路由与 Prompt 管理

职责：
1. build_prompt  — 拼接全局指令 + 模型隔离历史 + 当前用户消息
2. get_llm_response — 根据模型选择调用对应 API，保存记录并返回回复
3. get_available_models — 返回支持的模型列表

支持模型：
- OpenAI  : gpt-4o, gpt-4o-mini, gpt-3.5-turbo
- Anthropic: claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5-20251001
- DeepSeek : deepseek-chat (兼容 OpenAI SDK，自定义 base_url)

API Key 从环境变量读取：
  OPENAI_API_KEY / ANTHROPIC_API_KEY / DEEPSEEK_API_KEY
"""

from __future__ import annotations

import os
from typing import Generator, Iterator, Optional

import db
from config import AVAILABLE_MODELS

# ---------------------------------------------------------------------------
# 模型分组
# ---------------------------------------------------------------------------

_OPENAI_MODELS = {
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-3.5-turbo",
}

_ANTHROPIC_MODELS = {
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
}

_DEEPSEEK_MODELS = {
    "deepseek-chat",
    "deepseek-reasoner",
}

_GEMINI_MODELS = {
    "gemini-3.1-pro-preview",
    "gemini-2.0-flash",
    "gemini-2.0-flash-thinking-exp",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
}

_DEEPSEEK_BASE_URL = "https://api.deepseek.com"


def _get_api_key(env_name: str) -> str:
    """优先从数据库读取 API Key，不存在则 fallback 到环境变量。"""
    return db.get_config_value(env_name) or os.environ.get(env_name, "")


def get_available_models() -> list[str]:
    """返回 config.py 中配置的可用模型列表。"""
    return list(AVAILABLE_MODELS)


# ---------------------------------------------------------------------------
# Prompt 构建
# ---------------------------------------------------------------------------

def build_messages(
    session_id: int,
    current_model: str,
    user_message: str,
) -> list[dict]:
    """
    构建发送给 LLM 的完整 messages 列表。

    修复说明：
    - 起卦结果（sender=assistant, model_used=NULL）并入 system prompt，
      避免第一条消息是 assistant 导致 Anthropic/Gemini API 报错。
    - 历史对话按 model_used 隔离，各模型只看到自己的对话线程。
    """
    global_instructions = db.get_global_instructions()
    history = db.get_chat_history(session_id, model_used=current_model)

    system_parts: list[str] = []
    if global_instructions:
        system_parts.append(global_instructions)

    # 把初始卦象（model_used IS NULL 的 assistant 消息）提取出来放进 system prompt
    conv_history: list[dict] = []
    for msg in history:
        if msg["sender"] == "assistant" and msg.get("model_used") is None:
            system_parts.append(f"\n[本次卦象信息]\n{msg['content']}")
        else:
            conv_history.append(msg)

    messages: list[dict] = []
    if system_parts:
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})

    for msg in conv_history:
        role = "user" if msg["sender"] == "user" else "assistant"
        messages.append({"role": role, "content": msg["content"]})

    messages.append({"role": "user", "content": user_message})
    return messages


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def get_llm_response(
    session_id: int,
    current_model: str,
    user_message: str,
    stream: bool = False,
) -> str | Generator[str, None, None]:
    """
    完整流程：
    1. 构建 messages（全局指令 + 模型隔离历史 + 用户消息）
    2. 调用对应 LLM API
    3. 将用户消息和 AI 回复保存到数据库
    4. 返回 AI 回复字符串（stream=True 时返回生成器）

    stream=True 时，调用方需要在迭代完生成器后，
    用 save_messages() 手动保存（因为流式下内容要等完整收到才能存）。
    实际上这里直接返回完整回复字符串，流式由 app.py 处理。
    """
    messages = build_messages(session_id, current_model, user_message)

    if current_model in _ANTHROPIC_MODELS:
        reply = _call_anthropic(current_model, messages)
    elif current_model in _GEMINI_MODELS:
        reply = _call_gemini(current_model, messages)
    elif current_model in _DEEPSEEK_MODELS:
        reply = _call_openai_compatible(
            current_model, messages,
            api_key=_get_api_key("DEEPSEEK_API_KEY"),
            base_url=_DEEPSEEK_BASE_URL,
        )
    else:
        # 默认走 OpenAI
        reply = _call_openai(current_model, messages)

    # 保存到数据库（用户消息绑定当前模型，保证各模型对话线程隔离）
    db.add_message(session_id, "user",      user_message, model_used=current_model)
    db.add_message(session_id, "assistant", reply,        model_used=current_model)

    return reply


# ---------------------------------------------------------------------------
# 流式公开入口
# ---------------------------------------------------------------------------

def get_llm_response_stream(
    session_id: int,
    current_model: str,
    user_message: str,
) -> Iterator[str]:
    """
    流式版本：返回一个逐块 yield 文本的生成器。
    - 先将用户消息写入 DB
    - 流式拉取 LLM 回复，边 yield 边拼接
    - 流结束后将完整回复写入 DB

    用法（app.py）：
        reply = st.write_stream(llm_router.get_llm_response_stream(...))
    """
    messages = build_messages(session_id, current_model, user_message)
    db.add_message(session_id, "user", user_message, model_used=current_model)

    if current_model in _ANTHROPIC_MODELS:
        raw_gen = _stream_anthropic(current_model, messages)
    elif current_model in _GEMINI_MODELS:
        raw_gen = _stream_gemini(current_model, messages)
    elif current_model in _DEEPSEEK_MODELS:
        raw_gen = _stream_openai_compatible(
            current_model, messages,
            api_key=_get_api_key("DEEPSEEK_API_KEY"),
            base_url=_DEEPSEEK_BASE_URL,
        )
    else:
        raw_gen = _stream_openai(current_model, messages)

    chunks: list[str] = []
    for chunk in raw_gen:
        chunks.append(chunk)
        yield chunk

    full_reply = "".join(chunks)
    db.add_message(session_id, "assistant", full_reply, model_used=current_model)


# ---------------------------------------------------------------------------
# OpenAI 调用
# ---------------------------------------------------------------------------

def _call_openai(model: str, messages: list[dict]) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai 包未安装，请运行: pip install openai")

    api_key = _get_api_key("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("请在侧边栏 🔑 API Keys 中填写 OPENAI_API_KEY")

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
    )
    return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# OpenAI 兼容接口（DeepSeek 等）
# ---------------------------------------------------------------------------

def _call_openai_compatible(
    model: str,
    messages: list[dict],
    api_key: str,
    base_url: str,
) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai 包未安装，请运行: pip install openai")

    if not api_key:
        raise ValueError(f"请在侧边栏 🔑 API Keys 中填写 {model} 所需的 API Key")

    client = OpenAI(api_key=api_key, base_url=base_url)
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
    )
    return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Anthropic 调用
# ---------------------------------------------------------------------------

def _call_anthropic(model: str, messages: list[dict]) -> str:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic 包未安装，请运行: pip install anthropic")

    api_key = _get_api_key("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("请在侧边栏 🔑 API Keys 中填写 ANTHROPIC_API_KEY")

    # Anthropic API 的 system prompt 需要单独传，不能放在 messages 里
    system_prompt = ""
    chat_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_prompt = msg["content"]
        else:
            chat_messages.append({"role": msg["role"], "content": msg["content"]})

    client = anthropic.Anthropic(api_key=api_key)
    kwargs = dict(
        model=model,
        max_tokens=4096,
        messages=chat_messages,
    )
    if system_prompt:
        kwargs["system"] = system_prompt

    resp = client.messages.create(**kwargs)
    return resp.content[0].text if resp.content else ""


# ---------------------------------------------------------------------------
# Gemini 调用
# ---------------------------------------------------------------------------

def _gemini_prepare(model: str, messages: list[dict]):
    """
    使用新版 google-genai SDK 准备 Gemini 调用所需的 client / contents / config。
    新版 SDK 支持 Gemini 2.x 及以上模型。
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError("google-genai 包未安装，请运行: pip install google-genai")

    api_key = _get_api_key("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("请在侧边栏 🔑 API Keys 中填写 GOOGLE_API_KEY")

    client = genai.Client(api_key=api_key)

    system_prompt = ""
    chat_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_prompt = msg["content"]
        else:
            chat_messages.append(msg)

    # 转换为 Gemini Content 格式（role: "user" / "model"）
    contents = []
    for msg in chat_messages:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(
            types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])])
        )

    config = types.GenerateContentConfig(
        system_instruction=system_prompt or None,
    )

    return client, model, contents, config


def _call_gemini(model: str, messages: list[dict]) -> str:
    client, model_name, contents, config = _gemini_prepare(model, messages)
    response = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=config,
    )
    return response.text or ""


# ---------------------------------------------------------------------------
# 流式后端
# ---------------------------------------------------------------------------

def _stream_openai(model: str, messages: list[dict]) -> Iterator[str]:
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai 包未安装，请运行: pip install openai")

    api_key = _get_api_key("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("请在侧边栏 🔑 API Keys 中填写 OPENAI_API_KEY")

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(model=model, messages=messages, stream=True)
    for chunk in response:
        content = chunk.choices[0].delta.content
        if content:
            yield content


def _stream_openai_compatible(
    model: str,
    messages: list[dict],
    api_key: str,
    base_url: str,
) -> Iterator[str]:
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai 包未安装，请运行: pip install openai")

    if not api_key:
        raise ValueError(f"请在侧边栏 🔑 API Keys 中填写 {model} 所需的 API Key")

    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
    )
    reasoning_started = False
    for chunk in response:
        delta = chunk.choices[0].delta
        # DeepSeek-R1：先流出思考过程，再流出最终回答
        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning:
            if not reasoning_started:
                yield "<details><summary>💭 思考过程</summary>\n\n"
                reasoning_started = True
            yield reasoning
        else:
            if reasoning_started:
                yield "\n\n</details>\n\n"
                reasoning_started = False
            if delta.content:
                yield delta.content


def _stream_gemini(model: str, messages: list[dict]) -> Iterator[str]:
    client, model_name, contents, config = _gemini_prepare(model, messages)
    for chunk in client.models.generate_content_stream(
        model=model_name,
        contents=contents,
        config=config,
    ):
        if chunk.text:
            yield chunk.text


def _stream_anthropic(model: str, messages: list[dict]) -> Iterator[str]:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic 包未安装，请运行: pip install anthropic")

    api_key = _get_api_key("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("请在侧边栏 🔑 API Keys 中填写 ANTHROPIC_API_KEY")

    system_prompt = ""
    chat_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_prompt = msg["content"]
        else:
            chat_messages.append({"role": msg["role"], "content": msg["content"]})

    client = anthropic.Anthropic(api_key=api_key)
    kwargs = dict(model=model, max_tokens=4096, messages=chat_messages)
    if system_prompt:
        kwargs["system"] = system_prompt

    with client.messages.stream(**kwargs) as stream:
        for text in stream.text_stream:
            if text:
                yield text


# ---------------------------------------------------------------------------
# 快速自测
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    db.init_db()
    sid = db.create_session("路由测试会话", "乾为天·本卦数据")

    print("[router] 可用模型:", get_available_models())
    print("[router] messages 构建测试:")
    msgs = build_messages(sid, "gpt-4o", "帮我解读这一卦")
    for m in msgs:
        print(f"  [{m['role']}] {m['content'][:60]}")
