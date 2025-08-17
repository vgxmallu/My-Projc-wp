import requests
import random
import string

def gen_pass():
        adjresp = requests.get("https://gist.githubusercontent.com/hugsy/8910dc78d208e40de42deb29e62df913/raw/eec99c5597a73f6a9240cab26965a8609fa0f6ea/english-adjectives.txt")
        adj = random.choice(adjresp.text.split('\n'))
        nounresp = requests.get("https://raw.githubusercontent.com/hugsy/stuff/main/random-word/english-nouns.txt")
        noun = random.choice(nounresp.text.split("\n"))
        num = str(random.randrange(100))
        punct = random.choice(string.punctuation)
        passw = adj + noun + num + punct
        return passw
import requests
import bs4
import re
import random
import string

async def msonescrap(query, key):
    resultlist = []
    headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://google.com"
}

    if " " in query:
        query = query.replace(' ', '+')
    try:
        resp = requests.get(f'https://malayalamsubtitles.org/?s={query}', headers=headers, timeout=10)
        soup = bs4.BeautifulSoup(resp.text, 'html.parser')
    except:
        return 'Nothing'
    
    if key == 'link':
    # select all <a> inside <h2 class="entry-title">
        title_links = soup.select("h2.entry-title a")
        resultlist = [link.get("href") for link in title_links]
        return resultlist if resultlist else 'Nothing'

    elif key == 'title':
        total_titles = soup.select("h2.entry-title a")
        resultlist = [title.text.strip() for title in total_titles]
        return resultlist if resultlist else 'Nothing'
    elif key == 'thumb':
        image_links = [a.select_one("img")["src"] for a in soup.select("article.entry") if a.select_one("img")]
        return image_links if image_links else 'Nothing'
    
    
async def remove_duplicates(titles, links):
    unique_titles = []
    unique_links = []
    for i, title in enumerate(titles):
        if title not in unique_titles:  
            unique_titles.append(title)
            unique_links.append(links[i])
    return unique_titles, unique_links   

async def sanitize_filename(filename):
    # Replace invalid characters with an underscore or remove them
    return re.sub(r'[\/:*?"<>|]', '_', filename)

async def get_filename_from_cd(response):
    """
    Extracts filename from Content-Disposition header if present.
    """
    if 'Content-Disposition' in response.headers:
        cd = response.headers['Content-Disposition']
        filename = re.findall('filename="(.+)"', cd)
        if filename:
            return filename[0]
    return None 
