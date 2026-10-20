import numpy as np
import polars as pl
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler

df: pl.DataFrame = pl.read_csv('dataset.csv').unique()
sc: StandardScaler = StandardScaler()

print(df.columns)

data: pl.DataFrame = df.select(['duration_ms','danceability','energy','key','loudness','mode','speechiness','acousticness','instrumentalness','liveness','valence','tempo'])
print(data.columns)

X_scaled = sc.fit_transform(data.to_numpy())

def recommend_by_custom_vector(df: pl.DataFrame, custom_features: list[int], top_n=3):
    raw_vector = np.array([custom_features])

    scaled_vector = sc.transform(raw_vector)

    scores = cosine_similarity(scaled_vector, X_scaled)[0]

    result = (
        df.with_columns(similarity=scores)
          .sort("similarity", descending=True)
          .head(top_n)
          .select(["artists", "track_name", "similarity"])
    )
    return result

if __name__ == '__main__':
    my_custom_song = [
        124226,   # duration_ms
        0.29,    # danceability
        0.97,    # energy
        4,        # key (F#)
        -10.8,   # loudness
        1,        # mode (major)
        0.,    # speechiness
        0.44,    # acousticness
        0.16, # instrumentalness
        0.65,    # liveness
        0.86,    # valence
        143.6,    # tempo
    ]

    print(recommend_by_custom_vector(df, my_custom_song, top_n=10))
