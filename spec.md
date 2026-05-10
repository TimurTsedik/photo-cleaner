

# Photo Cleaner

## Overview

Photo Cleaner is a local-first archive maintenance tool for large personal photo collections.

Primary goals:

1. Detect and safely remove exact duplicates.
2. Detect incorrectly oriented photos.
3. Work safely with large NTFS archives mounted on macOS.
4. Avoid destructive operations during analysis stage.
5. Support offline review through static HTML reports.

Current archive statistics:

- Archive size: ~330 GB
- Files in archive: ~22k
- Indexed media files: ~17k
- JPEG files: ~7k
- RAW files: ~5k

---

# Core Design Principles

## Safety First

The system never modifies archive files during analysis.

All stages before explicit apply:

- read-only
- deterministic
- reproducible
- reviewable

Operations are generated separately and may later be applied on another machine.

---

## Cross-Platform Workflow

Primary workflow:

### macOS

Used for:

- scanning
- indexing
- hashing
- report generation
- review
- candidate selection

The archive is mounted read-only from NTFS.

### Windows

Used for:

- actual file operations
- moving duplicates
- rotating files
- metadata normalization

This avoids:

- Paragon NTFS dependency
- risky NTFS writes from macOS
- temporary local archive copies

---

## Non-Destructive Operation Model

Planned operation format:

```json
{"op":"move","src":"a.jpg","dst":".trash/a.jpg"}
{"op":"rotate","path":"b.jpg","angle":90}
```

Operations will be stored in:

```text
workspace/operations.jsonl
```

Planned execution modes:

```bash
python -m photo_cleaner apply --dry-run
python -m photo_cleaner apply
```

---

# Current Architecture

## Technology Stack

### Language

- Python 3.12+

### Libraries

- Pillow
- OpenCV
- PyYAML
- SQLite
- NumPy

### Storage

- SQLite database
- filesystem thumbnails
- static HTML reports

---

# Current Project Structure

```text
photo_cleaner/
    infrastructure/
    services/
    domain/
    cli.py
    __main__.py

workspace/
    cleanup.db
    reports/
    thumbs/
```

---

# Current Functionality

# 1. Archive Scanning

Implemented command:

```bash
python -m photo_cleaner scan
```

Responsibilities:

- recursive archive traversal
- media filtering by extension
- metadata extraction
- EXIF extraction
- SQLite indexing

Indexed metadata:

- relative path
- file size
- extension
- image dimensions
- SHA256 hash
- camera model
- EXIF orientation

---

## Supported Formats

### JPEG-like

- .jpg
- .jpeg
- .png
- .gif
- .bmp

### RAW-like

- .cr2
- .cr3
- .crw
- .dng
- .nef
- .arw
- .tif
- .tiff

### Video

- .mov
- .mp4

---

# 2. Exact Duplicate Detection

Implemented commands:

```bash
python -m photo_cleaner hash-duplicates
python -m photo_cleaner find-duplicates
```

Detection pipeline:

## Stage 1

Group files by size.

## Stage 2

Calculate SHA256 only inside same-size groups.

## Stage 3

Group exact duplicates by identical SHA256.

---

## Current Results

The system successfully detected:

- duplicate RAW files
- duplicate JPEG files
- duplicate PNG files
- broken duplicated imports
- renamed duplicates
- encoding-corrupted duplicate names

Examples:

```text
IMG_0606.JPG
IMG_0606 (1).jpg
```

```text
Снимок 018.jpg
æ¡¿¼«¬ 018.jpg
```

---

## Duplicate Reports

Implemented command:

```bash
python -m photo_cleaner build-report
```

Features:

- static HTML report
- side-by-side duplicate review
- thumbnails
- KEEP/MOVE recommendations
- duplicate grouping

Thumbnail cache:

```text
workspace/thumbs/
```

Reports:

```text
workspace/reports/
```

---

# 3. Candidate Prioritization

Current heuristics:

Preferred KEEP candidate:

- normal filename
- original filename
- no encoding corruption
- no "(1)" or "(2)"
- shorter cleaner path

Preferred MOVE candidate:

- broken filename encoding
- duplicated import suffixes
- renamed duplicate copies

Examples:

```text
æ¡¿¼«¬ 018.jpg
```

```text
IMG_0606 (1).jpg
```

