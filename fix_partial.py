#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Дотягивает НЕпереведённые куски ВНУТРИ частично переведённых строк.

Сравниваем английскую и русскую колонки посегментно (по \n). Где русский
сегмент = английскому И там связный текст (несколько слов) — переводим. Эти
куски обычно не прошли из-за тегов ВНУТРИ предложения (<i>слово</i>, @w1, цвет),
поэтому внутреннее форматирование убираем (внешние теги и {подстановки} храним),
а переводим пакетами по чистому тексту — быстро и почти без сбоев.

Имена/пути/идентификаторы (без пробела между словами) не трогаем.
"""
import importlib.util, csv, re, os, shutil, time, random


def _load(name, fn):
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), fn)
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


td = _load("td", "translate_dialogues.py")
csv.field_size_limit(10_000_000)

PROSE = re.compile(r"[A-Za-z]\s+[A-Za-z]")
CYR = re.compile(r"[А-Яа-яЁё]")
PLACE = re.compile(r"\{[^{}]*\}")
DROP = re.compile(r"</?[A-Za-z][^<>]*>|\[/?[A-Za-z]\]|\[-\]"
                  r"|\[[0-9A-Fa-f]{3,8}\]|@[A-Za-z]\d*")


def is_prose(seg):
    return bool(PROSE.search(td.TOKEN_RE.sub("", seg)))


def prep(seg):
    """seg -> (lead, trail, placeholders, plain_text_to_translate)."""
    lead, core, trail = td.split_edges(seg)
    ph = []
    def keep(m):
        ph.append(m.group(0)); return chr(0xE000 + len(ph) - 1)
    plain = DROP.sub("", PLACE.sub(keep, core))
    plain = re.sub(r"\s+", " ", plain).strip()
    return lead, trail, ph, plain


def finalize(seg, prepd, mid):
    lead, trail, ph, _ = prepd
    for k, p in enumerate(ph):
        mid = mid.replace(chr(0xE000 + k), p)
    ru = lead + mid.strip() + trail
    if td.PUA_RE.search(ru) or td.SEP in ru:
        return None
    if ru.count("[") != seg.count("[") or ru.count("]") != seg.count("]"):
        return None
    if sorted(PLACE.findall(seg)) != sorted(PLACE.findall(ru)):
        return None
    if not CYR.search(ru) or ru.strip() == seg.strip():
        return None
    return ru


def main():
    sources = [(s, m) for s, m in td.FILES if os.path.isfile(s)]
    need = set()
    files_rows = {}
    for src, _ in sources:
        rows = list(csv.reader(open(src, newline="", encoding="utf-8-sig")))
        files_rows[src] = rows
        h = rows[0]; ei = h.index("English"); ri = h.index("Russian")
        for r in rows[1:]:
            if len(r) <= ri or not r[ei].strip():
                continue
            es = r[ei].split("\\n"); rs = r[ri].split("\\n")
            if len(es) != len(rs):
                continue
            for e, rr in zip(es, rs):
                if td.has_text(e) and e.strip() == rr.strip() and is_prose(e):
                    need.add(e)
    print("сегментов-прозой к доводке:", len(need), flush=True)

    preps = {s: prep(s) for s in need}
    items = sorted([s for s in need if any(c.isalpha() for c in preps[s][3])],
                   key=lambda s: len(preps[s][3]))
    cache = {}
    done = fail = 0

    def do_group(group):
        nonlocal done, fail
        if not group:
            return
        if len(group) == 1:
            s = group[0]
            out = td.gt(preps[s][3])
            ru = finalize(s, preps[s], out.strip()) if out else None
            if ru: cache[s] = ru; done += 1
            else: fail += 1
            return
        sp = " %s " % td.SEP
        out = td.gt(sp + sp.join(preps[s][3] for s in group) + sp)
        pieces = out.split(td.SEP) if out else []
        if out is None or len(pieces) != len(group) + 2:
            mid = len(group) // 2                 # делим пополам
            do_group(group[:mid]); do_group(group[mid:])
            return
        for s, piece in zip(group, pieces[1:-1]):
            ru = finalize(s, preps[s], piece.strip())
            if ru: cache[s] = ru; done += 1
            else: fail += 1

    i = 0
    while i < len(items):
        group, chars = [], 0
        while i < len(items) and len(group) < 40 and chars < 2000:
            group.append(items[i]); chars += len(preps[items[i]][3]) + 4; i += 1
        while True:
            try:
                do_group(group); break
            except td.Blocked:
                if not td.wait_block(cache):
                    print("блокировка — применю что есть, запустите снова"); i = len(items); break
        print("  %d/%d (готово %d)" % (done + fail, len(items), done), flush=True)
        time.sleep(0.4 + random.random() * 0.4)

    # применить
    ei = files_rows[sources[0][0]][0].index("English")
    ri = files_rows[sources[0][0]][0].index("Russian")
    total = 0
    for src, mirror in sources:
        rows = files_rows[src]; changed = 0
        for r in rows[1:]:
            if len(r) <= ri or not r[ei].strip():
                continue
            es = r[ei].split("\\n"); rs = r[ri].split("\\n")
            if len(es) != len(rs):
                continue
            new = list(rs); hit = False
            for k, (e, rr) in enumerate(zip(es, rs)):
                if e.strip() == rr.strip() and e in cache:
                    new[k] = cache[e]; hit = True
            if hit:
                r[ri] = "\\n".join(new); changed += 1
        if changed:
            if not os.path.exists(src + ".bak2"):
                shutil.copyfile(src, src + ".bak2")
            with open(src, "w", newline="", encoding="utf-8") as fh:
                csv.writer(fh, quoting=csv.QUOTE_MINIMAL,
                           lineterminator="\n").writerows(rows)
            if mirror and os.path.isfile(mirror):
                shutil.copyfile(src, mirror)
            print("  %s: исправлено строк %d" % (os.path.relpath(src, td.HERE), changed))
        total += changed
    print("ИТОГО исправлено строк: %d | сегментов не поддалось: %d" % (total, fail))


if __name__ == "__main__":
    main()
