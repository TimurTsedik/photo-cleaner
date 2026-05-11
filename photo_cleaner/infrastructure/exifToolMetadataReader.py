import json
import re
import subprocess
from pathlib import Path
from typing import Any

try:
    import exifread
except ImportError:
    exifread = None


class ExifToolMetadataReader:
    def __init__(
        self,
        in_exifToolPath: str = "exiftool",
        in_timeoutSeconds: int = 10,
    ) -> None:
        self._exifToolPath = in_exifToolPath
        self._timeoutSeconds = in_timeoutSeconds
        self._isAvailable: bool | None = None
        self._isExifReadMissingWarned = False

    def readMetadata(
        self,
        in_path: Path,
    ) -> dict[str, Any]:
        ret = self._emptyMetadata()

        if self._checkAvailability():
            ret = self._mergeMetadata(
                ret,
                self._readWithExifTool(in_path),
            )

        if not self._hasAnyMetadata(ret):
            ret = self._mergeMetadata(
                ret,
                self._readWithExifRead(in_path),
            )

        return ret

    def _checkAvailability(
        self,
    ) -> bool:
        ret = False

        if self._isAvailable is None:
            try:
                process = subprocess.run(
                    [self._exifToolPath, "-ver"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self._timeoutSeconds,
                )
                self._isAvailable = process.returncode == 0
                if not self._isAvailable:
                    print("exiftool is not available, using python exifread fallback")
            except (subprocess.SubprocessError, OSError):
                self._isAvailable = False
                print("exiftool is not available, using python exifread fallback")

        ret = bool(self._isAvailable)
        return ret

    def _toInt(
        self,
        in_value: Any,
    ) -> int | None:
        ret: int | None = None

        if in_value is not None:
            try:
                ret = int(float(in_value))
            except (TypeError, ValueError):
                ret = None

        return ret

    def _pickFirst(
        self,
        in_payload: dict[str, Any],
        in_keys: tuple[str, ...],
    ) -> Any:
        ret = None

        for key in in_keys:
            if key in in_payload and in_payload[key] is not None:
                ret = in_payload[key]
                break

        return ret

    def _emptyMetadata(
        self,
    ) -> dict[str, Any]:
        ret = {
            "width": None,
            "height": None,
            "cameraModel": None,
            "exifOrientation": None,
        }
        return ret

    def _readWithExifTool(
        self,
        in_path: Path,
    ) -> dict[str, Any]:
        ret = self._emptyMetadata()
        command = [
            self._exifToolPath,
            "-j",
            "-n",
            "-Model",
            "-CameraModelName",
            "-Orientation",
            "-ImageWidth",
            "-ImageHeight",
            "-ExifImageWidth",
            "-ExifImageHeight",
            "-RawImageWidth",
            "-RawImageHeight",
            str(in_path),
        ]

        try:
            process = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeoutSeconds,
            )

            if process.returncode != 0:
                print(f"exiftool metadata failed: {in_path} -> {process.stderr.strip()}")
            else:
                payload = json.loads(process.stdout)
                firstItem = payload[0] if payload else {}

                modelValue = self._pickFirst(
                    firstItem,
                    ("Model", "CameraModelName"),
                )
                widthValue = self._pickFirst(
                    firstItem,
                    ("ImageWidth", "ExifImageWidth", "RawImageWidth"),
                )
                heightValue = self._pickFirst(
                    firstItem,
                    ("ImageHeight", "ExifImageHeight", "RawImageHeight"),
                )
                orientationValue = firstItem.get("Orientation")

                ret["cameraModel"] = str(modelValue).strip() if modelValue is not None else None
                ret["width"] = self._toInt(widthValue)
                ret["height"] = self._toInt(heightValue)
                ret["exifOrientation"] = self._toInt(orientationValue)
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exception:
            print(f"exiftool metadata failed: {in_path} -> {exception}")

        return ret

    def _readWithExifRead(
        self,
        in_path: Path,
    ) -> dict[str, Any]:
        ret = self._emptyMetadata()

        if exifread is None:
            if not self._isExifReadMissingWarned:
                print(
                    "python package exifread is not available. "
                    "Install it in project venv: .venv/bin/python -m pip install -r requirements.txt"
                )
                self._isExifReadMissingWarned = True
            return ret

        try:
            with in_path.open("rb") as fileObject:
                tags = exifread.process_file(
                    fileObject,
                    details=False,
                )

            modelValue = self._pickFirst(
                tags,
                ("Image Model", "EXIF Model"),
            )
            widthValue = self._pickFirst(
                tags,
                ("EXIF ExifImageWidth", "Image ImageWidth"),
            )
            heightValue = self._pickFirst(
                tags,
                ("EXIF ExifImageLength", "Image ImageLength"),
            )
            orientationValue = self._pickFirst(
                tags,
                ("Image Orientation", "EXIF Orientation"),
            )

            ret["cameraModel"] = str(modelValue).strip() if modelValue is not None else None
            ret["width"] = self._toInt(widthValue)
            ret["height"] = self._toInt(heightValue)
            ret["exifOrientation"] = self._toOrientation(orientationValue)
        except Exception as exception:
            print(f"exifread metadata failed: {in_path} -> {exception}")

        return ret

    def _toOrientation(
        self,
        in_value: Any,
    ) -> int | None:
        ret: int | None = None

        normalizedValue = str(in_value).strip().lower() if in_value is not None else ""
        orientationMap = {
            "horizontal (normal)": 1,
            "mirror horizontal": 2,
            "rotate 180": 3,
            "mirror vertical": 4,
            "mirror horizontal and rotate 270 cw": 5,
            "rotate 90 cw": 6,
            "mirror horizontal and rotate 90 cw": 7,
            "rotate 270 cw": 8,
        }

        if normalizedValue:
            if normalizedValue in orientationMap:
                ret = orientationMap[normalizedValue]
            else:
                matchedValue = re.search(r"\d+", normalizedValue)
                if matchedValue is not None:
                    ret = self._toInt(matchedValue.group(0))

        return ret

    def _mergeMetadata(
        self,
        in_current: dict[str, Any],
        in_new: dict[str, Any],
    ) -> dict[str, Any]:
        ret = dict(in_current)
        keys = ("width", "height", "cameraModel", "exifOrientation")

        for key in keys:
            newValue = in_new.get(key)
            if newValue is not None:
                ret[key] = newValue

        return ret

    def _hasAnyMetadata(
        self,
        in_metadata: dict[str, Any],
    ) -> bool:
        ret = (
            in_metadata.get("width") is not None or
            in_metadata.get("height") is not None or
            in_metadata.get("cameraModel") is not None or
            in_metadata.get("exifOrientation") is not None
        )
        return ret
