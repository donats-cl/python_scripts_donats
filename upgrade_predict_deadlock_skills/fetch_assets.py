"""Fetch Deadlock hero + signature ability data (assets only, no builds)."""
import json
import re
import urllib.request
from html import unescape
from pathlib import Path

BASE = "https://api.deadlock-api.com"
OUT = Path(__file__).parent / "data" / "heroes.json"


def get(url: str):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def clean(text) -> str:
    if not isinstance(text, str):
        return ""
    text = re.sub(r"<svg.*?</svg>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def main():
    heroes = get(f"{BASE}/v1/assets/heroes")
    items = get(f"{BASE}/v1/assets/items")
    by_class = {}
    for it in items:
        cn = it.get("class_name")
        if cn and cn not in by_class:
            by_class[cn] = it

    selectable = [h for h in heroes if h.get("player_selectable") and not h.get("disabled")]
    out = []
    for h in selectable:
        sig = h.get("items") or {}
        abilities = []
        for slot in range(1, 5):
            cn = sig.get(f"signature{slot}")
            it = by_class.get(cn)
            if not it:
                continue
            desc = it.get("description") or {}
            cleaned_desc = {k: clean(v) for k, v in desc.items() if isinstance(v, str)}
            props = {}
            for name, spec in (it.get("properties") or {}).items():
                if isinstance(spec, dict) and "value" in spec:
                    props[name] = spec["value"]
            abilities.append(
                {
                    "slot": slot,
                    "class_name": cn,
                    "name": it.get("name"),
                    "ability_type": it.get("ability_type"),
                    "description": cleaned_desc,
                    "upgrades": it.get("upgrades") or [],
                    "properties": props,
                }
            )
        out.append(
            {
                "hero_id": h.get("id"),
                "hero_name": h.get("name"),
                "abilities": abilities,
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB), heroes={len(out)}")
    bad = [h["hero_name"] for h in out if len(h["abilities"]) != 4]
    if bad:
        print("heroes without 4 signature abilities:", bad)
    missing = []
    for h in out:
        for a in h["abilities"]:
            if len(a["upgrades"]) != 3:
                missing.append((h["hero_name"], a["name"], len(a["upgrades"])))
    if missing:
        print("abilities not having 3 tiers:", missing[:20], "total", len(missing))


if __name__ == "__main__":
    main()
