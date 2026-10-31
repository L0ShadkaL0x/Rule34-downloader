# Rule34 Downloader

**One Python file. A keyboard-driven terminal interface. Downloads organized your way.**  
**Один Python-файл. Управление с клавиатуры. Загрузка в удобные папки.**

![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)
![Windows · Linux](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-555555)
![English · Русский](https://img.shields.io/badge/Language-English%20%7C%20Русский-D97757)
![Standard library only](https://img.shields.io/badge/Dependencies-stdlib%20only-3776AB)

Download images and videos from **rule34.xxx** by tags or post links. Use the terminal interface for everyday downloads and command-line options for automation.

Скачивайте изображения и видео с **rule34.xxx** по тегам или ссылкам на посты. Для обычной работы используйте терминальный интерфейс, для автоматизации — параметры командной строки.

**[English guide](#english)** · **[Инструкция на русском](#русский)**

---

## English

### Features

- **Terminal interface** inspired by Claude Code: dark background, warm orange accents, tabs and keyboard navigation.
- **Tag search** with required tags and optional exclusions.
- **Post links** for downloading specific images or videos.
- **Batch downloads**: process tags sequentially and create a folder for each tag.
- **Live file progress** with transferred bytes, speed and estimated time remaining.
- **English and Russian**, with a language picker on first launch.
- **One standalone `.py` file** using only the Python standard library.
- **Existing-file skipping** when repeating a download.

### Quick start

1. Install **Python 3.8 or newer**.
2. Download this repository using **Code → Download ZIP** and extract it, or download `r34_downloader.py` alone.
3. Open a terminal in the folder containing the script and run:

**Windows — PowerShell / Command Prompt**

```powershell
py r34_downloader.py
```

If `py` is unavailable, use `python r34_downloader.py`.

**Linux**

```bash
python3 r34_downloader.py
```

No `pip install` step is required. On first interactive launch, choose **English** or **Русский** with the arrow keys and press **Enter**.

For the fullscreen interface, use an ANSI-capable terminal with UTF-8 support and a window of at least **60 columns × 22 rows**. Windows Terminal is a suitable Windows option. If fullscreen mode is unavailable, the app falls back to a numbered text menu.

> Linux support is implemented, but the app has not yet been tested on a real Linux system. Fonts and colors may vary between terminals.

### Tabs and settings

| Tab | Purpose |
| --- | --- |
| **Tags** | Download posts containing **all** entered tags into one folder. |
| **Post URLs** | Download specific posts. Images and videos are included automatically. |
| **Batch download** | Download each tag separately into its own subfolder. |
| **Help** | Read the full guide for fields, buttons, downloads and troubleshooting. |
| **Settings** | Change the interface language. |

| Field | Meaning |
| --- | --- |
| **Tags** | Comma-separated tags. In **Tags**, they are combined with AND; in **Batch download**, each is a separate search. Spaces inside a tag become underscores. |
| **Exclude tags** | Skip posts containing **any** of these comma-separated tags. |
| **Include videos** | Include videos alongside images. Off by default for tag searches. |
| **Page limit** | Search up to **10,000 API pages** by default, with up to 100 posts per page. An empty page ends the search early. In batch mode, the limit applies to each tag. |
| **Output / Parent folder** | Save location, shared between tabs. Defaults to `downloads` in the terminal's working directory. Missing folders are created automatically. |

Paths may be relative, absolute or start with `~` for your home directory. Paths with spaces need no quotes inside the form. Form values remain during the current session; only the language is saved between launches.

### Keyboard controls

| Key | Action |
| --- | --- |
| `←` / `→` | Switch tabs when not editing. |
| `↑` / `↓`, `Tab` / `Shift+Tab` | Select a field or button. |
| `Enter` | Edit a field, confirm a value or activate a button. |
| `Space` | Toggle the video checkbox when selected. |
| `Esc` | Cancel an edit; outside the editor, exit the app. |
| `Q` | Exit outside the editor; ordinary text while editing. |
| `Ctrl+C` | Cancel a download or the entire batch queue. |

While editing, use `←` / `→`, `Home` / `End` and `Backspace` / `Delete`. In **Help**, use `↑` / `↓` to scroll a line, `PageUp` / `PageDown` or `Shift+Tab` / `Tab` to scroll a page, `Space` for the next page and `Home` / `End` to jump to the beginning or end.

### Batch download example

Open **Batch download**, enter:

```text
xipa,yonpii,toby
```

Set the parent folder to `downloads` and select **DOWNLOAD QUEUE**. The app processes the tags in order:

```text
downloads/
├── xipa/      ← posts tagged xipa
├── yonpii/    ← posts tagged yonpii
└── toby/      ← posts tagged toby
```

Duplicate tags are removed. Exclusions and the video checkbox apply to every tag. A post matching several queued tags is saved in each matching folder. Invalid folder names are rejected before starting. A failure for one tag does not stop later tags; `Ctrl+C` stops the queue.

### Downloading by post link

Open **Post URLs**, paste one or more post-page links separated by spaces, choose the output folder and select **DOWNLOAD**.

```text
https://rule34.xxx/index.php?page=post&s=view&id=12345
```

Replace `12345` with an actual post ID. Search pages and direct media/CDN links are not supported. Duplicate post IDs are processed once. Tag filters and page limits do not apply to this mode.

### Progress, cancellation and retries

The app first collects posts, then shows progress for the current file: filename, file index, progress bar, percentage, bytes, average speed and estimated time remaining. If the server does not provide the file size, bytes and speed still update without a percentage. Redirected output uses periodic status lines.

Files are named by post ID, for example `12345.png` or `12345.mp4`. Existing nonempty files are skipped; empty files are downloaded again. Transfers use temporary `.part` files, which are removed on normal errors or `Ctrl+C`. **Interrupted files restart from the beginning; byte-range resume is not supported.**

After completion or cancellation in the interface, press **Enter** to return to the form. **Reset form** resets the current tab while keeping the selected folder; it does not delete downloaded files.

### Command-line mode · optional

Run without arguments to use the interface. For automation, use the examples below. On Windows, replace `python3` with `py` or `python`.

```bash
# One tag
python3 r34_downloader.py --tag xipa --out-dir "./downloads/xipa"

# Both tags required; exclude posts with ai_generated
python3 r34_downloader.py --tags "petrification,cursed" --exclude-tags "ai_generated" --out-dir "./downloads"

# Images and videos, with a smaller page limit
python3 r34_downloader.py --tag yonpii --include-videos --max-pages 100 --out-dir "./downloads/yonpii"

# One folder per tag
python3 r34_downloader.py --batch-tags "xipa,yonpii,toby" --out-dir "./downloads"

# Specific post: replace the example ID
python3 r34_downloader.py --url "https://rule34.xxx/index.php?page=post&s=view&id=12345" --out-dir "./downloads"

# List available options
python3 r34_downloader.py --help
```

`--out-dir` is required in command-line mode. Repeat `--url` to download multiple posts; `--post-url` is an alias. Do not combine URLs with tag searches or exclusions. Do not combine `--batch-tags` with `--tag`, `--tags` or `--url`. Always quote URLs because they contain `&`.

### Language and troubleshooting

Change language in **Settings → Language**. In the text menu: **1** Tags, **2** Post URLs, **3** Help, **4** Language, **5** Batch download, **0** Exit. Enter `:back` at a prompt to return to the menu.

| Issue | What to check |
| --- | --- |
| Python command is missing | Install Python and reopen the terminal. On Windows, try `py` or `python`; on Linux, use `python3`. |
| No fullscreen interface | Check terminal size, ANSI/UTF-8 support and whether input/output is redirected. On Linux, `TERM=dumb` disables fullscreen mode. |
| No matching posts | Check tag spelling, exclusions, the page limit and API errors in the log. |
| API or download errors | Check connectivity, wait if requests are rate-limited, then retry. Finished files will be skipped. |
| No percentage in progress | The server may not have supplied the total size; watch transferred bytes and speed. |

Language settings are stored in `%APPDATA%\Rule34Downloader\settings.json` on Windows and `$XDG_CONFIG_HOME/Rule34Downloader/settings.json` on Linux, falling back to `~/.config/Rule34Downloader/settings.json`. Command-line runs use the saved language, or English if none exists, without prompting.

The script queries the `api.r34.app` mirror and downloads media from the source CDN. It includes DNS-over-HTTPS lookup for selected source hosts, but API availability, rate limits and network restrictions can still affect downloads.

---

## Русский

### Возможности

- **Терминальный интерфейс** в стиле Claude Code: тёмный фон, оранжевые акценты, вкладки и управление с клавиатуры.
- **Поиск по тегам** с обязательными тегами и исключениями.
- **Загрузка по ссылкам** на конкретные изображения и видео.
- **Массовая загрузка**: последовательная обработка тегов с отдельной папкой для каждого.
- **Прогресс файла**: объём, скорость и примерное оставшееся время.
- **Русский и английский языки**, выбор при первом запуске.
- **Один самостоятельный `.py`-файл**, только стандартная библиотека Python.
- **Пропуск готовых файлов** при повторном запуске.

### Быстрый старт

1. Установите **Python 3.8 или новее**.
2. Скачайте репозиторий через **Code → Download ZIP** и распакуйте архив либо скачайте только `r34_downloader.py`.
3. Откройте терминал в папке со скриптом и выполните команду:

**Windows — PowerShell / командная строка**

```powershell
py r34_downloader.py
```

Если команда `py` недоступна, используйте `python r34_downloader.py`.

**Linux**

```bash
python3 r34_downloader.py
```

Устанавливать пакеты через `pip` не требуется. При первом интерактивном запуске выберите **English** или **Русский** стрелками и нажмите **Enter**.

Для полноэкранного режима нужен терминал с ANSI и UTF-8, размер окна — минимум **60 столбцов × 22 строки**. На Windows подойдёт Windows Terminal. Если полноэкранный режим недоступен, программа откроет простое меню с номерами пунктов.

> Поддержка Linux реализована, но запуск на настоящей Linux-системе пока не проверен. Шрифты и цвета могут отличаться в разных терминалах.

### Вкладки и настройки

| Вкладка | Назначение |
| --- | --- |
| **По тегам** | Скачивает в одну папку посты, содержащие **все** указанные теги. |
| **По ссылкам** | Скачивает конкретные посты. Картинки и видео включаются автоматически. |
| **Массовая загрузка** | Ищет каждый тег отдельно и сохраняет результат в его подпапку. |
| **Справка** | Полная инструкция по полям, кнопкам, загрузке и ошибкам. |
| **Настройки** | Смена языка интерфейса. |

| Поле | Что означает |
| --- | --- |
| **Теги** | Список через запятую. Во вкладке **По тегам** пост должен содержать все теги; в **Массовой загрузке** каждый тег — отдельный поиск. Пробелы внутри тега заменяются на `_`. |
| **Исключить теги** | Пропускать пост, если он содержит хотя бы один тег из списка через запятую. |
| **Скачивать видео** | Добавляет видео к картинкам. При поиске по тегам изначально выключено. |
| **Лимит страниц** | По умолчанию — **10 000 страниц API**, до 100 постов на страницу. Пустая страница завершает поиск раньше. В массовой загрузке лимит действует отдельно для каждого тега. |
| **Папка сохранения / Родительская папка** | Общее для вкладок место сохранения. По умолчанию — `downloads` в рабочей папке терминала. Недостающие папки создаются автоматически. |

Можно использовать относительные и абсолютные пути, а также `~` для домашней папки. В форме путь с пробелами вводится без кавычек. Значения полей сохраняются в текущем сеансе; между запусками запоминается только язык.

### Управление

| Клавиша | Действие |
| --- | --- |
| `←` / `→` | Переключение вкладок вне редактирования. |
| `↑` / `↓`, `Tab` / `Shift+Tab` | Выбор поля или кнопки. |
| `Enter` | Редактирование поля, сохранение значения или нажатие кнопки. |
| `Пробел` | Переключение выбранного флажка видео. |
| `Esc` | Отмена правки; вне редактирования — выход из программы. |
| `Q` | Выход вне редактирования; в поле вводится как обычный текст. |
| `Ctrl+C` | Отмена загрузки или всей очереди. |

При редактировании работают `←` / `→`, `Home` / `End`, `Backspace` / `Delete`. В **Справке** стрелки `↑` / `↓` прокручивают строку, `PageUp` / `PageDown` или `Shift+Tab` / `Tab` — страницу, `Пробел` — следующую страницу, `Home` / `End` — начало и конец.

### Пример массовой загрузки

Откройте **Массовая загрузка** и введите:

```text
xipa,yonpii,toby
```

Укажите родительскую папку `downloads` и нажмите **СКАЧАТЬ ОЧЕРЕДЬ**. Теги обрабатываются по порядку:

```text
downloads/
├── xipa/      ← посты с тегом xipa
├── yonpii/    ← посты с тегом yonpii
└── toby/      ← посты с тегом toby
```

Повторяющиеся теги убираются. Исключения и флажок видео действуют на всю очередь. Пост с несколькими тегами очереди сохраняется в каждую подходящую папку. Недопустимые имена папок отклоняются до запуска. Ошибка одного тега не останавливает следующие; `Ctrl+C` отменяет всю очередь.

### Загрузка по ссылке

Откройте **По ссылкам**, вставьте одну или несколько ссылок на страницы постов через пробел, выберите папку и нажмите **СКАЧАТЬ**.

```text
https://rule34.xxx/index.php?page=post&s=view&id=12345
```

Вместо `12345` подставьте настоящий номер поста. Страницы поиска и прямые ссылки на файлы/CDN не поддерживаются. Повторы номеров обрабатываются один раз. Фильтры тегов и лимит страниц в этом режиме не применяются.

### Прогресс, отмена и повторный запуск

Сначала программа собирает посты, затем показывает прогресс текущего файла: имя, номер, полосу, процент, объём, среднюю скорость и примерное оставшееся время. Если сервер не сообщил размер, объём и скорость обновляются без процента. При перенаправлении вывода статус печатается отдельными строками.

Файлы называются по номеру поста, например `12345.png` или `12345.mp4`. Готовые непустые файлы пропускаются, пустые скачиваются заново. Во время передачи используется временный файл `.part`, который удаляется при обычной ошибке или `Ctrl+C`. **Недокачанный файл при повторном запуске скачивается с начала; продолжения с места обрыва нет.**

После завершения или отмены в интерфейсе нажмите **Enter**, чтобы вернуться к форме. **Сбросить форму** сбрасывает настройки текущей вкладки, сохраняя выбранную папку; скачанные файлы не удаляются.

### Командная строка · необязательно

Для интерфейса запускайте скрипт без аргументов. Для автоматизации используйте примеры ниже. На Windows замените `python3` на `py` или `python`.

```bash
# Один тег
python3 r34_downloader.py --tag xipa --out-dir "./downloads/xipa"

# Пост должен содержать оба тега; исключить ai_generated
python3 r34_downloader.py --tags "petrification,cursed" --exclude-tags "ai_generated" --out-dir "./downloads"

# Картинки и видео, с уменьшенным лимитом страниц
python3 r34_downloader.py --tag yonpii --include-videos --max-pages 100 --out-dir "./downloads/yonpii"

# Каждый тег — в отдельную папку
python3 r34_downloader.py --batch-tags "xipa,yonpii,toby" --out-dir "./downloads"

# Конкретный пост: замените номер в примере
python3 r34_downloader.py --url "https://rule34.xxx/index.php?page=post&s=view&id=12345" --out-dir "./downloads"

# Список параметров
python3 r34_downloader.py --help
```

В командной строке `--out-dir` обязателен. Для нескольких постов повторите `--url`; его альтернативное имя — `--post-url`. Ссылки нельзя совмещать с поиском по тегам и исключениями. `--batch-tags` нельзя совмещать с `--tag`, `--tags` и `--url`. Ссылки обязательно заключайте в кавычки: они содержат `&`.

### Язык и решение проблем

Сменить язык можно в **Настройки → Язык**. В текстовом меню: **1** По тегам, **2** По ссылкам, **3** Справка, **4** Язык, **5** Массовая загрузка, **0** Выход. Команда `:back` в ответ на вопрос возвращает в меню.

| Проблема | Что проверить |
| --- | --- |
| Команда Python не найдена | Установите Python и заново откройте терминал. На Windows попробуйте `py` или `python`, на Linux — `python3`. |
| Нет полноэкранного интерфейса | Проверьте размер окна, поддержку ANSI/UTF-8 и перенаправление ввода/вывода. На Linux `TERM=dumb` отключает полноэкранный режим. |
| Посты не найдены | Проверьте написание тегов, исключения, лимит страниц и ошибки API в журнале. |
| Ошибка API или скачивания | Проверьте соединение; при ограничении запросов подождите и повторите. Готовые файлы будут пропущены. |
| Нет процента загрузки | Сервер мог не сообщить размер файла; ориентируйтесь на объём и скорость. |

Настройка языка хранится в `%APPDATA%\Rule34Downloader\settings.json` на Windows и `$XDG_CONFIG_HOME/Rule34Downloader/settings.json` на Linux либо в `~/.config/Rule34Downloader/settings.json`, если переменная не задана. При запуске с аргументами используется сохранённый язык или английский без дополнительного вопроса.

Скрипт обращается к зеркалу `api.r34.app`, а файлы получает с CDN источника. Для отдельных хостов источника встроен DNS-over-HTTPS, однако доступность API, ограничения запросов и сетевые блокировки всё равно могут влиять на загрузку.
