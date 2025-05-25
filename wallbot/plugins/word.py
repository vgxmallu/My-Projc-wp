import os

WORDS_FILE = "words.txt"

def load_words():
    if not os.path.exists(WORDS_FILE):
        return set()
    with open(WORDS_FILE, "r") as file:
        words = {line.strip().lower() for line in file if line.strip()}
    return words

COMMON_WORDS_FILE = "common.txt"

def load_common_words():
    if not os.path.exists(COMMON_WORDS_FILE):
        return set()
    with open(COMMON_WORDS_FILE, "r") as file:
        common_words = {line.strip().lower() for line in file if line.strip()}
    return common_words
