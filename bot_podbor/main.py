import asyncio
import logging
import os
import sys

import polars as pl
import requests
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN: str = str(os.getenv("BOT_TOKEN"))
TMDB_API: str = str(os.getenv("TMDB_API"))
PATH = "list.csv"

URL: str = "https://api.themoviedb.org/3/search/{2}?query={0}&year={1}&language={3}"
URL_PHOTO: str = "https://image.tmdb.org/t/p/w500"

dp = Dispatcher()
users = {}
movies = {}

def _get(path):
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {TMDB_API}"
    }
    r = requests.get(path, headers=headers)
    r.raise_for_status()
    return r.json()

def calc_vote(a: dict[str, str]):
    r: dict[str, int] = {}
    names = [i for i in a]

    for i in names:
        j = len(a[i][1])
        k = len(a[i][1])
        r[i] = j-k

    win = max(r, key=lambda k: r[k])
    lose = min(r, key=lambda k: r[k])

    return (win, lose, r)

def get_main_keyboard(title: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="+", callback_data=f"pos_{title}"),
        InlineKeyboardButton(text="-", callback_data=f"neg_{title}"),
    )
    return builder.as_markup()

@dp.callback_query(F.data.startswith("pos_"))
async def like_movie(call: CallbackQuery):
    movie_id = call.data.split("_", 1)[1]
    if not movie_id in movies: movies[movie_id] = [set({}), set({})]
    usr_id = call.from_user.id
    movies[movie_id][0].add(usr_id)
    movies[movie_id][1].discard(usr_id)
    await call.answer("Liked!")

@dp.callback_query(F.data.startswith("neg_"))
async def dis_movie(call: CallbackQuery):
    movie_id = call.data.split("_", 1)[1]
    if not movie_id in movies: movies[movie_id] = [set({}), set({})]
    usr_id = call.from_user.id
    movies[movie_id][0].discard(usr_id)
    movies[movie_id][1].add(call.from_user.id)
    await call.answer("Disliked!")

@dp.message(CommandStart())
async def start(msg: Message):
    usr_id = msg.from_user.id
    users[usr_id] = users[usr_id]+1 if usr_id in users else 0
    if len(list_movie) == users[usr_id]:
        r = calc_vote(movies)
        await msg.answer(f"End! Wait Result\nWin: {r[0]}\nLose: {r[1]}\n\nTEST: {r}")
    else:
        info = list_movie[users[usr_id]]
        title = info.get('title')
        org_key = 'original_title'
        if not title:
            org_key = 'original_name'
            title = info.get('name')
        org_title = f"({info[org_key]})" if title != info[org_key] else ""
        res = f"{title}{org_title}\n"
        res += info["overview"]
        await msg.answer_photo(
            photo=f"{URL_PHOTO}{info['poster_path']}",
            caption=res,
            reply_markup=get_main_keyboard(info[org_key])
        )

async def main():
    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    df = pl.read_csv(PATH)

    list_movie = []

    for title, years, type in df.iter_rows():
        movie = _get(URL.format(title, years, type, "ru-RU"))
        if len(movie["results"]) < 1:
            print(f"miss {title}")
            continue
        if movie["results"][0]['overview'] == "":
            movie = _get(URL.format(title, years, type, "en-US"))
        list_movie.append(movie["results"][0])

    asyncio.run(main())
