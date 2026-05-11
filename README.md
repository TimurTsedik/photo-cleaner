# photo-cleaner

Утилита для сканирования архива фотографий (SQLite), отчётов по дубликатам и **ML-пайплайна ориентации** для камеры Canon EOS 5D Mark II: сборка датасета из «доверенных» JPEG с `EXIF Orientation = 1`, обучение EfficientNet-B0, инференс с порогами `confidence`/`margin`, HTML-отчёт с превью и рекомендуемым действием (`keep` / `rotate90` / `rotate270` / `manual_review`).

Кандидаты на ML-отчёт и инференс — только JPEG **без тега ориентации в БД** (`exifOrientation IS NULL`), т.е. когда при сканировании ориентация в метаданных не была определена.

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Конфигурация

В `config.yaml` блок `orientation.ml` задаёт:

- `datasetCameraModel` — модель камеры для обучающей выборки (по умолчанию `Canon EOS 5D Mark II`);
- `datasetRoot`, `checkpointPath`, `metricsPath`;
- `trainRatio` / `valRatio` / `randomSeed`;
- `imageSize`, `batchSize`, `epochs`, `learningRate`, `device` (`mps` на Apple Silicon, иначе `cpu`), `numWorkers`;
- `confidenceThreshold`, `marginThreshold` (по умолчанию `0.95` и `0.25` как в `ML.md`).

## Команды CLI

Из корня проекта (после активации venv):

| Команда | Назначение |
|--------|------------|
| `python -m photo_cleaner train-orientation-model --config config.yaml` | Обучение EfficientNet-B0, checkpoint и `metrics.json` |

## Веб-панель управления

Основной режим работы запускается без команды:

```bash
python -m photo_cleaner --config config.yaml
```

Откроется локальная панель управления с кнопками:
- сканировать архив;
- собрать дубликаты (хэширование + `duplicates.html`);
- найти кандидатов на разворот (`orientation_ml.html`);
- открыть каждый отчёт принудительно в новой вкладке.

Порядок работы в панели: `scan` → `собрать дубликаты` → `найти кандидатов на разворот`. До ручной проверки не выполняйте массовый автоповорот файлов.

## Тесты

```bash
source .venv/bin/activate
python -m unittest discover -s tests -p "test_*.py" -v
```

## Калибровка порогов

На выборке ручной разметки подстройте `confidenceThreshold` и `marginThreshold` в `orientation.ml`, чтобы снизить ложные срабатывания; неуверенные случаи должны попадать в `manual_review`.
