import polars as pl
import json
import re

author: list = []
titles: list = []

with open("h.json", "r", encoding='utf-8') as f:
	d: list[dict] = json.load(f)
	for i in d:
		# print("-"*100)
		if i.get("header") == "YouTube": continue
		# print(f"{i=}")
		sub = i.get("subtitles")
		# print(f"{sub=}")
		ru = sub[0] if type(sub) == list else sub
		# print(f"{r=}")
		if not ru: continue

		name: str = ru.get("name")
		author.append(re.sub(r' \-.*', '', name))

		title: str = re.sub(r' \(.*?\)', '', i.get("title", '').replace('Ви дивилися відео ', ''))
		titles.append(title)

data: pl.DataFrame = pl.DataFrame({
    "author": author,
    "title": titles
}).with_columns(
    pl.col("title").str.replace(r"^.*?\s* - \s*", "").alias("title")
)

dubl_data: pl.DataFrame = (
    data.group_by(data.columns)  # або просто df
    .len(name="count")                # створює колонку 'count' з кількістю повторень
    .sort("count", descending=True)   # сортує: найбільше повторів зверху
)

print(data)
print(dubl_data)
dubl_data.write_csv('export.csv')
