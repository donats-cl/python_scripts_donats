from boon import Demo


def analys_demo(path: str):
    dem: Demo = Demo(path)
    dem.abilities.write_parquet("./abilities.parquet")
    dem.ability_ticks.write_parquet("./ability_ticks.parquet")
    dem.ability_upgrades.write_parquet("./ability_upgrades.parquet")
    dem.active_modifiers.write_parquet("./active_modifiers.parquet")
    dem.breakables.write_parquet("./breakables.parquet")
    dem.chat.write_parquet("./chat.parquet")
    dem.damage.write_parquet("./damage.parquet")
    dem.flex_slots.write_parquet("./flex_slots.parquet")
    dem.item_purchases.write_parquet("./item_purchases.parquet")
    dem.kills.write_parquet("./kills.parquet")
    dem.mid_boss.write_parquet("./mid_boss.parquet")
    dem.neutrals.write_parquet("./neutrals.parquet")
    dem.objectives.write_parquet("./objectives.parquet")
    dem.player_ticks.write_parquet("./player_ticks.parquet")
    dem.players.write_parquet("./players.parquet")
    dem.rift.write_parquet("./rift.parquet")
    dem.sinners_sacrifice.write_parquet("./sinners_sacrifice.parquet")
    dem.stat_modifier_events.write_parquet("./stat_modifier_events.parquet")
    dem.troopers.write_parquet("./troopers.parquet")
    dem.urn.write_parquet("./urn.parquet")
    dem.kill_participation().write_parquet("./kill_participation.parquet")
    dem.teamfights().write_parquet("./teamfights.parquet")
    dem.time_dead().write_parquet("./time_dead.parquet")

MATCH_ID = 127800067

analys_demo(rf"C:\Program Files (x86)\Steam\steamapps\common\Deadlock\game\citadel\addons\replays\{MATCH_ID}.dem")
