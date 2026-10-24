import polars as pl

df: pl.DataFrame = pl.read_csv('./hero_stats.csv')

move = df.select('move_speed')

sum_move = move.sum()
len_sum: int = move.height

avg = sum_move / len_sum

print(sum_move, len_sum, avg)
