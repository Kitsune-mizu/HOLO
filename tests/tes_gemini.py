import os, httpx
from dotenv import load_dotenv
load_dotenv()
for m in ["gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-flash-lite-latest", "gemini-2.5-flash"]:
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json={"contents": [{"parts": [{"text": "hi"}]}]}, timeout=30)
    print(m, r.status_code, r.text[:100].replace("\n", " "))