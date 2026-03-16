# config.py - 应用配置
import os

# 数据库路径
DB_PATH = os.path.join(os.path.dirname(__file__), "cybermeihua.db")

# 支持的 LLM 模型列表
AVAILABLE_MODELS = [
    # OpenAI
    "gpt-4o",
    "gpt-4o-mini",
    # Anthropic
    "claude-opus-4-6",        # 最强推理 / 长文本
    "claude-sonnet-4-6",
    # Google Gemini
    "gemini-3.1-pro-preview",           # Gemini 3 最强
    "gemini-2.0-flash-thinking-exp",  # Gemini 推理模型
    "gemini-2.0-flash",
    "gemini-1.5-pro",
    # DeepSeek
    "deepseek-reasoner",      # DeepSeek-R1 推理模型
    "deepseek-chat",
]

# 默认全局指令
DEFAULT_GLOBAL_INSTRUCTIONS = "请以现代心理学角度解读卦象，避免使用过于封建迷信的语言。"

# 爬虫相关配置
SCRAPER_TIMEOUT = 15  # 秒
SCRAPER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
