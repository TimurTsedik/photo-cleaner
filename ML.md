# Photo Orientation ML Pipeline Plan

## Goal

Build a robust semi-automatic orientation detection system for legacy photo archives where:

* EXIF orientation is missing
* EXIF orientation is incorrect
* old cameras and phones produced physically rotated JPEGs
* manual review of tens of thousands of photos is impractical

The system must:

* operate locally
* support large archives
* avoid destructive operations
* provide confidence-based predictions
* minimize false positives
* support manual review for uncertain cases

---

# High-Level Strategy

Instead of trying to infer orientation heuristically using:

* OpenCV face detection
* EXIF metadata
* generic VLMs
* OCR only

we train a dedicated orientation classifier.

The problem becomes:

```text
image -> upright / rotate90 / rotate270
```

This is a standard supervised image classification task.

---

# Why This Approach Is Better

## Traditional Heuristics Fail

### EXIF Orientation

Problems:

* viewers already auto-correct orientation
* EXIF may be absent
* EXIF may be wrong
* EXIF != visually incorrect image

### Face Detection

Problems:

* many images contain no faces
* weak on low-resolution images
* weak on side faces
* weak on dark scenes
* weak on landscapes

### Vision LLMs

Problems:

* inconsistent
* expensive
* hallucinate
* difficult to batch process
* difficult to calibrate confidence

---

# Core ML Idea

We create a synthetic orientation dataset.

For every trusted upright image:

```text
original -> class 0
rotate90 -> class 90
rotate270 -> class 270
```

This allows generating large supervised datasets automatically.

---

# Pipeline Overview

## Phase 1 — Build Trusted Upright Dataset

## Objective

Collect a clean set of correctly oriented photos.

---

## Trusted Sources

### Preferred Sources

* Canon EOS 5D Mark II
* manually verified folders
* RAW-derived JPEGs
* folders already visually inspected

### Avoid Initially

* old phone cameras
* damaged scans
* screenshots
* memes
* collages
* images with uncertain orientation

---

## Requirements

Trusted dataset should:

* contain only upright images
* avoid duplicates
* contain varied scenes
* contain indoor/outdoor photos
* contain portraits and landscapes
* contain people and non-people scenes

---

## Recommended Initial Size

### Minimum

```text
2000 upright images
```

### Preferred

```text
5000-10000 upright images
```

---

# Phase 2 — Dataset Generation

## Objective

Generate labeled rotated copies automatically.

---

## Dataset Structure

```text
dataset/
    train/
        0/
        90/
        270/

    val/
        0/
        90/
        270/

    test/
        0/
        90/
        270/
```

---

## Critical Rule — No Leakage

This is extremely important.

Never allow:

```text
IMG_0001 original -> train
IMG_0001 rotate90 -> validation
```

This creates data leakage.

---

## Correct Splitting

Split by ORIGINAL IMAGE before augmentation.

Example:

```text
IMG_0001
    original
    rotate90
    rotate270
```

All variants must belong to:

* train only
* OR validation only
* OR test only

---

## Dataset Generation Steps

### Step 1

Normalize source images.

Apply:

```text
ImageOps.exif_transpose
```

before saving dataset images.

This guarantees upright ground truth.

---

### Step 2

Resize images.

Recommended:

```text
224x224
```

Reason:

* EfficientNet default
* lower VRAM usage
* faster training

---

### Step 3

Generate classes.

### Class 0

```text
upright image
```

### Class 90

```text
rotate clockwise 90
```

### Class 270

```text
rotate clockwise 270
```

---

## Recommended Storage Format

```text
JPEG quality 90-95
```

---

# Phase 3 — Model Selection

## Recommended First Model

### EfficientNet-B0

Reasons:

* lightweight
* strong accuracy
* fast inference
* small VRAM usage
* excellent transfer learning support

---

## Alternative Models

### ResNet18

Pros:

* simpler
* fast
* robust baseline

Cons:

* slightly weaker

---

### ConvNeXt-Tiny

Pros:

* stronger modern backbone

Cons:

* heavier
* slower

---

## Initial Recommendation

Start with:

```text
EfficientNet-B0
```

---

# Phase 4 — Training

## Framework

Recommended:

```text
PyTorch
```

---

## Input

```text
224x224 RGB image
```

---

## Output Classes

```text
0
90
270
```

---

## Loss Function

```text
CrossEntropyLoss
```

---

## Optimizer

```text
AdamW
```

---

## Metrics

### Primary

```text
validation accuracy
```

### Important

```text
confidence calibration
```

because the system will rely on confidence thresholds.

---

## Data Augmentation

Recommended:

* brightness changes
* contrast changes
* JPEG compression
* noise
* blur
* slight crops

