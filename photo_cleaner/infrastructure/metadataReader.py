from pathlib import Path
from typing import Any

from PIL import Image, ExifTags


class MetadataReader:
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

        try:
            with Image.open(in_path) as image:
                ret["width"] = image.width
                ret["height"] = image.height

                exif = image.getexif()

                if exif:
                    tagNames = {
                        value: key
                        for key, value in ExifTags.TAGS.items()
                    }

                    modelTag = tagNames.get("Model")
                    orientationTag = tagNames.get("Orientation")

                    if modelTag:
                        ret["cameraModel"] = exif.get(modelTag)

                    if orientationTag:
                        ret["exifOrientation"] = exif.get(orientationTag)

        except Exception as exception:
            print(f"metadata failed: {in_path} -> {exception}")

        return ret