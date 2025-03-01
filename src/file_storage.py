import os
import random
from datetime import timedelta

class FileStorage:
    def __init__(self, conf:dict):
        self.Directory = conf['directory']
        if not os.path.isdir(self.Directory):
            raise RuntimeError("dir not exists: "+self.Directory)
        self.MaxFileSize = int(conf.get('max_file_size', 1024*256))
        self.FileTotalSizeLimit = int(conf.get('files_total_size_limit_mb', 256)) * 1024*1024
        self.RetentionPeriod = timedelta(days=int(conf.get('retention_days', 10))) 

    @staticmethod
    def MakeUniqueFileName(name:str) -> str:
        return str(random.randint(100, 2000000))+"_"+name

    def GetFileFullPath(self, name:str) -> str:

        return os.path.join(self.Directory, self.MakeUniqueFileName(name))

    def DeleteFileFullPath(self, file_path:str):
        if os.path.exists(file_path):
            os.remove(file_path)

    def GetFileSize(self, file_path:str) -> int:
        return os.path.getsize(file_path)