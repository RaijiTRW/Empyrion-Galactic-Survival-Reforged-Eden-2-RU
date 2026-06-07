# -*- coding: utf-8 -*-
"""
Перевод русификатора Reforged Eden 2 через Google Translate.

ЧТО ДЕЛАЕТ:
  - Находит в CSV-файлах перевода строки, где русская колонка пустая или равна
    английской (т.е. ещё не переведена).
  - Переводит ТОЛЬКО человеческий текст между тегами через Google Translate.
    Сами теги (<color=...>, [c][00ff00], [-], @w3, {PlayerName}, \\n и т.п.)
    в гугл НЕ отправляются и остаются нетронутыми -> разметка не ломается.
  - Пишет перевод обратно в CSV (UTF-8, LF, без BOM) и синхронизирует копии в Saves.
  - Кэширует переводы в translation_cache_google.json -> можно прерывать и
    перезапускать, продолжит с места остановки.

КАК ЗАПУСТИТЬ (на своём ПК, где Google доступен):
  1. Установить Python 3.8+.
  2. Положить этот файл в корень папки русификатора (рядом с папкой translation/).
  3. В терминале выполнить:
         pip install deep-translator
         python translate_via_google.py
     (скрипт сам попробует поставить deep-translator, если его нет)
  4. Дождаться окончания. Если оборвётся (интернет/лимит Google) — просто
     запустить снова, продолжит с кэша.

ОПЦИИ:
  python translate_via_google.py --sleep 0.4   # пауза между запросами к Google (сек)
  python translate_via_google.py --dry          # только показать, сколько строк к переводу
"""

import os, sys, csv, re, json, time, argparse, shutil

# ------------------------------------------------------------------ настройки
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(SCRIPT_DIR, "translation")
SCEN = os.path.join(BASE, "Content", "Scenarios", "Reforged Eden 2")
SAVE = os.path.join(BASE, "Saves", "Games", "_SAVE_NAME_")

# (файл, который правим) -> (копия-зеркало, которую потом перезапишем тем же содержимым)
FILES = [
    (os.path.join(SCEN, "Content", "Configuration", "Dialogues.csv"),
     os.path.join(SAVE, "Content", "Configuration", "Dialogues.csv")),
    (os.path.join(SCEN, "Extras", "PDA", "PDA.csv"),
     os.path.join(SAVE, "PDA", "PDA.csv")),
    (os.path.join(SCEN, "Extras", "Localization.csv"), None),
]

CACHE_PATH = os.path.join(SCRIPT_DIR, "translation_cache_google.json")
ENG_COL, RUS_COL = 1, 9
BATCH_CHARS = 4000          # макс. суммарная длина фрагментов в одном запросе
csv.field_size_limit(10_000_000)

# Токены, которые НЕЛЬЗЯ переводить (порядок важен — длинные первыми).
TOKEN = re.compile(
    r"(<[^>]+>"                 # html-теги: <color=#...>, </color>, <b>, <i> ...
    r"|\[/?[A-Za-z]\]"          # [c] [b] [/b] [u] [/u] [i] [/i]
    r"|\[-\]"                   # [-]
    r"|\[[0-9A-Fa-f]{3,8}\]"    # цвет в скобках: [00ff00] [ffae00] [c0c0c0]
    r"|@[A-Za-z]+\d*"           # тайминги речи: @w2 @p9 @q0
    r"|\{[^}]+\}"               # подстановки: {PlayerName}
    r"|\\n)"                    # литеральный перенос строки \n
)
HAS_LETTER = re.compile(r"[A-Za-z]")
WS = re.compile(r"^(\s*)(.*?)(\s*)$", re.S)


# ------------------------------------------------------------------ утилиты
def load_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))

def save_rows(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, quoting=csv.QUOTE_MINIMAL, lineterminator="\n").writerows(rows)

def is_pending(eng, rus):
    eng = eng.strip()
    return bool(eng) and (rus.strip() == "" or rus.strip() == eng)

def translatable_pieces(text):
    """Вернуть список (stripped_core) кусков текста, которые надо перевести."""
    out = []
    for i, part in enumerate(TOKEN.split(text)):
        if i % 2 == 1:           # нечётные = токены, пропускаем
            continue
        core = WS.match(part).group(2)
        if core and HAS_LETTER.search(core):
            out.append(core)
    return out

