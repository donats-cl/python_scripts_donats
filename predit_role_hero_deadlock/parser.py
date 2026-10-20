import glob
import os
import re
import sys
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import polars as pl

# Ground truth role mapping for Deadlock heroes
KNOWN_HERO_ROLES: dict[str, str] = {
    "Abrams": "Weapon-Offlaner",
    "Apollo": "Spirit-Offlaner",
    "Bebop": "Runner-Side-Support",
    "Billy": "Weapon-Offlaner",
    "Calico": "Spirit-Offlaner",
    "Celeste": "Spirit-Offlaner",
    "The Doorman": "Jumper-Side-Support",
    "Drifter": "Weapon-Offlaner",
    "Dynamo": "Mid-Support",
    "Graves": "Jumper-Side-Support",
    "Grey Talon": "Jumper-Side-Support",
    "Haze": "Core",
    "Holliday": "Jumper-Side-Support",
    "Infernus": "Spirit-Offlaner",
    "Ivy": "Mid-Support",
    "Kelvin": "Runner-Side-Support",
    "Lady Geist": "Spirit-Offlaner",
    "Lash": "Jumper-Side-Support",
    "McGinnis": "Mid-Support",
    "Mina": "Spirit-Offlaner",
    "Mirage": "Spirit-Offlaner",
    "Mo & Krill": "Runner-Side-Support",
    "Paige": "Mid-Support",
    "Paradox": "Jumper-Side-Support",
    "Pocket": "Jumper-Side-Support",
    "Rem": "Jumper-Side-Support",
    "Seven": "Core",
    "Shiv": "Spirit-Offlaner",
    "Silver": "Weapon-Offlaner",
    "Sinclair": "Jumper-Side-Support",
    "Venator": "Weapon-Offlaner",
    "Victor": "Spirit-Offlaner",
    "Vindicta": "Jumper-Side-Support",
    "Viscous": "Runner-Side-Support",
    "Vyper": "Spirit-Offlaner",
    "Warden": "Runner-Side-Support",
    "Wraith": "Core",
    "Yamato": "Spirit-Offlaner",
}

HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def parse_hero_wiki(hero_name: str):
    """Scrapes Deadlock wiki and saves hero table stats as markdown."""
    url = f"https://deadlock.wiki/{hero_name}"
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200:
        print(f"Failed to fetch {hero_name}: status {response.status_code}")
        return

    soup = BeautifulSoup(response.text, "html.parser")
    cards = soup.find_all("th", class_="infobox-h-dropdown")

    if cards:
        markdown_contents = []
        for card in cards:
            for img in card.find_all("img"):
                img.decompose()
            for a in card.find_all("a"):
                a.unwrap()
            markdown_contents.append(md(str(card)))

        os.makedirs("./out", exist_ok=True)
        with open(f"./out/{hero_name}.md", "w", encoding="utf-8") as f:
            f.write("\n\n---\n\n".join(markdown_contents))


def _clean_val_str(val_str: str) -> str:
    """Removes verbose text inside wiki value strings."""
    cleaned = re.sub(r'[A-Za-z\s]+from[^\s]+', '', val_str).strip()
    return cleaned


def _parse_base_scale(val_str: str) -> tuple[float, float]:
    """Parses strings like '800+49' into (800.0, 49.0) base and scaling values."""
    cleaned = _clean_val_str(val_str).replace('m/s', '').replace('s', '').replace('%', '').strip()
    if '+' in cleaned:
        parts = cleaned.split('+')
        try:
            b_match = re.findall(r'[-+]?\d*\.\d+|\d+', parts[0])
            s_match = re.findall(r'[-+]?\d*\.\d+|\d+', parts[1])
            b = float(b_match[0]) if b_match else 0.0
            s = float(s_match[0]) if s_match else 0.0
            return b, s
        except Exception:
            return 0.0, 0.0
    else:
        nums = re.findall(r'[-+]?\d*\.\d+|\d+', cleaned)
        if nums:
            return float(nums[0]), 0.0
        return 0.0, 0.0


def _parse_float(val_str: str, default: float = 0.0) -> float:
    """Parses a float out of string, removing units."""
    cleaned = _clean_val_str(val_str).replace('m/s', '').replace('s', '').replace('%', '').strip()
    nums = re.findall(r'[-+]?\d*\.\d+|\d+', cleaned)
    if nums:
        return float(nums[0])
    return default