---

# 4. Face-Based Orientation Detection

Implemented experimental command:

```bash
python -m photo_cleaner build-face-orientation-report
```

Purpose:

Detect photos likely rotated incorrectly.

---

## Why EXIF-Based Detection Failed

Initial approach used:

```text
EXIF Orientation
```

This produced incorrect results because:

- EXIF orientation already fixes display
- viewers automatically apply orientation
- EXIF != 1 does not mean photo is visually wrong

Conclusion:

EXIF orientation cannot be used directly to determine incorrect rotation.

---

## Current Face-Based Approach

The system now uses OpenCV face detection.

Pipeline:

For every candidate image:

```text
original
rotate 90
rotate 270
```

The detector compares:

- number of faces
- face sizes
- detection confidence

If rotated version scores significantly higher:

```text
suggestedRotation = 90 or 270
```

---

## Current Status

Experimental.

Needs:

- tuning
- confidence calibration
- better classifiers
- OCR integration
- more heuristics

---

# Current Reports

## Duplicate Report

```text
workspace/reports/duplicates.html
```

## EXIF Orientation Report

```text
workspace/reports/orientation.html
```

Legacy experimental report.

## Face Orientation Report

```text
workspace/reports/face_orientation.html
```

Experimental face-based orientation suggestions.

---

# Current Configuration

Main config:

```text
config.yaml
```

Supports:

- archive root
- workspace path
- extension lists
- thumbnail settings
- orientation settings
- trusted camera models

---

# Known Issues

## 1. Orientation Detection

Still experimental.

Current false-positive rate is too high.

---

## 2. Face Detection

Current OpenCV Haar cascade:

- weak on side faces
- weak on low resolution
- weak on dark images

Future migration candidates:

- MediaPipe Tasks API
- RetinaFace
- YOLO face models

---

## 3. Thumbnail Errors

Some images produce:

```text
image file is truncated
```

Observed behavior:

- files still open correctly
- thumbnails still often generated

Likely caused by:

- malformed JPEG endings
- damaged EXIF blocks
- legacy camera exports

---

# Planned Features

# Phase 1

## Operations Generator

Planned command:

```bash
python -m photo_cleaner build-operations
```

Responsibilities:

- generate move operations
- generate rotate operations
- generate normalize operations
- generate trash moves

---

## Apply Engine

Planned commands:

```bash
python -m photo_cleaner apply --dry-run
python -m photo_cleaner apply
```

Responsibilities:

- execute operations.jsonl
- transactional logging
- rollback support
- operation verification

---

# Phase 2

## Lossless JPEG Rotation

Planned:

- jpegtran integration
- EXIF normalization
- orientation reset to 1

---

## OCR Orientation Detection

Planned:

- text direction analysis
- sign detection
- document orientation

Possible engines:

- Tesseract
- PaddleOCR

---

## Advanced ML Orientation Detection

Planned:

- neural orientation classifiers
- upright/down/left/right classification
- confidence-based filtering

---

# Phase 3

## RAW/JPEG Pair Management

Planned functionality:

Detect and preserve:

```text
IMG_1234.CR2
IMG_1234.JPG
```

Rules:

- never treat RAW/JPEG pair as duplicates
- optionally group pairs
- optionally separate RAW archive

---

## Web UI

Planned:

- local review server
- approve/reject operations
- operation editing
- image comparison UI
- duplicate voting

---

## Similar Image Detection

Planned:

- perceptual hashing
- resized duplicates
- edited duplicates
- burst-photo grouping

Possible approaches:

- pHash
- dHash
- CLIP embeddings

---

# Long-Term Goals

## Production-Grade Archive Maintenance System

Target characteristics:

- deterministic
- safe
- offline
- local-first
- large archive support
- static-report capable
- cross-platform
- resumable
- review-oriented

---

# Current Development Status

## Implemented

- archive scanning
- SQLite indexing
- SHA256 duplicate detection
- HTML duplicate reports
- thumbnail generation
- duplicate prioritization
- experimental orientation detection
- face-based orientation experiments

---

## In Progress

- orientation tuning
- thumbnail review UX
- operation generation
- apply pipeline

---

## Planned

- safe apply engine
- rollback support
- lossless rotation
- OCR orientation
- ML orientation detection
- perceptual duplicate detection
- full review UI