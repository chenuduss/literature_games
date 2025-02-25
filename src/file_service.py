from telegram.ext import ContextTypes
from file_worker import FileWorker
from file_storage import FileStorage
from fb2_tool import SectionToFb2
from db_worker import FileInfo

class FileService(FileWorker):
    def __init__(self, file_stor:FileStorage):
        FileWorker.__init__(self, file_stor)

    async def SendFB2(self, f:FileInfo, chat_id:int, context: ContextTypes.DEFAULT_TYPE):
        fb2_filepath = None

        try:
            fb2_name = f.Title+".fb2"
            fb2_filepath = self.FileStorage.GetFileFullPath(fb2_name) 
            SectionToFb2(f.FilePath, fb2_filepath, f.Title)

            file_obj = open(fb2_filepath, "rb")            
            await context.bot.send_document(chat_id, file_obj, filename=fb2_name)
        finally:
            if not (fb2_filepath is None):
                self.FileStorage.DeleteFileFullPath(fb2_filepath)        