from glob import glob

from sentence_transformers import SentenceTransformer, util

from info import known_heroes

model = SentenceTransformer("all-MiniLM-L6-v2")

known_texts = []

for i in glob("out/*.md"):
    with open(i, "r", encoding='utf-8') as f:
        known_texts.append(f.read())

known_embeddings = model.encode(known_texts, convert_to_tensor=True)

new_hero_description = """
Setup Bishop
Cast Range 20m
Radius 3.5m
Cooldown 12s
Create a bishop that remains in place indefinitely.

Move ( Zoom / alt-fire): Moves the bishop, applying a fading slow and dealing spirit damage to enemies it passes through. After a delay, activates diagonal squares that deal additional spirit damage when stepped on.

Re-activate to recall all bishops, ending the ability.

-30%
Fading Move Speed

x2

70
Impact Damage
On Square:

x0.64

25
Damage

2  Square Range

12m  Move Distance  x0.23

3s  Slow Duration

3s  Move Cooldown
Ability Point1
+5m Move Distance
+15% Fading Slow
Ability Point2
+1 Max Pieces
Can Recast within 8s
Ability Point5
+1 Square Range
Squares reduce Spirit Resist by -2.5%, stacking 10 times
Debuff duration reduced by Debuff ResistEffect can be dispelledCC effect suppressed by Unstoppable

Kingside Knight

Kingside Knight
Cast Range 28m
Cooldown 25s
Promote an ally to be a knight, granting bonus stamina and barrier for a duration.

If self-cast you develop yourself as king instead, granting double the barrier but no stamina.

Move ( Zoom / alt-fire): Moves the piece, making it invulnerable during the duration before landing.

x0.8

80
Barrier

1
Stamina

7m  King Move Distance  x0.14

13m  Move Distance  x0.23

7s  Buff Duration
Ability Point1
-8s Cooldown
Ability Point2
+80 Barrier
+1 Stamina
Ability Point5
Can target two allies within radius.
On Self: Remove all debuffs after a move
Rook Battery

Rook Battery
Cooldown 33s
Release a pair of rooks that travel forward, dealing spirit damage and applying immobilize. If the rooks hit a wall, they reflect back in the opposite direction.

Re-Activate: Split the rooks perpendicularly.

x1.3

50
Damage
On Enemy Hit:
Immobilize
1s
Immobilize Duration

1  Wall Reflects
Ability Point1
On Hit: Reduce 25% Fire Rate for 5s
Ability Point2
On Hit: 5% Current Health as Damage
Ability Point5
+1 Wall Reflects
-12s Cooldown
+0.5s Immobilize Duration
Debuff duration reduced by Debuff ResistTriggers Reactive BarrierEffect can be dispelledDisable prevented by IndomitableCC effect suppressed by Unstoppable
Develop Queen

Develop Queen
Cast Range 30m
Cooldown 210s
Summon a queen that crashes down, dealing spirit damage in an area. After a delay, the queen releases squares in straight lines that deal spirit damage again and apply stun.

Move ( Zoom / alt-fire): The queen leaps to the target location, dealing the same effects again.

Re-activate to recall the queen early, ending the ability.

x1.4

120
Damage
Stun
1.25s
Stun Duration

3  Square Range

16m  Move Distance  x0.23

5s  Move Cooldown

2  Additional Moves

15%  Move Speed

1.5s  Slow Duration
Ability Point1
-40s Cooldown
Ability Point2
+15% Slow. Checkmates heroes below 200 health, executing them.
Ability Point5
+2 Moves
+1 Square Range
"""

# new_hero_description = "Pillow Toss: Hurl a pillow that deals spirit damage, knocks back enemies, and reduces Rem's cooldowns on hit.\nTag Along: Jump onto an ally to hitch a ride, healing them based on missing health and providing persistent health regeneration.\nLil Helpers: Dispatch dream helpers to pick up boxes, gather souls, or buff and heal allies and troopers.\nNaptime: Channel a gaze through walls and terrain that slows enemies, prevents movement abilities, and puts them into a deep sleep."

new_hero_embedding = model.encode(new_hero_description, convert_to_tensor=True)

cosine_scores = util.cos_sim(new_hero_embedding, known_embeddings)[0]

results = []
for idx, hero in enumerate(known_heroes):
    score = cosine_scores[idx].item()
    results.append((hero["hero"], hero["role"], score))
results.sort(key=lambda x: x[2], reverse=True)

print("--- Результаты предсказания ---")
for hero, role, score in results:
    print(
        f"Похож на: {hero:12} | Роль: {role:15} | Сходство: {score * 100:.1f}%"
    )

top_match = results[0]
print(
    f"\nИтог: скорее всего роль нового героя — '{top_match[1]}' (сходство с {top_match[0]})"
)
