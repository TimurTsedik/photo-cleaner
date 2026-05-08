import html
from pathlib import Path
from typing import Any

from photo_cleaner.infrastructure.sqlitePhotoRepository import (
    SqlitePhotoRepository,
)
from photo_cleaner.infrastructure.thumbnailGenerator import (
    ThumbnailGenerator,
)
from photo_cleaner.services.duplicateKeepSelector import (
    DuplicateKeepSelector,
)


class HtmlDuplicateReportService:
    def __init__(
        self,
        in_repository: SqlitePhotoRepository,
        in_thumbnailGenerator: ThumbnailGenerator,
    ) -> None:
        self._repository = in_repository
        self._thumbnailGenerator = in_thumbnailGenerator
        self._keepSelector = DuplicateKeepSelector()

    def buildReport(
        self,
        in_archiveRoot: str,
        in_workspacePath: str,
        in_maxSide: int,
        in_quality: int,
    ) -> None:
        duplicateGroups = self._repository.getSha256DuplicateGroups()

        workspacePath = Path(in_workspacePath)
        thumbsPath = workspacePath / "thumbs"
        reportsPath = workspacePath / "reports"

        reportsPath.mkdir(
            parents=True,
            exist_ok=True,
        )

        htmlParts: list[str] = []

        htmlParts.append("""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Photo Cleaner — Exact Duplicates</title>
<style>
body {
    font-family: Arial, sans-serif;
    background: #111;
    color: #eee;
    margin: 24px;
}
.group {
    border: 1px solid #444;
    border-radius: 12px;
    margin-bottom: 24px;
    padding: 16px;
    background: #1b1b1b;
}
.meta {
    color: #aaa;
    font-size: 13px;
    margin-bottom: 12px;
}
.items {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
}
.item {
    width: 300px;
    border: 1px solid #333;
    border-radius: 10px;
    padding: 12px;
    background: #222;
}
.keep {
    border-color: #2f9e44;
}
.move {
    border-color: #e03131;
}
.badge {
    display: inline-block;
    padding: 4px 8px;
    border-radius: 6px;
    font-weight: bold;
    margin-bottom: 8px;
}
.badgeKeep {
    background: #2f9e44;
}
.badgeMove {
    background: #e03131;
}
img {
    max-width: 256px;
    max-height: 256px;
    display: block;
    margin-bottom: 8px;
    background: #333;
}
.path {
    font-size: 12px;
    word-break: break-all;
    color: #ddd;
}
.rawBox {
    width: 256px;
    height: 160px;
    background: #333;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #aaa;
    margin-bottom: 8px;
}
</style>
</head>
<body>
<h1>Exact duplicate report</h1>
""")

        htmlParts.append(
            f"<p>Total duplicate groups: {len(duplicateGroups)}</p>"
        )

        archiveRoot = Path(in_archiveRoot)

        for groupIndex, group in enumerate(duplicateGroups, start=1):
            keepItem = self._keepSelector.selectKeepItem(group)

            htmlParts.append('<div class="group">')
            htmlParts.append(f"<h2>Duplicate group #{groupIndex}</h2>")
            htmlParts.append(
                '<div class="meta">'
                f"sha256: {html.escape(group[0]['sha256'])}<br>"
                f"size: {group[0]['size']}"
                "</div>"
            )
            htmlParts.append('<div class="items">')

            for item in group:
                isKeep = item["id"] == keepItem["id"]
                role = "KEEP" if isKeep else "MOVE"
                cssClass = "keep" if isKeep else "move"
                badgeClass = "badgeKeep" if isKeep else "badgeMove"

                relativePath = item["relativePath"]
                sourcePath = archiveRoot / relativePath

                thumbFileName = f"{item['id']}.jpg"
                thumbPath = thumbsPath / thumbFileName
                thumbRelativePath = f"../thumbs/{thumbFileName}"

                hasThumb = False

                if Path(relativePath).suffix.lower() in {".jpg", ".jpeg"}:
                    if not thumbPath.exists():
                        hasThumb = self._thumbnailGenerator.generateThumbnail(
                            sourcePath,
                            thumbPath,
                            in_maxSide,
                            in_quality,
                        )
                    else:
                        hasThumb = True

                htmlParts.append(f'<div class="item {cssClass}">')
                htmlParts.append(
                    f'<div class="badge {badgeClass}">{role}</div>'
                )

                if hasThumb:
                    htmlParts.append(
                        f'<img src="{html.escape(thumbRelativePath)}">'
                    )
                else:
                    htmlParts.append('<div class="rawBox">RAW / no preview</div>')

                htmlParts.append(
                    f'<div class="path">{html.escape(relativePath)}</div>'
                )
                htmlParts.append("</div>")

            htmlParts.append("</div>")
            htmlParts.append("</div>")

        htmlParts.append("""
</body>
</html>
""")

        reportPath = reportsPath / "duplicates.html"

        reportPath.write_text(
            "\n".join(htmlParts),
            encoding="utf-8",
        )

        print(f"report created: {reportPath}")