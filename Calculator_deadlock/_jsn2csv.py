"""Собирает все предметы из ability_data/upgrade_*.json в таблицы:

  items.csv       — компактная: одна строка на предмет, свойства сгруппированы
                    в 8 смысловых кластеров (weapon, vitality, spirit, mobility,
                    control, stacks, economy, utility). В ячейке кластера —
                    `Свойство=значение; ...`; нулевые/default-значения и
                    свойства, одинаковые у всех предметов, скрыты.
  items_full.csv  — полная: одна колонка на каждое из 441 свойств (m_strValue).

Запуск: python _jsn2csv.py
"""

import csv
import json
import re
from glob import glob
from pathlib import Path

SRC = Path("ability_data")
OUT_GROUPED = Path("items.csv")
OUT_FULL = Path("items_full.csv")

SLOT_NAMES = {
    "EItemSlotType_WeaponMod": "Weapon",
    "EItemSlotType_Armor": "Armor",
    "EItemSlotType_Tech": "Tech",
}

META_COLUMNS = [
    "id",
    "name",
    "slot",
    "tier",
    "activation",
    "disabled",
    "folder",
    "components",
    "shop_icon",
    "ability_image",
    "upgrades",
]

CLUSTERS = ["weapon", "vitality", "spirit", "mobility", "control", "stacks", "economy", "utility"]

# Свойства, которые всегда относятся к оружию, даже если в имени есть
# слова из других кластеров (Duration, Range и т.п.).
WEAPON_OVERRIDES = re.compile(
    r"Melee|WeaponDamage|WeaponPower|Clip|Ammo|Reload|DPS|AttackDamage|"
    r"HealthDamage|HealthPctDamage|MaxHealthDamage|CurrentHealthDamage|AirBonusDamage",
    re.I,
)

# Порядок правил важен: первое совпадение задаёт кластер.
RULES = [
    ("economy", r"Gold|Souls|Bounty|Trophy|BuffsPerGold|AmmoPerSoul"),
    # резисты/броня/щиты раньше остального vitality, чтобы MeleeResist не ушёл в weapon
    ("vitality", r"Resist|Armor|Shield|Barrier|DamageReduction|DamageTaken|Deflect|Evasion|Surviv"),
    ("utility", r"\bProc|Chance|Trigger"),
    ("__weapon__", r"$^"),  # сюда попадает всё, что совпало с WEAPON_OVERRIDES
    ("stacks", r"Stack|Fervor|BuildUp"),
    ("control", r"Slow|Stun|Silence|Disarm|Root|Freeze|Sleep|Daze|Debuff|Status|Immun|Parry|Shrink|Tether|Pull|Knock|Interrupt|Stasis|Curse|Hex|Banish|Blind|^EMP|Dispel|Purge|Cleanse|Reveal|Spotted"),
    ("mobility", r"Move|Sprint|Slide|Jump|Air|Stamina|Dash|Gravity|Fall|Fly|Float|Landing|Velocity"),
    ("vitality", r"Health|Heal|Lifesteal|LifeSteal|Restor|Rejuvenat|Siphon|Lifestrike|Regen|Steal"),
    ("spirit", r"Tech|Spirit|Ability|Imbue|Magic|Spell|Cooldown|Charge|Duration|Cast|Channel|Radius|Range|Interval|Tick|Aura"),
    ("weapon", r"Damage|WeaponPower|FireRate|Bullet|Ammo|Clip|Reload|Headshot|Crit|Melee|Ricochet|Split|Spread|Zoom|DPS|Shot|Burst|Projectile|Pierce|Accuracy|Attack|Explode|Impact|Toss|Beam|Recoil"),
    ("utility", r"ActivateTime|ArmingTime|Respawn|Vision|Invis|ModelScale|Footstep|ThinkRate|SkipFrames|Target|MinAim|Height|Width|Length"),
]


