"""Minimal Meta Graph API client: Instagram Story + Facebook Page photo Story."""
import time

import requests


class MetaError(RuntimeError):
    pass


class Meta:
    def __init__(self, token: str, ig_user_id: str, page_id: str, version: str = "v21.0"):
        self.token, self.ig, self.page = token, ig_user_id, page_id
        self.base = f"https://graph.facebook.com/{version}"

    def _check(self, r: requests.Response) -> dict:
        try:
            data = r.json()
        except ValueError:
            raise MetaError(f"HTTP {r.status_code}: {r.text[:300]}")
        if r.status_code >= 400 or "error" in data:
            err = data.get("error", {})
            raise MetaError(f"{err.get('message', data)} (code {err.get('code')}, "
                            f"subcode {err.get('error_subcode')})")
        return data

    def _post(self, path, data=None, files=None):
        data = dict(data or {}, access_token=self.token)
        return self._check(requests.post(f"{self.base}/{path}", data=data, files=files, timeout=120))

    def _get(self, path, params=None):
        params = dict(params or {}, access_token=self.token)
        return self._check(requests.get(f"{self.base}/{path}", params=params, timeout=60))

    # ---- Instagram -------------------------------------------------------
    def ig_story(self, image_url: str) -> str:
        c = self._post(f"{self.ig}/media", {"media_type": "STORIES", "image_url": image_url})
        cid = c["id"]
        for _ in range(12):  # wait until the container is ready
            st = self._get(cid, {"fields": "status_code"}).get("status_code")
            if st in (None, "FINISHED"):
                break
            if st == "ERROR":
                raise MetaError("Instagram could not process the image (status ERROR)")
            time.sleep(5)
        return self._post(f"{self.ig}/media_publish", {"creation_id": cid})["id"]

    # ---- Facebook --------------------------------------------------------
    def fb_story(self, image_path: str) -> str:
        with open(image_path, "rb") as f:
            photo = self._post(f"{self.page}/photos", {"published": "false"},
                               files={"source": ("story.jpg", f, "image/jpeg")})
        res = self._post(f"{self.page}/photo_stories", {"photo_id": photo["id"]})
        return str(res.get("post_id") or res.get("id") or photo["id"])
