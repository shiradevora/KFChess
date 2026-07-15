from __future__ import annotations

import pathlib

import cv2
import numpy as np


class Img:
    def __init__(self):
        self.img = None

    def read(self, path: str | pathlib.Path,
             size: tuple[int, int] | None = None,
             keep_aspect: bool = False,
             interpolation: int = cv2.INTER_AREA) -> "Img":
        path = str(path)
        self.img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if self.img is None:
            raise FileNotFoundError(f"Cannot load image: {path}")

        if size is not None:
            target_w, target_h = size
            h, w = self.img.shape[:2]
            if keep_aspect:
                scale = min(target_w / w, target_h / h)
                new_w, new_h = int(w * scale), int(h * scale)
            else:
                new_w, new_h = target_w, target_h
            self.img = cv2.resize(self.img, (new_w, new_h), interpolation=interpolation)

        return self

    def draw_on(self, canvas: "Img", x: int, y: int) -> None:
        if self.img is None or canvas.img is None:
            raise ValueError("Both images must be loaded before drawing.")

        src = self._match_channels(canvas)
        h, w = src.shape[:2]
        H, W = canvas.img.shape[:2]

        x = max(0, min(x, W - w))
        y = max(0, min(y, H - h))

        roi = canvas.img[y:y + h, x:x + w]
        if src.shape[2] == 4:
            alpha = src[..., 3:4] / 255.0
            roi[..., :3] = (1 - alpha) * roi[..., :3] + alpha * src[..., :3]
            if canvas.img.shape[2] == 4:
                roi[..., 3:4] = np.maximum(roi[..., 3:4], src[..., 3:4])
        else:
            canvas.img[y:y + h, x:x + w] = src

    def _match_channels(self, canvas: "Img"):
        sc, cc = self.img.shape[2], canvas.img.shape[2]
        if sc == cc:
            return self.img
        if sc == 3 and cc == 4:
            return cv2.cvtColor(self.img, cv2.COLOR_BGR2BGRA)
        if sc == 4 and cc == 3:
            return cv2.cvtColor(self.img, cv2.COLOR_BGRA2BGR)
        return self.img

    def put_text(self, txt, x, y, font_size, color=(255, 255, 255, 255), thickness=1):
        if self.img is None:
            raise ValueError("Image not loaded.")
        cv2.putText(self.img, txt, (x, y),
                    cv2.FONT_HERSHEY_SIMPLEX, font_size, color, thickness, cv2.LINE_AA)