def classify(prop: str) -> str:
    if re.search(r"Gold|Souls|Bounty|Trophy|BuffsPerGold|AmmoPerSoul", prop, re.I):
        return "economy"
    if WEAPON_OVERRIDES.search(prop) and not re.search(r"Resist|Armor|Shield|Barrier", prop):
        return "weapon"
    for group, pattern in RULES:
        if group == "__weapon__":
            continue
        if re.search(pattern, prop, re.I):
            return group
    return "utility"


def is_meaningful(value: str) -> bool:
    value = str(value).strip()
    if not value or value.lower() in ("false", "none"):
        return False
    try:
        return float(value.rstrip("m%")) not in (0.0, -1.0)
    except ValueError:
        return True


def load_items():
    items = []
    for path in glob(str(SRC / "upgrade_*.json")):
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        item_id = next(iter(data))
        body = data[item_id]

        # upgrade_base — служебная запись без слота и тира
        if str(body.get("_not_pickable", "")).strip() not in ("", "0", "false"):
            continue

        tier = body.get("m_iItemTier") or ""
        if tier.startswith("EModTier_"):
            tier = int(tier.removeprefix("EModTier_"))

        upgrades = {}
        for level, upgrade in enumerate(body.get("m_vecAbilityUpgrades") or [], start=1):
            upgrades[level] = {
                p["m_strPropertyName"]: p["m_strBonus"]
                for p in upgrade.get("m_vecPropertyUpgrades", [])
            }

        props = {
            prop: value.get("m_strValue", "")
            for prop, value in body.get("m_mapAbilityProperties", {}).items()
        }

        items.append(
            {
                "id": item_id,
                "name": item_id.removeprefix("upgrade_"),
                "slot": SLOT_NAMES.get(body.get("m_eItemSlotType"), ""),
                "tier": tier,
                "activation": (body.get("m_eAbilityActivation") or "").removeprefix(
                    "CITADEL_ABILITY_ACTIVATION_"
                ),
                "disabled": str(body.get("m_bDisabled", "false")).lower()
                in ("true", "1"),
                "folder": body.get("_editor", {}).get("folder_name", ""),
                "components": ";".join(
                    c.removeprefix("upgrade_")
                    for c in body.get("m_vecComponentItems") or []
                ),
                "shop_icon": Path(body.get("m_strShopIconLarge") or "").stem,
                "ability_image": Path(body.get("m_strAbilityImage") or "").stem,
                "upgrades": json.dumps(upgrades, ensure_ascii=False, separators=(",", ":")),
                "_props": props,
            }
        )
    return items


def write_full(items, prop_columns):
    with open(OUT_FULL, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f, fieldnames=META_COLUMNS + prop_columns, extrasaction="ignore"
        )
        writer.writeheader()
        for item in items:
            row = {k: v for k, v in item.items() if k != "_props"}
            row.update(item["_props"])
            writer.writerow(row)


def write_grouped(items):
    all_props = {prop for item in items for prop in item["_props"]}
    # свойства с одинаковым значением у всех предметов ничего не дают таблице
    constant_props = {
        prop for prop in all_props
        if len({item["_props"].get(prop) for item in items}) == 1
    }

    with open(OUT_GROUPED, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=META_COLUMNS + CLUSTERS)
        writer.writeheader()
        for item in items:
            grouped = {cluster: [] for cluster in CLUSTERS}
            for prop, value in sorted(item["_props"].items()):
                if prop not in constant_props and is_meaningful(value):
                    grouped[classify(prop)].append(f"{prop}={value}")
            row = {k: v for k, v in item.items() if k != "_props"}
            row.update({k: "; ".join(v) for k, v in grouped.items()})
            writer.writerow(row)


def main():
    items = load_items()
    items.sort(
        key=lambda i: (i["slot"], i["tier"] if isinstance(i["tier"], int) else 99, i["name"])
    )

    prop_columns = sorted({p for item in items for p in item["_props"]})
    write_full(items, prop_columns)
    write_grouped(items)

    print(f"{OUT_FULL}: {len(items)} предметов, {len(META_COLUMNS) + len(prop_columns)} колонок")
    print(f"{OUT_GROUPED}: {len(items)} предметов, {len(META_COLUMNS) + len(CLUSTERS)} колонок")


if __name__ == "__main__":
    main()
