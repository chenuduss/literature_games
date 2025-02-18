from telegram import Update, User, Chat
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
import argparse
from db_worker import DbWorkerService
import logging
import json
import time
from datetime import timedelta, datetime
from litgb_exception import LitGBException
from zoneinfo import ZoneInfo
from file_worker import FileStorage
from fb2_tool import GetTextSize
    
def MakeHumanReadableAmount(value:int) -> str:     
    if value > 1000000:
        return str(round(float(value)/1000000.0, 2))+"M"
    if value > 1000:
        return str(round(float(value)/1000.0, 1))+"k" 
        
    return str(value)

class CommandLimits:
    def __init__(self, global_min_inteval:float, chat_min_inteval:float):
        self.GlobalMinimumInterval = global_min_inteval
        self.ChatMinimumInterval = chat_min_inteval
        self.ChatLimits:dict[int, float] = {}
        self.LastHandled = time.time()

    def Check(self, user_id:int, chat_id:int) -> bool:
        t = time.time() 
        if t - self.LastHandled < self.GlobalMinimumInterval:            
            return True
        if chat_id in self.ChatLimits:
            if t - self.ChatLimits[chat_id] < self.ChatMinimumInterval: 
                return True
            self.ChatLimits[chat_id] = t
        else:
            self.ChatLimits[chat_id] = t    
        
        self.LastHandledStatCommand = t
        return False        

