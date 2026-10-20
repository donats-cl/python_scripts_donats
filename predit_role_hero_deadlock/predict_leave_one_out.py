import sys
import polars as pl
from parser import load_hero_dataframe
from ml_engine import DeadlockMLEngine

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 80)
    print(" DEADLOCK HERO ROLE PREDICTION - LEAVE-ONE-HERO-OUT (LOO) EVALUATION ")
    print(" (Each hero is predicted by a model trained WITHOUT that hero in the dataset) ")
    print("=" * 80)

    # 1. Load full dataset
    df = load_hero_dataframe()
    all_heroes = df.select("hero").to_series().to_list()
    total_heroes = len(all_heroes)

    print(f"\nLoaded {total_heroes} heroes from dataset.")
    print("Starting Leave-One-Out validation...\n")

    results = []
    correct_count = 0

    print(f"{'Hero':<16} | {'True Role':<14} | {'Predicted Role':<14} | {'Status':<8} | {'Prob':<6} | {'Nearest Training Hero'}")
    print("-" * 88)

    for hero_name in all_heroes:
        # Split: Train dataset excludes target hero, Test dataset contains only target hero
        df_train = df.filter(pl.col("hero") != hero_name)
        df_test = df.filter(pl.col("hero") == hero_name)

        true_role = df_test.select("true_role").item()

        # Initialize ML engine trained ONLY on df_train
        engine_train = DeadlockMLEngine(df_train)
        engine_train.train_role_classifier()
        engine_train.fit_similarity_engine()

        # Extract features of test hero
        test_hero_row = df_test.to_dicts()[0]
        
        # Predict using engine trained without test hero
        pred_res = engine_train.predict_custom_hero(test_hero_row, top_n=1)
        pred_role = pred_res["predicted_role"]
        top_prob = max(pred_res["probabilities"].values())
        nearest_hero = pred_res["similar_heroes"][0]["hero"] if pred_res["similar_heroes"] else "N/A"
        nearest_dist = pred_res["similar_heroes"][0]["distance"] if pred_res["similar_heroes"] else 0.0

        is_match = (pred_role == true_role)
        if is_match:
            correct_count += 1
            status_str = "MATCH"
        else:
            status_str = "MISMATCH"

        results.append({
            "hero": hero_name,
            "true_role": true_role,
            "predicted_role": pred_role,
            "status": status_str,
            "confidence": top_prob,
            "nearest_hero": nearest_hero,
            "nearest_distance": nearest_dist,
            "probabilities": pred_res["probabilities"]
        })

        print(f"{hero_name:<16} | {true_role:<14} | {pred_role:<14} | {status_str:<8} | {top_prob*100:5.1f}% | {nearest_hero} (d={nearest_dist:.2f})")

    accuracy = (correct_count / total_heroes) * 100

    print("=" * 88)
    print(f" LEAVE-ONE-OUT ACCURACY SUMMARY: {correct_count}/{total_heroes} ({accuracy:.1f}%) ")
    print("=" * 88)

    if correct_count < total_heroes:
        print("\nMisclassified Heroes Breakdown:")
        for r in results:
            if r["status"] == "MISMATCH":
                print(f" - {r['hero']}: True='{r['true_role']}', Predicted='{r['predicted_role']}' (Confidence: {r['confidence']*100:.1f}%)")
    else:
        print("\nAll heroes were accurately predicted when excluded from the training dataset!")

if __name__ == "__main__":
    main()
