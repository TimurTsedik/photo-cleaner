import base64
import json
import time
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib import error, request

from PIL import Image, ImageDraw


class FaceOrientationDetector:
    def __init__(
        self,
        in_options: dict[str, Any] | None = None,
    ) -> None:
        self._options = self._buildOptions(in_options)
        self._debugDumpDone = False

    def detectBestRotation(
        self,
        in_imagePath: Path,
    ) -> dict[str, Any]:
        ret: dict[str, Any] = {
            "suggestedRotation": None,
            "confidence": 0.0,
            "scores": {},
            "decisionReason": "no_confident_signal",
            "model": self._options["model"],
            "rawRotation": None,
            "rawChoice": "",
            "rawReason": "",
        }

        imageB64 = self._encodeCompareImageForModel(in_imagePath)

        if imageB64 is None:
            ret["decisionReason"] = "image_load_failed"
        else:
            responsePayload = self._requestModel(imageB64)
            modelDecision = self._parseModelDecision(responsePayload)

            if modelDecision is None:
                ret["decisionReason"] = "model_parse_failed"
            else:
                ret["rawRotation"] = modelDecision["rotation"]
                ret["rawChoice"] = modelDecision["choice"]
                ret["rawReason"] = modelDecision["reason"]
                ret["confidence"] = modelDecision["confidence"]

                if modelDecision["rotation"] == 0:
                    ret["decisionReason"] = "model_says_no_rotation"
                elif modelDecision["confidence"] < self._options["minConfidence"]:
                    ret["decisionReason"] = "low_confidence"
                else:
                    ret["decisionReason"] = "openrouter_vision"
                    ret["suggestedRotation"] = modelDecision["rotation"]

        return ret

    def _buildOptions(
        self,
        in_options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        ret: dict[str, Any] = {
            "model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
            "endpoint": "https://openrouter.ai/api/v1/chat/completions",
            "apiKey": "",
            "timeoutSeconds": 120,
            "minConfidence": 0.85,
            "maxImageSide": 448,
            "comparePanelSide": 128,
            "jpegQuality": 65,
            "maxRateLimitWaitSeconds": 15,
            "maxRateLimitRetries": 1,
            "debugDumpEnabled": False,
            "debugDumpDir": "./workspace/debug",
            "allowedRotations": [0, 90, 270],
            "prompt": (
                "You receive one comparison image with three variants of the same photo: "
                "A, B, C. A is original (0), B is rotated clockwise (90), "
                "C is rotated counterclockwise (270). "
                "Choose the best upright orientation by visual cues: "
                "people/faces upright, readable text, natural horizon/vertical lines. "
                "If uncertain, prefer A and lower confidence. "
                "Return JSON only, no markdown, no extra keys: "
                "{\"choice\":\"A|B|C\",\"confidence\":0..1,\"reason\":\"short\"}. "
                "Reason must be short and concrete."
            ),
        }

        options = in_options or {}
        for key in ret:
            if key in options:
                ret[key] = options[key]

        ret["timeoutSeconds"] = int(ret["timeoutSeconds"])
        ret["minConfidence"] = float(ret["minConfidence"])
        ret["maxImageSide"] = int(ret["maxImageSide"])
        ret["comparePanelSide"] = int(ret["comparePanelSide"])
        ret["jpegQuality"] = int(ret["jpegQuality"])
        ret["maxRateLimitWaitSeconds"] = int(ret["maxRateLimitWaitSeconds"])
        ret["maxRateLimitRetries"] = int(ret["maxRateLimitRetries"])
        ret["debugDumpEnabled"] = bool(ret["debugDumpEnabled"])
        ret["debugDumpDir"] = str(ret["debugDumpDir"])
        ret["apiKey"] = str(ret["apiKey"])

        return ret

    def _encodeCompareImageForModel(
        self,
        in_imagePath: Path,
    ) -> str | None:
        ret: str | None = None

        try:
            with Image.open(in_imagePath) as image:
                image = image.convert("RGB")
                panelSide = self._options["comparePanelSide"]
                variants = [
                    ("A (0)", image),
                    ("B (90)", image.transpose(Image.Transpose.ROTATE_270)),
                    ("C (270)", image.transpose(Image.Transpose.ROTATE_90)),
                ]

                panels: list[Image.Image] = []
                for _, variantImage in variants:
                    variantCopy = variantImage.copy()
                    variantCopy.thumbnail(
                        (panelSide, panelSide),
                        Image.Resampling.LANCZOS,
                    )
                    panel = Image.new(
                        "RGB",
                        (panelSide, panelSide),
                        (25, 25, 25),
                    )
                    pasteX = (panelSide - variantCopy.width) // 2
                    pasteY = (panelSide - variantCopy.height) // 2
                    panel.paste(
                        variantCopy,
                        (pasteX, pasteY),
                    )
                    panels.append(panel)

                padding = 12
                labelHeight = 28
                canvasWidth = (padding * 4) + (panelSide * 3)
                canvasHeight = (padding * 3) + labelHeight + panelSide
                canvas = Image.new(
                    "RGB",
                    (canvasWidth, canvasHeight),
                    (12, 12, 12),
                )
                draw = ImageDraw.Draw(canvas)

                for index, (label, _) in enumerate(variants):
                    panelX = padding + (index * (panelSide + padding))
                    panelY = padding + labelHeight
                    draw.text(
                        (panelX, padding),
                        label,
                        fill=(220, 220, 220),
                    )
                    canvas.paste(
                        panels[index],
                        (panelX, panelY),
                    )

                canvas.thumbnail(
                    (
                        self._options["maxImageSide"],
                        self._options["maxImageSide"],
                    ),
                    Image.Resampling.LANCZOS,
                )
                self._dumpCompareCanvas(
                    in_canvas=canvas,
                    in_imagePath=in_imagePath,
                )
                out_buffer = BytesIO()
                canvas.save(
                    out_buffer,
                    format="JPEG",
                    quality=self._options["jpegQuality"],
                    optimize=True,
                )
                ret = base64.b64encode(out_buffer.getvalue()).decode("ascii")
        except Exception as exception:
            print(f"vision orientation load failed: {in_imagePath} -> {exception}")

        return ret

    def _dumpCompareCanvas(
        self,
        in_canvas: Image.Image,
        in_imagePath: Path,
    ) -> None:
        if not self._options["debugDumpEnabled"]:
            return

        if self._debugDumpDone:
            return

        try:
            debugDir = Path(self._options["debugDumpDir"])
            debugDir.mkdir(parents=True, exist_ok=True)
            outputPath = debugDir / f"{in_imagePath.stem}_compare.jpg"
            in_canvas.save(
                outputPath,
                format="JPEG",
                quality=self._options["jpegQuality"],
                optimize=True,
            )
            self._debugDumpDone = True
            print(f"compare debug image saved: {outputPath}")
        except Exception as exception:
            print(f"compare debug image save failed: {exception}")

    def _requestModel(
        self,
        in_imageB64: str,
    ) -> dict[str, Any] | None:
        ret: dict[str, Any] | None = None

        payload = {
            "model": self._options["model"],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": self._options["prompt"],
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{in_imageB64}",
                            },
                        },
                    ],
                }
            ],
            "response_format": {
                "type": "json_object",
            },
        }

        requestData = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
        }
        if self._options["apiKey"].strip():
            headers["Authorization"] = f"Bearer {self._options['apiKey'].strip()}"

        httpRequest = request.Request(
            self._options["endpoint"],
            data=requestData,
            headers=headers,
            method="POST",
        )

        retryAttempt = 0
        maxRetries = self._options["maxRateLimitRetries"]

        while retryAttempt <= maxRetries:
            try:
                with request.urlopen(
                    httpRequest,
                    timeout=self._options["timeoutSeconds"],
                ) as response:
                    body = response.read().decode("utf-8")
                    ret = json.loads(body)
                    break
            except error.HTTPError as exception:
                errorBody = ""
                try:
                    errorBody = exception.read().decode("utf-8")
                except Exception:
                    errorBody = ""

                if exception.code == 429:
                    waitSeconds = self._parseRateLimitWaitSeconds(
                        in_exception=exception,
                        in_errorBody=errorBody,
                    )

                    if waitSeconds <= 0:
                        print("openrouter rate limit hit, no valid reset window")
                        break

                    if waitSeconds > self._options["maxRateLimitWaitSeconds"]:
                        print(
                            "openrouter rate limit wait too long, skip request: "
                            f"wait={waitSeconds}s, "
                            f"max={self._options['maxRateLimitWaitSeconds']}s"
                        )
                        break

                    if retryAttempt >= maxRetries:
                        print("openrouter rate limit retries exhausted")
                        break

                    print(
                        "openrouter rate limit hit, waiting before retry: "
                        f"{waitSeconds}s"
                    )
                    time.sleep(waitSeconds)
                    retryAttempt += 1
                    continue

                print(f"openrouter request failed: {exception} {errorBody}")
                break
            except (error.URLError, TimeoutError, json.JSONDecodeError) as exception:
                print(f"openrouter request failed: {exception}")
                break

        return ret

    def _parseRateLimitWaitSeconds(
        self,
        in_exception: error.HTTPError,
        in_errorBody: str,
    ) -> int:
        ret = 0
        retryAfter = in_exception.headers.get("Retry-After")

        if retryAfter is not None:
            try:
                ret = max(int(float(retryAfter)), 0)
            except ValueError:
                ret = 0

        if ret <= 0 and in_errorBody:
            try:
                payload = json.loads(in_errorBody)
                metadata = payload.get("error", {}).get("metadata", {})
                headers = metadata.get("headers", {})
                resetMsRaw = headers.get("X-RateLimit-Reset")
                if resetMsRaw is not None:
                    resetEpochMs = int(str(resetMsRaw))
                    nowEpochMs = int(time.time() * 1000)
                    waitMs = max(resetEpochMs - nowEpochMs, 0)
                    ret = max((waitMs + 999) // 1000, 0)
            except (TypeError, ValueError, json.JSONDecodeError):
                ret = 0

        if ret <= 0:
            ret = 1

        return ret

    def _parseModelDecision(
        self,
        in_responsePayload: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        ret: dict[str, Any] | None = None

        if in_responsePayload is not None:
            choices = in_responsePayload.get("choices", [])
            messageData = choices[0].get("message", {}) if choices else {}
            contentValue = messageData.get("content", "{}")
            content = contentValue

            try:
                if isinstance(contentValue, list):
                    firstPart = contentValue[0] if contentValue else {}
                    content = firstPart.get("text", "{}")
                parsed = json.loads(content)
                confidence = float(parsed.get("confidence", 0.0))
                reason = str(parsed.get("reason", "")).strip()
                choice = str(parsed.get("choice", "")).strip().upper()
                choiceToRotation = {
                    "A": 0,
                    "B": 90,
                    "C": 270,
                }
                rotation = choiceToRotation.get(choice)

                if rotation is None and "rotation" in parsed:
                    fallbackRotation = int(parsed.get("rotation"))
                    if fallbackRotation in self._options["allowedRotations"]:
                        rotation = fallbackRotation
                        if fallbackRotation == 0:
                            choice = "A"
                        elif fallbackRotation == 90:
                            choice = "B"
                        elif fallbackRotation == 270:
                            choice = "C"

                if rotation in self._options["allowedRotations"]:
                    ret = {
                        "choice": choice,
                        "rotation": rotation,
                        "confidence": confidence,
                        "reason": reason,
                    }
            except (TypeError, ValueError, json.JSONDecodeError):
                ret = None

        return ret