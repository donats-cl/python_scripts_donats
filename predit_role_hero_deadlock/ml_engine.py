import numpy as np
import polars as pl
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.neighbors import NearestNeighbors
from sklearn.metrics import classification_report, accuracy_score


class DeadlockMLEngine:
    """
    Machine Learning Engine using Polars & Scikit-Learn for Deadlock Hero Analytics:
    - Supervised Role Classification (Random Forest)
    - Stratified K-Fold Cross-Validation
    - Unsupervised Role Clustering (K-Means & PCA)
    - Feature Importance Analysis
    - Hero Similarity Search (KNN for existing heroes or custom stats)
    """

    FEATURE_COLS = [
        "dps",
        "bullet_damage_base",
        "bullet_damage_scale",
        "pellets_per_shot",
        "ammo",
        "bullets_per_sec",
        "reload_time",
        "bullet_velocity",
        "light_melee_base",
        "heavy_melee_base",
        "heavy_melee_scale",
        "health_base",
        "health_scale",
        "health_regen",
        "move_speed",
        "sprint_speed",
        "dash_speed",
        "stamina",
        "stamina_cooldown",
        "spirit_power_scale",
        "health_lvl10",
        "bullet_damage_lvl10",
        "clip_damage_potential",
        "mobility_score",
        "effective_hp_base",
        "dps_to_hp_ratio",
    ]

    def __init__(self, df: pl.DataFrame):
        self.df = df
        self.scaler = StandardScaler()
        self.kmeans = None
        self.pca = None
        self.rf_classifier = None
        self.knn = None
        
        # Convert Polars numerical columns to numpy array
        self.X_raw = self.df.select(self.FEATURE_COLS).to_numpy()
        self.X_scaled = self.scaler.fit_transform(self.X_raw)
        self.hero_names = self.df.select("hero").to_series().to_list()
        
        if "true_role" in self.df.columns:
            self.y_true = self.df.select("true_role").to_series().to_list()
        else:
            self.y_true = None

    def fit_clusters(self, n_clusters: int = 4) -> pl.DataFrame:
        """Applies K-Means clustering to categorize heroes into role archetypes."""
        self.kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        cluster_ids = self.kmeans.fit_predict(self.X_scaled)

        cluster_labels = self._map_clusters_to_roles(cluster_ids)
        role_names = [cluster_labels[cid] for cid in cluster_ids]

        self.df = self.df.with_columns([
            pl.Series("cluster_id", cluster_ids),
            pl.Series("cluster_role", role_names),
        ])
        return self.df

    def _map_clusters_to_roles(self, cluster_ids: np.ndarray) -> dict[int, str]:
        """Assigns distinct semantic role titles to clusters based on feature centroids."""
        n_clusters = len(np.unique(cluster_ids))
        stats_by_cluster = []

        for cid in range(n_clusters):
            mask = (cluster_ids == cid)
            sub_raw = self.X_raw[mask]
            stats_by_cluster.append({
                "cid": cid,
                "avg_hp": float(np.mean(sub_raw[:, self.FEATURE_COLS.index("health_base")])),
                "avg_dps": float(np.mean(sub_raw[:, self.FEATURE_COLS.index("dps")])),
                "avg_ammo": float(np.mean(sub_raw[:, self.FEATURE_COLS.index("ammo")])),
                "avg_mobility": float(np.mean(sub_raw[:, self.FEATURE_COLS.index("mobility_score")])),
                "avg_heavy_melee": float(np.mean(sub_raw[:, self.FEATURE_COLS.index("heavy_melee_base")])),
            })

        sorted_by_hp = sorted(stats_by_cluster, key=lambda x: x["avg_hp"], reverse=True)
        sorted_by_dps = sorted(stats_by_cluster, key=lambda x: x["avg_dps"] * x["avg_ammo"], reverse=True)
        sorted_by_mob = sorted(stats_by_cluster, key=lambda x: x["avg_mobility"], reverse=True)

        assigned_roles = {}
        assigned_cids = set()

        tank_cid = sorted_by_hp[0]["cid"]
        assigned_roles[tank_cid] = "Tank / Frontline"
        assigned_cids.add(tank_cid)

        for item in sorted_by_dps:
            cid = item["cid"]
            if cid not in assigned_cids:
                assigned_roles[cid] = "Carry / Marksman"
                assigned_cids.add(cid)
                break

        for item in sorted_by_mob:
            cid = item["cid"]
            if cid not in assigned_cids:
                assigned_roles[cid] = "Assassin / Ganker"
                assigned_cids.add(cid)
                break

        for cid in range(n_clusters):
            if cid not in assigned_cids:
                assigned_roles[cid] = "Support / Utility"

        return assigned_roles

    def compute_pca(self, n_components: int = 2) -> tuple[np.ndarray, np.ndarray]:
        """Computes 2D PCA for visual representation and variance analysis."""
        self.pca = PCA(n_components=n_components, random_state=42)
        X_pca = self.pca.fit_transform(self.X_scaled)
        
        self.df = self.df.with_columns([
            pl.Series("pca_1", X_pca[:, 0]),
            pl.Series("pca_2", X_pca[:, 1]),
        ])
        return X_pca, self.pca.explained_variance_ratio_

    def train_role_classifier(self) -> dict:
        """
        Trains Random Forest Classifier on ground truth hero roles (Core, Offlaner, Side-Support, Mid-Support).
        Computes Stratified K-Fold Cross-Validation and Feature Importances.
        """
        if self.y_true is None:
            raise ValueError("Ground truth roles ('true_role') not present in DataFrame.")

        y = np.array(self.y_true)
        skf = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
        
        rf = RandomForestClassifier(n_estimators=150, max_depth=6, random_state=42)
        cv_scores = cross_val_score(rf, self.X_scaled, y, cv=skf, scoring="accuracy")

        rf.fit(self.X_scaled, y)
        self.rf_classifier = rf

        y_pred = rf.predict(self.X_scaled)
        train_acc = float(accuracy_score(y, y_pred))

        importances = dict(zip(self.FEATURE_COLS, rf.feature_importances_))
        sorted_importances = dict(sorted(importances.items(), key=lambda x: x[1], reverse=True))

        self.df = self.df.with_columns([
            pl.Series("predicted_true_role", y_pred)
        ])

        return {
            "train_accuracy": train_acc,
            "cv_accuracy_mean": float(np.mean(cv_scores)),
            "cv_accuracy_std": float(np.std(cv_scores)),
            "feature_importances": sorted_importances,
            "report": classification_report(y, y_pred, output_dict=True)
        }

    def fit_similarity_engine(self):
        """Initializes Nearest Neighbors model for hero recommendation."""
        self.knn = NearestNeighbors(n_neighbors=len(self.hero_names), metric="euclidean")
        self.knn.fit(self.X_scaled)

    def find_similar_heroes(self, hero_name: str, top_n: int = 5) -> list[tuple[str, str, float]]:
        """Finds top N most stat-similar heroes for a given existing hero."""
        if self.knn is None:
            self.fit_similarity_engine()

        if hero_name not in self.hero_names:
            matches = [h for h in self.hero_names if h.lower() == hero_name.lower()]
            if not matches:
                raise ValueError(f"Hero '{hero_name}' not found in dataset.")
            hero_name = matches[0]

        idx = self.hero_names.index(hero_name)
        distances, indices = self.knn.kneighbors([self.X_scaled[idx]], n_neighbors=top_n + 1)

        results = []
        for dist, i in zip(distances[0][1:], indices[0][1:]):
            name = self.hero_names[i]
            role = self.y_true[i] if self.y_true else "N/A"
            results.append((name, role, float(dist)))
        return results

    def _build_raw_vector_from_dict(self, custom_stats: dict) -> list[float]:
        """Fills missing custom stat values with feature dataset means."""
        # Calculate calculated fields if missing
        hp = custom_stats.get("health_base", custom_stats.get("health", 750.0))
        hp_scale = custom_stats.get("health_scale", 40.0)
        dps = custom_stats.get("dps", 55.0)
        ammo = custom_stats.get("ammo", 20.0)
        b_dmg_b = custom_stats.get("bullet_damage_base", custom_stats.get("bullet_damage", 10.0))
        b_dmg_s = custom_stats.get("bullet_damage_scale", 0.5)
        heavy_b = custom_stats.get("heavy_melee_base", 116.0)
        heavy_s = custom_stats.get("heavy_melee_scale", 3.5)
        move_sp = custom_stats.get("move_speed", 7.0)
        sprint_sp = custom_stats.get("sprint_speed", 2.0)
        dash_sp = custom_stats.get("dash_speed", 14.0)

        derived = {
            "health_base": hp,
            "health_scale": hp_scale,
            "dps": dps,
            "ammo": ammo,
            "bullet_damage_base": b_dmg_b,
            "bullet_damage_scale": b_dmg_s,
            "heavy_melee_base": heavy_b,
            "heavy_melee_scale": heavy_s,
            "move_speed": move_sp,
            "sprint_speed": sprint_sp,
            "dash_speed": dash_sp,
            "health_lvl10": hp + hp_scale * 10,
            "bullet_damage_lvl10": b_dmg_b + b_dmg_s * 10,
            "heavy_melee_lvl10": heavy_b + heavy_s * 10,
            "clip_damage_potential": ammo * b_dmg_b,
            "mobility_score": move_sp + sprint_sp + (dash_sp / 5.0),
            "effective_hp_base": hp * (1.0 + custom_stats.get("bullet_resist_base", 0.0) / 100.0),
            "dps_to_hp_ratio": dps / (hp + 1.0),
        }

        raw_vec = []
        for col in self.FEATURE_COLS:
            if col in custom_stats:
                raw_vec.append(float(custom_stats[col]))
            elif col in derived:
                raw_vec.append(float(derived[col]))
            else:
                # Default to median column value from dataset
                raw_vec.append(float(self.df.select(col).median().item()))
        return raw_vec

    def predict_custom_hero(self, custom_stats: dict, top_n: int = 3) -> dict:
        """
        Predicts ground truth role archetype and finds top N similar heroes for custom stats input.
        """
        if self.rf_classifier is None:
            self.train_role_classifier()
        if self.knn is None:
            self.fit_similarity_engine()

        raw_vec = self._build_raw_vector_from_dict(custom_stats)
        scaled_vec = self.scaler.transform([raw_vec])

        # Predict Role
        pred_role = self.rf_classifier.predict(scaled_vec)[0]
        role_probs = self.rf_classifier.predict_proba(scaled_vec)[0]
        classes = self.rf_classifier.classes_
        prob_dict = {cls: float(prob) for cls, prob in zip(classes, role_probs)}

        # Find Nearest Similar Heroes
        distances, indices = self.knn.kneighbors(scaled_vec, n_neighbors=top_n)

        similar_heroes = []
        for dist, i in zip(distances[0], indices[0]):
            name = self.hero_names[i]
            role = self.y_true[i] if self.y_true else "N/A"
            similar_heroes.append({
                "hero": name,
                "role": role,
                "distance": float(dist)
            })

        return {
            "predicted_role": pred_role,
            "probabilities": prob_dict,
            "similar_heroes": similar_heroes
        }
