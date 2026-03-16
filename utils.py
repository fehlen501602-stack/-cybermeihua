# utils.py - 通用工具函数
# TODO: 实现时间格式化、UUID 生成等工具函数
import uuid
from datetime import datetime


def generate_uuid() -> str:
    return str(uuid.uuid4())


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
