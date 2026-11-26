import requests

from dotenv import load_dotenv

prompt = """I have a bunch of games on Steam. I want to find a game I'll enjoy playing. Here's a list of the games I own:

{games_list}

I want to play something I'll actually enjoy. Can you help me find a game I'll enjoy?

"""

load_dotenv()
STEAM_KEY = str(os.getenv("STEAM_KEY"))
STEAM_ID = str(os.getenv("STEAM_ID"))


url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={STEAM_KEY}&steamid={STEAM_ID}&include_appinfo=1&include_played_free_games=1&format=json"

res = requests.get(url).json()["response"]

count = res["game_count"]

print(f"You have {count} games")

games = []

for i in res.get("games"):
    name = i.get("name")
    time = i.get("playtime_forever")/60
    # if time < 1: continue
    games.append([name, time])

sorted_games = sorted(games, key=lambda x: x[1], reverse=True)

games_list = "\n".join([f"{i[0]} - {i[1]} hours" for i in sorted_games])
print(prompt.format(games_list=games_list))
