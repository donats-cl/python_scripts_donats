import json

import requests

URL: str = "https://api.deadlock-api.com/v1/assets/items"

with open("./items.json", "w", encoding="utf-8") as f:
    json.dump(requests.get(URL).json(), f, indent=4)
