# Utilities to parse slip text and attempt to decode 1xBet coupon pages via HTTP.
import re
from typing import List, Tuple
import requests

DELIMS = [r'\s+vs\s+', r'\s+v\s+', r'\s*-\s*', r'\s*—\s*', r'\s*\|\s*']

def normalize_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r'\s+', ' ', name)
    return name

def normalize_pair(a: str, b: str) -> str:
    a_n = normalize_name(a).lower()
    b_n = normalize_name(b).lower()
    return " | ".join(sorted([a_n, b_n]))

def parse_bet_slip(text: str) -> List[Tuple[str, str]]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    matches = []
    for ln in lines:
        found = False
        for d in DELIMS:
            parts = re.split(d, ln, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) == 2:
                a, b = parts[0].strip(), parts[1].strip()
                if a and b:
                    matches.append((a, b))
                    found = True
                    break
        if not found:
            parts = [p.strip() for p in ln.split(",") if p.strip()]
            if len(parts) == 2:
                matches.append((parts[0], parts[1]))
    return matches

def _extract_pairs_from_text(text: str) -> List[Tuple[str, str]]:
    # find patterns like "Team A - Team B" or "Team A vs Team B"
    pattern = re.compile(r'([\w\u0600-\u06FF.&()\-\'"\s]{2,60}?)\s*(?:vs|v|\-|—|\|)\s*([\w\u0600-\u06FF.&()\-\'"\s]{2,60}?)', re.IGNORECASE)
    results = []
    for m in pattern.finditer(text):
        a = m.group(1).strip()
        b = m.group(2).strip()
        if a and b:
            results.append((a, b))
    return results

def decode_1xbet_coupon(code: str) -> List[Tuple[str, str]]:
    # Try to fetch the 1xBet coupon page for the given code and extract match pairs.
    code = code.strip()
    if not code:
        return []
    urls = [
        f"https://1xbet.com/en/line/mobileCoupon/{code}",
        f"https://1xbet.com/en/line/coupon/{code}",
        f"https://1xbet.com/coupon/{code}",
        f"https://1xbet.com/ru/line/coupon/{code}",
        f"https://www.1xbet.com/en/line/coupon/{code}",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0 Safari/537.36"
    }
    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue
            text = resp.text
            pairs = _extract_pairs_from_text(text)
            if pairs:
                seen = set()
                out = []
                for a,b in pairs:
                    key = (a.lower(), b.lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append((a, b))
                return out
        except Exception:
            continue
    return []
