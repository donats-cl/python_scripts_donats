import json
from dataclasses import dataclass
from enum import Enum


class Type(Enum):
    WEAPON = 1
    GREEN = 2
    SPIRIT = 3


@dataclass
class Item:
    id: int
    name: str
    type: str
    cost: int
    is_active: bool

    def __repr__(self) -> str:
        return f"{self.name}({self.type})[{self.cost}]"


if __name__ == "__main__":
    items_: list[Item] = []
    with open("./items.json", "r", encoding="utf-8") as f:
        items: dict = json.load(f)
        for i in items:
            if i["type"] != "upgrade" and not i.get("shopable"):
                continue
            item: Item = Item(
                i["id"],
                i["name"],
                i["item_slot_type"],
                i["cost"],
                i["is_active_item"],
            )
            items_.append(item)
    print(items_)
