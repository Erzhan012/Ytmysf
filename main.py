import os
import asyncio
import hashlib
import html
import shutil
import re
from pathlib import Path
from typing import List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from config import BOT_TOKEN, SEARCH_SOURCES, MAX_RESULTS_TOTAL, PAGE_SIZE, SEARCH_CACHE_TTL, TEMP_DIR, ADMIN_ID
from cache import TTLCache
from utils import sanitize_title, format_duration
import music_downloader

# Проверка токена
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан. Установите переменную окружения BOT_TOKEN.")

search_cache = TTLCache(ttl=SEARCH_CACHE_TTL)
URL_RE = re.compile(r"https?://\S+")

def _cache_key_for_query(query: str) -> str:
    h = hashlib.sha256()
    h.update(query.strip().lower().encode("utf-8"))
    return h.hexdigest()

def build_keyboard(cache_key: str, page: int, total_pages: int, entries: List[dict]) -> InlineKeyboardMarkup:
    buttons = []
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, len(entries))
    for idx in range(start, end):
        title = entries[idx].get("title") or "Unknown"
        title = sanitize_title(title)
        cb = f"play:{cache_key}:{idx}"
        buttons.append([InlineKeyboardButton(text=f"{idx - start + 1}. {title[:50]}", callback_data=cb)])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page:{cache_key}:{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"page:{cache_key}:{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("Закрыть", callback_data=f"close:{cache_key}")])
    return InlineKeyboardMarkup(buttons)

async def _run_search(query: str):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, music_downloader.search_combined, query, SEARCH_SOURCES, MAX_RESULTS_TOTAL)

async def _run_fetch_info(url: str):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, music_downloader.fetch_info, url)

async def _run_download(url: str, out_dir: str):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, music_downloader.download_to_mp3, url, out_dir)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Отправь название песни или ссылку на трек, либо используй команду /search <запрос>.\n"
        "Бот покажет результаты (страницы по 10), нажми кнопку чтобы скачать MP3. Панель останется доступной."
    )

async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        query = " ".join(context.args).strip()
    else:
        await update.message.reply_text("Укажите запрос, например: /search Billie Jean")
        return
    await do_search_and_send(update, query)

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        return
    if URL_RE.search(text):
        url = URL_RE.search(text).group(0)
        await do_fetch_and_send(update, url)
        return
    await do_search_and_send(update, text)

async def do_fetch_and_send(update: Update, url: str):
    key = _cache_key_for_query(url)
    cached = search_cache.get(key)
    if cached:
        entries = cached
    else:
        msg = await update.message.reply_text(f"Извлекаю информацию о ссылке...")
        try:
            info = await _run_fetch_info(url)
        finally:
            try:
                await msg.delete()
            except Exception:
                pass
        if not info:
            await update.message.reply_text("Не удалось извлечь информацию по ссылке.")
            return
        entries = [info]
        search_cache.set(key, entries)
    total_pages = (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE
    page = 0
    keyboard = build_keyboard(key, page, total_pages, entries)
    e = entries[0]
    dur = e.get("duration")
    dur_str = f" [{format_duration(dur)}]" if dur else ""
    text = f"Найден трек: {html.escape(e.get('title') or 'Unknown')}{dur_str}"
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")

async def do_search_and_send(update: Update, query: str):
    key = _cache_key_for_query(query)
    cached = search_cache.get(key)
    if cached:
        entries = cached
    else:
        msg = await update.message.reply_text(f"Ищу: {html.escape(query)} ...")
        try:
            entries = await _run_search(query)
        finally:
            try:
                await msg.delete()
            except Exception:
                pass
        search_cache.set(key, entries)
    if not entries:
        await update.message.reply_text("❌ Ничего не найдено. Попробуйте изменить запрос.")
        return
    total_pages = (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE
    page = 0
    keyboard = build_keyboard(key, page, total_pages, entries)
    first_chunk = entries[0: min(PAGE_SIZE, len(entries))]
    text_lines = [f"Результаты поиска: {html.escape(query)} (всего: {len(entries)})"]
    for i, e in enumerate(first_chunk, start=1):
        dur = e.get("duration")
        dur_str = f" [{format_duration(dur)}]" if dur else ""
        t = sanitize_title(e.get("title") or "Unknown")
        text_lines.append(f"{i}. {t}{dur_str}")
    text = "\n".join(text_lines)
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if data.startswith("page:"):
        _, cache_key, page_s = data.split(":", 2)
        page = int(page_s)
        entries = search_cache.get(cache_key)
        if not entries:
            await query.message.reply_text("Кэш просрочен. Повторите поиск.")
            return
        total_pages = (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE
        keyboard = build_keyboard(cache_key, page, total_pages, entries)
        try:
            await query.message.edit_reply_markup(reply_markup=keyboard)
        except Exception:
            await query.message.reply_text("Обновление страницы...", reply_markup=keyboard)
        return
    if data.startswith("play:"):
        _, cache_key, idx_s = data.split(":", 2)
        idx = int(idx_s)
        entries = search_cache.get(cache_key)
        if not entries:
            await query.message.reply_text("Кэш просрочен. Повторите поиск.")
            return
        if idx < 0 or idx >= len(entries):
            await query.message.reply_text("Неверный индекс трека.")
            return
        entry = entries[idx]
        await query.answer(text="Начинаю загрузку, подожди...")

        os.makedirs(TEMP_DIR, exist_ok=True)
        out_dir = Path(TEMP_DIR) / f"{cache_key}_{idx}"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        url = entry.get("webpage_url") or entry.get("_raw", {}).get
