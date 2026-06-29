"""sizes.py — 尺寸字串 → 吋徑 解析,供 DB數 自動計算。
DB數 = max(1, 尺寸吋) × 係數。匯入器與 API 共用。
"""
import re

_FRAC = {"\u00bd": 0.5, "\u00bc": 0.25, "\u00be": 0.75, "\u215c": 0.375,
         "\u215d": 0.625, "\u215e": 0.875, "\u215b": 0.125}


def parse_inch(s):
    """1.5 / 1-1/2" / \u00bd" / 3/4" 等寫法 → 吋(float);無法解析回 None。"""
    if s is None:
        return None
    s = str(s).strip().replace("\uff02", '"').replace("\u201d", '"')
    for u, val in _FRAC.items():
        s = s.replace(u, "+%s" % val)
    s = s.replace('"', "").replace("inch", "").replace("IN", "").strip()
    toks = re.findall(r"\d+/\d+|\d+\.?\d*", s)
    if not toks:
        return None
    total = 0.0
    for t in toks:
        if "/" in t:
            a, b = t.split("/")
            total += int(a) / int(b)
        else:
            total += float(t)
    return total or None


def db_count(size, factor=1):
    """DB數 = max(1, 吋) × 係數;尺寸無法解析回 None。"""
    inch = parse_inch(size)
    if inch is None:
        return None
    return round(max(1.0, inch) * (factor or 1), 4)
