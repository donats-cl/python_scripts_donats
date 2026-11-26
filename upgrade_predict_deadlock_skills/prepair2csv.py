import json
import re
from operator import attrgetter

import polars as pl

# HARD_CC = re.compile("stun|sleep|curse|lift", re.IGNORECASE)
# SOFT_CC = re.compile(
#     "silence|disarm|slow|immobiliz|knocks|knockback|knockup", re.IGNORECASE
# )

STUN = re.compile("stun ", re.IGNORECASE)
SLEEP = re.compile("sleep", re.IGNORECASE)
CURSE = re.compile("cruse", re.IGNORECASE)
LIFT = re.compile("lift", re.IGNORECASE)

SILENCE = re.compile("silence", re.IGNORECASE)
DISARM = re.compile("disarm", re.IGNORECASE)
SLOW = re.compile("slow", re.IGNORECASE)
IMMOBILIZE = re.compile("immobiliz", re.IGNORECASE)
DISPLAYSMENT = re.compile("knocks|knockback|knockup", re.IGNORECASE)

COUNTER_DEBUFF = re.compile(
    "unstoppable|untargetable|debuff resist|protects|escape into|immunity to|dispels|slow resistance",
    re.IGNORECASE,
)
SHIELDS = re.compile("barrier", re.IGNORECASE)
LIFESTEAL = re.compile("lifesteal|heal |heals|stealing life", re.IGNORECASE)
REDUCTION_RESIST = re.compile("", re.IGNORECASE)
REDUCTION_HEAL = re.compile("", re.IGNORECASE)


class Ability:
    def __init__(self, slot_id, name, desc, t1d="", t2d="", t3d=""):
        self.slot = slot_id
        self.name = name
        self.description = desc
        self.t1d = t1d  # description t1 ability
        self.t2d = t2d
        self.t3d = t3d
        ad: str = f"{desc} {t1d} {t2d} {t3d}"  # all description (desc +t1d +t2d +t3d)

        self.stun: bool = bool(STUN.findall(ad))
        self.sleep: bool = bool(SLEEP.findall(ad))
        self.curse: bool = bool(CURSE.findall(ad))
        self.lift: bool = bool(LIFT.findall(ad))

        self.silence: bool = bool(SILENCE.findall(ad))
        self.disarm: bool = bool(DISARM.findall(ad))
        self.slow: bool = bool(SLOW.findall(ad))
        self.immobilize: bool = bool(IMMOBILIZE.findall(ad))
        self.displacement: bool = bool(DISPLAYSMENT.findall(ad))

        self.shields: bool = bool(SHIELDS.findall(ad))
        self.lifesteal: bool = bool(LIFESTEAL.findall(ad))

        self.hard_cc: bool = any(
            [self.stun, self.sleep, self.curse, self.lift]
        )  # bool(HARD_CC.findall(ad))
        self.soft_cc: bool = any(
            [self.silence, self.disarm, self.slow, self.immobilize, self.displacement]
        )  # bool(SOFT_CC.findall(ad))
        self.cdebuff: bool = bool(COUNTER_DEBUFF.findall(ad))  # COUNTER_DEBUFF

    def __str__(self):
        return f"#{self.slot}/{self.name}\n{self.description}"


class Hero:
    def __init__(self, hero_id, hero_name, abil):
        self.id = hero_id
        self.name = hero_name
        self.abilitys: list[Ability] = abil

        self.stun: bool = any(i.stun for i in self.abilitys)
        self.sleep: bool = any(i.sleep for i in self.abilitys)
        self.curse: bool = any(i.curse for i in self.abilitys)
        self.lift: bool = any(i.lift for i in self.abilitys)

        self.silence: bool = any(i.silence for i in self.abilitys)
        self.disarm: bool = any(i.disarm for i in self.abilitys)
        self.slow: bool = any(i.slow for i in self.abilitys)
        self.immobilize: bool = any(i.immobilize for i in self.abilitys)
        self.displacement: bool = any(i.displacement for i in self.abilitys)

        self.shields: bool = any(i.shields for i in self.abilitys)
        self.lifesteal: bool = any(i.lifesteal for i in self.abilitys)

        self.cdebuff = any(i.cdebuff for i in self.abilitys)

        self.hard_cc = any(i.hard_cc for i in self.abilitys)
        self.soft_cc = any(i.soft_cc for i in self.abilitys)

        self.n: int = int(
            self.stun
            | (self.sleep << 1)
            | (self.curse << 2)
            | (self.lift << 3)
            | (self.silence << 4)
            | (self.disarm << 5)
            | (self.slow << 6)
            | (self.immobilize << 7)
            | (self.displacement << 8)
            | (self.shields << 9)
            | (self.lifesteal << 10)
            | (self.cdebuff << 11)
        )

    def __repr__(self):
        # a = "\n".join(str(i) for i in self.abilitys)
        return (
            f"#{self.id}, {self.name}, {self.hard_cc=} {self.soft_cc=} {self.cdebuff=}"
        )

    def __str__(self):
        return f"{self.stun=}\n{self.sleep=}\n{self.curse=}\n{self.lift=}\n{self.silence=}\n{self.disarm=}\n{self.slow=}\n{self.immobilize=}\n{self.displacement=}\n{self.shields=}\n{self.lifesteal=}\n{self.cdebuff=}"


with open("./data/heroes.json", "r", encoding="utf-8") as f:
    js: list[dict] = json.load(f)

    heros: dict[str, Hero] = {}

    for i in js:
        hid: int = i["hero_id"]  # hero id
        hname: str = i["hero_name"]
        ablilities: list[dict] = i.get("abilities", [])

        abil: list[Ability] = []

        for j in ablilities:
            description: dict = j["description"]
            desc: str = description.get("desc", description.get("quip", ""))
            t1d: str = description.get("t1_desc", "")
            t2d: str = description.get("t2_desc", "")
            t3d: str = description.get("t3_desc", "")

            abil.append(Ability(j["slot"], j["name"], desc, t1d, t2d, t3d))

        h: Hero = Hero(hid, hname, abil)
        heros[hname] = h
    print(str(heros["Apollo"]))
    print(heros["Calico"].abilitys[3].description)
    t: int = heros["Mina"].n
    mask: int = 0b110010111111  # 3263
    print(f"{mask=}")
    for n, i in heros.items():
        if (i.n & mask) == (t & mask):
            print(n)

    attrs = (
        "name",
        "stun",
        "sleep",
        "curse",
        "lift",
        "silence",
        "disarm",
        "slow",
        "immobilize",
        "displacement",
        "shields",
        "lifesteal",
        "cdebuff",
    )

    getter = attrgetter(*attrs)
    rows = [getter(hero) for hero in heros.values()]

    df: pl.DataFrame = pl.DataFrame(rows, schema=attrs, orient="row").with_columns(
        pl.col("name").cast(pl.String),
        pl.exclude("name").cast(pl.UInt8),
    )

    df.write_csv("./heros_classificated.csv")
    print(df)
