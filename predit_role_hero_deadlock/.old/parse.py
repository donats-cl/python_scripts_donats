import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/[IP_ADDRESS] Safari/537.36"
}

def parse(HERO_NAME):
    URL = f"https://deadlock.wiki/{HERO_NAME}"
    response = requests.get(URL, headers=HEADERS)
    print(response.status_code)  # Should be 200

    # Parse the HTML
    soup = BeautifulSoup(response.text, "html.parser")

    # Find all containers with hero's abilities
    cards = soup.find_all("div", class_="ability-section-card")

    if cards:
        markdown_contents = []
        for card in cards:
            for img in card.find_all("img"):
                img.decompose()  # Убираем картинки ![](/images/...)

            for a in card.find_all("a"):
                a.unwrap()       # Убираем ссылки [text](url)

            markdown_contents.append(md(str(card)))

        with open(f"./out/{HERO_NAME}.md", "w", encoding="utf-8") as f:
            f.write("\n\n---\n\n".join(markdown_contents))
    else:
        print("not found")

def main():
    HEROES = [
        # "Abrams",
        # "Apollo",
        # "Bebop",
        # "Billy",
        # "Calico",
        # "Celeste",
        # "The_Doorman",
        # "Drifter",
        # "Dynamo",
        # "Graves",
        # "Grey_Talon",
        # "Haze",
        # "Holliday",
        # "Infernus",
        # "Ivy",
        # "Kelvin",
        # "Lady_Geist",
        # "Lash",
        # "McGinnis",
        # "Mina",
        # "Mirage",
        # "Mo_%26_Krill",
        # "Paige",
        # "Paradox",
        # "Pocket",
        # "Rem",
        # "Seven",
        # "Shiv",
        # "Silver",
        # "Sinclair",
        # "Venator",
        # "Victor",
        # "Vindicta",
        # "Viscous",
        # "Vyper",
        # "Warden",
        # "Wraith",
        # "Yamato",
        "Solomon"
    ]

    for hero in HEROES:
        print(hero)
        parse(hero)


if __name__ == "__main__":
    main()
