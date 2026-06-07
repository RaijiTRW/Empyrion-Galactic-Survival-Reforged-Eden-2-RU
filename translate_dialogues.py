#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Перевод русификатора Reforged Eden 2 на русский через Google Translate.

ЗАПУСК (из папки русификатора, ПОСЛЕ ОТКЛЮЧЕНИЯ VPN):

    python3 translate_dialogues.py
    python3 translate_dialogues.py --dry          # только показать объём
    python3 translate_dialogues.py --sleep 1.0    # пауза между запросами (по умолч. 0.6)

Как устроено (чтобы Google реже блокировал):
  * короткие строки (их ~98%) переводятся ПЕРВЫМИ и ПАКЕТАМИ — мало запросов;
  * длинные строки режутся по переносам \\n и собираются обратно; если кусок
    не перевёлся — он остаётся на английском, но вся реплика не рушится;
  * игровые теги ({PlayerName}, <color=#..>, <b>, @w2, \\n, [c][00ff00] ...)
    сохраняются; целостность проверяется; декор «< WARNING >» переводится;
  * прогресс пишется в .re2_translate_cache.json — можно прервать (Ctrl+C)
    и запустить снова, продолжит с места;
  * при блокировке IP скрипт ждёт и пробует снова (уже сделанное не теряется);
  * перед записью делает резервные копии (*.bak); меняет только колонку Russian;
  * синхронизирует копии-зеркала в Saves/Games/_SAVE_NAME_/.

Зависимостей нет — нужен только Python 3.6+.
"""
import csv, json, os, re, sys, time, random, html, shutil
import urllib.request, urllib.parse, urllib.error

# ---------------------------------------------------------------- пути / файлы -
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "translation")
SCEN = os.path.join(BASE, "Content", "Scenarios", "Reforged Eden 2")
SAVE = os.path.join(BASE, "Saves", "Games", "_SAVE_NAME_")
CACHE = os.path.join(HERE, ".re2_translate_cache.json")

FILES = [
    (os.path.join(SCEN, "Content", "Configuration", "Dialogues.csv"),
     os.path.join(SAVE, "Content", "Configuration", "Dialogues.csv")),
    (os.path.join(SCEN, "Extras", "PDA", "PDA.csv"),
     os.path.join(SAVE, "PDA", "PDA.csv")),
    (os.path.join(SCEN, "Extras", "Localization.csv"), None),
]
csv.field_size_limit(10_000_000)

# ---------------------------------------------------------------- настройки ----
SHORT_LIMIT = 1200          # строки длиннее режем на сегменты
BATCH_MAX_N = 40            # макс. строк в одном запросе
BATCH_BUDGET = 2200         # макс. символов в запросе (ограничено длиной URL Lingva)
SAVE_EVERY = 20
SLEEP = 0.5                 # пауза между запросами (меняется флагом --sleep)

# Перевод идёт через Lingva — это Google Translate, но запрос к Google делает
# СЕРВЕР Lingva, а не твой IP. Поэтому блокировка твоего IP не мешает, и новых
# блокировок на твой IP не возникает. Несколько зеркал на случай сбоев.
INSTANCES = ["lingva.ml", "lingva.lunar.icu"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_inst = [0]

TOKEN_RE = re.compile(
    r"\\n"
    r"|\{[^{}]*\}"
    r"|</?[A-Za-z][^<>]*>"
    r"|\[/?[A-Za-z]\]|\[-\]|\[[0-9A-Fa-f]{3,8}\]"
    r"|@[A-Za-z]\d*")
PUA_START, PUA_END = 0xE000, 0xF8FE
SEP = chr(0xF8FF)
PUA_RE = re.compile("[%s-%s]" % (chr(PUA_START), chr(PUA_END)))


class Blocked(Exception):
    pass


class GiveUp(Exception):
    pass


# ---------------------------------------------------------------- HTTP ---------
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def http_error_301(self, req, fp, code, msg, headers):
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)
    http_error_302 = http_error_303 = http_error_307 = http_error_308 = http_error_301


_OPENER = urllib.request.build_opener(_NoRedirect)


_BLOCKISH = (429, 502, 503, 520, 522, 403)


def _lingva_once(masked):
    """Один проход по зеркалам. Возвращает перевод, None (повторить) или
    бросает Blocked (все зеркала ограничивают/недоступны)."""
    enc = urllib.parse.quote(masked, safe="")
    blocked_all = True
    for off in range(len(INSTANCES)):
        host = INSTANCES[(_inst[0] + off) % len(INSTANCES)]
        url = "https://%s/api/v1/en/ru/%s" % (host, enc)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with _OPENER.open(req, timeout=30) as resp:
                code = resp.status
                body = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code not in _BLOCKISH:
                blocked_all = False
            continue
        except Exception:
            blocked_all = False           # сеть/таймаут — не блок, просто повтор
            continue
        if code == 200:
            try:
                tr = json.loads(body).get("translation")
            except Exception:
                tr = None
            if tr:
                _inst[0] = (_inst[0] + off + 1) % len(INSTANCES)
                return html.unescape(tr)
            blocked_all = False           # 200, но без перевода — не блок
        elif code not in _BLOCKISH:
            blocked_all = False
    if blocked_all:
        raise Blocked("lingva")
    return None


def gt(masked, retries=4):
    delay = 2.0
    for _ in range(retries):
        r = _lingva_once(masked)          # Blocked пробрасывается наверх
        if r is not None:
            return r
        time.sleep(delay + random.random())
        delay *= 2
    return None


# ------------------------------------------------------ защита тегов / проверка -
def protect(text):
    mapping = []
    def repl(m):
        mapping.append(m.group(0))
        return chr(PUA_START + len(mapping) - 1)
    return TOKEN_RE.sub(repl, text), mapping


def restore(masked, mapping):
    def repl(m):
        i = ord(m.group(0)) - PUA_START
        return mapping[i] if 0 <= i < len(mapping) else ""
    return PUA_RE.sub(repl, masked)


def verify(src, final):
    if final is None or final.strip() == "":
        return False
    if PUA_RE.search(final) or SEP in final:
        return False
    if sorted(TOKEN_RE.findall(src)) != sorted(TOKEN_RE.findall(final)):
        return False
    for ch in "[]<>":
        if src.count(ch) != final.count(ch):
            return False
    return True


def has_text(s):
    return any(c.isalpha() for c in TOKEN_RE.sub(" ", s))


def split_edges(text):
    """Отделить ведущие/замыкающие теги и пробелы от переводимой середины.
    Крайние теги Google роняет на границе запроса, поэтому их НЕ отправляем,
    а просто приклеиваем обратно. Середину переводим (внутренние теги в ней
    защищены спец-символами и переживают перевод)."""
    spans = [(m.start(), m.end()) for m in TOKEN_RE.finditer(text)]
    i, n = 0, len(text)
    moved = True
    while moved:
        moved = False
        while i < n and text[i] in " \t":
            i += 1; moved = True
        for s, e in spans:
            if s == i:
                i = e; moved = True; break
    j = n
    moved = True
    while moved:
        moved = False
        while j > i and text[j - 1] in " \t":
            j -= 1; moved = True
        for s, e in spans:
            if e == j and s >= i:
                j = s; moved = True; break
    return text[:i], text[i:j], text[j:]


def is_pending(eng, rus):
    eng = eng.strip()
    return bool(eng) and (rus.strip() == "" or rus.strip() == eng)


# ------------------------------------------------------------- перевод единиц --
def _framed_translate(units):
    """Перевести список строк одним запросом. У каждой строки отрезаем крайние
    теги (их Google роняет на границе) и шлём только середину, обрамлённую
    разделителями. Потом приклеиваем крайние теги обратно."""
    leads, cores, trails, maps, masks = [], [], [], [], []
    for t in units:
        lead, core, trail = split_edges(t)
        m, mp = protect(core)
        leads.append(lead); cores.append(core); trails.append(trail)
        masks.append(m); maps.append(mp)
    s = " %s " % SEP
    out = gt(s + s.join(masks) + s)          # SEP c0 SEP c1 SEP ... cn SEP
    if out is None:
        return [None] * len(units)
    pieces = out.split(SEP)
    if len(pieces) != len(units) + 2:        # [край] c0 c1 ... [край]
        return [None] * len(units)
    res = []
    for t, lead, trail, piece, mp in zip(units, leads, trails, pieces[1:-1], maps):
        fin = lead + restore(piece.strip(), mp) + trail
        res.append(fin if verify(t, fin) else None)
    return res


def translate_unit(text):
    """Перевести одну строку/сегмент. Вернуть перевод или None."""
    masked, mapping = protect(text)
    if not mapping and not any(c.isalpha() for c in text):
        return text
    return _framed_translate([text])[0]


def translate_batch(units):
    return _framed_translate(units)


# ------------------------------------------------------------------- кэш --------
def load_cache():
    if os.path.exists(CACHE):
        try:
            with open(CACHE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cache(c):
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)
    os.replace(tmp, CACHE)


def wait_block(cache):
    save_cache(cache)
    for wait in (30, 60, 120, 180, 300, 300, 300, 600):
        print("   ⏳ Google заблокировал запросы (IP). Жду %d сек и пробую снова…"
              % wait, flush=True)
        print("      (если включён VPN — выключите; Ctrl+C прервёт, прогресс сохранён)",
              flush=True)
        time.sleep(wait)
        try:
            if gt("ping", retries=1) is not None:
                print("   ✅ доступ восстановлен, продолжаю", flush=True)
                return True
        except Blocked:
            continue
    return False


# ----------------------------------------------------------- движок перевода ---
def masked_len(s):
    # длина того, что реально уходит в Google (каждый тег = 1 символ)
    return len(TOKEN_RE.sub(".", s))


def run_units(cache, units, label):
    """Перевести список уникальных строк/сегментов крупными пакетами.

    Если пакет не сошёлся (Google потерял разделитель или обрезал длинный
    запрос) — он делится пополам и повторяется, а не рассыпается на тысячи
    одиночных запросов. Так суммарно запросов в разы меньше."""
    units = sorted(units, key=masked_len)        # короткие первыми
    total = len(units)
    stat = {"done": 0, "fail": 0, "last": time.time()}

    def tick():
        if time.time() - stat["last"] > SAVE_EVERY:
            save_cache(cache); stat["last"] = time.time()

    def rec(group):
        """Перевести группу; делить пополам при полном провале. Raises Blocked."""
        if not group:
            return
        if len(group) == 1:
            r = translate_unit(group[0])
            if r is None:
                stat["fail"] += 1
            else:
                cache[group[0]] = r
            stat["done"] += 1
            return
        res = translate_batch(group)
        if all(x is None for x in res):          # разделитель/обрезка — делим
            mid = len(group) // 2
            rec(group[:mid]); rec(group[mid:])
        else:
            for u, x in zip(group, res):
                if x is None:
                    rec([u])                     # одиночный повтор
                else:
                    cache[u] = x; stat["done"] += 1

    i = 0
    while i < total:
        group, chars = [], 0
        while i < total and len(group) < BATCH_MAX_N and chars < BATCH_BUDGET:
            group.append(units[i]); chars += masked_len(units[i]) + 4; i += 1
        while True:
            try:
                rec(group); break
            except Blocked:
                if not wait_block(cache):
                    raise GiveUp()
        print("   %s: %d/%d (%.1f%%), не удалось %d"
              % (label, stat["done"], total, 100.0 * stat["done"] / total,
                 stat["fail"]), flush=True)
        tick(); time.sleep(SLEEP + random.random() * 0.4)
    save_cache(cache)


# --------------------------------------------------------------------- сборка --
def render(en, cache):
    """Собрать перевод строки из кэша по сегментам (между \\n).
    Непереведённые сегменты остаются на английском — реплика не рушится."""
    out, any_tr = [], False
    for p in en.split("\\n"):
        if has_text(p) and p in cache:
            out.append(cache[p]); any_tr = True
        else:
            out.append(p)
    ru = "\\n".join(out)
    return ru if (any_tr and ru != en) else None


# --------------------------------------------------------------------- main ----
def load_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.reader(fh))


def main():
    global SLEEP, BATCH_BUDGET
    dry = "--dry" in sys.argv
    if "--sleep" in sys.argv:
        try:
            SLEEP = float(sys.argv[sys.argv.index("--sleep") + 1])
        except Exception:
            pass
    if "--budget" in sys.argv:
        try:
            BATCH_BUDGET = int(sys.argv[sys.argv.index("--budget") + 1])
        except Exception:
            pass

    if not os.path.isdir(BASE):
        print("НЕ НАЙДЕНА папка translation/ рядом со скриптом.")
        print("Положите этот файл в корень папки русификатора.")
        sys.exit(1)
    sources = [(s, m) for s, m in FILES if os.path.isfile(s)]
    if not sources:
        print("НЕ НАЙДЕНЫ CSV-файлы перевода внутри translation/."); sys.exit(1)

    # собрать единицы перевода: КАЖДУЮ строку режем по \n на сегменты
    # (Google роняет \n в середине, поэтому переводим только куски без \n)
    per_file = {}
    eidx = ridx = None
    seg_set = set()
    pending_rows = 0
    for src, _ in sources:
        rows = load_rows(src)
        per_file[src] = rows
        h = rows[0]; ei = h.index("English"); ri = h.index("Russian")
        eidx, ridx = ei, ri
        for r in rows[1:]:
            if len(r) <= ri or not is_pending(r[ei], r[ri]) or not has_text(r[ei]):
                continue
            pending_rows += 1
            for seg in r[ei].split("\\n"):
                if has_text(seg):
                    seg_set.add(seg)

    cache = load_cache()
    todo = [s for s in seg_set if s not in cache]
    print("Строк к переводу: %d | уник. сегментов: %d | в кэше: %d | осталось: %d"
          % (pending_rows, len(seg_set), len(seg_set) - len(todo), len(todo)),
          flush=True)
    if dry:
        print("Google (через Lingva) доступен:",
              "да" if _probe() else "НЕТ (сеть/зеркала)")
        return

    try:
        if todo:
            run_units(cache, todo, "сегменты")
        print("Перевод завершён.", flush=True)
    except KeyboardInterrupt:
        print("\nПрервано вами. Записываю то, что уже переведено…", flush=True)
    except GiveUp:
        print("Блокировка затянулась. Записываю переведённое; запустите позже ещё раз.",
              flush=True)
    finally:
        save_cache(cache)

    apply_all(per_file, sources, eidx, ridx, cache)


def _probe():
    try:
        return gt("ping", retries=1) is not None
    except Blocked:
        return False


def apply_all(per_file, sources, ei, ri, cache):
    print("\nЗаписываю перевод в файлы…", flush=True)
    tot_applied = tot_bad = tot_still = 0
    for src, mirror in sources:
        rows = per_file[src]
        applied = bad = 0
        for r in rows[1:]:
            if len(r) <= ri or not is_pending(r[ei], r[ri]) or not has_text(r[ei]):
                continue
            ru = render(r[ei], cache)
            if ru is None:
                continue
            if not verify(r[ei], ru):            # подстраховка — не пишем кривое
                bad += 1; continue
            r[ri] = ru; applied += 1
        rel = os.path.relpath(src, HERE)
        if applied == 0:
            print("  %-68s без изменений" % rel, flush=True)
            continue
        if not os.path.exists(src + ".bak"):
            shutil.copyfile(src, src + ".bak")
        with open(src, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh, quoting=csv.QUOTE_MINIMAL, lineterminator="\n").writerows(rows)
        still = sum(1 for r in rows[1:] if len(r) > ri
                    and is_pending(r[ei], r[ri]) and has_text(r[ei]))
        print("  %-68s записано %d | кривых %d | осталось %d"
              % (rel, applied, bad, still), flush=True)
        if mirror and os.path.isfile(mirror):
            shutil.copyfile(src, mirror)
            print("     зеркало -> %s" % os.path.relpath(mirror, HERE), flush=True)
        tot_applied += applied; tot_bad += bad; tot_still += still

    print("\nИТОГО: записано %d | кривых (пропущено) %d | осталось непереведённых %d"
          % (tot_applied, tot_bad, tot_still), flush=True)
    if tot_still:
        print("→ осталось из-за блокировки/обрыва — просто запустите скрипт ещё раз.",
              flush=True)
    print("Готово. Запустите игру и проверьте диалоги (F1 / разговоры с NPC).", flush=True)


if __name__ == "__main__":
    main()