Do NOT use:

```text
random rotations
```

because rotation is the target label.

---

## Batch Size

Suggested:

```text
32
```

Adjust depending on GPU VRAM.

---

## Epochs

Suggested:

```text
10-30
```

Use early stopping.

---

# Phase 5 — Evaluation

## Objective

Measure real-world usefulness.

---

## Build Manual Evaluation Set

Create:

```text
200-500 manually verified problematic images
```

from:

* old phones
* Sony cameras
* Nikon cameras
* broken EXIF images
* legacy exports

---

## Evaluate Separately

### Overall Accuracy

### High-Confidence Accuracy

This is the most important metric.

---

## Desired Result

Example:

```text
all predictions: 82%
confidence > 0.95: 98%
```

This would already be very useful.

---

# Phase 6 — Inference Pipeline

## Objective

Run model on archive candidates.

---

## Candidate Selection

Do NOT run on entire archive initially.

Prefer:

* suspicious cameras
* folders with known problems
* JPEGs only
* no trusted cameras

---

## Inference Output

Example:

```json
{
  "path": "IMG_1234.JPG",
  "prediction": 90,
  "probabilities": {
    "0": 0.02,
    "90": 0.96,
    "270": 0.02
  },
  "confidence": 0.96
}
```

---

## Confidence Filtering

Only auto-suggest if:

```text
max_probability >= 0.95
```

AND:

```text
margin_between_top1_and_top2 >= 0.25
```

Everything else goes to manual review.

---

# Phase 7 — Manual Review UI

## Objective

Minimize human work.

---

## UI Features

### Show

* original image
* suggested orientation
* confidence
* camera model
* folder

---

## Keyboard Workflow

Suggested:

```text
A = accept
R = reject
S = skip
G = apply to group
```

---

## Grouping

Very important optimization.

Group by:

* camera model
* date folder
* filename prefix
* sequence

Often entire bursts share same incorrect orientation.

---

# Phase 8 — Safe Operations Pipeline

## Objective

Generate reversible operations.

---

## Planned Operation Format

```json
{"op":"rotate","path":"IMG_1234.JPG","angle":90}
```

---

## Execution Strategy

### macOS

Analysis only.

### Windows

Apply operations.

---

## Rotation Method

Preferred:

```text
jpegtran lossless rotation
```

Avoid:

```text
decode/re-encode JPEG
```

because it degrades image quality.

---

## EXIF Handling

After rotation:

```text
normalize pixels
set EXIF Orientation = 1
```

---

# Recommended Project Commands

## Dataset

```bash
python -m photo_cleaner build-orientation-dataset
```

---

## Training

```bash
python -m photo_cleaner train-orientation-model
```

---

## Inference

```bash
python -m photo_cleaner predict-orientation
```

---

## Report Generation

```bash
python -m photo_cleaner build-orientation-ml-report
```

---

## Apply Operations

```bash
python -m photo_cleaner apply --dry-run
python -m photo_cleaner apply
```

---

# Recommended Development Order

## Step 1

Build trusted upright dataset.

---

## Step 2

Implement dataset generator.

---

## Step 3

Train EfficientNet-B0 baseline.

---

## Step 4

Build evaluation set.

---

## Step 5

Measure confidence calibration.

---

## Step 6

Generate prediction report.

---

## Step 7

Implement review UI.

---

## Step 8

Implement safe apply pipeline.

---

# Critical Risks

## 1. Dataset Contamination

If upright dataset contains rotated images:

```text
model learns incorrect orientation
```

This is the biggest risk.

---

## 2. Distribution Shift

Training on:

```text
Canon DSLR photos
```

and inferring on:

```text
2003 phone camera JPEGs
```

may reduce quality.

---

## 3. Ambiguous Images

Some images are fundamentally ambiguous.

Examples:

* walls
* carpets
* sky
* close-up objects
* abstract scenes

System must allow:

```text
unknown / low confidence
```

instead of forcing predictions.

---

# Realistic Expectations

This system will likely NOT achieve:

```text
100% automatic orientation fixing
```

A realistic production-quality target:

```text
40-70% of problematic images auto-resolved
remaining images sent to fast manual review
```

This is still extremely valuable for large archives.

---

# Final Recommendation

This ML-based approach is significantly more promising than:

* OpenCV heuristics
* EXIF-only logic
* generic VLM prompting
* OCR-only methods

because:

* the task is naturally classifiable
* synthetic dataset generation is easy
* labels are cheap
* inference is fast
* confidence scoring is possible
* system can be calibrated conservatively

The correct objective is NOT:

```text
fully automatic orientation fixing
```

The correct objective is:

```text
high-confidence semi-automatic archive correction system
```
