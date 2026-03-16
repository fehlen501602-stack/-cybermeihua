"""
models.py - Pydantic 数据模型定义
用于在各模块之间传递结构化数据，提供类型安全和自动验证。
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    message_id:   Optional[int] = None
    session_id:   int
    message_uuid: str
    sender:       str           # 'user' | 'assistant'
    content:      str
    timestamp:    str
    model_used:   Optional[str] = None


class HexagramInfo(BaseModel):
    gua:  str                   # 上卦+下卦，如 "离离"
    name: str                   # 卦名，如 "离为火"
    src:  str = ""              # 卦辞全文


class DivinationResult(BaseModel):
    success:            bool
    error:              Optional[str] = None
    method:             str = ""
    note:               str = ""        # 公历时间备注
    eight:              str = ""        # 农历八字
    up:                 str = ""        # 上卦字
    down:               str = ""        # 下卦字
    hexagram:           Optional[HexagramInfo] = None
    nuclear_hexagram:   Optional[HexagramInfo] = None
    changing_hexagram:  Optional[HexagramInfo] = None
    changing_line:      int = 0
    changing_line_text: str = ""        # 动爻爻辞


class DivinationSession(BaseModel):
    session_id:          int
    name:                str
    created_at:          str
    initial_prompt_data: Optional[str] = None


class GlobalConfig(BaseModel):
    global_instructions: str = ""
