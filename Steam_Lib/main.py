import requests

prompt = """I have a bunch of games on Steam. I want to find a game I'll enjoy playing. Here's a list of the games I own:

{games_list}

I want to play something I'll actually enjoy. Can you help me find a game I'll enjoy?

"""

STEAM_KEY = "FC1E517729FC2AA6E59D85BBE9D78064"
STEAM_ID = "76561198981419174"

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