def load_hero_dataframe(out_dir: str = "./out") -> pl.DataFrame:
    """
    Parses all hero .md files in out_dir into a Polars DataFrame with feature extraction
    and ground truth role assignment.
    """
    md_files = [f for f in glob.glob(os.path.join(out_dir, "*.md")) if ".old" not in f]
    
    if not md_files:
        raise FileNotFoundError(f"No markdown files found in {out_dir}")

    rows = []
    for fpath in md_files:
        hero_raw = os.path.basename(fpath).replace(".md", "").replace("%26", "&")
        hero = hero_raw.replace("_", " ")

        with open(fpath, "r", encoding="utf-8") as f:
            text = f.read()

        matches = re.findall(r'\|\s*([^|:]+):\s*\|\s*([^|]+)\|', text)
        kv = {}
        for k, v in matches:
            k_clean = k.strip()
            if k_clean not in kv:
                kv[k_clean] = v.strip()

        dps = _parse_float(kv.get("Damage Per Second", "0"))
        b_dmg_b, b_dmg_s = _parse_base_scale(kv.get("Bullet Damage", "0"))
        pellets = _parse_float(kv.get("Pellets per shot", "1"), default=1.0)
        ammo = _parse_float(kv.get("Ammo", "0"))
        bps = _parse_float(kv.get("Bullets per sec", "0"))
        reload_t = _parse_float(kv.get("Reload Time", "0"))
        b_vel = _parse_float(kv.get("Bullet Velocity", "0"))

        l_melee_b, l_melee_s = _parse_base_scale(kv.get("Light Melee", "0"))
        h_melee_b, h_melee_s = _parse_base_scale(kv.get("Heavy Melee", "0"))

        hp_b, hp_s = _parse_base_scale(kv.get("Health", "0"))
        hp_regen = _parse_float(kv.get("Health Regen", "0"))
        b_resist_b, b_resist_s = _parse_base_scale(kv.get("Bullet Resist", "0"))
        s_resist_b, s_resist_s = _parse_base_scale(kv.get("Spirit Resist", "0"))

        move_sp = _parse_float(kv.get("Move Speed", "0"))
        sprint_sp = _parse_float(kv.get("Sprint Speed", "0"))
        dash_sp = _parse_float(kv.get("Dash Speed", "0"))
        stamina = _parse_float(kv.get("Stamina", "0"))
        stamina_cd = _parse_float(kv.get("Stamina Cooldown", "0"))

        spirit_b, spirit_s = _parse_base_scale(kv.get("Spirit Power", "0"))

        true_role = KNOWN_HERO_ROLES.get(hero, "Unknown")

        row = {
            "hero": hero,
            "true_role": true_role,
            "dps": dps,
            "bullet_damage_base": b_dmg_b,
            "bullet_damage_scale": b_dmg_s,
            "pellets_per_shot": pellets,
            "ammo": ammo,
            "bullets_per_sec": bps,
            "reload_time": reload_t,
            "bullet_velocity": b_vel,
            "light_melee_base": l_melee_b,
            "light_melee_scale": l_melee_s,
            "heavy_melee_base": h_melee_b,
            "heavy_melee_scale": h_melee_s,
            "health_base": hp_b,
            "health_scale": hp_s,
            "health_regen": hp_regen,
            "bullet_resist_base": b_resist_b,
            "bullet_resist_scale": b_resist_s,
            "spirit_resist_base": s_resist_b,
            "spirit_resist_scale": s_resist_s,
            "move_speed": move_sp,
            "sprint_speed": sprint_sp,
            "dash_speed": dash_sp,
            "stamina": stamina,
            "stamina_cooldown": stamina_cd,
            "spirit_power_scale": spirit_s,
        }
        rows.append(row)

    raw_df = pl.DataFrame(rows)

    # Polars Feature Engineering using Polars Expressions
    df = raw_df.with_columns([
        (pl.col("health_base") + pl.col("health_scale") * 10).alias("health_lvl10"),
        (pl.col("bullet_damage_base") + pl.col("bullet_damage_scale") * 10).alias("bullet_damage_lvl10"),
        (pl.col("heavy_melee_base") + pl.col("heavy_melee_scale") * 10).alias("heavy_melee_lvl10"),
        (pl.col("ammo") * pl.col("bullet_damage_base")).alias("clip_damage_potential"),
        (pl.col("move_speed") + pl.col("sprint_speed") + (pl.col("dash_speed") / 5.0)).alias("mobility_score"),
        (pl.col("health_base") * (1.0 + pl.col("bullet_resist_base") / 100.0)).alias("effective_hp_base"),
        (pl.col("dps") / (pl.col("health_base") + 1.0)).alias("dps_to_hp_ratio"),
    ])

    return df
