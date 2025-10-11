
from os import mkdir, path
from wallbot import wbot 



if name == "main":
    if not path.exists("cache"):
        mkdir("cache")
    wbot().run()
