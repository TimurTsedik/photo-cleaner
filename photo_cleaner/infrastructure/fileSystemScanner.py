import os
import time
import uuid
from pathlib import Path
from typing import Any, Protocol
from photo_cleaner.infrastructure.metadataReader import MetadataReader


class MetadataReaderProtocol(Protocol):
    def readMetadata(
        self,
        in_path: Path,
    ) -> dict[str, Any]:
        ...


def pathMatchesExcludedPrefix(
    in_candidatePath: Path,
    in_archiveRoot: Path,
    in_excludedPrefixes: list[str],
) -> bool:
    ret = False

    try:
        resolvedCandidate = in_candidatePath.resolve()
    except OSError:
        resolvedCandidate = in_candidatePath

    try:
        resolvedArchiveRoot = in_archiveRoot.resolve()
    except OSError:
        resolvedArchiveRoot = in_archiveRoot

    for rawPrefix in in_excludedPrefixes:
        prefixStr = str(rawPrefix).strip()
        if not prefixStr:
            continue

        normalizedSlashPrefix = prefixStr.replace("\\", "/")
        prefixPath = Path(normalizedSlashPrefix).expanduser()

        if prefixPath.is_absolute():
            try:
                resolvedPrefix = prefixPath.resolve()
            except OSError:
                resolvedPrefix = prefixPath

            if resolvedCandidate == resolvedPrefix:
                ret = True
                break

            try:
                resolvedCandidate.relative_to(resolvedPrefix)
                ret = True
                break
            except ValueError:
                continue
        else:
            normalizedRelativePrefix = normalizedSlashPrefix.strip("/")
            try:
                relativeCandidate = resolvedCandidate.relative_to(
                    resolvedArchiveRoot,
                )
            except ValueError:
                continue

            relativeStr = str(relativeCandidate).replace("\\", "/")
            if relativeStr == normalizedRelativePrefix:
                ret = True
                break

            if relativeStr.startswith(normalizedRelativePrefix + "/"):
                ret = True
                break

    return ret


class FileSystemScanner:
    def __init__(
        self,
        in_metadataReader: MetadataReader,
        in_rawMetadataReader: MetadataReaderProtocol | None = None,
    ) -> None:
        self._metadataReader = in_metadataReader
        self._rawMetadataReader = in_rawMetadataReader
    
    def scan(
        self,
        in_rootPath: str,
        in_jpegExtensions: set[str],
        in_rawExtensions: set[str],
        in_excludedPathPrefixes: list[str],
    ) -> list[dict[str, Any]]:
        ret: list[dict[str, Any]] = []

        rootPath = Path(in_rootPath)
        jpegExtensions = {
            str(extension).strip().lower()
            for extension in in_jpegExtensions
            if str(extension).strip()
        }
        rawExtensions = {
            str(extension).strip().lower()
            for extension in in_rawExtensions
            if str(extension).strip()
        }

        supportedExtensions = (
            jpegExtensions |
            rawExtensions
        )

        skippedDirectoryCount = 0
        scanDirectoryErrorCount = 0
        scannedFilesCount = 0
        matchedFilesCount = 0
        errorCount = 0

        print(f"scan started: {rootPath}")
        print(f"supported extensions: {sorted(supportedExtensions)}")
        if in_excludedPathPrefixes:
            print(f"excluded path prefixes: {in_excludedPathPrefixes}")

        def onWalkError(
            in_error: OSError,
        ) -> None:
            nonlocal scanDirectoryErrorCount
            scanDirectoryErrorCount += 1
            print(
                "scan directory failed: "
                f"path={getattr(in_error, 'filename', None)} "
                f"error={in_error}"
            )

        for currentRoot, dirnames, files in os.walk(
            rootPath,
            topdown=True,
            onerror=onWalkError,
        ):
            print(f"scan directory: {currentRoot}, files={len(files)}")

            beforeCount = len(dirnames)
            dirnames[:] = [
                dirnameValue
                for dirnameValue in dirnames
                if not pathMatchesExcludedPrefix(
                    Path(currentRoot) / dirnameValue,
                    rootPath,
                    in_excludedPathPrefixes,
                )
            ]
            skippedDirectoryCount += max(0, beforeCount - len(dirnames))

            for fileName in files:
                scannedFilesCount += 1

                if scannedFilesCount % 500 == 0:
                    print(
                        f"scan progress: scanned={scannedFilesCount}, "
                        f"matched={matchedFilesCount}, errors={errorCount}"
                    )

                extension = Path(fileName).suffix.lower()

                if extension not in supportedExtensions:
                    continue

                fullPath = Path(currentRoot) / fileName

                if pathMatchesExcludedPrefix(
                    fullPath,
                    rootPath,
                    in_excludedPathPrefixes,
                ):
                    continue

                try:
                    stat = fullPath.stat()

                    relativePath = str(
                        fullPath.relative_to(rootPath)
                    )

                    isRaw = extension in rawExtensions
                    isJpeg = extension in jpegExtensions
                    metadata = self._readMetadataForFile(fullPath, isRaw, isJpeg)

                    ret.append({
                        "id": str(uuid.uuid4()),
                        "relativePath": relativePath,
                        "extension": extension,
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                        "sha256": None,
                        "partialSha256": None,
                        "width": metadata["width"],
                        "height": metadata["height"],
                        "cameraModel": metadata["cameraModel"],
                        "exifOrientation": metadata["exifOrientation"],
                        "isRaw": int(isRaw),
                        "isJpeg": int(isJpeg),
                        "thumbnailPath": None,
                        "createdAt": time.time(),
                    })

                    matchedFilesCount += 1

                    if matchedFilesCount % 100 == 0:
                        print(
                            f"photos found: {matchedFilesCount}, "
                            f"last={relativePath}"
                        )

                except Exception as exception:
                    errorCount += 1
                    print(f"scan file failed: {fullPath} -> {exception}")

        print(
            f"scan finished: scanned={scannedFilesCount}, "
            f"matched={matchedFilesCount}, errors={errorCount}, "
            f"skippedDirs={skippedDirectoryCount}, walkErrors={scanDirectoryErrorCount}"
        )

        return ret

    def _readMetadataForFile(
        self,
        in_fullPath: Path,
        in_isRaw: bool,
        in_isJpeg: bool,
    ) -> dict[str, Any]:
        ret = {
            "width": None,
            "height": None,
            "cameraModel": None,
            "exifOrientation": None,
        }

        if in_isJpeg:
            ret = self._mergeMetadata(
                ret,
                self._metadataReader.readMetadata(in_fullPath),
            )

        if self._rawMetadataReader is not None:
            rawMetadata = self._rawMetadataReader.readMetadata(in_fullPath)
            ret = self._mergeMetadata(ret, rawMetadata)

            if in_isRaw and (
                rawMetadata.get("width") is None and
                rawMetadata.get("height") is None and
                rawMetadata.get("cameraModel") is None and
                rawMetadata.get("exifOrientation") is None
            ):
                print(f"raw metadata is empty: {in_fullPath}")

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
