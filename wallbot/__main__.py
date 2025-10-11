
from os import mkdir, path
import sys
import asyncio
from wallbot import wbot 



if name == "main":
    if not path.exists("cache"):
        mkdir("cache")
    wbot().run()
