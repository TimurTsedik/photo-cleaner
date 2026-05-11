# photo-cleaner

`photo-cleaner` — локальный инструмент для:
- сканирования большого фотоархива в SQLite;
- поиска групп дубликатов;
- поиска и ручного подтверждения кандидатов на разворот;
- подготовки датасета и обучения модели ориентации.

Система работает через веб-панель и хранит решения в БД.  
Отчеты (`/reports/duplicates`, `/reports/orientation`) теперь динамические: страница строится из текущего состояния БД, без генерации статических `html` файлов в `workspace/reports`.

## Что хранится в БД

Основная таблица `photos` содержит:
- путь к файлу;
- размер, mtime, расширение;
- метаданные (`cameraModel`, `width`, `height`, `exifOrientation`);
- флаги `isJpeg`/`isRaw`.

Также есть таблицы действий:
- `duplicateActions` — решения по дубликатам (какой файл оставить);
- `orientationActions` — решения по ориентации (подтвержденный разворот/ручная проверка).

## Требования

- Python 3.11+ (рекомендуется 3.12/3.13).
- Рабочее виртуальное окружение `.venv`.
- Доступ к архиву, указанному в `config.yaml`.

По метаданным:
- если в системе есть `exiftool`, он используется для RAW;
- если `exiftool` нет, используется Python-пакет `exifread` (устанавливается из `requirements.txt` в `.venv`).

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Проверка установки `exifread`:

```bash
.venv/bin/python -m pip show exifread
```

## Запуск панели управления (основной режим)

```bash
python -m photo_cleaner --config config.yaml
```

После запуска откроется локальная панель:
- `Скан` — сканирование архива и заполнение `photos`;
- `Собрать дубликаты` — расчет групп дубликатов и заполнение `duplicateActions`;
- `Найти кандидатов на неверную ориентацию фото` — ML-инференс и заполнение `orientationActions`.

Рекомендуемый порядок:
1. `scan`
2. `duplicates`
3. `orientation`
4. ручная проверка в отчетах `/reports/duplicates` и `/reports/orientation`.

## Как устроены отчеты

### Дубликаты
- открываются по `/reports/duplicates`;
- каждая группа показывает recommended KEEP;
- выбор сохраняется сразу в БД через `/api/actions`.

### Ориентация
- открываются по `/reports/orientation`;
- можно принять предложенный угол или выбрать вручную (`90`/`270`/`manual`);
- подтверждения сохраняются в `orientationActions`.

## Обучение модели ориентации

Есть два шага: сборка датасета и обучение.

### 1) Сборка датасета

Команда:

```bash
.venv/bin/python -c "from photo_cleaner.operations import PhotoCleanerOperations; PhotoCleanerOperations('config.yaml').runBuildOrientationDataset()"
```

В выборку попадают:
- trusted upright фото (`exifOrientation = 1`) по `datasetCameraModel`;
- подтвержденные в UI кейсы ориентации (`status=confirmed`, `selectedRotation=90/270`) с учетом выбранного разворота.

Итоговый манифест:
- `workspace/orientation_dataset/dataset_manifest.json`.

### 2) Обучение

```bash
python -m photo_cleaner train-orientation-model --config config.yaml
```

Результаты:
- checkpoint: путь из `orientation.ml.checkpointPath`;
- метрики: путь из `orientation.ml.metricsPath`.

## Применение действий к архиву

Команды:

```bash
python -m photo_cleaner apply --config config.yaml --dry-run
python -m photo_cleaner apply --config config.yaml
python -m photo_cleaner undo-last-apply --config config.yaml --dry-run
python -m photo_cleaner undo-last-apply --config config.yaml
```

Что делает `apply`:
- читает подтвержденные действия из БД;
- для `orientationActions` вращает JPEG с `selectedRotation=90/270`;
- для `duplicateActions` переносит файлы (кроме KEEP) в `duplicates.trashDir`.

`--dry-run` только печатает план операций и ничего не меняет на диске.

`undo-last-apply`:
- откатывает последний завершенный `apply` (не dry-run) по журналу;
- восстанавливает перемещенные дубликаты обратно;
- восстанавливает JPEG из backup перед поворотом.

## Ключевые параметры `config.yaml`

### `archive`
- `root` — корень архива фотографий.

### `workspace`
- `path` — рабочая директория (БД, датасет, модели, превью).

### `files`
- `jpegExtensions` — расширения, которые сканируются как JPEG/preview-кандидаты;
- `rawExtensions` — расширения RAW/видео/доп. форматов.

### `orientation`
- `trustedCameraModels` — модели камер, считающиеся “доверенными”;
- `excludedPathPrefixes` — подпути, исключаемые из обработки;
- `candidateExtensions` — расширения кандидатов на разворот;
- `neverRotateExtensions` — форматы, которые не вращаем автоматически.

### `orientation.ml`
- `datasetCameraModel`, `datasetRoot`;
- `checkpointPath`, `metricsPath`;
- `trainRatio`, `valRatio`, `randomSeed`;
- `imageSize`, `jpegQuality`, `batchSize`, `epochs`, `learningRate`;
- `device` (`mps`/`cpu`);
- `confidenceThreshold`, `marginThreshold`.

## Тесты

Полный прогон:

```bash
source .venv/bin/activate
python -m unittest discover -s tests -p "test_*.py" -v
```

## Типичные проблемы

### 1) Не читаются RAW-метаданные
Проверь зависимости в `.venv`:

```bash
python -m pip install -r requirements.txt
```

Если нет `exiftool`, будет использован `exifread`.

### 2) KPI в панели выглядят “старыми”
- обнови страницу (hard refresh);
- убедись, что сервер запущен на актуальном коде (перезапусти панель).

### 3) В датасет попало меньше подтвержденных кейсов, чем ожидалось
Проверь в `orientationActions`:
- `status` должен быть `confirmed`;
- `selectedRotation` должен быть `90` или `270`;
- файл должен быть JPEG и попадать в `candidateExtensions`.

## Быстрые команды

Запуск панели:

```bash
python -m photo_cleaner --config config.yaml
```

Сборка датасета:

```bash
.venv/bin/python -c "from photo_cleaner.operations import PhotoCleanerOperations; PhotoCleanerOperations('config.yaml').runBuildOrientationDataset()"
```

Обучение:

```bash
python -m photo_cleaner train-orientation-model --config config.yaml
```

Применение действий:

```bash
python -m photo_cleaner apply --config config.yaml --dry-run
python -m photo_cleaner apply --config config.yaml
python -m photo_cleaner undo-last-apply --config config.yaml --dry-run
python -m photo_cleaner undo-last-apply --config config.yaml
```
