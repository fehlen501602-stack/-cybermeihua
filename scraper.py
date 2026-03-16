"""
scraper.py - 梅花易数起卦模块

核心发现：https://meihua.guoxueju.com/ 是纯前端 Vue.js SPA，
所有起卦计算均在浏览器 JS 中完成，无后端 API。

本模块完整复现其 JS 算法（go()、ben2hu()、ben2bian()、yao2gua() 等），
并加载从该网站 JS bundle 中提取的 64 卦数据库（hexagrams.json）。

算法来源：对 /js/app.54ee948f.js 进行逆向工程。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

from lunardate import LunarDate

# ---------------------------------------------------------------------------
# 八卦常量
# ---------------------------------------------------------------------------

# 起卦时用的八卦顺序：乾1 兑2 离3 震4 巽5 坎6 艮7 坤8
_TRIGRAM_ORDER = "乾兑离震巽坎艮坤"

# 十二地支
_EARTHLY_BRANCHES = "子丑寅卯辰巳午未申酉戌亥"

# 二进制数组 → 卦字（yao2gua）
_YAO_TO_GUA: dict[tuple, str] = {
    (1, 1, 1): "乾",
    (0, 1, 0): "坎",
    (1, 0, 0): "艮",
    (0, 0, 1): "震",
    (1, 1, 0): "巽",
    (1, 0, 1): "离",
    (0, 0, 0): "坤",
    (0, 1, 1): "兑",
}

# 卦字 → 二进制数组（gua2yao）
_GUA_TO_YAO: dict[str, tuple] = {v: k for k, v in _YAO_TO_GUA.items()}

# ---------------------------------------------------------------------------
# 加载 64 卦数据库
# ---------------------------------------------------------------------------

_HEXAGRAM_DB: dict[str, dict] = {}

def _load_hexagrams() -> None:
    global _HEXAGRAM_DB
    if _HEXAGRAM_DB:
        return
    db_path = os.path.join(os.path.dirname(__file__), "hexagrams.json")
    if not os.path.exists(db_path):
        raise FileNotFoundError(
            f"hexagrams.json not found at {db_path}. "
            "Run build_hexagram_db.py to generate it."
        )
    with open(db_path, encoding="utf-8") as f:
        data = json.load(f)
    for entry in data:
        _HEXAGRAM_DB[entry["gua"]] = entry


def _lookup_hexagram(up: str, down: str) -> dict:
    """根据上卦+下卦字符查找卦象信息。"""
    _load_hexagrams()
    key = up + down
    entry = _HEXAGRAM_DB.get(key)
    if not entry:
        return {"gua": key, "name": f"{up}{down}（未知）", "src": "", **{f"change_{i}": "" for i in range(1, 7)}}
    return entry


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------

def fetch_divination_data(params: dict) -> dict:
    """
    根据起卦参数计算并返回结构化卦象数据。

    Parameters
    ----------
    params : dict
        支持以下键（至少提供一种）：
        - "method"   : str  — 起卦方法："time"（默认）或 "number"
        - "datetime" : str  — 时间起卦时间，格式 "YYYY-MM-DD HH:MM" 或 "YYYY-MM-DD HH"
        - "number"   : int  — 数字起卦主数字（任意正整数）
        - "hour"     : int  — 数字起卦时辰（0-23），不传则取当前时刻

    Returns
    -------
    dict  {
        "success": bool,
        "error": str | None,
        "method": str,            # 起卦方式说明
        "note": str,              # 起卦备注
        "eight": str,             # 时间描述
        "hexagram": dict,         # 本卦
        "nuclear_hexagram": dict, # 互卦
        "changing_hexagram": dict,# 变卦
        "changing_line": int,     # 动爻（1-6）
    }
    """
    method = params.get("method", "time")

    if method == "time":
        dt_str = params.get("datetime") or datetime.now().strftime("%Y-%m-%d %H:%M")
        dt = _parse_datetime(dt_str)
        return _calc_time_divination(dt)
    elif method == "number":
        raw = params.get("number")
        if raw is None:
            return _error_result("数字起卦需要提供 number 参数")
        try:
            n = int(raw)
            if n <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return _error_result("number 必须为正整数")
        hour = params.get("hour")
        hour = int(hour) if hour is not None else datetime.now().hour
        return _calc_number_divination(n, hour)
    else:
        return _error_result(f"不支持的起卦方法: {method}（支持 time / number）")


# ---------------------------------------------------------------------------
# 数字起卦核心算法
# ---------------------------------------------------------------------------

def _calc_number_divination(n: int, hour: int) -> dict:
    """
    数字起卦法（梅花易数"以数起卦"）：

    算法：
        f    = 时地支序号（1-12），与时间起卦相同
        sum1 = n             → 上卦底数
        sum2 = n + f         → 下卦底数 + 动爻底数
        d    = sum1 % 8 (0→8) → 上卦序号
        m    = sum2 % 8 (0→8) → 下卦序号
        v    = sum2 % 6 (0→6) → 动爻序号
    """
    try:
        hour_branch_idx = ((hour + 1) // 2) % 12   # 0-11
        f = hour_branch_idx + 1                      # 1-12
        hour_branch_char = _EARTHLY_BRANCHES[hour_branch_idx]

        sum1 = n
        sum2 = n + f

        d = sum1 % 8 or 8
        m = sum2 % 8 or 8
        v = sum2 % 6 or 6

        up   = _TRIGRAM_ORDER[d - 1]
        down = _TRIGRAM_ORDER[m - 1]

        ben_info            = _lookup_hexagram(up, down)
        hu_up,   hu_down    = _ben2hu(up, down)
        bian_up, bian_down  = _ben2bian(up, down, v)

        return {
            "success": True,
            "error":   None,
            "method":  "数字起卦",
            "note":    f"起卦数字：{n}，时辰：{hour_branch_char}时（{hour}:00）",
            "eight":   f"数字 {n} + {hour_branch_char}时",
            "up":      up,
            "down":    down,
            "hexagram": {
                "gua":  f"{up}{down}",
                "name": ben_info["name"],
                "src":  ben_info["src"],
                "changing_line_text": ben_info.get(f"change_{v}", ""),
            },
            "nuclear_hexagram": {
                "gua": f"{hu_up}{hu_down}",
                **_lookup_hexagram(hu_up, hu_down),
            },
            "changing_hexagram": {
                "gua": f"{bian_up}{bian_down}",
                **_lookup_hexagram(bian_up, bian_down),
            },
            "changing_line": v,
            "_debug": {
                "n": n, "hour": hour, "f": f,
                "sum1": sum1, "sum2": sum2,
                "d": d, "m": m, "v": v,
            },
        }
    except Exception as e:
        return _error_result(f"数字起卦计算失败: {e}")


# ---------------------------------------------------------------------------
# 时间起卦核心算法
# （完整复现 meihua.guoxueju.com 前端 JS 的 go() 函数）
# ---------------------------------------------------------------------------

def _calc_time_divination(dt: datetime) -> dict:
    """
    时间起卦算法：

    JS 原始逻辑（go() 函数，已逆向）：
        s = "子丑寅卯辰巳午未申酉戌亥"
        r = "乾兑离震巽坎艮坤"
        c = solar2lunar(year, month, day, hour)
        i = s.indexOf(c.gzYear[-1]) + 1   // 年地支序号 1-12
        h = lunar_month
        g = lunar_day
        f = s.indexOf(c.gzHour[1]) + 1    // 时地支序号 1-12
        _ = i + h + g
        l = _ + f
        d = _ % 8  (if 0 → 8)    // 上卦序号
        m = l % 8  (if 0 → 8)    // 下卦序号
        v = l % 6  (if 0 → 6)    // 动爻序号
        up   = r[d-1]
        down = r[m-1]
        change = v
    """
    try:
        # 1. 阳历 → 农历
        lunar = LunarDate.fromSolarDate(dt.year, dt.month, dt.day)
        lunar_year  = lunar.year
        lunar_month = lunar.month
        lunar_day   = lunar.day

        # 2. 年地支序号 i（1-12）
        year_branch_idx = (lunar_year - 1900) % 12  # 0-11
        i = year_branch_idx + 1                      # 1-12

        # 3. 时地支序号 f（1-12）
        # 子时: 0/23点, 丑时: 1-2点, 寅时: 3-4点... 亥时: 21-22点
        hour_branch_idx = ((dt.hour + 1) // 2) % 12  # 0-11
        f = hour_branch_idx + 1                       # 1-12

        # 4. 起卦数字
        sum1 = i + lunar_month + lunar_day   # 上卦底数
        sum2 = sum1 + f                      # 下卦底数

        # 5. 卦序（1-8）
        d = sum1 % 8 or 8
        m = sum2 % 8 or 8

        # 6. 动爻（1-6）
        v = sum2 % 6 or 6

        # 7. 卦字
        up   = _TRIGRAM_ORDER[d - 1]
        down = _TRIGRAM_ORDER[m - 1]

        # 8. 三卦信息
        ben_info  = _lookup_hexagram(up, down)
        hu_up, hu_down      = _ben2hu(up, down)
        bian_up, bian_down  = _ben2bian(up, down, v)

        year_branch_char = _EARTHLY_BRANCHES[year_branch_idx]
        hour_branch_char = _EARTHLY_BRANCHES[hour_branch_idx]

        return {
            "success": True,
            "error":   None,
            "method":  "年月日时",
            "note":    f"公历{dt.year}年{dt.month}月{dt.day}日{dt.hour}时",
            "eight":   (
                f"农历{lunar_year}年（{year_branch_char}年）"
                f"{lunar_month}月{lunar_day}日 {hour_branch_char}时"
            ),
            # 上下卦原始字
            "up":   up,
            "down": down,
            # 三卦
            "hexagram": {
                "gua":  f"{up}{down}",
                "name": ben_info["name"],
                "src":  ben_info["src"],
                "changing_line_text": ben_info.get(f"change_{v}", ""),
            },
            "nuclear_hexagram": {
                "gua":  f"{hu_up}{hu_down}",
                **_lookup_hexagram(hu_up, hu_down),
            },
            "changing_hexagram": {
                "gua":  f"{bian_up}{bian_down}",
                **_lookup_hexagram(bian_up, bian_down),
            },
            "changing_line": v,
            # 调试用
            "_debug": {
                "lunar_year": lunar_year,
                "lunar_month": lunar_month,
                "lunar_day": lunar_day,
                "i": i, "h": lunar_month, "g": lunar_day, "f": f,
                "sum1": sum1, "sum2": sum2, "d": d, "m": m, "v": v,
            },
        }

    except Exception as e:
        return _error_result(f"起卦计算失败: {e}")


# ---------------------------------------------------------------------------
# 互卦 / 变卦 算法
# （复现 JS 的 ben2hu() / ben2bian()）
# ---------------------------------------------------------------------------

def _gua2yao(gua: str) -> list[int]:
    """卦字 → 3 爻二进制列表（从上到下）。"""
    return list(_GUA_TO_YAO[gua])


def _yao2gua(yao: list[int]) -> str:
    """3 爻二进制列表 → 卦字。"""
    return _YAO_TO_GUA[tuple(yao)]


def _ben2hu(up: str, down: str) -> tuple[str, str]:
    """
    互卦算法：
        a = gua2yao(up) + gua2yao(down)   // 6 爻（上卦在前）
        hu_up   = yao2gua(a[1:4])
        hu_down = yao2gua(a[2:5])
    """
    a = _gua2yao(up) + _gua2yao(down)
    return _yao2gua(a[1:4]), _yao2gua(a[2:5])


def _ben2bian(up: str, down: str, change: int) -> tuple[str, str]:
    """
    变卦算法：
        t = gua2yao(up) + gua2yao(down)   // 6 爻（上卦在前）
        c = 6 - change                     // 0-indexed 动爻位置
        t[c] ^= 1                          // 翻转动爻
        bian_up   = yao2gua(t[0:3])
        bian_down = yao2gua(t[3:6])
    """
    t = _gua2yao(up) + _gua2yao(down)
    c = 6 - change
    t[c] = 1 - t[c]
    return _yao2gua(t[0:3]), _yao2gua(t[3:6])


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _parse_datetime(dt_str: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_str.strip(), fmt)
        except ValueError:
            continue
    return datetime.now()


def _error_result(msg: str) -> dict:
    return {
        "success": False,
        "error":   msg,
        "method": "", "note": "", "eight": "",
        "up": "", "down": "",
        "hexagram": None,
        "nuclear_hexagram": None,
        "changing_hexagram": None,
        "changing_line": 0,
    }


# ---------------------------------------------------------------------------
# 快速自测
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_dt = "2026-03-07 14"
    print(f"[scraper] 起卦时间: {test_dt}")
    result = fetch_divination_data({"method": "time", "datetime": test_dt})

    if result["success"]:
        print(f"  公历备注  : {result['note']}")
        print(f"  农历八字  : {result['eight']}")
        print(f"  本卦      : {result['hexagram']['name']} ({result['hexagram']['gua']})")
        print(f"  互卦      : {result['nuclear_hexagram']['name']} ({result['nuclear_hexagram']['gua']})")
        print(f"  变卦      : {result['changing_hexagram']['name']} ({result['changing_hexagram']['gua']})")
        print(f"  动爻      : 第 {result['changing_line']} 爻")
        print(f"  动爻辞    : {result['hexagram']['changing_line_text'][:80]}...")
        print(f"  调试信息  : {result['_debug']}")
    else:
        print(f"  失败: {result['error']}")
