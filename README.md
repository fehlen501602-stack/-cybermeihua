# 赛博梅花 CyberMeihua 🌸

基于梅花易数的 AI 解卦工具，支持 OpenAI / Anthropic / Google Gemini / DeepSeek 多模型。

## 一键部署到 Streamlit Cloud（免费）

1. 点击右上角 **Fork** 到自己的 GitHub 账号
2. 打开 [share.streamlit.io](https://share.streamlit.io)，用 GitHub 账号登录
3. **New App** → 选择刚 fork 的仓库 → 主文件填 `app.py` → **Deploy**
4. 部署完成后，打开 App，在左侧边栏 **🔑 API Keys** 填入自己的 Key

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 支持的模型与 API Key

| 模型 | 需要的 Key | 申请地址 |
|------|-----------|---------|
| GPT-4o / GPT-4o-mini | `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/api-keys) |
| Claude (Anthropic) | `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) |
| Gemini | `GOOGLE_API_KEY` | [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| DeepSeek | `DEEPSEEK_API_KEY` | [platform.deepseek.com](https://platform.deepseek.com/) |

只需填写你打算使用的模型对应的 Key。
