from pedalboard import (
    Pedalboard,
    Chorus,
    Compressor,
    HighShelfFilter,
    Limiter,
    LowShelfFilter,
    PeakFilter,
    Reverb,
)
from pedalboard.io import AudioFile

input_file = "my.mp3"
output_file = "my_moon_my_man_deep.wav"

# 1. Загружаем аудио
with AudioFile(input_file) as f:
    audio = f.read(f.frames)
    sr = f.samplerate

# 2. Создаем цепочку придания «глубины»
board = Pedalboard([
    # ШАГ 1: Добавляем веса и мягкого баса (глубина снизу)
    LowShelfFilter(cutoff_frequency_hz=80, gain_db=3.5),
    # ШАГ 2: Убираем коробочную "муть" в средних частотах
    PeakFilter(cutoff_frequency_hz=300, gain_db=-2.5, q=1.0),
    # ШАГ 3: Добавляем "воздуха" и прозрачности на высоких частотах
    HighShelfFilter(cutoff_frequency_hz=10000, gain_db=2.0),
    # ШАГ 4: Стерео-расширение (хорус создает объём и 3D-ощущение ширины)
    Chorus(rate_hz=0.4, depth=0.12, feedback=0.1, mix=0.20),
    # ШАГ 5: Микро-пространство (реверберация совсем чуть-чуть (10-12%), чтобы не превратить в кашу)
    Reverb(
        room_size=0.65, damping=0.4, wet_level=0.12, dry_level=0.95
    ),
    # ШАГ 6: Компрессия (склеивает звук и вытягивает тихие глубокие детали)
    Compressor(threshold_db=-14.0, ratio=2.5, attack_ms=20, release_ms=100),
    # ШАГ 7: Лимитер (защищает от искажений и делает звук собранным)
    Limiter(threshold_db=-0.5),
])

# 3. Применяем обработку
print("Обрабатываем трек и добавляем глубину...")
effected = board(audio, sr)

# 4. Сохраняем результат
with AudioFile(output_file, "w", sr, effected.shape[0]) as f:
    f.write(effected)

print(f"Готово! Глубокая версия сохранена в {output_file}")
