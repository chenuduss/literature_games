import os
import random

class FileStorage:
    def __init__(self, directory:str):
        self.Directory = directory

    def MakeUniqueFileName(name:str) -> str:
        return str(random.randint(100, 2000000))+"_"+name

    def GetFileFullPath(self, name:str) -> str:

        return os.path.join(self.Directory, self.MakeUniqueFileName(name))
