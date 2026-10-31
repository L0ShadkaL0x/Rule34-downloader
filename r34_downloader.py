#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
r34_downloader.py — downloader for rule34.xxx images/videos via the r34.app mirror API.

Bypasses provider-level DNS blocking for rule34.xxx sites by pinning DNS
answers from DNS-over-HTTPS (dns.google) inside this process.

Usage examples
--------------
# interactive menu (Windows: python, Linux: python3)
python r34_downloader.py

# all images of one author
python r34_downloader.py --tag xipa --out-dir "C:\\path\\xipa"

# several tags at once = post must contain ALL of them (AND)
python r34_downloader.py --tags "petrification,cursed" --out-dir "..."

# three tags + exclude some tag
python r34_downloader.py --tags "petrification,statue" --exclude-tags "ai_generated" --out-dir "..."

# images AND videos
python r34_downloader.py --tag yonpii --include-videos --out-dir "..."

# one post (image or video; --url can be repeated)
python r34_downloader.py --url "https://rule34.xxx/index.php?page=post&s=view&id=19151225" --out-dir "..."

Notes
-----
* Files are saved as <post_id>.<ext>; existing files are skipped,
  so you can re-run the script daily to fetch only new posts.
* If the API rate-limits you ("empty response"), wait a few minutes and re-run.
* The video CDN (api-cdn-mp4.rule34.xxx) is blocked by some ISPs on the
  connection level — images still work, videos may fail with VIDEO FAIL.
