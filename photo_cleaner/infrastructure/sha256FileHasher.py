import hashlib
from pathlib import Path


class Sha256FileHasher:
    def calculate(
        self,
        in_path: Path,
    ) -> str:
        ret: str

        hasher = hashlib.sha256()

        with in_path.open("rb") as file:
            while True:
                chunk = file.read(1024 * 1024)

                if not chunk:
                    break

                hasher.update(chunk)

        ret = hasher.hexdigest()

        return ret