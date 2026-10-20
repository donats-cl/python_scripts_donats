import os
import sys
import polars as pl
from parser import load_hero_dataframe
from ml_engine import DeadlockMLEngine

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 65)
    print(" DEADLOCK HERO ROLE PREDICTION & ANALYTICS PIPELINE ")
    print(" Supervised ML & Polars Integration ")
    print("=" * 65)

    # 1. Load Data with Polars & Ground Truth Roles
    out_dir = "./out"
    print(f"\n[1/5] Loading hero stat files and ground truth roles...")
    df = load_hero_dataframe(out_dir=out_dir)
    print(f" Loaded {df.height} heroes with ground truth roles.")

    # Export datasets via Polars
    csv_path = "./hero_stats.csv"
    parquet_path = "./hero_stats.parquet"
    df.write_csv(csv_path)
    df.write_parquet(parquet_path)
    print(f" Exported datasets to '{csv_path}' and '{parquet_path}' (via Polars)")

    # 2. ML Engine & Supervised Role Classification
    print("\n[2/5] Training Supervised Random Forest Classifier on Ground Truth Roles...")
    engine = DeadlockMLEngine(df)
    clf_metrics = engine.train_role_classifier()

    print(f"  Training Accuracy: {clf_metrics['train_accuracy']*100:.1f}%")
    print(f"  Stratified 3-Fold CV Accuracy: {clf_metrics['cv_accuracy_mean']*100:.1f}% (+/- {clf_metrics['cv_accuracy_std']*100:.1f}%)")

    print("\nTop 7 Stat Drivers for Official Roles:")
    for feat, imp in list(clf_metrics["feature_importances"].items())[:7]:
        print(f"  - {feat:25s}: {imp*100:5.2f}%")

    # 3. Unsupervised Clustering & PCA
    print("\n[3/5] Performing Unsupervised Role Clustering (K-Means) & PCA...")
    df_clustered = engine.fit_clusters(n_clusters=4)
    X_pca, var_ratio = engine.compute_pca(n_components=2)
    print(f"  PCA Variance Ratio: PC1 = {var_ratio[0]*100:.2f}%, PC2 = {var_ratio[1]*100:.2f}%")

    # 4. Hero Similarity Search Demonstration
    print("\n[4/5] Hero Similarity Search (KNN) with True Roles:")
    demo_heroes = ["Abrams", "Bebop", "Haze", "Kelvin", "Seven"]
    for hero in demo_heroes:
        try:
            sims = engine.find_similar_heroes(hero, top_n=3)
            sim_str = ", ".join([f"{h} [{r}] (d={d:.2f})" for h, r, d in sims])
            print(f"  - Most similar to {hero:10s} -> {sim_str}")
        except ValueError:
            pass

    # 5. Generate Markdown Summary Report
    report_path = "./roles_summary.md"
    generate_markdown_report(engine.df, clf_metrics, report_path)
    print(f"\n Summary report generated and saved to '{report_path}'.")

    # 6. Hero Roles Summary Table
    print("\n" + "=" * 65)
    print(" GROUND TRUTH VS PREDICTED HERO ROLES ")
    print("=" * 65)
    summary_table = engine.df.select([
        "hero", "true_role", "predicted_true_role", "cluster_role", "health_base", "dps", "move_speed"
    ])
    print(summary_table)


def generate_markdown_report(df: pl.DataFrame, clf_metrics: dict, output_path: str):
    """Generates a structured markdown report summarizing hero ground truth roles and ML findings."""
    lines = []
    lines.append("# Deadlock Hero Ground Truth Role & Stats ML Report\n")
    lines.append("## Overview")
    lines.append(f"Analysis of **{df.height} Deadlock Heroes** using **Polars** and Supervised Random Forest Machine Learning.")
    lines.append("\n## Official Role Breakdown & Average Stats\n")

    roles = df.select("true_role").unique().to_series().to_list()
    for role in sorted(roles):
        sub = df.filter(pl.col("true_role") == role)
        heroes_list = ", ".join(sub.select("hero").to_series().to_list())
        avg_hp = sub.select("health_base").mean().item()
        avg_dps = sub.select("dps").mean().item()
        avg_speed = sub.select("move_speed").mean().item()
        
        lines.append(f"### {role} ({sub.height} Heroes)")
        lines.append(f"- **Heroes**: {heroes_list}")
        lines.append(f"- **Average Base HP**: {avg_hp:.1f}")
        lines.append(f"- **Average DPS**: {avg_dps:.1f}")
        lines.append(f"- **Average Move Speed**: {avg_speed:.2f} m/s\n")

    lines.append("## Supervised Model Performance & Top Feature Drivers\n")
    lines.append(f"- **Model**: Random Forest Classifier")
    lines.append(f"- **Training Accuracy**: {clf_metrics['train_accuracy']*100:.1f}%")
    lines.append(f"- **Stratified 3-Fold Cross-Validation Accuracy**: {clf_metrics['cv_accuracy_mean']*100:.1f}% (+/- {clf_metrics['cv_accuracy_std']*100:.1f}%)\n")

    lines.append("| Rank | Stat Feature | Feature Importance |")
    lines.append("| --- | --- | --- |")
    for rank, (feat, imp) in enumerate(list(clf_metrics["feature_importances"].items())[:10], 1):
        lines.append(f"| {rank} | `{feat}` | {imp*100:.2f}% |")

    lines.append("\n---\n*Report generated using Polars & Scikit-Learn.*")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
