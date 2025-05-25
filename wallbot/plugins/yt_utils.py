import os
import requests
from bs4 import BeautifulSoup
from pyrogram.types import Message


def fetch_download_options(video_url):
    session = requests.Session()
    post_url = "https://ssyoutube.online/"
    detail_url = "https://ssyoutube.online/yt-video-detail/"

    session.post(post_url, data={"videoURL": video_url}, timeout=10)
    res = session.get(detail_url, timeout=10)

    soup = BeautifulSoup(res.text, "html.parser")
    rows = soup.find_all("tr")
    results = []

    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 3:
            fmt_tag = cols[0].get_text(strip=True)
            size_tag = cols[1].get_text(strip=True)
            btn = cols[2].find("button")
            if btn and btn.has_attr("data-url"):
                results.append({
                    "format": fmt_tag,
                    "size": size_tag,
                    "url": btn["data-url"],
                    "ext": "mp4" if "video" in fmt_tag.lower() else "m4a"
                })
    return results

def send_file_with_thumbnail(client, message: Message, url: str, filename: str):
    thumb_path = "thumb.jpg"
    if not os.path.exists(thumb_path):
        thumb_path = None

    message.edit_text("⬇️ Downloading...")
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    message.reply_document(
        document=filename,
        thumb=thumb_path,
        file_name=filename,
        caption=f"`{filename}`"
    )
    os.remove(filename)
