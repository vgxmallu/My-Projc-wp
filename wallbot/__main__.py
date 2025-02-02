
from os import mkdir, path

from wallbot import wbot

if __name__ == "__main__":
    if not path.exists("cache"):
        mkdir("cache")
    wbot().run()
