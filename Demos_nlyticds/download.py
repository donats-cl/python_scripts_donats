import requests

URL = "https://api.deadlock-api.com/v1/matches/{match_id}/salts"


def check_url_api(url: str) -> dict[str, str | int | None]:
    """get url for download"""
    result = requests.get(url).json()
    return result

def unzip_demo():
    """unzip demo"""
