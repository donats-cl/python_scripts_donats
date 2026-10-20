import os
import tempfile

import librosa
import numpy as np
import telebot

from config import TOKEN

bot = telebot.TeleBot(TOKEN)


# ---------- Извлечение признаков из librosa ----------

KEY_NAMES = ["C", "C#", "D", "D#", "E", "F",
             "F#", "G", "G#", "A", "A#", "B"]
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                          2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                          2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def detect_key(y, sr):
    """Тональность через хромаграмму + Krumhansl-Schmuckler profiles."""
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    chroma = chroma / (chroma.sum() + 1e-9)

    best, best_corr = ("C", 1), -2
    for i in range(12):
        major = np.roll(MAJOR_PROFILE, i) / MAJOR_PROFILE.sum()
        minor = np.roll(MINOR_PROFILE, i) / MINOR_PROFILE.sum()
        c_maj = np.corrcoef(chroma, major)[0, 1]
        c_min = np.corrcoef(chroma, minor)[0, 1]
        if c_maj > best_corr:
            best, best_corr = (KEY_NAMES[i], 1), c_maj
        if c_min > best_corr:
            best, best_corr = (KEY_NAMES[i], 0), c_min
    return best  # (тоника, 1=major / 0=minor)


def estimate_features(y, sr):
    """Оценка Spotify-подобных признаков из librosa."""
    duration_ms = int(librosa.get_duration(y=y, sr=sr) * 1000)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)

    # --- нормализация выходов librosa до скаляров ---
    tempo = float(np.atleast_1d(tempo)[0])
    beats = np.atleast_1d(beats)

    rms = librosa.feature.rms(y=y)[0]
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    zcr = librosa.feature.zero_crossing_rate(y)[0]
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    flatness = librosa.feature.spectral_flatness(y=y)[0]

    key, mode = detect_key(y, sr)

    def norm(x, lo, hi):
        return float(np.clip((x - lo) / (hi - lo), 0, 1))

    loudness = float(librosa.amplitude_to_db(np.sqrt(np.mean(rms**2))).item())

    features = {
        "popularity": None,
        "duration_ms": duration_ms,
        "danceability": norm(np.std(np.diff(beats)), 0, 0.1)
                          * norm(np.mean(onset_env), 0, 5),
        "energy": norm(np.sqrt(np.mean(rms**2)), 0, 0.3),
        "key": KEY_NAMES.index(key),
        "loudness": loudness,
        "mode": mode,
        "speechiness": norm(np.mean(zcr), 0.05, 0.25)
                          * (1 - norm(np.mean(chroma.max(axis=0)), 0.3, 0.8)),
        "acousticness": 1 - norm(np.mean(centroid), 500, 5000),
        "instrumentalness": norm(np.mean(flatness), 0, 0.3),
        "liveness": norm(np.mean(np.abs(rms - rms.mean())), 0, 0.15),
        "valence": float(np.clip(0.5 * mode
                           + 0.5 * norm(np.mean(centroid), 500, 4000), 0, 1)),
        "tempo": round(tempo, 1),
        "time_signature": 4,
    }
    return features


# ---------- Handlers ----------

@bot.message_handler(content_types=["audio", "voice"])
def handle_audio(message):
    file_info = (message.audio or message.voice).file_id
    file = bot.get_file(file_info)
    ext = ".ogg" if message.voice else os.path.splitext(
        message.audio.file_name or ".mp3")[1]

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        downloaded = bot.download_file(file.file_path)
        tmp.write(downloaded)
        path = tmp.name

    try:
        y, sr = librosa.load(path, sr=22050, mono=True)
        features = estimate_features(y, sr)

        text = (
            f"🎵 Анализ аудио:\n"
            f"⏱ duration_ms: {features['duration_ms']}\n"
            f"💃 danceability: {features['danceability']:.2f}\n"
            f"⚡ energy: {features['energy']:.2f}\n"
            f"🎹 key: {KEY_NAMES[features['key']]} ({features['key']})"
            f" {'major' if features['mode'] else 'minor'}\n"
            f"🔊 loudness: {features['loudness']:.1f} dB\n"
            f"🗣 speechiness: {features['speechiness']:.2f}\n"
            f"🎸 acousticness: {features['acousticness']:.2f}\n"
            f"🎼 instrumentalness: {features['instrumentalness']:.2f}\n"
            f"🎤 liveness: {features['liveness']:.2f}\n"
            f"😊 valence: {features['valence']:.2f}\n"
            f"🥁 tempo: {features['tempo']} BPM\n"
            f"📏 time_signature: {features['time_signature']}/4"
        )
        bot.reply_to(message, text)
    except Exception as e:
        bot.reply_to(message, f"Ошибка обработки: {e}")
    finally:
        os.unlink(path)


if __name__ == "__main__":
    print("Start Bot")
    bot.infinity_polling()
