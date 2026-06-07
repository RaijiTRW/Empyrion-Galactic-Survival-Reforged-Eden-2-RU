#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Добивает «упрямые» строки, которые не прошли обычный перевод.

Эти строки содержат форматирование ВНУТРИ предложения (<i>слово</i>, @w1 в
середине, инлайновый <color>). Google переставляет слова в русском, и вернуть
такие теги на место нельзя. Здесь мы переводим текст, но ВНУТРЕННЕЕ
форматирование убираем (внешние теги и {подстановки} сохраняем). Теряется лишь
курсив/цвет на отдельных словах — зато строка переводится, а не остаётся англ.

Запуск:  python3 finish_residue.py
"""
import importlib.util, csv, re, os, shutil

spec = importlib.util.spec_from_file_location("td", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "translate_dialogues.py"))
td = importlib.util.module_from_spec(spec); spec.loader.exec_module(td)
csv.field_size_limit(10_000_000)

PLACE_RE = re.compile(r"\{[^{}]*\}")                       # {PlayerName} — сохранить
DROP_RE = re.compile(r"</?[A-Za-z][^<>]*>|\[/?[A-Za-z]\]|\[-\]"
                     r"|\[[0-9A-Fa-f]{3,8}\]|@[A-Za-z]\d*")  # форматирование — убрать


def loose_translate(seg):
    lead, core, trail = td.split_edges(seg)
    ph = []
    def keep(m):
        ph.append(m.group(0)); return chr(0xE000 + len(ph) - 1)
    plain = DROP_RE.sub("", PLACE_RE.sub(keep, core))
    plain = re.sub(r"\s+", " ", plain).strip()
    if not any(c.isalpha() for c in plain):
        return None
    s = " %s " % td.SEP
    out = td.gt(s + plain + s)
    mid = None
    if out is not None:
        pieces = out.split(td.SEP)
        if len(pieces) == 3:
            mid = pieces[1].strip()
    if mid is None:                       # без обрамления как запасной путь
        out = td.gt(plain)
        mid = out.strip() if out else None
    if not mid:
        return None
    for i, p in enumerate(ph):
        mid = mid.replace(chr(0xE000 + i), p)
    ru = lead + mid + trail
    # мягкая проверка: нет мусора, скобки/подстановки целы, текст изменился
    if td.PUA_RE.search(ru) or td.SEP in ru:
        return None
    if ru.count("[") != seg.count("[") or ru.count("]") != seg.count("]"):
        return None
    if sorted(PLACE_RE.findall(seg)) != sorted(PLACE_RE.findall(ru)):
        return None
    return ru if ru.strip() != seg.strip() else None


def render_loose(en, segcache):
    out, any_tr = [], False
    for p in en.split("\\n"):
        if td.has_text(p) and p in segcache:
            out.append(segcache[p]); any_tr = True
        else:
            out.append(p)
    ru = "\\n".join(out)
    return ru if (any_tr and ru != en) else None


def main():
    sources = [(s, m) for s, m in td.FILES if os.path.isfile(s)]
    # собрать остаточные сегменты
    segset = set()
    per_file = {}
    for src, _ in sources:
        rows = list(csv.reader(open(src, newline="", encoding="utf-8-sig")))
        per_file[src] = rows
        h = rows[0]; ei = h.index("English"); ri = h.index("Russian")
        for r in rows[1:]:
            if len(r) > ri and td.is_pending(r[ei], r[ri]) and td.has_text(r[ei]):
                for p in r[ei].split("\\n"):
                    if td.has_text(p):
                        segset.add(p)
    print("упрямых сегментов к добивке:", len(segset), flush=True)

    segcache = {}
    done = fail = 0
    for s in segset:
        try:
            r = loose_translate(s)
        except td.Blocked:
            print("блокировка зеркал — подождите и запустите снова"); break
        if r is None:
            fail += 1
        else:
            segcache[s] = r; done += 1
        if (done + fail) % 10 == 0:
            print("  обработано %d/%d (удачно %d)" % (done + fail, len(segset), done),
                  flush=True)

    # применить
    ei = per_file[sources[0][0]][0].index("English")
    ri = per_file[sources[0][0]][0].index("Russian")
    total = 0
    for src, mirror in sources:
        rows = per_file[src]
        applied = 0
        for r in rows[1:]:
            if len(r) > ri and td.is_pending(r[ei], r[ri]) and td.has_text(r[ei]):
                ru = render_loose(r[ei], segcache)
                if ru is not None:
                    r[ri] = ru; applied += 1
        if applied:
            if not os.path.exists(src + ".bak"):
                shutil.copyfile(src, src + ".bak")
            with open(src, "w", newline="", encoding="utf-8") as fh:
                csv.writer(fh, quoting=csv.QUOTE_MINIMAL,
                           lineterminator="\n").writerows(rows)
            if mirror and os.path.isfile(mirror):
                shutil.copyfile(src, mirror)
            print("  %s: дописано %d" % (os.path.relpath(src, td.HERE), applied))
        total += applied
    print("ИТОГО добито строк: %d | сегментов не поддалось: %d" % (total, fail))


if __name__ == "__main__":
    main()
