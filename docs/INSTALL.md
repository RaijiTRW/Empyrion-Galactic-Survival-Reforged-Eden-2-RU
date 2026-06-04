# Подробная установка

## Steam

Обычно игра находится здесь:

```text
Steam/steamapps/common/Empyrion - Galactic Survival/
```

Сценарии находятся здесь:

```text
Empyrion - Galactic Survival/Content/Scenarios/
```

В этой папке могут быть только стандартные сценарии игры. Если Reforged Eden 2 установлен через Steam Workshop, папки `Reforged Eden 2` здесь может не быть.

Локальная папка сценария после ручного копирования обычно выглядит так:

```text
Empyrion - Galactic Survival/Content/Scenarios/Reforged Eden 2/
```

## Steam Workshop

Если Reforged Eden 2 установлен через Workshop, Steam хранит исходные файлы сценария в папке Workshop:

```text
Steam/steamapps/workshop/content/383120/
```

`383120` - это Steam App ID игры Empyrion - Galactic Survival.

Папка Reforged Eden 2 обычно называется числовым Workshop ID:

```text
Steam/steamapps/workshop/content/383120/3143225812/
```

Если папки `3143225812` нет, найдите нужную папку так:

1. Откройте `Steam/steamapps/workshop/content/383120/`.
2. Отсортируйте папки по дате изменения.
3. Откройте свежие папки и проверьте файл `description.txt`.
4. Нужная папка должна относиться к `Reforged Eden 2`.

## Куда ставить русификатор

Есть два рабочих варианта.

### Вариант 1: прямо в Workshop-папку

Скопируйте файлы русификатора в:

```text
Steam/steamapps/workshop/content/383120/3143225812/
```

Минус: Steam может перезаписать эти файлы после обновления Workshop-мода.

### Вариант 2: локальная копия сценария

Скопируйте папку:

```text
Steam/steamapps/workshop/content/383120/3143225812/
```

в:

```text
Steam/steamapps/common/Empyrion - Galactic Survival/Content/Scenarios/Reforged Eden 2/
```

После этого ставьте русификатор в локальную копию сценария. Этот вариант удобнее, если нужно зафиксировать версию мода и не зависеть от автообновлений Steam Workshop.

Если после установки часть текста осталась на английском:

1. Проверьте папку сценария в `Content/Scenarios/`.
2. Проверьте папку Workshop-сценария в `steamapps/workshop/content/383120/`.
3. Проверьте папку нужного сохранения в `Saves/Games/`.
4. Скопируйте PDA-файлы русификатора в папку сохранения, если игра уже была начата до установки перевода.

## Epic Games / ручная установка

Путь к игре отличается, но внутренняя структура такая же:

```text
Empyrion - Galactic Survival/Content/
Empyrion - Galactic Survival/Saves/Games/
```

Скопируйте файлы русификатора в соответствующие папки внутри установленной игры.

## Проверка

После установки:

1. Запустите игру.
2. Выберите русский язык в настройках игры, если он еще не выбран.
3. Запустите Reforged Eden 2.
4. Проверьте PDA, описания предметов, задания и диалоги.
