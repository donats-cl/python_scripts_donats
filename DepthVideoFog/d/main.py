from glob import glob
from boon import Demo
from zipfile import ZipFile, ZIP_DEFLATED

p = "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Deadlock\\game\\citadel\\addons\\replays"


for i in glob(p+"\\*.dem"):
	demo = Demo(i)
	_id = i.split("\\")[-1].split(".")[0]
	print(f"Started: {_id}")
	with ZipFile(f"{_id}.zip", "w", ZIP_DEFLATED) as z:
		for name in [
			"players",
			"player_ticks",
			"kills",
			"damage",
			"abilities",
			"item_purchases",
			"objectives",
			"world_ticks",
		]:
			path = f"{name}.parquet"
			print(path)
			getattr(demo, name).write_parquet(path)
			z.write(path)
