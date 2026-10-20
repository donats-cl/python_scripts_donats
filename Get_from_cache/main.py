import polars as pl

df: pl.DataFrame = pl.read_parquet(r"C:\Users\donats_cl\Documents\GitHub\Deadlock_HEATMAP\cache\106191832\extra\stat_modifier_events.parquet")

print(df.to_numpy())
