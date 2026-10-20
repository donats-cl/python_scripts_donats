import polars as pl
import yt_dlp

df: pl.DataFrame = pl.read_csv('export.csv')

def download_track(artist: str, title: str, output_folder: str = "downloads"):
    # ytsearch1: limits the search to the single top result
    search_query = f"ytsearch1:{artist} - {title} audio"

    ydl_opts = {
        # Select best available audio stream
        'format': 'bestaudio/best',

        # Post-processor to convert audio to MP3 using ffmpeg
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',  # 192, 256, or 320 kbps
        }],

        'postprocessor_args': [
                '-filter:a', 'loudnorm' # или проще: '-af', 'volume=-1.5dB'
        ],

        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
            }
        },

        # Filename format: e.g., "downloads/Daft Punk - Get Lucky.mp3"
        'outtmpl': f'{output_folder}/%(title)s.%(ext)s',

        # Avoid downloading entire playlists if search returns one
        'noplaylist': True,

        # Clean console output
        'quiet': False,
        'no_warnings': True,
    }

    print(f"Searching and downloading: {artist} - {title}...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([search_query])
    print("Download complete!")

for row in df.head(50).iter_rows():
    download_track(*row)
