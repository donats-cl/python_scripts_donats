import polars as pl
from sklearn.linear_model import LogisticRegression

df = pl.read_csv("heros.csv")

target_col = "class"  # колонка с классом (или "name", если строк на героя много)
target_class = "weapon_offlaner"  # интересующий класс

# Выбираем только колонки со статами
feature_cols = df.select(pl.exclude(["name", target_col])).columns

X = df.select(feature_cols).to_numpy()
y = (df[target_col] == target_class).cast(pl.Int8).to_numpy()

# class_weight="balanced" важен, так как одного класса обычно меньше, чем всех остальных вместе
model = LogisticRegression(class_weight="balanced", max_iter=1000)
model.fit(X, y)

# Собираем результаты обратно в Polars для удобного вывода
importance = pl.DataFrame(
    {
        "stat": feature_cols,
        "weight": model.coef_[0],
    }
).sort("weight", descending=True)

print(importance)