class LitGBot:
    def __init__(self, db_worker:DbWorkerService, file_stor:FileStorage):
        self.Db = db_worker
        self.StartTS = int(time.time())        
        
        self.MyStatLimits = CommandLimits(0.7, 1.25)
        self.StatLimits = CommandLimits(1, 3)    
        self.MaxFileSize = 1024*256
        self.FileTotalSizeLimit = 1024*1024*256
        self.FileStorage = file_stor        

    @staticmethod
    def GetUserTitleForLog(user:User) -> str:
        return "["+str(user.id)+"]{"+user.name+"}" 
    
    @staticmethod
    def GetChatTitleForLog(ch:Chat) -> str:
        return "["+str(ch.id)+"]{"+ch.effective_name+"}"     

    @staticmethod    
    def MakeUserTitle(user:User) -> str:
        result = user.full_name
        if (len(result) < 2):
            result = user.name
        if (len(result) < 1):
            result = "@"+str(user.id)
        return result
    
    @staticmethod    
    def MakeChatTitle(ch:Chat) -> str:
        result = ch.effective_name
        if (len(result) < 1):
            result = "@"+str(ch.id)
        return result              

    @staticmethod
    def MakeErrorMessage(ex: LitGBException) -> str:
        return "⛔️ Ошибка!\n\n"+str(ex)
    
    @staticmethod
    def MakeExternalErrorMessage(ex: BaseException) -> str:
        return "❗️ Ошибка при выполнении команды: "+str(ex)
          

    async def mystat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logging.info("[MYSTAT] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat))    
        if self.MyStatLimits.Check(update.effective_user.id, update.effective_chat.id):
            logging.warning("[MYSTAT] Ignore command from user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat))        
            return
        self.LastHandledMyStatCommand = time.time()

        try:
            stat_message = "в разработке"        

            await update.message.reply_text(stat_message)    
        except LitGBException as ex:
            await update.message.reply_text(LitGBot.MakeErrorMessage(ex)) 
        except BaseException as ex:    
            logging.error("[MYSTAT] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat) + ", text: "+update.message.text + ". EXCEPTION: "+str(ex))       
            await update.message.reply_text(LitGBot.MakeExternalErrorMessage(ex))



    

    async def stat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:        
        logging.info("[STAT] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat))    
        if self.StatLimits.Check(update.effective_user.id, update.effective_chat.id):
            logging.warning("[STAT] Ignore command from user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat))                
            return
        self.LastHandledStatCommand = time.time()

        try:
            stat_message = "в разработке"        

            await update.message.reply_text(stat_message)      
        except LitGBException as ex:
            await update.message.reply_text(LitGBot.MakeErrorMessage(ex)) 
        except BaseException as ex:    
            logging.error("[STAT] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat) + ", text: "+update.message.text + ". EXCEPTION: "+str(ex))       
            await update.message.reply_text(LitGBot.MakeExternalErrorMessage(ex))  

    async def top(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:        
        logging.info("[TOP] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat))    
        if self.StatLimits.Check(update.effective_user.id, update.effective_chat.id):
            logging.warning("[TOP] Ignore command from user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat))                
            return
        self.LastHandledStatCommand = time.time()

        try:            
            stat_message = "в разработке"        

            await update.message.reply_text(stat_message)     
        except LitGBException as ex:
            await update.message.reply_text(LitGBot.MakeErrorMessage(ex)) 
        except BaseException as ex:    
            logging.error("[TOP] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat) + ", text: "+update.message.text + ". EXCEPTION: "+str(ex))       
            await update.message.reply_text(LitGBot.MakeExternalErrorMessage(ex))              

    @staticmethod
    def get_help() -> str:
        result = "Команды: "
        return result

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        ut = LitGBot.GetUserTitleForLog(update.effective_user)
        logging.info("[STATUS] user id "+ut+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat))    
        status_msg = "Привет, "+LitGBot.MakeUserTitle(update.effective_user)+"! ("+ut+")"
        status_msg +="\nЭто чат: "+LitGBot.MakeChatTitle(update.effective_chat)
        uptime_sec = time.time() - self.StartTS
        uptime = timedelta(seconds = uptime_sec)
        status_msg +="\nАптайм "+ str(uptime)
        status_msg += "\n\n"+ LitGBot.get_help()

        #status_msg +="\nВерсия "+ str(uptime)
        await update.message.reply_text(status_msg)

    def DeleteOldestFile(self, user_id:int) -> str|None:
        """ return new deleted file title"""
        file_list = self.Db.GetNotLockedFileList(user_id)

        if len(file_list) > 0:
            oldest_file = min(file_list, key = lambda x: x.Loaded)
            self.FileStorage.DeleteFileFullPath(oldest_file.FilePath)
            self.Db.ClearFilePath(oldest_file.Id)
            return oldest_file.Title

        return None

    @staticmethod
    def MakeFileTitle(filename:str) -> str:
        return filename

    async def downloader(self, update, context):            
        logging.info("[DOWNLOADER] user id "+LitGBot.GetUserTitleForLog(update.effective_user))    

        file_full_path = None
        try:            
            total_files_Size = self.Db.GetFilesTotalSize()
            if total_files_Size > self.FileTotalSizeLimit:
                raise LitGBException("Достигнут лимит хранилища файлов: "+MakeHumanReadableAmount(self.FileTotalSizeLimit))

            deleted_file_name = None
            flimit = self.Db.GetUserFileLimit(update.effective_user.id)
            if flimit < 1:
                raise LitGBException("Вам не разрешена загрузка файлов")
            
            cfile_count = self.Db.GetFileCount(update.effective_user.id)

            if cfile_count >= flimit:
                deleted_file_name = self.DeleteOldestFile(update.effective_user.id)
                if not (deleted_file_name is None):
                    cfile_count = self.Db.GetFileCount(update.effective_user.id)
                    if cfile_count >= flimit:
                        raise LitGBException("Достигнут лимит загруженных файлов")                
                

            file = await context.bot.get_file(update.message.document)             
            if file.file_size > self.MaxFileSize:
                raise LitGBException("Файл слишком большой. Максимальный разрешённый размер: "+MakeHumanReadableAmount(self.MaxFileSize))
            
            file_full_path = self.FileStorage.GetFileFullPath(file.file_path)
            file_title = self.MakeFileTitle(file.file_path)
            logging.info("[DOWNLOADER] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+" file size "+str(file.file_size)+" downloading...") 
            await file.download_to_drive(file_full_path)             
            text_size = GetTextSize(file_full_path)            
            logging.info("[DOWNLOADER] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+" file size "+str(file.file_size)+" download success. Text size: "+str(text_size)) 

            _ = self.Db.InsertFile(update.effective_user.id, file_title, file.file_size, text_size, file_full_path)
            file_full_path = None

            logging.info("[DOWNLOADER] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+" file size "+str(file.file_size)+", text size: "+str(text_size)+". Insert to DB success") 

            reply_text = "☑️ Файл успешно загружен. Имя файла: "+file_title+". Текст: "+ MakeHumanReadableAmount(text_size)
            if not (deleted_file_name is None):
                reply_text += "\nБыл удалён файл "+ deleted_file_name
            await update.message.reply_text(reply_text)            
        except LitGBException as ex:
            await update.message.reply_text(LitGBot.MakeErrorMessage(ex)) 
        except BaseException as ex:    
            logging.error("[DOWNLOADER] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+ ". EXCEPTION: "+str(ex))       
            await update.message.reply_text(LitGBot.MakeExternalErrorMessage(ex))         
        finally:
            if not (file_full_path is None):
                self.FileStorage.DeleteFileFullPath(file_full_path)

    async def filelist(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:            
        logging.info("[FILELIST] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        if update.effective_user.id != update.effective_chat.id:
            await update.message.reply_text("⛔️ Выполнение команды разрешено только в личных сообщениях бота")
            

if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    parser = argparse.ArgumentParser(
        prog = 'LitGBot', description = '''Literature games bot''', epilog = '''(c) 2025''')   


    parser.add_argument ('--conf', dest='conf', action="store", type=str, required=True)

    args = parser.parse_args()

    
    with open(args.conf, 'r') as file:
        conf = json.load(file)

       
    file_str = FileStorage(conf['files_dir'])

    db = DbWorkerService(conf['db'])

    app = ApplicationBuilder().token(conf['bot_token']).build()

    bot = LitGBot(db, file_str)

    app.add_handler(CommandHandler("status", bot.status))
    app.add_handler(CommandHandler("filelist", bot.filelist))
    app.add_handler(CommandHandler("mystat", bot.mystat))
    app.add_handler(CommandHandler("stat", bot.stat))
    app.add_handler(CommandHandler("top", bot.top))
    app.add_handler(MessageHandler(filters.Document.ALL, bot.downloader))

    app.run_polling()

