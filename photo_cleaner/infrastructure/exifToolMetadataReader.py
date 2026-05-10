import json
import subprocess
from pathlib import Path
from typing import Any


class ExifToolMetadataReader:
    def __init__(
        self,
        in_exifToolPath: str = "exiftool",
        in_timeoutSeconds: int = 10,
    ) -> None:
        self._exifToolPath = in_exifToolPath
        self._timeoutSeconds = in_timeoutSeconds
        self._isAvailable: bool | None = None

    def readMetadata(
        self,
        in_path: Path,
    ) -> dict[str, Any]:
        ret: dict[str, Any] = {
            "width": None,
            "height": None,
            "cameraModel": None,
            "exifOrientation": None,
        }

        if not self._checkAvailability():
            return ret

        command = [
            self._exifToolPath,
            "-j",
            "-n",
            "-Model",
            "-Orientation",
            "-ImageWidth",
            "-ImageHeight",
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
                return ret

            payload = json.loads(process.stdout)
            firstItem = payload[0] if payload else {}

            modelValue = firstItem.get("Model")
            widthValue = firstItem.get("ImageWidth")
            heightValue = firstItem.get("ImageHeight")
            orientationValue = firstItem.get("Orientation")

            ret["cameraModel"] = str(modelValue).strip() if modelValue is not None else None
            ret["width"] = self._toInt(widthValue)
            ret["height"] = self._toInt(heightValue)
            ret["exifOrientation"] = self._toInt(orientationValue)
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exception:
            print(f"exiftool metadata failed: {in_path} -> {exception}")

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
                    print("exiftool is not available, RAW cameraModel will be empty")
            except (subprocess.SubprocessError, OSError):
                self._isAvailable = False
                print("exiftool is not available, RAW cameraModel will be empty")

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
