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

        supportedExtensions = (
            in_jpegExtensions |
            in_rawExtensions
        )

        scannedFilesCount = 0
        matchedFilesCount = 0
        errorCount = 0

        print(f"scan started: {rootPath}")
        print(f"supported extensions: {sorted(supportedExtensions)}")
        if in_excludedPathPrefixes:
            print(f"excluded path prefixes: {in_excludedPathPrefixes}")

        for currentRoot, dirnames, files in os.walk(
            rootPath,
            topdown=True,
        ):
            print(f"scan directory: {currentRoot}, files={len(files)}")

            dirnames[:] = [
                dirnameValue
                for dirnameValue in dirnames
                if not pathMatchesExcludedPrefix(
                    Path(currentRoot) / dirnameValue,
                    rootPath,
                    in_excludedPathPrefixes,
                )
            ]

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

                    isRaw = extension in in_rawExtensions
                    isJpeg = extension in in_jpegExtensions

                    metadata = {
                        "width": None,
                        "height": None,
                        "cameraModel": None,
                        "exifOrientation": None,
                    }

                    if isJpeg:
                        metadata = self._metadataReader.readMetadata(fullPath)
                    elif isRaw and self._rawMetadataReader is not None:
                        metadata = self._rawMetadataReader.readMetadata(fullPath)

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
            f"matched={matchedFilesCount}, errors={errorCount}"
        )

        return ret