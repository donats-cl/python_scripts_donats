import argparse
import sys
import polars as pl
from parser import load_hero_dataframe
from ml_engine import DeadlockMLEngine

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Predict Deadlock hero role and find similar heroes based on custom stats.")
    
    # Weapon Stats
    parser.add_argument("--dps", type=float, help="Damage Per Second")
    parser.add_argument("--bullet_damage_base", type=float, help="Base Bullet Damage")
    parser.add_argument("--bullet_damage_scale", type=float, help="Bullet Damage Scaling per Level")
    parser.add_argument("--pellets_per_shot", type=float, help="Pellets per Shot")
    parser.add_argument("--ammo", type=float, help="Ammo capacity")
    parser.add_argument("--bullets_per_sec", type=float, help="Bullets per second (fire rate)")
    parser.add_argument("--reload_time", type=float, help="Reload time in seconds")
    parser.add_argument("--bullet_velocity", type=float, help="Bullet velocity m/s")

    # Melee Stats
    parser.add_argument("--light_melee_base", type=float, help="Light Melee Base Damage")
    parser.add_argument("--light_melee_scale", type=float, help="Light Melee Scaling per Level")
    parser.add_argument("--heavy_melee_base", type=float, help="Heavy Melee Base Damage")
    parser.add_argument("--heavy_melee_scale", type=float, help="Heavy Melee Scaling per Level")

    # Health & Defense Stats
    parser.add_argument("--health_base", type=float, help="Base Health (HP)")
    parser.add_argument("--health_scale", type=float, help="Health Scaling per Level")
    parser.add_argument("--health_regen", type=float, help="Health Regen per second")
    parser.add_argument("--bullet_resist_base", type=float, help="Bullet Resist Base %")
    parser.add_argument("--bullet_resist_scale", type=float, help="Bullet Resist Scaling %")
    parser.add_argument("--spirit_resist_base", type=float, help="Spirit Resist Base %")
    parser.add_argument("--spirit_resist_scale", type=float, help="Spirit Resist Scaling %")

    # Mobility & Spirit Stats
    parser.add_argument("--move_speed", type=float, help="Move Speed m/s")
    parser.add_argument("--sprint_speed", type=float, help="Sprint Speed m/s")
    parser.add_argument("--dash_speed", type=float, help="Dash Speed m/s")
    parser.add_argument("--stamina", type=float, help="Stamina charges")
    parser.add_argument("--stamina_cooldown", type=float, help="Stamina Cooldown in seconds")
    parser.add_argument("--spirit_power_scale", type=float, help="Spirit Power Scaling")
    
    args = parser.parse_args()

    # Load dataset & engine
    df = load_hero_dataframe()
    engine = DeadlockMLEngine(df)
    engine.train_role_classifier()
    engine.fit_similarity_engine()

    cli_dict = {k: v for k, v in vars(args).items() if v is not None}
    custom_stats = {}

    if cli_dict:
        # User passed CLI flags
        custom_stats.update(cli_dict)
    else:
        print("=" * 70)
        print(" DEADLOCK CUSTOM HERO ROLE PREDICTOR (ALL 22 STAT FEATURES) ")
        print("=" * 70)

        # Preset Hero selection option
        preset_hero = None
        preset_name = input("Enter existing hero name to pre-fill stats (or press Enter for defaults): ").strip()
        if preset_name:
            all_heroes = df.select("hero").to_series().to_list()
            matches = [h for h in all_heroes if h.lower() == preset_name.lower()]
            if matches:
                preset_hero = matches[0]
                hero_row = df.filter(pl.col("hero") == preset_hero).to_dicts()[0]
                print(f" Loaded preset stats for hero: '{preset_hero}'\n")
            else:
                print(f" Hero '{preset_name}' not found. Using dataset medians as defaults.\n")
                hero_row = {}
        else:
            hero_row = {}

        def get_stat(key: str, prompt: str, fallback_default: float) -> float:
            default_val = float(hero_row.get(key, fallback_default))
            val_str = input(f"  - {prompt:<38} [{default_val}]: ").strip()
            if not val_str:
                return default_val
            return float(val_str)

        print("--- [1/4] Weapon Stats ---")
        custom_stats["dps"] = get_stat("dps", "Damage Per Second (DPS)", 60.0)
        custom_stats["bullet_damage_base"] = get_stat("bullet_damage_base", "Base Bullet Damage", 11.0)
        custom_stats["bullet_damage_scale"] = get_stat("bullet_damage_scale", "Bullet Damage Scale per level", 0.5)
        custom_stats["pellets_per_shot"] = get_stat("pellets_per_shot", "Pellets per shot", 1.0)
        custom_stats["ammo"] = get_stat("ammo", "Ammo capacity", 20.0)
        custom_stats["bullets_per_sec"] = get_stat("bullets_per_sec", "Bullets per second (fire rate)", 5.0)
        custom_stats["reload_time"] = get_stat("reload_time", "Reload Time (sec)", 2.0)
        custom_stats["bullet_velocity"] = get_stat("bullet_velocity", "Bullet Velocity (m/s)", 500.0)

        print("\n--- [2/4] Melee Stats ---")
        custom_stats["light_melee_base"] = get_stat("light_melee_base", "Light Melee Base Damage", 63.0)
        custom_stats["light_melee_scale"] = get_stat("light_melee_scale", "Light Melee Scale per level", 1.6)
        custom_stats["heavy_melee_base"] = get_stat("heavy_melee_base", "Heavy Melee Base Damage", 116.0)
        custom_stats["heavy_melee_scale"] = get_stat("heavy_melee_scale", "Heavy Melee Scale per level", 3.4)

        print("\n--- [3/4] Health & Defense Stats ---")
        custom_stats["health_base"] = get_stat("health_base", "Base Health (HP)", 750.0)
        custom_stats["health_scale"] = get_stat("health_scale", "Health Scale per level", 40.0)
        custom_stats["health_regen"] = get_stat("health_regen", "Health Regen per sec", 1.5)
        custom_stats["bullet_resist_base"] = get_stat("bullet_resist_base", "Bullet Resist Base (%)", 0.0)
        custom_stats["bullet_resist_scale"] = get_stat("bullet_resist_scale", "Bullet Resist Scale (%)", 0.0)
        custom_stats["spirit_resist_base"] = get_stat("spirit_resist_base", "Spirit Resist Base (%)", 0.0)
        custom_stats["spirit_resist_scale"] = get_stat("spirit_resist_scale", "Spirit Resist Scale (%)", 0.0)

        print("\n--- [4/4] Mobility & Spirit Stats ---")
        custom_stats["move_speed"] = get_stat("move_speed", "Move Speed (m/s)", 7.0)
        custom_stats["sprint_speed"] = get_stat("sprint_speed", "Sprint Speed (m/s)", 2.0)
        custom_stats["dash_speed"] = get_stat("dash_speed", "Dash Speed (m/s)", 14.0)
        custom_stats["stamina"] = get_stat("stamina", "Stamina charges", 3.0)
        custom_stats["stamina_cooldown"] = get_stat("stamina_cooldown", "Stamina Cooldown (sec)", 5.0)
        custom_stats["spirit_power_scale"] = get_stat("spirit_power_scale", "Spirit Power Scale per level", 1.0)

    # Run Prediction
    result = engine.predict_custom_hero(custom_stats, top_n=5)

    print("\n" + "=" * 70)
    print(" PREDICTION RESULTS ")
    print("=" * 70)
    print(f"\n🎯 Predicted Ground Truth Role:  >>> {result['predicted_role'].upper()} <<<\n")
    
    print("Role Probabilities:")
    for role, prob in sorted(result["probabilities"].items(), key=lambda x: x[1], reverse=True):
        bar = "█" * int(prob * 20)
        print(f"  - {role:22s}: {prob*100:5.1f}%  {bar}")

    print("\n👥 Top 5 Most Similar Existing Deadlock Heroes:")
    for idx, sim in enumerate(result["similar_heroes"], 1):
        print(f"  {idx}. {sim['hero']:16s} (Role: {sim['role']:20s} | Distance: {sim['distance']:.2f})")

if __name__ == "__main__":
    main()
