import json
import re

SPIRIT_RESIST = re.compile("spirit resist |spirit resists", re.IGNORECASE)
BULLET_RESIST = re.compile("bullet resist |bullet resists", re.IGNORECASE)

res: dict = {}
spirit: list = []
bullet: list = []

with (
    open("./data/heroes.json", "r", encoding="utf-8") as f,
    open("./res.json", "w", encoding="utf-8") as js,
):
    for i in json.load(f):
        name_hero: str = i["hero_name"]
        abls: list = i["abilities"]
        for j in abls:
            d: dict = j["description"]
            name_abl: str = j["name"]
            desk: str = f"{d.get('desc', d.get('quip', ''))} {d.get('t1_desc', '')} {d.get('t2_desc', '')} {d.get('t3_desc', '')}"

            # if ETALON in desk:
            #     res[name] = desk
            pattern = f"{name_hero}({name_abl})/{desk}"
            if SPIRIT_RESIST.findall(desk):
                spirit.append(pattern)
            if BULLET_RESIST.findall(desk):
                bullet.append(pattern)
    res["spirit"] = spirit
    res["bullet"] = bullet
    json.dump(res, js, indent=4)