def rebuild(text, cache):
    """Собрать строку заново, подставив переводы из cache, сохранив теги/пробелы."""
    res = []
    for i, part in enumerate(TOKEN.split(text)):
        if i % 2 == 1:
            res.append(part)     # токен как есть
            continue
        m = WS.match(part)
        lead, core, trail = m.group(1), m.group(2), m.group(3)
        if core and HAS_LETTER.search(core) and cache.get(core):
            res.append(lead + cache[core] + trail)
        else:
            res.append(part)
    return "".join(res)


# ------------------------------------------------------------------ основной код
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=0.3, help="пауза между запросами к Google, сек")
    ap.add_argument("--dry", action="store_true", help="только показать объём, не переводить")
    args = ap.parse_args()

    for src, _ in FILES:
        if not os.path.isfile(src):
            print("НЕ НАЙДЕН файл:", src)
            print("Положите скрипт в корень папки русификатора (рядом с папкой translation/).")
            sys.exit(1)

    # 1) собрать все уникальные куски текста к переводу
    needed = set()
    per_file_rows = {}
    for src, _ in FILES:
        rows = load_rows(src)
        per_file_rows[src] = rows
        for r in rows[1:]:
            if len(r) <= RUS_COL:
                continue
            if is_pending(r[ENG_COL], r[RUS_COL]):
                for core in translatable_pieces(r[ENG_COL]):
                    needed.add(core)

    print(f"Уникальных кусков текста к переводу: {len(needed)}")
    if args.dry:
        return

    # 2) кэш
    cache = {}
    if os.path.isfile(CACHE_PATH):
        try:
            cache = json.load(open(CACHE_PATH, encoding="utf-8"))
            print(f"Загружен кэш: {len(cache)} готовых переводов")
        except Exception:
            cache = {}

    todo = [s for s in needed if s not in cache]
    print(f"Осталось перевести: {len(todo)}")

    if todo:
        from deep_translator import GoogleTranslator
        tr = GoogleTranslator(source="en", target="ru")

        def flush(buf):
            """Перевести список кусков одним запросом (через \\n), с откатом по одному."""
            if not buf:
                return
            joined = "\n".join(buf)
            try:
                out = tr.translate(joined)
                parts = out.split("\n") if out else []
            except Exception as e:
                parts = []
            if len(parts) == len(buf):
                for s, t in zip(buf, parts):
                    cache[s] = t.strip() if t and t.strip() else s
            else:
                # откат: по одному
                for s in buf:
                    for attempt in range(3):
                        try:
                            t = tr.translate(s)
                            cache[s] = t.strip() if t and t.strip() else s
                            break
                        except Exception:
                            time.sleep(1.5 * (attempt + 1))
                    else:
                        cache[s] = s  # не удалось — оставим оригинал, повторим при перезапуске
                        del cache[s]
            time.sleep(args.sleep)

        buf, blen, done = [], 0, 0
        for s in todo:
            if blen + len(s) > BATCH_CHARS and buf:
                flush(buf); done += len(buf); buf, blen = [], 0
                if done % 500 < len(buf) + 50:
                    json.dump(cache, open(CACHE_PATH, "w", encoding="utf-8"), ensure_ascii=False)
                    print(f"  переведено ~{done}/{len(todo)}")
            buf.append(s); blen += len(s) + 1
        flush(buf); done += len(buf)
        json.dump(cache, open(CACHE_PATH, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"Перевод фрагментов завершён: {len([k for k in needed if k in cache])}/{len(needed)}")

    # 3) применить к файлам
    for src, mirror in FILES:
        rows = per_file_rows[src]
        changed = 0
        for r in rows[1:]:
            if len(r) <= RUS_COL:
                continue
            if is_pending(r[ENG_COL], r[RUS_COL]):
                new = rebuild(r[ENG_COL], cache)
                if new != r[RUS_COL]:
                    r[RUS_COL] = new
                    changed += 1
        save_rows(src, rows)
        print(f"Записано {changed} строк -> {os.path.relpath(src, SCRIPT_DIR)}")
        if mirror and os.path.isfile(mirror):
            shutil.copyfile(src, mirror)
            print(f"   зеркало обновлено -> {os.path.relpath(mirror, SCRIPT_DIR)}")

    print("\nГОТОВО. Если что-то осталось на английском — запустите скрипт ещё раз.")


if __name__ == "__main__":
    try:
        import deep_translator  # noqa
    except ImportError:
        print("Ставлю deep-translator ...")
        os.system(f'"{sys.executable}" -m pip install deep-translator')
    main()
