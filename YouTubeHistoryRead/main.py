import json
from collections import Counter


author = []
titles = []

with open("h.json", "r", encoding='utf-8') as f:
	d = json.load(f)
	for i in d:
		# print("-"*100)
		if i.get("header") == "YouTube": continue
		# print(f"{i=}")
		sub = i.get("subtitles")
		# print(f"{sub=}")
		r = sub[0] if type(sub) == list else sub
		# print(f"{r=}")
		if not r: continue
		
		name = r.get("name")
		author.append(name)

		title = i.get("title")
		titles.append(title)

# print(Counter(author).most_common(5))
print(Counter(titles).most_common(10))
# print(author)
