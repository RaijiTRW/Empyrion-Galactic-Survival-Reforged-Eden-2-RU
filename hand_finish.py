#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ручной перевод последних реплик, которые автоперевод не осилил из-за
подстановок/таймингов в середине предложения. Теги и {подстановки} сохранены
точно. Код, пути и ID-строки сознательно оставлены как есть."""
import importlib.util, csv, os, shutil

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "translate_dialogues.py")
spec = importlib.util.spec_from_file_location("td", p)
td = importlib.util.module_from_spec(spec); spec.loader.exec_module(td)
csv.field_size_limit(10_000_000)

MAP = {
 '@p4<color=#00ffff>Signal match detected! Strength {Random(5,50)}.{Random(0,9)}. Distance {Random(5,250)}ly. Heading {Random(1,359)}.{Random(0,9)}, {Random(1,359)}.{Random(0,9)}.</color>':
 '@p4<color=#00ffff>Обнаружено совпадение сигнала! Мощность {Random(5,50)}.{Random(0,9)}. Расстояние {Random(5,250)} св.лет. Курс {Random(1,359)}.{Random(0,9)}, {Random(1,359)}.{Random(0,9)}.</color>',

 'Thank you for defending our ship! By my count you helped take out {Eden_Score} bandit ships!':
 'Спасибо, что защитил наш корабль! По моим подсчётам, ты помог уничтожить {Eden_Score} бандитских кораблей!',

 "@w2Be careful, @w1black holes are typically avoided for a reason. @w1I won't lie and say this will be without danger. @w1And remember I will pay you quite well. @w2Oh and bring along some of your fancy {Loc(Item1)}s. @w1You're going to need them.":
 '@w2Будь осторожен, @w1чёрные дыры обходят стороной не просто так. @w1Не буду врать — без риска не обойдётся. @w1И помни, я заплачу тебе очень щедро. @w2Да, и прихвати свои навороченные {Loc(Item1)}. @w1Они тебе пригодятся.',

 'Complete is {Eden_Complete}':
 'Готово: {Eden_Complete}',

 'This job will be to take a time sensitive package to a {CargoFactionName} Distribution Center in their galactic faction territory.':
 'Задача — доставить срочную посылку в распределительный центр {CargoFactionName} на территории их галактической фракции.',

 '@w2See I was playing some old fashioned Galaxy Blackjack with some less than reputable mates when one of dem mentioned a mighty fine stash of some Zacosite Crystals he gone an found out in some asteroid field in{PlanetSystem}.':
 '@w2Понимаешь, играл я как-то в старый добрый «Галактический блэкджек» с не самыми порядочными приятелями, и тут один из них обмолвился о знатной заначке кристаллов закосита, которую он нашёл в каком-то поясе астероидов в{PlanetSystem}.',

 '<color=#ffae00><b>[ Prisoner Geam ]</b></color>':
 '<color=#ffae00><b>[ Заключённый Геам ]</b></color>',

 '<b><color=#4dc3ff>< UCH-002 M.S Titan Hangar Flight Control ></color></b>@w2':
 '<b><color=#4dc3ff>< UCH-002 M.S Titan — управление полётами ангара ></color></b>@w2',

 '<b><color=#4dc3ff>@q0@d0< UCH-002 M.S Titan Hangar Flight Control ></color></b>@w2':
 '<b><color=#4dc3ff>@q0@d0< UCH-002 M.S Titan — управление полётами ангара ></color></b>@w2',

 'x1 Autominer Core</u></b></color>':
 'x1 Ядро автодобытчика</u></b></color>',

 '<u><b><color=#ff00ff>x65 Dino Stew</color></b></u>':
 '<u><b><color=#ff00ff>x65 Рагу из динозавра</color></b></u>',

 '<color=#ff0000><b><u>x10 Flux Coils</u></b></color>':
 '<color=#ff0000><b><u>x10 Катушки потока</u></b></color>',
}


def main():
    # самопроверка целостности тегов в моих переводах
    for en, ru in MAP.items():
        if not td.verify(en, ru):
            print("ВНИМАНИЕ: не сходятся теги для:", repr(en[:60]))
    sources = [(s, m) for s, m in td.FILES if os.path.isfile(s)]
    ei = ri = None
    total = 0
    for src, mirror in sources:
        rows = list(csv.reader(open(src, newline="", encoding="utf-8-sig")))
        h = rows[0]; ei = h.index("English"); ri = h.index("Russian")
        changed = 0
        for r in rows[1:]:
            if len(r) <= ri or not r[ei].strip():
                continue
            es = r[ei].split("\\n"); rs = r[ri].split("\\n")
            if len(es) != len(rs):
                continue
            new = list(rs); hit = False
            for k, (e, rr) in enumerate(zip(es, rs)):
                if e.strip() == rr.strip() and e in MAP:
                    new[k] = MAP[e]; hit = True
            if hit:
                r[ri] = "\\n".join(new); changed += 1
        if changed:
            if not os.path.exists(src + ".bak3"):
                shutil.copyfile(src, src + ".bak3")
            with open(src, "w", newline="", encoding="utf-8") as fh:
                csv.writer(fh, quoting=csv.QUOTE_MINIMAL,
                           lineterminator="\n").writerows(rows)
            if mirror and os.path.isfile(mirror):
                shutil.copyfile(src, mirror)
            print("  %s: исправлено строк %d" % (os.path.relpath(src, td.HERE), changed))
        total += changed
    print("ИТОГО вручную дописано строк:", total)


if __name__ == "__main__":
    main()