"""

import argparse
import codecs
import re
import textwrap
import os
import socket
import shutil
import sys
import time
import urllib.parse
import urllib.request
import json

DEFAULT_MAX_PAGES = 10000
CURRENT_LANGUAGE = "en"


def tr(english, russian):
    return russian if CURRENT_LANGUAGE == "ru" else english


def language_settings_path():
    if os.name == "nt":
        root = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    else:
        root = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(root, "Rule34Downloader", "settings.json")


def choose_language():
    """Ask before the first interactive session, then remember the choice."""
    global CURRENT_LANGUAGE
    selected = 1 if CURRENT_LANGUAGE == "ru" else 0
    try:
        if (sys.stdin.isatty() and sys.stdout.isatty()
                and (os.name == "nt" or os.environ.get("TERM") != "dumb")):
            try:
                with Terminal() as terminal:
                    while True:
                        lines = ["", "  Rule34 Downloader", "",
                                 "  Choose your language / Выберите язык", ""]
                        for index, name in enumerate(("English", "Русский")):
                            lines.append((ACCENT + "  ❯ " if selected == index else FOREGROUND + "    ") + name)
                        lines += ["", MUTED + "  ↑/↓ select / выбор · Enter confirm / выбрать · Esc exit"]
                        sys.stdout.write(BASE + "\x1b[H\x1b[J" + "\r\n".join(BASE + line for line in lines))
                        sys.stdout.flush()
                        key, text = terminal.read_key()
                        if key in ("up", "down", "tab", "backtab", "left", "right"):
                            selected = 1 - selected
                        elif key == "text" and text in ("1", "2"):
                            selected = int(text) - 1
                        elif key == "enter":
                            break
                        elif key == "escape":
                            return False
                return save_language(("en", "ru")[selected])
            except OSError:
                pass
        print("\nChoose your language / Выберите язык")
        print("  1. English\n  2. Русский")
        while True:
            answer = input("Language / Язык [1]: ").strip().lower() or "1"
            if answer in ("1", "en", "english", "2", "ru", "русский"):
                return save_language("ru" if answer in ("2", "ru", "русский") else "en")
            print("Enter 1 or 2 / Введите 1 или 2.")
    except (EOFError, KeyboardInterrupt):
        return False


def save_language(language):
    global CURRENT_LANGUAGE
    CURRENT_LANGUAGE = language
    path = language_settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as handle:
            json.dump({"language": language}, handle)
        os.replace(path + ".tmp", path)
    except OSError as error:
        print(tr("Language selected, but could not save the preference: {}",
                 "Язык выбран, но сохранить настройку не удалось: {}").format(error))
    return True


def initialize_language(interactive=False):
    global CURRENT_LANGUAGE
    CURRENT_LANGUAGE = "en"
    try:
        with open(language_settings_path(), encoding="utf-8") as handle:
            settings = json.load(handle)
        if isinstance(settings, dict) and settings.get("language") in ("en", "ru"):
            CURRENT_LANGUAGE = settings["language"]
            return True
    except (OSError, ValueError):
        pass
    return choose_language() if interactive else True

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

API_URL = "https://api.r34.app/booru/rule34.xxx/posts"

# DNS pinning: real A records for blocked domains, cached for 10 minutes
DNS_OVERRIDES = {
    "api.r34.app": [],
    "r34.app": [],
    "api-cdn.rule34.xxx": [],
    "api-cdn-mp4.rule34.xxx": [],
}
DNS_CACHE_TIMES = {k: 0.0 for k in DNS_OVERRIDES}
DNS_TTL_SECONDS = 600.0

_original_getaddrinfo = socket.getaddrinfo


def resolve_via_doh(name):
    url = "https://dns.google/resolve?name={}&type=A".format(name)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    ips = [a["data"] for a in data.get("Answer", []) if a.get("type") == 1]
    return ips


def getaddrinfo_patched(host, port, family=0, type=0, proto=0, flags=0):
    if host in DNS_OVERRIDES:
        now = time.monotonic()
        if not DNS_OVERRIDES[host] or (now - DNS_CACHE_TIMES[host] > DNS_TTL_SECONDS):
            try:
                ips = resolve_via_doh(host)
                DNS_OVERRIDES[host] = ips
                DNS_CACHE_TIMES[host] = now
                print("[dns] {} -> {}".format(host, ", ".join(ips)))
            except Exception as e:
                print(tr("[dns] DoH resolve failed for {}: {}",
                         "[dns] Не удалось определить IP через DoH для {}: {}").format(host, e))
        if DNS_OVERRIDES[host]:
            ip = DNS_OVERRIDES[host][0]
            # ensure TLS SNI/verification still uses the original hostname
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port if port else 443))]
    return _original_getaddrinfo(host, port, family, type, proto, flags)


def http_get(url, headers=None, timeout=60):
    request_headers = {"User-Agent": UA, "Origin": "https://r34.app", "Referer": "https://r34.app/"}
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_download(url, dest_path, timeout=600, progress=None):
    request_headers = {"User-Agent": UA, "Referer": "https://r34.app/"}
    req = urllib.request.Request(url, headers=request_headers)
    partial_path = dest_path + ".part"
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            try:
                total = int(getattr(resp, "headers", {}).get("Content-Length", 0)) or None
                if total is not None and total < 0:
                    total = None
            except (TypeError, ValueError):
                total = None
            received = 0
            if progress:
                progress(received, total)
            with open(partial_path, "wb") as f:
                # read1 returns available bytes instead of waiting to fill 64 KiB.
                read_chunk = getattr(resp, "read1", resp.read)
                while True:
                    chunk = read_chunk(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)
                    if progress:
                        progress(received, total)
            if total is not None and received < total:
                raise IOError(tr("Incomplete download: {} of {} bytes",
                                 "Файл скачан не полностью: {} из {} байт").format(received, total))
        os.replace(partial_path, dest_path)
    finally:
        if os.path.exists(partial_path):
            os.remove(partial_path)


def format_bytes(count):
    value = float(count)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return "{:.1f} {}".format(value, unit)
        value /= 1024


class DownloadProgress:
    """Live terminal status, with periodic snapshots for captured output."""

    def __init__(self, stream=None):
        self.stream = sys.stdout if stream is None else stream
        self.in_place = self.stream.isatty()
        self.enabled = True
        self.active = False

    def begin(self, index, count, filename):
        self.label = "[{}/{}] {}".format(index, count, filename)
        self.started = time.monotonic()
        self.last_draw = -float("inf")
        self.received = 0
        self.total = None
        self.active = True
        self.draw(tr('connecting...', 'соединение...'))

    def update(self, received, total):
        self.received, self.total = received, total
        now = time.monotonic()
        interval = 0.1 if self.in_place else 1.0
        if received == 0 or now - self.last_draw >= interval or (total and received >= total):
            self.draw()

    def status(self):
        elapsed = max(0.001, time.monotonic() - self.started)
        speed = self.received / elapsed
        if self.total:
            fraction = min(1.0, self.received / self.total)
            filled = int(8 * fraction)
            bar = "[{}{}] {:3.0f}%".format("#" * filled, "-" * (8 - filled), fraction * 100)
            size = "{} / {}".format(format_bytes(self.received), format_bytes(self.total))
            eta = tr(' · ~{}s', ' · ~{}с').format(int(max(0, self.total - self.received) / speed)) if speed else ""
        else:
            bar = tr('[ size unknown ]', '[ размер неизвестен ]')
            size = format_bytes(self.received)
            eta = ""
        return "{} · {} · {}/s{}".format(bar, size, format_bytes(speed), eta)

    def draw(self, message=None):
        if not self.enabled:
            return
        width = max(1, shutil.get_terminal_size((100, 24)).columns - 1)
        detail = self.status() if message is None else message
        # Keep byte counts and speed visible even in a narrow terminal.
        label_width = max(0, width - len(detail) - 5)
        label = self.label if len(self.label) <= label_width else self.label[:max(0, label_width - 1)] + "…"
        line = ("  " + label + " · " + detail)[:width]
        if self.in_place:
            self.stream.write("\r" + line.ljust(width))
        else:
            self.stream.write(line + "\n")
        self.stream.flush()
        self.last_draw = time.monotonic()

    def finish(self, outcome):
        if self.active:
            self.draw(outcome + " · " + self.status())
            if self.enabled and self.in_place:
                self.stream.write("\n")
                self.stream.flush()
            self.active = False


def fetch_page(tags_query, page_id, retries=3):
    qs = urllib.parse.urlencode({
        "baseEndpoint": "rule34.xxx",
        "limit": 100,
        "pageID": page_id,
        "tags": tags_query,
    })
    url = "{}?{}".format(API_URL, qs)
    for attempt in range(retries):
        try:
            raw = http_get(url, timeout=60)
            return json.loads(raw.decode("utf-8")).get("data") or []
        except Exception as e:
            print(tr("[api] attempt {}: error: {}", "[api] попытка {}: ошибка: {}").format(attempt + 1, e))
            time.sleep(3 * (attempt + 1))
    return None  # give up on this page


def all_tags_of(post):
    tags = post.get("tags") or {}
    flat = []
    for v in tags.values():
        flat.extend(v or [])
    return flat


def post_id_from_url(value):
    """Accept a rule34.xxx post page, never an arbitrary URL or search page."""
    try:
        parsed = urllib.parse.urlsplit(value.strip())
        query = urllib.parse.parse_qs(parsed.query)
        ids = query.get("id", [])
        valid = (
            parsed.scheme in ("http", "https")
            and parsed.hostname in ("rule34.xxx", "www.rule34.xxx")
            and parsed.path == "/index.php"
            and query.get("page") == ["post"]
            and query.get("s") == ["view"]
            and len(ids) == 1
            and ids[0].isascii() and ids[0].isdecimal()
            and int(ids[0]) > 0
        )
        if valid:
            return int(ids[0])
    except ValueError:
        pass
    raise argparse.ArgumentTypeError(
        "expected a post URL: https://rule34.xxx/index.php?page=post&s=view&id=12345"
    )


def build_parser():
    ap = argparse.ArgumentParser(description="rule34.xxx mass downloader (via r34.app API)")
    ap.add_argument("--tag", default="", help="single tag, e.g. xipa (space -> underscore)")
    ap.add_argument("--tags", default="", help="comma separated tags, ALL required (AND)")
    ap.add_argument("--batch-tags", default="", help=tr(
        "comma separated tags, downloaded separately into one folder per tag",
        "теги через запятую, каждый скачивается отдельно в собственную папку"))
    ap.add_argument("--exclude-tags", default="", help="comma separated tags to exclude")
    ap.add_argument("--include-videos", action="store_true", help="also download videos (.mp4)")
    ap.add_argument("--url", "--post-url", dest="post_ids", action="append",
                    type=post_id_from_url, default=[], metavar="URL",
                    help="download one post (image or video); can be repeated; no tags needed")
    ap.add_argument("--out-dir", required=True, help="destination folder")
    ap.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES, help="safety cap for pages (default 10000)")
    return ap


def normalize_tags(value):
    return sorted({"_".join(t.split()) for t in value.split(",") if t.strip()})


def help_sections():
    """Shared bilingual manual for the fullscreen and plain-text interfaces."""
    return [
        (tr("1. Getting started and navigation", "1. Начало работы и управление"), [
            tr("Start with python r34_downloader.py on Windows or python3 r34_downloader.py on Linux. Select your language on the first launch. Choose a tab, fill in its fields, then select DOWNLOAD or DOWNLOAD QUEUE.",
               "Запуск: python r34_downloader.py на Windows или python3 r34_downloader.py на Linux. При первом запуске выберите язык. Откройте вкладку, заполните поля и нажмите СКАЧАТЬ или СКАЧАТЬ ОЧЕРЕДЬ."),
            tr("Outside the editor: Left/Right switch tabs; Up/Down or Tab/Shift+Tab select fields and buttons. Enter opens a field or presses a button. Space toggles the videos checkbox. Esc or Q exits the app.",
               "Вне редактирования: влево/вправо переключают вкладки; вверх/вниз или Tab/Shift+Tab выбирают поля и кнопки. Enter открывает поле или нажимает кнопку. Пробел переключает флажок видео. Esc или Q закрывает программу."),
            tr("While editing: type or paste text; Left/Right, Home/End move the cursor; Backspace/Delete remove characters. Enter saves, Esc discards the edit. Tab saves and moves to the next field; Shift+Tab moves back. Q is ordinary text while editing.",
               "При редактировании: вводите или вставляйте текст; влево/вправо и Home/End перемещают курсор; Backspace/Delete удаляют символы. Enter сохраняет, Esc отменяет правку. Tab сохраняет и выбирает следующее поле, Shift+Tab — предыдущее. Буква Q при редактировании вводится как обычный текст.")]),
        (tr("2. Tags: matching all tags", "2. По тегам: совпадение всех тегов"), [
            tr("Tags, comma-separated: enter an author or topic, for example xipa. With multiple tags, a post must contain ALL of them. Example: petrification,cursed downloads posts containing both tags into the selected output folder. Spaces inside a tag become underscores.",
               "Теги через запятую: укажите автора или тему, например xipa. Если тегов несколько, пост должен содержать ВСЕ теги. Пример: petrification,cursed скачает в выбранную папку посты с обоими тегами. Пробелы внутри тега заменяются подчёркиванием."),
            tr("Exclude tags: optional comma-separated tags. A post is skipped if it contains ANY excluded tag. Example: ai_generated. Leave this field empty to exclude nothing.",
               "Исключить теги: необязательный список через запятую. Пост пропускается, если содержит ХОТЯ БЫ ОДИН исключённый тег. Пример: ai_generated. Пустое поле ничего не исключает.")]),
        (tr("3. Post URLs: individual posts", "3. По ссылкам: отдельные посты"), [
            tr("URLs, space-separated: paste one or several links to post pages, then save the field with Enter. Expected format: https://rule34.xxx/index.php?page=post&s=view&id=12345 . Use real post IDs; search pages and direct CDN file URLs are not supported.",
               "Ссылки через пробел: вставьте одну или несколько ссылок на страницы постов и сохраните поле через Enter. Формат: https://rule34.xxx/index.php?page=post&s=view&id=12345 . Подставьте настоящие номера постов; страницы поиска и прямые ссылки на файлы CDN не поддерживаются."),
            tr("Images and videos are included automatically. Duplicate post IDs are downloaded once. Tag filters and page limits do not apply in this tab. Choose an output folder and press DOWNLOAD.",
               "Картинки и видео скачиваются автоматически. Повторяющиеся номера постов обрабатываются один раз. Фильтры тегов и лимит страниц в этой вкладке не применяются. Выберите папку и нажмите СКАЧАТЬ.")]),
        (tr("4. Batch download: one folder per tag", "4. Массовая загрузка: папка на каждый тег"), [
            tr("Tags, one folder each: enter xipa,yonpii,toby. With parent folder downloads, the app downloads xipa into downloads/xipa/, then yonpii into downloads/yonpii/, then toby into downloads/toby/. Each tag is a separate search, processed in the order entered.",
               "Теги, каждый в свою папку: введите xipa,yonpii,toby. При родительской папке downloads программа скачает тег xipa в downloads/xipa/, затем yonpii в downloads/yonpii/, затем toby в downloads/toby/. Каждый тег — отдельный поиск; порядок соответствует вводу."),
            tr("Duplicate tags are removed; spaces inside a tag become underscores. A post matching several queued tags is saved in each matching folder. Invalid Windows/Linux folder names are rejected before starting. Existing tag folders are reused.",
               "Повторы тегов убираются; пробелы внутри тега заменяются подчёркиванием. Пост с несколькими тегами очереди сохраняется в каждую подходящую папку. Недопустимые для Windows/Linux имена папок отклоняются до запуска. Существующие папки тегов используются повторно."),
            tr("Exclude tags and Include videos apply to every tag in the queue. Page limit per tag applies separately to each search. Select the Parent folder, then DOWNLOAD QUEUE. An individual tag failure does not stop later tags; Ctrl+C cancels the whole queue.",
               "Исключения и флажок видео применяются к каждому тегу очереди. Лимит страниц на тег действует отдельно для каждого поиска. Выберите Родительскую папку и нажмите СКАЧАТЬ ОЧЕРЕДЬ. Ошибка одного тега не останавливает последующие; Ctrl+C отменяет всю очередь.")]),
        (tr("5. Video and page limit fields", "5. Поля видео и лимита страниц"), [
            tr("Include videos: unchecked means images only; checked means images and videos. This setting exists in Tags and Batch download. It does not need to be enabled for Post URLs.",
               "Скачивать видео: без флажка скачиваются только картинки; с флажком — картинки и видео. Поле есть во вкладках По тегам и Массовая загрузка. Для скачивания по ссылкам флажок не требуется."),
            tr("Page limit: a positive whole number, 10000 by default. Each API page contains up to 100 posts. This is a search cap, not an exact file count: filtering may reduce the results, and an empty page ends the search early. In a batch, every tag receives its own limit.",
               "Лимит страниц: целое число больше нуля, по умолчанию 10000. Страница API содержит до 100 постов. Это ограничение поиска, а не точное число файлов: фильтры могут уменьшить результат, а пустая страница завершает поиск раньше. В очереди каждый тег получает собственный лимит.")]),
        (tr("6. Output folder and files", "6. Папка сохранения и файлы"), [
            tr("Output folder / Parent folder: choose where files are saved. The default is downloads in the terminal's working directory. Relative paths, absolute paths and ~ for your home directory are supported. Paths with spaces need no quotes in the form. Missing folders are created automatically.",
               "Папка сохранения / Родительская папка: место для файлов. По умолчанию это downloads в рабочей папке терминала. Поддерживаются относительные и абсолютные пути, а также ~ для домашней папки. Путь с пробелами можно вводить без кавычек. Недостающие папки создаются автоматически."),
            tr("The folder field is shared between tabs. Tags and Post URLs save directly into it; Batch download creates a subfolder for each tag. Files are named by post ID and extension, for example 12345.png or 12345.mp4. Existing nonempty files are skipped; empty files are downloaded again.",
               "Поле папки общее для вкладок. По тегам и По ссылкам сохраняют файлы прямо в неё; Массовая загрузка создаёт подпапку для каждого тега. Имя файла — номер поста и расширение, например 12345.png или 12345.mp4. Готовые непустые файлы пропускаются; пустые скачиваются заново.")]),
        (tr("7. Buttons and cancellation", "7. Кнопки и отмена"), [
            tr("DOWNLOAD starts the current Tags or Post URLs job. DOWNLOAD QUEUE starts all batch tags. Invalid fields display an error instead of starting. Reset form clears only the current tab's settings, restores the default page limit and keeps the folder; it does not delete downloaded files.",
               "СКАЧАТЬ запускает текущую задачу По тегам или По ссылкам. СКАЧАТЬ ОЧЕРЕДЬ запускает все теги массовой загрузки. При неверных значениях вместо запуска появится ошибка. Сбросить форму очищает настройки только текущей вкладки, возвращает стандартный лимит и оставляет папку; скачанные файлы не удаляются."),
            tr("Exit closes the app. During a download, Ctrl+C cancels the current job or entire queue; completed files remain. After completion, failure or cancellation, press Enter to return to the form. Field values stay for this session; only your language choice is saved between launches.",
               "Выход закрывает программу. Во время скачивания Ctrl+C отменяет задачу или всю очередь; готовые файлы остаются. После завершения, ошибки или отмены нажмите Enter для возврата к форме. Значения полей сохраняются в текущем сеансе; между запусками запоминается только язык.")]),
        (tr("8. Progress and retrying", "8. Прогресс и повторный запуск"), [
            tr("First the log shows post lookup and API page collection. File transfer then shows its index, filename, progress bar, percentage, downloaded/total bytes, average speed and estimated time remaining. Batch logs also show the current tag and its queue position.",
               "Сначала журнал показывает поиск постов и сбор страниц API. Затем при скачивании файла видны номер, имя, полоса прогресса, процент, скачанный и полный объём, средняя скорость и примерное оставшееся время. Для массовой загрузки также видны текущий тег и его номер в очереди."),
            tr("Connecting means the file server has not responded yet. Size unknown means the server supplied no total size; bytes and speed still update. SKIP means a nonempty file already exists. Captured output uses periodic status lines rather than overwriting a line.",
               "Соединение означает ожидание ответа файлового сервера. Неизвестный размер означает, что сервер не сообщил общий объём; полученные байты и скорость всё равно обновляются. ПРОПУСК означает, что непустой файл уже есть. При перенаправленном выводе статус печатается отдельными строками."),
            tr("Interrupted transfers use .part temporary files, removed on normal errors or Ctrl+C. Retrying starts an unfinished file from the beginning and skips finished files. If the API rate-limits requests, wait and retry. Network or video CDN access failures are shown in the log; inspect errors if a batch summary reports failed tags.",
               "Незавершённая загрузка использует временный файл .part, удаляемый при обычной ошибке или Ctrl+C. Повторный запуск начинает недокачанный файл заново и пропускает готовые. При ограничении запросов API подождите и повторите. Ошибки сети и доступа к видео-CDN выводятся в журнале; если итог очереди сообщает об ошибках тегов, проверьте журнал.")]),
        (tr("9. Settings and language", "9. Настройки и язык"), [
            tr("Settings > Language opens the English / Russian selector. Use Up/Down and Enter to confirm; Esc leaves the current language unchanged. The choice is saved for later launches. The first launch asks only when no valid language setting exists.",
               "Настройки > Язык открывает выбор English / Русский. Выберите вариант стрелками вверх/вниз и подтвердите Enter; Esc оставляет прежний язык. Выбор сохраняется для будущих запусков. Вопрос при старте появляется только без корректной сохранённой настройки языка.")]),
        (tr("10. Help and plain-text menu", "10. Справка и текстовое меню"), [
            tr("In Help: Up/Down scroll a line; PageUp/PageDown, Tab/Shift+Tab or Space scroll a page; Home/End jump to the beginning/end. Left/Right switch tabs. The line counter shows your reading position. Help uses your selected language.",
               "В Справке: вверх/вниз прокручивают строку; PageUp/PageDown, Tab/Shift+Tab или пробел — страницу; Home/End переходят к началу/концу. Влево/вправо переключают вкладки. Счётчик строк показывает позицию чтения. Справка отображается на выбранном языке."),
            tr("If fullscreen mode is unavailable, the plain-text menu opens: 1 Tags, 2 Post URLs, 3 Help, 4 Language, 5 Batch download, 0 Exit. Follow the prompts; Enter accepts a default in brackets, and :back returns to the menu. Menu item 3 prints this same manual.",
               "Если полноэкранный режим недоступен, открывается текстовое меню: 1 По тегам, 2 По ссылкам, 3 Справка, 4 Язык, 5 Массовая загрузка, 0 Выход. Следуйте вопросам; Enter принимает значение в скобках, а :back возвращает в меню. Пункт 3 выводит эту же инструкцию.")])
    ]


def parse_batch_tags(value):
    items = value.split(",") if isinstance(value, str) else value
    tags = list(dict.fromkeys("_".join(tag.split()) for tag in items if tag.strip()))
    if not tags:
        raise ValueError(tr("Enter at least one batch tag.", "Укажите хотя бы один тег для массовой загрузки."))
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    reserved.update("COM{}".format(i) for i in range(1, 10))
    reserved.update("LPT{}".format(i) for i in range(1, 10))
    for tag in tags:
        if (tag in (".", "..") or len(tag) > 200 or tag.endswith(".")
                or any(c in '/\\:*?"<>|' or not c.isprintable() for c in tag)
                or tag.split(".", 1)[0].upper() in reserved):
            raise ValueError(tr(
                "Tag '{}' cannot be used as a folder name on Windows and Linux.",
                "Тег '{}' нельзя использовать как имя папки на Windows и Linux.").format(tag))
    # Avoid two tasks sharing the same folder on case-insensitive filesystems.
    unique = []
    seen = set()
    for tag in tags:
        if tag.casefold() not in seen:
            unique.append(tag)
            seen.add(tag.casefold())
    return unique


def batch_target_folder(root, tag):
    root = os.path.realpath(os.path.abspath(root))
    target = os.path.realpath(os.path.join(root, tag))
    if os.path.normcase(os.path.commonpath([root, target])) != os.path.normcase(root) or target == root:
        raise ValueError(tr("Tag folder must stay inside the output folder: {}",
                            "Папка тега должна находиться внутри папки сохранения: {}").format(tag))
    return target


def run_batch_download(args):
    tags = parse_batch_tags(args.batch_tags)
    # Validate the whole queue before creating folders or making network requests.
    for tag in tags:
        batch_target_folder(args.out_dir, tag)
    os.makedirs(args.out_dir, exist_ok=True)
    failed = 0
    for index, tag in enumerate(tags, 1):
        print(tr("\nBatch [{}/{}] Tag: {}", "\nМассовая загрузка [{}/{}] Тег: {}").format(
            index, len(tags), tag), flush=True)
        try:
            job = argparse.Namespace(**vars(args))
            job.batch_tags = []
            job.tag, job.tags, job.post_ids = tag, "", []
            job.out_dir = batch_target_folder(args.out_dir, tag)
            print(tr("Folder: {}", "Папка: {}").format(job.out_dir), flush=True)
            if run_download(job):
                failed += 1
        except (OSError, ValueError) as error:
            failed += 1
            print(tr("Tag '{}' failed: {}. Continuing with the next tag.",
                     "Ошибка тега '{}': {}. Перехожу к следующему тегу.").format(tag, error), flush=True)
    print(tr("\nBatch complete. Tags OK: {}, tags with errors: {}.",
             "\nМассовая загрузка завершена. Тегов без ошибок: {}, с ошибками: {}.").format(
                 len(tags) - failed, failed), flush=True)
    return 1 if failed else 0


class MenuBack(Exception):
    pass


def prompt(message):
    value = input(message).strip()
    if value.lower() == ":back":
        raise MenuBack
    return value


def ask_choice(message, choices, default=None):
    while True:
        value = prompt(message).lower()
        if not value and default is not None:
            return default
        if value in choices:
            return value
        print(tr('Choose one of: {}.', 'Введите один из вариантов: {}.').format(", ".join(choices)))


def ask_positive_int(message, default):
    while True:
        value = prompt(message)
        if not value:
            return default
        try:
            number = int(value)
            if number > 0:
                return number
        except ValueError:
            pass
        print(tr('Enter a positive whole number.', 'Введите целое число больше нуля.'))


def interactive_settings(mode, default_dir):
    args = argparse.Namespace(tag="", tags="", exclude_tags="", post_ids=[],
                              include_videos=False, max_pages=DEFAULT_MAX_PAGES, out_dir=default_dir)
    print(tr('\nType :back in any field to return to the menu.', '\nВведите :back в любом поле, чтобы вернуться в меню.'))
    if mode in ("1", "5"):
        while not normalize_tags(args.tags):
            args.tags = prompt(tr("Batch tags, comma-separated (one folder each): ",
                                  "Теги через запятую (каждый в свою папку): ") if mode == "5" else
                               tr('Tags, comma-separated (all required): ', 'Теги через запятую (пост должен содержать все): '))
            if not normalize_tags(args.tags):
                print(tr('Enter at least one tag.', 'Укажите хотя бы один тег.'))
            elif mode == "5":
                try:
                    args.batch_tags = parse_batch_tags(args.tags)
                except ValueError as error:
                    print(error)
                    args.tags = ""
        if mode == "5":
            args.tags = ""
        args.exclude_tags = prompt(tr('Exclude tags, comma-separated [none]: ', 'Исключить теги через запятую [нет]: '))
        answer = ask_choice(tr('Include videos? [y/N]: ', 'Скачивать видео? [д/Н]: '),
                            ("д", "да", "y", "yes", "н", "нет", "n", "no"), "н")
        args.include_videos = answer in ("д", "да", "y", "yes")
        args.max_pages = ask_positive_int(tr('Page limit (100 posts per page) [10000]: ', 'Лимит страниц (по 100 постов) [10000]: '), DEFAULT_MAX_PAGES)
    else:
        print(tr('Enter post URLs one per line or separated by spaces.', 'Вставляйте ссылки на посты по одной или несколько через пробел.'))
        print(tr('An empty line completes the list. Images and videos are included.', 'Пустая строка завершает список. Картинки и видео скачиваются автоматически.'))
        while True:
            line = prompt(tr('URL{}: ', 'Ссылка{}: ').format(tr(' (Enter to finish)', ' (Enter — готово)') if args.post_ids else ""))
            if not line:
                if args.post_ids:
                    break
                print(tr('Enter at least one URL.', 'Нужна хотя бы одна ссылка.'))
                continue
            try:
                ids = [post_id_from_url(url.strip("\"'")) for url in line.split()]
            except argparse.ArgumentTypeError:
                print(tr('Line not added. Expected URL format:', 'Строка не добавлена. Формат ссылки:'))
                print("https://rule34.xxx/index.php?page=post&s=view&id=12345")
                continue
            args.post_ids = list(dict.fromkeys(args.post_ids + ids))
            print(tr('Posts added: {}', 'Добавлено постов: {}').format(len(args.post_ids)))

    while True:
        folder = prompt(tr('Output folder [{}]: ', 'Папка сохранения [{}]: ').format(default_dir))
        folder = folder.strip("\"'") or default_dir
        folder = os.path.abspath(os.path.expandvars(os.path.expanduser(folder)))
        if os.path.exists(folder) and not os.path.isdir(folder):
            print(tr('This path is a file. Choose a folder.', 'Этот путь указывает на файл. Выберите папку.'))
            continue
        args.out_dir = folder
        break

    print(tr('\nDownload settings:', '\nНастройки загрузки:'))
    if args.post_ids:
        print(tr('Posts: {}', 'Посты: {}').format(", ".join(map(str, args.post_ids))))
        print(tr('Media: images and videos', 'Медиа: картинки и видео'))
    elif getattr(args, "batch_tags", None):
        print(tr("Batch tags (separate folders): {}", "Теги (отдельные папки): {}").format(
            ", ".join(args.batch_tags)))
        print(tr("Excluded: {}", "Исключения: {}").format(args.exclude_tags or tr("none", "нет")))
        print(tr("Include videos: {}", "Скачивать видео: {}").format(
            tr("yes", "да") if args.include_videos else tr("no", "нет")))
        print(tr("Page limit per tag: {}", "Лимит страниц на каждый тег: {}").format(args.max_pages))
    else:
        print(tr('Tags (all): {}', 'Теги (все): {}').format(", ".join(normalize_tags(args.tags))))
        print(tr('Excluded: {}', 'Исключения: {}').format(", ".join(normalize_tags(args.exclude_tags)) or tr("none", "нет")))
        print(tr('Media: {}', 'Медиа: {}').format(tr('images and videos', 'картинки и видео') if args.include_videos else tr('images', 'картинки')))
        print(tr('Page limit: {}', 'Лимит страниц: {}').format(args.max_pages))
    print(tr('Folder: {}', 'Папка: {}').format(args.out_dir))
    return args


def interactive_menu():
    default_dir = os.path.abspath("downloads")
    while True:
        try:
            print("\n" + "=" * 48)
            print(" Rule34 Downloader")
            print("=" * 48)
            print(tr(' 1. Download by tags / author', ' 1. Скачать по тегам / автору'))
            print(tr(' 2. Download by post URLs', ' 2. Скачать по ссылкам на посты'))
            print(tr(' 3. Help', ' 3. Справка'))
            print(tr(" 4. Language", " 4. Язык"))
            print(tr(" 5. Batch download (one folder per tag)", " 5. Массовая загрузка (папка на каждый тег)"))
            print(tr(' 0. Exit', ' 0. Выход'))
            choice = ask_choice(tr('Choose an action: ', 'Выберите действие: '), ("1", "2", "3", "4", "5", "0"))
            if choice == "0":
                return 0
            if choice == "4":
                choose_language()
                continue
            if choice == "3":
                for title, paragraphs in help_sections():
                    print("\n" + title)
                    for paragraph in paragraphs:
                        print(textwrap.fill(paragraph, width=max(30, shutil.get_terminal_size((80, 24)).columns - 2)))
                        print()
                continue
            args = interactive_settings(choice, default_dir)
            answer = ask_choice(tr('Start downloading? [Y/n]: ', 'Начать скачивание? [Д/н]: '),
                                ("д", "да", "y", "yes", "н", "нет", "n", "no"), "д")
            if answer in ("н", "нет", "n", "no"):
                continue
            default_dir = args.out_dir
            status = execute_download(args)
            if status:
                print(tr('Download finished with errors. You can retry from the menu.', 'Загрузка завершилась с ошибками. Можно повторить её через меню.'))
            else:
                print(tr('Done. You can start another download.', 'Готово. Можно выбрать следующую загрузку.'))
        except (MenuBack, KeyboardInterrupt):
            print(tr('\nAction cancelled. Returning to the menu.', '\nДействие отменено. Возврат в меню.'))
        except EOFError:
            print(tr('\nInput closed. Exiting.', '\nВвод закрыт. Выход.'))
            return 0
        except OSError as e:
            print(tr('\nError: {}. Check the path and permissions.', '\nОшибка: {}. Проверьте путь и права доступа.').format(e))


def execute_download(args):
    original_resolver = socket.getaddrinfo
    try:
        socket.getaddrinfo = getaddrinfo_patched
        if getattr(args, "batch_tags", None):
            return run_batch_download(args)
        return run_download(args)
    finally:
        socket.getaddrinfo = original_resolver


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not initialize_language(interactive=not argv):
        return 0
    if not argv:
        if (sys.stdin.isatty() and sys.stdout.isatty()
                and (os.name == "nt" or os.environ.get("TERM") != "dumb")):
            return run_terminal(sys.modules[__name__])
        return interactive_menu()
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.max_pages <= 0:
        ap.error("--max-pages must be greater than zero")
    if args.batch_tags:
        if args.tag or args.tags or args.post_ids:
            ap.error(tr("--batch-tags cannot be combined with --tag, --tags or --url",
                        "--batch-tags нельзя совмещать с --tag, --tags или --url"))
        try:
            args.batch_tags = parse_batch_tags(args.batch_tags)
        except ValueError as error:
            ap.error(str(error))
    if not (normalize_tags(args.tag) or normalize_tags(args.tags) or args.post_ids or args.batch_tags):
        ap.error(tr("use --url, --tag, --tags or --batch-tags", "укажите --url, --tag, --tags или --batch-tags"))
    if args.post_ids and (args.tag or args.tags or args.exclude_tags):
        ap.error("--url cannot be combined with --tag, --tags or --exclude-tags")
    return execute_download(args)


def run_download(args):

    include = []
    if args.tag:
        include += args.tag.split(",")
    if args.tags:
        include += args.tags.split(",")
    include = normalize_tags(",".join(include))

    exclude = normalize_tags(args.exclude_tags)

    os.makedirs(args.out_dir, exist_ok=True)

    server_query = " ".join(include + ["-" + e for e in exclude])
    if not args.post_ids:
        print(tr("tags (AND): {} | excluded: {} | videos: {}",
                 "теги (И): {} | исключения: {} | видео: {}").format(
            " + ".join(include), ", ".join(exclude) or "-",
            tr("yes", "да") if args.include_videos else tr("no", "нет")))

    # -- collect all posts ------------------------------------------------
    all_posts = []
    lookup_failures = 0
    for pid in dict.fromkeys(args.post_ids):
        print(tr('  Looking up post {}...', '  Поиск поста {}...').format(pid), flush=True)
        data = fetch_page("id:{}".format(pid), 0)
        matches = [p for p in (data or []) if str(p.get("id")) == str(pid)]
        if not matches:
            lookup_failures += 1
            print(tr("ERROR: post {} could not be fetched or was not found",
                     "ОШИБКА: не удалось получить или найти пост {}").format(pid))
        else:
            all_posts.append(matches[0])
        time.sleep(0.6)

    page = 0
    while not args.post_ids and page < args.max_pages:
        print(tr('  Finding posts: page {} / {}, found {}...', '  Поиск постов: страница {} / {}, найдено {}...').format(
            page + 1, args.max_pages, len(all_posts)), flush=True)
        data = fetch_page(server_query, page)
        if data is None:
            print(tr("[api] page {}: gave up after retries; stopping collection",
                     "[api] страница {}: попытки исчерпаны; сбор остановлен").format(page))
            lookup_failures += 1
            break
        if not data:
            break
        all_posts.extend(data)
        print(tr("page {}: +{}", "страница {}: +{}").format(page, len(data)))
        page += 1
        time.sleep(0.6)

    # -- filter -------------------------------------------------------------
    selected = {}
    for p in all_posts:
        flat = all_tags_of(p)
        if any(e in flat for e in exclude):
            continue
        if any(i not in flat for i in include):
            continue
        url = (p.get("high_res_file") or {}).get("url")
        if not url:
            if args.post_ids:
                lookup_failures += 1
                print(tr("ERROR: post {} has no downloadable file",
                         "ОШИБКА: у поста {} нет файла для скачивания").format(p["id"]))
            continue
        mt = p.get("media_type")
        if args.include_videos or args.post_ids:
            if mt not in ("image", "video"):
                if args.post_ids:
                    lookup_failures += 1
                    print(tr("ERROR: post {} has unsupported media type: {}",
                             "ОШИБКА: у поста {} неподдерживаемый тип медиа: {}").format(p["id"], mt))
                continue
        else:
            if mt != "image" or "api-cdn-mp4" in url:
                continue
        selected[p["id"]] = (url, mt == "video")

    print(tr("posts fetched: {} -> to download: {}", "получено постов: {} -> к скачиванию: {}").format(
        len(all_posts), len(selected)))

    # -- download -----------------------------------------------------------
    ok_img = ok_vid = fail = 0
    progress = DownloadProgress()
    for index, pid in enumerate(sorted(selected), 1):
        url, is_video = selected[pid]
        ext = os.path.splitext(urllib.parse.urlsplit(url).path)[1].lower() or (
            ".mp4" if is_video else ".jpg")
        dest = os.path.join(args.out_dir, "{}{}".format(pid, ext))
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print(tr("[{}/{}] SKIP {}", "[{}/{}] ПРОПУСК {}").format(index, len(selected), os.path.basename(dest)))
            if is_video:
                ok_vid += 1
            else:
                ok_img += 1
            continue
        try:
            print(tr("[{}/{}] Download {}", "[{}/{}] Скачивание {}").format(index, len(selected), os.path.basename(dest)))
            progress.begin(index, len(selected), os.path.basename(dest))
            http_download(url, dest, progress=progress.update)
        except KeyboardInterrupt:
            progress.finish(tr('Cancelled', 'Отменено'))
            raise
        except Exception as e:
            progress.finish(tr('Error', 'Ошибка'))
            fail += 1
            if os.path.exists(dest):
                os.remove(dest)
            if is_video:
                print(tr("VIDEO FAIL (video CDN blocked by some ISPs): {} ({})",
                         "ОШИБКА ВИДЕО (CDN блокируется некоторыми провайдерами): {} ({})").format(url, e))
            else:
                print(tr("FAIL {} ({})", "ОШИБКА {} ({})").format(url, e))
            time.sleep(2)
        else:
            progress.finish(tr('Done', 'Готово'))
            if is_video:
                ok_vid += 1
            else:
                ok_img += 1
        time.sleep(0.25)

    print(tr("done. images OK: {}, videos OK: {}, failed: {}",
             "готово. картинок успешно: {}, видео успешно: {}, ошибок: {}").format(ok_img, ok_vid, fail))
    return 1 if lookup_failures or fail else 0


# Warm, quiet terminal palette inspired by Claude Code.
BACKGROUND = "\x1b[48;2;29;28;26m"
FOREGROUND = "\x1b[38;2;225;220;210m"
ACCENT = "\x1b[38;2;217;119;87m"
MUTED = "\x1b[38;2;145;140;130m"
SELECTED = "\x1b[48;2;49;43;38m"
BASE = BACKGROUND + FOREGROUND


class Terminal:
    """Restore console settings even when input or rendering fails."""

    def __enter__(self):
        self.windows = os.name == "nt"
        if self.windows:
            import ctypes
            from ctypes import wintypes
            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self.kernel.GetStdHandle.argtypes = [wintypes.DWORD]
            self.kernel.GetStdHandle.restype = wintypes.HANDLE
            self.kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            self.kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            self.handle = self.kernel.GetStdHandle(-11 & 0xffffffff)
            self.mode = wintypes.DWORD()
            if not self.kernel.GetConsoleMode(self.handle, ctypes.byref(self.mode)):
                raise OSError(tr('Cannot open the Windows console', 'Не удалось открыть консоль Windows'))
            if not self.kernel.SetConsoleMode(self.handle, self.mode.value | 4):
                raise OSError(tr('ANSI is not supported. Use Windows Terminal', 'Терминал не поддерживает ANSI. Используйте Windows Terminal'))
        else:
            import termios
            import tty
            self.fd = sys.stdin.fileno()
            self.settings = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        try:
            sys.stdout.write("\x1b[?1049h\x1b[?25l" + ("" if self.windows else "\x1b[?2004h"))
            sys.stdout.flush()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc):
        try:
            sys.stdout.write("\x1b[0m" + ("" if self.windows else "\x1b[?2004l") + "\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()
        finally:
            if self.windows:
                self.kernel.SetConsoleMode(self.handle, self.mode.value)
            else:
                import termios
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.settings)

    def read_key(self):
        if self.windows:
            import msvcrt
            char = msvcrt.getwch()
            if char in ("\x00", "\xe0"):
                return ({"H": "up", "P": "down", "K": "left", "M": "right",
                         "G": "home", "O": "end", "I": "pageup", "Q": "pagedown",
                         "S": "delete", "\x0f": "backtab"}
                        .get(msvcrt.getwch(), "unknown"), "")
            return decode_char(char)
        import select
        decoder = codecs.getincrementaldecoder(sys.stdin.encoding or "utf-8")(errors="replace")
        char = ""
        while not char:
            chunk = os.read(self.fd, 1)
            if not chunk:
                raise EOFError
            char = decoder.decode(chunk)
        if char != "\x1b":
            return decode_char(char)
        # Read bytes after Escape without blocking on a standalone Escape key.
        # os.read avoids TextIO buffering hiding already-read escape bytes.
        sequence = ""
        while select.select([self.fd], [], [], 0.04)[0]:
            part = os.read(self.fd, 1).decode("ascii", errors="ignore")
            sequence += part
            if part and (part.isalpha() or part == "~"):
                break
            if len(sequence) > 20:
                break
        keys = {"[A": "up", "[B": "down", "[C": "right", "[D": "left",
                "OA": "up", "OB": "down", "OC": "right", "OD": "left",
                "[Z": "backtab", "[H": "home", "[F": "end", "OH": "home",
                "OF": "end", "[1~": "home", "[4~": "end", "[3~": "delete",
                "[5~": "pageup", "[6~": "pagedown"}
        if sequence == "[200~":
            data = bytearray()
            while not data.endswith(b"\x1b[201~"):
                chunk = os.read(self.fd, 1)
                if not chunk:
                    raise EOFError
                data.extend(chunk)
            return "paste", data[:-6].decode(sys.stdin.encoding or "utf-8", errors="replace")
        return keys.get(sequence, "escape" if not sequence else "unknown"), ""


def decode_char(char):
    if not char or char == "\x04":
        raise EOFError
    if char == "\x03":
        raise KeyboardInterrupt
    return ({"\r": "enter", "\n": "enter", "\t": "tab", "\x1b": "escape",
             "\x08": "backspace", "\x7f": "backspace"}.get(char, "text"), char)


def safe_text(value):
    """User input must never inject terminal commands into the renderer."""
    return "".join(c for c in value if c.isprintable())


def clip_line(line, width):
    parts = re.split(r"(\x1b\[[0-9;]*m)", line)
    result = []
    for part in parts:
        if part.startswith("\x1b["):
            result.append(part)
        else:
            result.append(part[:width])
            width -= len(part[:width])
    return "".join(result) + "\x1b[0m"


class DownloaderUI:
    @property
    def tabs(self):
        return (tr("Tags", "По тегам"), tr("Post URLs", "По ссылкам"),
                tr("Batch download", "Массовая загрузка"),
                tr("Help", "Справка"), tr("Settings", "Настройки"))

    def __init__(self, downloader):
        self.downloader = downloader
        self.tab = 0
        self.selected = 0
        self.values = {"tags": "", "exclude": "", "videos": False, "pages": str(DEFAULT_MAX_PAGES),
                       "batch_tags": "", "batch_exclude": "", "batch_videos": False,
                       "batch_pages": str(DEFAULT_MAX_PAGES),
                       "links": "", "folder": os.path.abspath("downloads")}
        self.message = tr('Select a field and press Enter.', 'Выберите поле и нажмите Enter.')
        self.editing = None
        self.draft = ""
        self.cursor = 0
        self.help_offset = 0
        self.help_page_size = 1
        self.help_max_offset = 0

    def fields(self):
        if self.tab == 4:
            return [("language", tr("Language", "Язык") + ": " +
                     ("English" if CURRENT_LANGUAGE == "en" else "Русский")),
                    ("quit", tr("Exit", "Выход"))]
        if self.tab == 2:
            return [("batch_tags", tr("Tags, one folder each", "Теги, каждый в свою папку")),
                    ("batch_exclude", tr("Exclude tags", "Исключить теги")),
                    ("batch_videos", tr("Include videos", "Скачивать видео")),
                    ("batch_pages", tr("Page limit per tag", "Лимит страниц на тег")),
                    ("folder", tr("Parent folder", "Родительская папка")),
                    ("start", tr("DOWNLOAD QUEUE", "СКАЧАТЬ ОЧЕРЕДЬ")),
                    ("clear", tr("Reset form", "Сбросить форму")), ("quit", tr("Exit", "Выход"))]
        if self.tab == 0:
            return [("tags", tr('Tags, comma-separated', 'Теги через запятую')), ("exclude", tr('Exclude tags', 'Исключить теги')),
                    ("videos", tr('Include videos', 'Скачивать видео')), ("pages", tr('Page limit', 'Лимит страниц')),
                    ("folder", tr('Output folder', 'Папка сохранения')), ("start", tr('DOWNLOAD', 'СКАЧАТЬ')),
                    ("clear", tr('Reset form', 'Сбросить форму')), ("quit", tr('Exit', 'Выход'))]
        if self.tab == 1:
            return [("links", tr('URLs, space-separated', 'Ссылки через пробел')), ("folder", tr('Output folder', 'Папка сохранения')),
                    ("start", tr('DOWNLOAD', 'СКАЧАТЬ')), ("clear", tr('Reset form', 'Сбросить форму')), ("quit", tr('Exit', 'Выход'))]
        return [("quit", tr('Exit', 'Выход'))]

    def settings(self):
        d = self.downloader
        folder = self.values["folder"].strip().strip("\"'") or "downloads"
        folder = os.path.abspath(os.path.expandvars(os.path.expanduser(folder)))
        if os.path.exists(folder) and not os.path.isdir(folder):
            raise ValueError(tr('The path is a file. Choose a folder.', 'Путь указывает на файл. Выберите папку.'))
        args = argparse.Namespace(tag="", tags="", exclude_tags="", post_ids=[],
                                  include_videos=False, max_pages=DEFAULT_MAX_PAGES, out_dir=folder)
        if self.tab in (0, 2):
            batch = self.tab == 2
            prefix = "batch_" if batch else ""
            if batch:
                args.batch_tags = parse_batch_tags(self.values["batch_tags"])
                for tag in args.batch_tags:
                    batch_target_folder(folder, tag)
            else:
                args.tags = self.values["tags"]
            if not batch and not d.normalize_tags(args.tags):
                raise ValueError(tr('Enter at least one tag.', 'Укажите хотя бы один тег.'))
            args.exclude_tags = self.values[prefix + "exclude"]
            args.include_videos = self.values[prefix + "videos"]
            try:
                args.max_pages = int(self.values[prefix + "pages"])
                if args.max_pages <= 0:
                    raise ValueError
            except ValueError:
                raise ValueError(tr('Page limit must be a positive whole number.', 'Лимит страниц должен быть целым числом больше нуля.'))
        else:
            links = self.values["links"].split()
            if not links:
                raise ValueError(tr('Add at least one post URL.', 'Добавьте хотя бы одну ссылку на пост.'))
            try:
                args.post_ids = list(dict.fromkeys(d.post_id_from_url(url.strip("\"'"))
                                                  for url in links))
            except argparse.ArgumentTypeError:
                raise ValueError(tr('Invalid URL. Use a rule34.xxx post with page=post&s=view&id=...', 'Неверная ссылка. Нужна страница rule34.xxx с page=post&s=view&id=...'))
        return args

    def handle(self, key, text=""):
        if self.editing is not None:
            if key == "escape":
                self.editing = None
                self.message = tr('Edit cancelled.', 'Изменение отменено.')
            elif key in ("enter", "tab", "backtab"):
                self.values[self.editing] = self.draft
                self.editing = None
                self.message = tr('Saved.', 'Сохранено.')
                if key != "enter":
                    self.selected = (self.selected + (1 if key == "tab" else -1)) % len(self.fields())
            elif key in ("left", "right", "home", "end"):
                self.cursor = {"left": max(0, self.cursor - 1),
                               "right": min(len(self.draft), self.cursor + 1),
                               "home": 0, "end": len(self.draft)}[key]
            elif key == "backspace" and self.cursor:
                self.draft = self.draft[:self.cursor - 1] + self.draft[self.cursor:]
                self.cursor -= 1
            elif key == "delete":
                self.draft = self.draft[:self.cursor] + self.draft[self.cursor + 1:]
            elif key in ("text", "paste"):
                value = safe_text(text.replace("\r", " ").replace("\n", " ").replace("\t", " "))
                self.draft = self.draft[:self.cursor] + value + self.draft[self.cursor:]
                self.cursor += len(value)
            return None
        if self.tab == 3:
            if key in ("up", "down", "pageup", "pagedown", "tab", "backtab", "home", "end") or (key == "text" and text == " "):
                if key == "home":
                    self.help_offset = 0
                elif key == "end":
                    self.help_offset = self.help_max_offset
                else:
                    amount = -1 if key in ("up", "pageup", "backtab") else 1
                    if key not in ("up", "down"):
                        amount *= self.help_page_size
                    self.help_offset = max(0, min(self.help_max_offset, self.help_offset + amount))
                return None
            if key == "enter":
                return None
        if key in ("left", "right"):
            self.tab = (self.tab + (1 if key == "right" else -1)) % len(self.tabs)
            self.selected = 0
            self.message = tr('Select a field and press Enter.', 'Выберите поле и нажмите Enter.')
        elif key in ("up", "down", "tab", "backtab"):
            self.selected = (self.selected + (1 if key in ("down", "tab") else -1)) % len(self.fields())
        elif key == "escape" or (key == "text" and text.lower() == "q"):
            return "quit"
        elif key == "enter" or (key == "text" and text == " "):
            field = self.fields()[self.selected][0]
            if field == "quit":
                return "quit"
            if field == "language":
                return "language"
            if field == "start":
                try:
                    return self.settings()
                except ValueError as e:
                    self.message = str(e)
            elif field == "clear":
                keys = (("batch_tags", "batch_exclude", "batch_videos", "batch_pages") if self.tab == 2 else
                        ("tags", "exclude", "videos", "pages") if self.tab == 0 else ("links",))
                for name in keys:
                    self.values[name] = {"videos": False, "pages": str(DEFAULT_MAX_PAGES),
                                         "batch_videos": False, "batch_pages": str(DEFAULT_MAX_PAGES)}.get(name, "")
                self.message = tr('Form reset. Output folder kept.', 'Форма очищена. Папка сохранена.')
            elif field in ("videos", "batch_videos"):
                self.values[field] = not self.values[field]
            else:
                self.editing = field
                self.draft = self.values[field]
                self.cursor = len(self.draft)
                self.message = tr('Type a value; Enter saves, Esc cancels.', 'Введите значение; Enter — сохранить, Esc — отменить.')
        return None

    def render_help(self, width, height, header):
        body = []
        for title, paragraphs in help_sections():
            body.extend(ACCENT + "  " + line for line in textwrap.wrap(title, width - 4))
            for paragraph in paragraphs:
                body.extend("  " + line for line in textwrap.wrap(paragraph, width - 4))
                body.append("")
        self.help_page_size = max(1, height - len(header) - 6)
        self.help_max_offset = max(0, len(body) - self.help_page_size)
        self.help_offset = min(self.help_offset, self.help_max_offset)
        start = self.help_offset
        visible = body[start:start + self.help_page_size]
        end = start + len(visible)
        lines = header + [MUTED + tr("  User guide · scroll to read all sections",
                                     "  Руководство · прокрутите для чтения всех разделов")]
        lines += visible + [""] * (self.help_page_size - len(visible))
        lines += [MUTED + "  " + "─" * (width - 4),
                  ACCENT + "  " + tr("Lines {}–{} of {}", "Строки {}–{} из {}").format(start + 1, end, len(body)),
                  MUTED + tr("  ↑/↓ scroll · PgUp/PgDn page · Home/End first/last",
                             "  ↑/↓ строки · PgUp/PgDn страницы · Home/End края"),
                  MUTED + tr("  ←/→ tabs · Tab/Space next page · Esc/Q exit",
                             "  ←/→ вкладки · Tab/Пробел следующая · Esc/Q выход")]
        return BASE + "\x1b[H\x1b[J" + "\r\n".join(BASE + clip_line(line, width) + BASE for line in lines)

    def render(self, width, height):
        width = max(1, width - 1)
        if width < 59 or height < 22:
            return tr('\x1b[H\x1b[JResize the terminal to 60 x 22. Exit: Esc / Ctrl+C.', '\x1b[H\x1b[JУвеличьте терминал до 60 x 22. Выход: Esc / Ctrl+C.')
        lines = [FOREGROUND + "  Rule34 Downloader" + MUTED + "  /  terminal", ""]
        tabs = []
        tab_names = self.tabs
        if sum(len(name) + 6 for name in tab_names) > width - 2:
            tab_names = (tr("Tags", "Теги"), tr("URLs", "Ссылки"), tr("Batch", "Массовая"),
                         tr("Help", "Справка"), tr("Settings", "Язык"))
        for index, name in enumerate(tab_names):
            label = " {} ".format(name)
            tabs.append(ACCENT + "\x1b[1m" + label + "\x1b[22m" + FOREGROUND
                        if index == self.tab else MUTED + label + FOREGROUND)
        lines += ["  " + (MUTED + " / " + FOREGROUND).join(tabs),
                  MUTED + "  " + "─" * (width - 4)]
        if self.tab == 3:
            return self.render_help(width, height, lines)
        if self.tab == 2:
            lines += [MUTED + tr("  Each tag downloads separately, in the order entered.",
                                 "  Каждый тег скачивается отдельно, в порядке ввода."),
                      MUTED + tr("  Example: xipa,yonpii,toby → xipa/ yonpii/ toby/",
                                 "  Пример: xipa,yonpii,toby → xipa/ yonpii/ toby/")]
        else:
            lines += [MUTED + tr('  Configure your download. Enter edits the selected field.', '  Настройте загрузку. Enter — изменить выбранное поле.'), ""]
        for index, (field, label) in enumerate(self.fields()):
            prefix = "❯ " if index == self.selected else "  "
            if field in ("start", "clear", "quit", "language"):
                content = "[ ↓ {} ]".format(label) if field == "start" else "[ {} ]".format(label)
            elif field in ("videos", "batch_videos"):
                content = "[{}] {}".format("x" if self.values[field] else " ", label)
            else:
                value = safe_text(self.draft if self.editing == field else self.values[field])
                available = max(5, width - len(label) - 10)
                if self.editing == field:
                    offset = max(0, self.cursor - available + 1)
                    visible = (value + " ")[offset:offset + available]
                    pos = self.cursor - offset
                    value = visible[:pos] + "│" + visible[pos:]
                elif len(value) > available:
                    value = value[:available - 3] + "..."
                content = "{}: {}".format(label, value or tr('(empty)', '(пусто)'))
            line = "  " + prefix + content
            if index == self.selected:
                line = SELECTED + ACCENT + line.ljust(width) + BASE
            else:
                line = FOREGROUND + line
            lines.append(line)
        lines = lines[:height - 5]
        lines += [""] * max(0, height - 5 - len(lines))
        lines += [MUTED + "  " + "─" * (width - 4)]
        lines += [ACCENT + "  ● " + FOREGROUND + safe_text(self.message)[:width - 6],
                  MUTED + tr('  ←/→ tabs · ↑/↓ select · Enter open · Esc exit', '  ←/→ вкладки · ↑/↓ выбор · Enter открыть · Esc выйти'),
                  MUTED + tr('  Editing: Enter save · Esc cancel', '  При вводе: Enter сохранить · Esc отменить')]
        return BASE + "\x1b[H\x1b[J" + "\r\n".join(
            BASE + clip_line(line, width) + BASE for line in lines)

    def choose(self, terminal):
        while True:
            size = shutil.get_terminal_size((80, 24))
            sys.stdout.write(self.render(size.columns, size.lines))
            sys.stdout.flush()
            key, text = terminal.read_key()
            if size.columns < 60 or size.lines < 22:
                if key == "escape" or (key == "text" and text.lower() == "q"):
                    return "quit"
                continue
            result = self.handle(key, text)
            if result is not None:
                return result


def run_terminal(downloader):
    ui = DownloaderUI(downloader)
    while True:
        try:
            with Terminal() as terminal:
                args = ui.choose(terminal)
            if args == "quit":
                return 0
            if args == "language":
                choose_language()
                ui.help_offset = 0
                ui.message = tr("Select a field and press Enter.", "Выберите поле и нажмите Enter.")
                continue
        except (KeyboardInterrupt, EOFError):
            return 0
        except OSError as e:
            print(tr('Cannot open the UI: {}. Opening the text menu.', 'Не удалось открыть интерфейс: {}. Открываю текстовое меню.').format(e))
            return downloader.interactive_menu()
        try:
            print(tr('Folder: {}', 'Папка: {}').format(args.out_dir))
            status = downloader.execute_download(args)
            ui.message = tr('Finished with errors; you can retry.', 'Завершено с ошибками; можно повторить.') if status else tr('Download complete.', 'Загрузка завершена.')
        except KeyboardInterrupt:
            ui.message = tr('Download cancelled. Completed files were kept.', 'Загрузка отменена. Готовые файлы сохранены.')
        except Exception as e:
            ui.message = tr('Error: {}', 'Ошибка: {}').format(e)
        print(ui.message)
        try:
            input(tr('Press Enter to return to the interface...', 'Enter — вернуться к интерфейсу...'))
        except (KeyboardInterrupt, EOFError):
            return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted")
        sys.exit(130)
    except OSError as e:
        print("ERROR: {}".format(e), file=sys.stderr)
        sys.exit(1)
