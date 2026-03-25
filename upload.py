"""
GitHub API로 index.html 자동 업로드
git 명령어 불필요 — Python requests만 사용
"""

import requests
import base64
import os
import sys
from config import GITHUB_TOKEN, GITHUB_USER, GITHUB_REPO, OUTPUT_DIR

def upload_to_github():
    fpath = os.path.join(OUTPUT_DIR, "index.html")

    if not os.path.exists(fpath):
        print("❌ output/index.html 파일이 없습니다. recall.py 먼저 실행하세요.")
        return False

    # 파일 읽기 → base64 인코딩
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    api_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/index.html"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    # 기존 파일 SHA 조회 (업데이트 시 필요)
    sha = None
    resp = requests.get(api_url, headers=headers)
    if resp.status_code == 200:
        sha = resp.json().get("sha")

    # 업로드 (신규 or 업데이트)
    from datetime import datetime
    payload = {
        "message": f"리콜 자동 업데이트 {datetime.now().strftime('%Y-%m-%d')}",
        "content": encoded,
    }
    if sha:
        payload["sha"] = sha

    resp = requests.put(api_url, headers=headers, json=payload)

    if resp.status_code in (200, 201):
        print(f"✅ GitHub 업로드 완료!")
        print(f"🌐 URL: https://{GITHUB_USER}.github.io/{GITHUB_REPO}")
        return True
    else:
        print(f"❌ 업로드 실패: {resp.status_code} — {resp.json().get('message')}")
        return False


if __name__ == "__main__":
    upload_to_github()
