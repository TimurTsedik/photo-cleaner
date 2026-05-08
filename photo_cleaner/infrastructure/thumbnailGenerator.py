from pathlib import Path

from PIL import Image, ImageOps, ImageFile


ImageFile.LOAD_TRUNCATED_IMAGES = True


class ThumbnailGenerator:
    def generateThumbnail(
        self,
        in_sourcePath: Path,
        in_outputPath: Path,
        in_maxSide: int,
        in_quality: int,
    ) -> bool:
        ret = False

        try:
            in_outputPath.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with Image.open(in_sourcePath) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail((in_maxSide, in_maxSide))
                image.convert("RGB").save(
                    in_outputPath,
                    "JPEG",
                    quality=in_quality,
                    optimize=True,
                )

            ret = True

        except Exception as exception:
            print(f"thumbnail failed: {in_sourcePath} -> {exception}")

        return ret