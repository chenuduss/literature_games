from telegram import Update, User, Chat, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler, ConversationHandler
import argparse
from db_worker import DbWorkerService, FileInfo
import logging
import json
import time
import os
from datetime import timedelta, datetime
from litgb_exception import LitGBException
from zoneinfo import ZoneInfo
from file_worker import FileStorage
from fb2_tool import GetTextSize, FileToFb2
    
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
        
        self.LastHandled = t
        return False       

class UserConversation:
    def __init__(self): 
        self.SetTitleFor = None

class LitGBot:
    def __init__(self, db_worker:DbWorkerService, file_stor:FileStorage):
        self.Db = db_worker
        self.StartTS = int(time.time())       
        
        self.CompetitionChangeLimits = CommandLimits(1, 3)
        self.CompetitionViewLimits = CommandLimits(0.7, 3)
        self.CreateCompetitionLimits = CommandLimits(10, 30)
        self.UploadFilesLimits = CommandLimits(3, 10)
        self.FilesViewLimits = CommandLimits(1, 3)
        self.MyStatLimits = CommandLimits(0.7, 1.25)
        self.StatLimits = CommandLimits(1, 3)
        
        self.FileStorage = file_stor  
        self.MaxFileNameSize = 280
        self.UserConversations:dict[int, UserConversation] = {}

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
        status_msg +="\nФайлы: "+str(self.Db.GetFileTotalCount())+ ". Суммарный размер: "+ MakeHumanReadableAmount(self.Db.GetFilesTotalSize())
        status_msg +="\nЛимит хранилища: " + MakeHumanReadableAmount(self.FileStorage.FileTotalSizeLimit)
        status_msg += "\n\n"+ LitGBot.get_help()

        #status_msg +="\nВерсия "+ str(uptime)
        await update.message.reply_text(status_msg)

    def DeleteFile(self, f:FileInfo):
        logging.warning("[FILESTORAGE] delete file #"+str(f.Id))
        self.FileStorage.DeleteFileFullPath(f.FilePath)
        self.Db.ClearFilePath(f.Id)

    def DeleteOldestFile(self, user_id:int) -> str|None:
        """ return new deleted file title"""
        file_list = self.Db.GetNotLockedFileList(user_id)

        if len(file_list) > 0:
            oldest_file = min(file_list, key = lambda x: x.Loaded)
            self.DeleteFile(oldest_file)
            return oldest_file.Title

        return None
    
    def DeleteOldFiles(self) -> None:

        try:
            file_list = self.Db.GetNotLockedFileListBefore(datetime.now() - self.FileStorage.RetentionPeriod)
            for file in file_list:                
                self.DeleteFile(file)
        except BaseException as ex:
            logging.error("[FILESTORAGE] exception on delete file: "+str(ex)) 


    @staticmethod
    def MakeFileTitle(filename:str) -> str:
        return filename

    async def downloader(self, update: Update, context: ContextTypes.DEFAULT_TYPE):            
        logging.info("[DOWNLOADER] user id "+LitGBot.GetUserTitleForLog(update.effective_user))    
        if self.UploadFilesLimits.Check(update.effective_user.id, update.effective_chat.id):
            logging.warning("[DOWNLOADER] Ignore command from user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat))        
            return
            

        self.DeleteOldFiles()

        file_full_path = None
        try:            
            total_files_Size = self.Db.GetFilesTotalSize()
            if total_files_Size > self.FileStorage.FileTotalSizeLimit:
                raise LitGBException("Достигнут лимит хранилища файлов: "+MakeHumanReadableAmount(self.FileStorage.FileTotalSizeLimit))
            
            self.Db.EnsureUserExists(update.effective_user.id, self.MakeUserTitle(update.effective_user))

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
            if file.file_size > self.FileStorage.MaxFileSize:
                raise LitGBException("Файл слишком большой. Максимальный разрешённый размер: "+MakeHumanReadableAmount(self.FileStorage.MaxFileSize))
            
            _, ext = os.path.splitext(file.file_path)

            file_title = None
            if not (update.message.caption is None):
                if len(update.message.caption) > 0:
                    file_title = update.message.caption.strip()
            if file_title is None:
                file_title = "f_"+str(int(time.time()))    
                
            if len(file_title) > self.MaxFileNameSize:
                raise LitGBException("Имя файла слишком длинное. Максимальная разрешённая длина: "+str(self.MaxFileNameSize))
            file_full_path = self.FileStorage.GetFileFullPath(file_title+ext)            
            
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

    @staticmethod
    def LockedMark(l:bool) ->str:
        if l:
            return "🔒 "
        
        return ""
    
    @staticmethod
    def FileSizeCaption(f:FileInfo) ->str:        
        return "Текст "+MakeHumanReadableAmount(f.TextSize)+ " (Файл: "+MakeHumanReadableAmount(f.Size)+")"

    @staticmethod
    def MakeFileListItem(f:FileInfo) -> str:
        return LitGBot.LockedMark(f.Locked) + "#"+str(f.Id) + ": " +f.Title+" | "+LitGBot.FileSizeCaption(f)

    async def filelist(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:            
        logging.info("[FILELIST] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        if self.FilesViewLimits.Check(update.effective_user.id, update.effective_chat.id):
            logging.warning("[FILELIST] Ignore command from user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat))        
            return        

        self.DeleteOldFiles()      

        if update.effective_user.id != update.effective_chat.id:
            await update.message.reply_text("⛔️ Выполнение команды разрешено только в личных сообщениях бота")

        try:
            files = self.Db.GetFileList(update.effective_user.id, 30)
            files.sort(key=lambda x: x.Loaded)

            reply_text = "Список файлов\n"
            for file in files:
                reply_text += "\n"+self.MakeFileListItem(file)

            await update.message.reply_text(reply_text)   
        except LitGBException as ex:
            await update.message.reply_text(LitGBot.MakeErrorMessage(ex))             
        except BaseException as ex:    
            logging.error("[DOWNLOADER] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+ ". EXCEPTION: "+str(ex))       
            await update.message.reply_text(LitGBot.MakeExternalErrorMessage(ex)) 

    @staticmethod
    def ParseGetFB2Command(msg:str) -> int:
        result = None
        try:
            parts = msg.strip().split(" ", 1)
            if len(parts) < 2:
                raise LitGBException("Некорректный формат команды /getfb2")
            else:
                second_part = parts[1].strip()
                result = int(second_part)                
        except BaseException as ex:
            raise LitGBException("Некорректный формат команды /getfb2")        

        return result    


    def GetFileAndCheckAccess(self, file_id:int, user_id:int) -> FileInfo:
        result = self.Db.FindFile(file_id)
        if result is None:
            raise LitGBException("Файл с указанным идентификатором не найден")
        if (result.Owner != user_id) or (result.FilePath is None):
            raise LitGBException("Файл с указанным идентификатором не найден")
        return result
    
    async def SendFB2(self, f:FileInfo, update: Update, context: ContextTypes.DEFAULT_TYPE):
        fb2_filepath = None

        try:
            fb2_name = f.Title+".fb2"
            fb2_filepath = self.FileStorage.GetFileFullPath(fb2_name) 
            FileToFb2(f.FilePath, fb2_filepath, f.Title)

            file_obj = open(fb2_filepath, "rb")
            await context.bot.send_document(update.effective_chat.id, file_obj, filename=fb2_name)
        finally:
            if not (fb2_filepath is None):
                self.FileStorage.DeleteFileFullPath(fb2_filepath)


    async def getfb2(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:            
        logging.info("[GETFB2] user id "+LitGBot.GetUserTitleForLog(update.effective_user))         
        if self.FilesViewLimits.Check(update.effective_user.id, update.effective_chat.id):
            logging.warning("[FILELIST] Ignore command from user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat))        
            return         
        self.DeleteOldFiles() 
        if update.effective_user.id != update.effective_chat.id:
            await update.message.reply_text("⛔️ Выполнение команды разрешено только в личных сообщениях бота")
        
        try:
            file_id = self.ParseGetFB2Command(update.message.text)
            file = self.GetFileAndCheckAccess(file_id, update.effective_user.id)

            await self.SendFB2(file, update, context)
        except LitGBException as ex:
            await update.message.reply_text(LitGBot.MakeErrorMessage(ex)) 
        except BaseException as ex:    
            logging.error("[GETFB2] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+ ". EXCEPTION: "+str(ex))       
            await update.message.reply_text(LitGBot.MakeExternalErrorMessage(ex))             


    @staticmethod
    def file_menu_message(f:FileInfo|None) -> str:        
        result = LitGBot.LockedMark(f.Locked) + "#" + str(f.Id)
        result +="\nНазвание: " + f.Title
        result +="\n"+LitGBot.FileSizeCaption(f)
        result +="\nЗагружено: " + f.Loaded.strftime("%d.%m.%Y %H:%M")

        return result

    @staticmethod
    def error_menu_message(self, error:LitGBException) -> str:
        return LitGBot.MakeErrorMessage(error)

    def file_menu_keyboard(self, file_index:int, files:list[FileInfo]):
        if len(files) == 0:
            return InlineKeyboardMarkup([])

        file = files[file_index]
        file_id_str = str(file.Id)
        keyboard = []   
        


        keyboard.append([InlineKeyboardButton('Удалить', callback_data='file_delete_'+file_id_str)])
        keyboard.append([InlineKeyboardButton('Установить название', callback_data='file_settitle_'+file_id_str)])
        keyboard.append([InlineKeyboardButton('FB2', callback_data='file_fb2_'+file_id_str)])

        list_buttons_line = []
        if file_index > 0:
            list_buttons_line.append(InlineKeyboardButton('<=', callback_data='file_show_'+str(files[file_index-1].Id)))
        if file_index < len(files)-1:
            list_buttons_line.append(InlineKeyboardButton('=>', callback_data='file_show_'+str(files[file_index+1].Id)))
        if len(list_buttons_line) > 0:
            keyboard.append(list_buttons_line)    

        return InlineKeyboardMarkup(keyboard)
    

    async def file_menu_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: 
        logging.info("[file_menu_handler] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        if update.effective_user.id != update.effective_chat.id:
            return        
        
        query = update.callback_query                
        await query.answer()
        try:
            if len(query.data) < 7:
                raise LitGBException("invalid query.data value: "+query.data)
            qdata = query.data[5:]
            params = qdata.split("_", 1)        

            if params[0] == "show":
                file_id = int(params[1])                
                f = self.GetFileAndCheckAccess(file_id, update.effective_user.id )
                files = self.Db.GetFileList(update.effective_user.id, 30)
                if len(files)==0:                
                    raise LitGBException("file list empty")
                
                files.sort(key=lambda x: x.Loaded)

                file_index = -1
                for i, v in enumerate(files): 
                    if v.Id == f.Id:
                        file_index = i
                        break

                if file_index < 0:
                    raise LitGBException("file not found in file list")
                await query.edit_message_text(
                            text=self.file_menu_message(f),
                            reply_markup=self.file_menu_keyboard(file_index, files))
            elif params[0] == "delete":  
                file_id = int(params[1])                
                f = self.GetFileAndCheckAccess(file_id, update.effective_user.id )
                if f.Locked:
                    raise LitGBException("file locked")                
                self.DeleteFile(f)
            elif params[0] == "settitle":  
                file_id = int(params[1])                
                f = self.GetFileAndCheckAccess(file_id, update.effective_user.id )
                if f.Locked:
                    raise LitGBException("file locked")            
                uconv = UserConversation()
                uconv.SetTitleFor = f.Id
                self.UserConversations[update.effective_user.id] = uconv
                await query.edit_message_text(
                    text="Введите новое название файла", reply_markup=InlineKeyboardMarkup([]))                
            elif params[0] == "fb2":
                file_id = int(params[1])
                f = self.GetFileAndCheckAccess(file_id, update.effective_user.id)
                await self.SendFB2(f, update, context)
            else:
                raise LitGBException("unknown menu action: "+params[0])
        except LitGBException as ex:
            await query.edit_message_text(
                text=self.error_menu_message(ex), reply_markup=InlineKeyboardMarkup([]))                    
        except BaseException as ex:    
            logging.error("[DOWNLOADER] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+ ". EXCEPTION: "+str(ex))       
            await query.edit_message_text(
                text=LitGBot.MakeExternalErrorMessage(ex), reply_markup=InlineKeyboardMarkup([])) 


    async def files(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:            
        logging.info("[FILES] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        if self.FilesViewLimits.Check(update.effective_user.id, update.effective_chat.id):
            logging.warning("[FILELIST] Ignore command from user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat))        
            return 
        self.DeleteOldFiles() 
        if update.effective_user.id != update.effective_chat.id:
            await update.message.reply_text("⛔️ Выполнение команды разрешено только в личных сообщениях бота")
        
        try:
            files = self.Db.GetFileList(update.effective_user.id, 30)
            if len(files) > 0:
                files.sort(key=lambda x: x.Loaded)                
                await update.message.reply_text(self.file_menu_message(files[0]), reply_markup=self.file_menu_keyboard(0, files))   
            else:
                await update.message.reply_text(self.file_menu_message(None), reply_markup=self.file_menu_keyboard(0, []))   
        except LitGBException as ex:
            await update.message.reply_text(LitGBot.MakeErrorMessage(ex))             
        except BaseException as ex:    
            logging.error("[DOWNLOADER] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+ ". EXCEPTION: "+str(ex))       
            await update.message.reply_text(LitGBot.MakeExternalErrorMessage(ex))    

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:                
        logging.info("[HANDLE_TEXT] user id "+LitGBot.GetUserTitleForLog(update.effective_user))         
        
        try:
            if update.effective_user.id in self.UserConversations:
                if update.effective_user.id != update.effective_chat.id:
                    return
                convers = self.UserConversations.pop(update.effective_user.id)
                if not (convers.SetTitleFor is None):
                    logging.info("[FILE_SETTITLE] new title for file #"+str(convers.SetTitleFor)+": "+update.message.text) 
                    if len(update.message.text) > self.MaxFileNameSize:
                        raise LitGBException("Имя файла слишком длинное. Максимальная разрешённая длина: "+str(self.MaxFileNameSize))
                    self.Db.SetFileTitle(convers.SetTitleFor, update.message.text.strip())
                    await update.message.reply_text("Новое имя файла #"+str(convers.SetTitleFor)+" установлено: "+update.message.text)            
        except LitGBException as ex:
            await update.message.reply_text(LitGBot.MakeErrorMessage(ex))             
        except BaseException as ex:    
            logging.error("[HANDLE_TEXT] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+ ". EXCEPTION: "+str(ex))       
            await update.message.reply_text(LitGBot.MakeExternalErrorMessage(ex))                    

    async def create_closed_competition(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[CREATECLOSED] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        if self.CreateCompetitionLimits.Check(update.effective_user.id, update.effective_chat.id):
            logging.warning("[CREATECLOSED] Ignore command from user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat))        
            return
        
    async def create_open_competition(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[CREATEOPEN] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        if self.CreateCompetitionLimits.Check(update.effective_user.id, update.effective_chat.id):
            logging.warning("[CREATEOPEN] Ignore command from user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat))        
            return
        
    async def attach_competition(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[ATTACHCOMP] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        if self.CompetitionChangeLimits.Check(update.effective_user.id, update.effective_chat.id):
            logging.warning("[ATTACHCOMP] Ignore command from user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat))        
            return    
        if update.effective_user.id == update.effective_chat.id:
            await update.message.reply_text("⛔️ Выполнение команды в личных сообщениях бота лишено смысла")

        
    async def competitions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[COMPS] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        if self.CompetitionViewLimits.Check(update.effective_user.id, update.effective_chat.id):
            logging.warning("[COMPS] Ignore command from user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat))        
            return
        
        # в конфе - список конкурсов связанных с этим чатом. Режим: только просмотр
        # в личке - список конкурсов в которым можно присоединиться. Режим: просмотр и возможность присоединиться
        
    async def mycompetitions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[MYCOMPS] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        if self.CompetitionViewLimits.Check(update.effective_user.id, update.effective_chat.id):
            logging.warning("[MYCOMPS] Ignore command from user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat))        
            return
        if update.effective_user.id != update.effective_chat.id:
            await update.message.reply_text("⛔️ Выполнение команды разрешено только в личных сообщениях бота")          

        # список конкурсов, в которых юзер участвует или создал

if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    parser = argparse.ArgumentParser(
        prog = 'LitGBot', description = '''Literature games bot''', epilog = '''(c) 2025''')   


    parser.add_argument ('--conf', dest='conf', action="store", type=str, required=True)

    args = parser.parse_args()

    
    with open(args.conf, 'r') as file:
        conf = json.load(file)

       
    file_str = FileStorage(conf['file_storage'])

    db = DbWorkerService(conf['db'])

    app = ApplicationBuilder().token(conf['bot_token']).build()

    bot = LitGBot(db, file_str)   

    app.add_handler(CommandHandler("status", bot.status))
    app.add_handler(CommandHandler("filelist", bot.filelist))
    app.add_handler(CommandHandler("files", bot.files))
    app.add_handler(CommandHandler("getfb2", bot.getfb2))
    app.add_handler(CommandHandler("mystat", bot.mystat))
    app.add_handler(CommandHandler("stat", bot.stat))
    app.add_handler(CommandHandler("top", bot.top))
    app.add_handler(CommandHandler("create_closed_competition", bot.create_closed_competition))
    app.add_handler(CommandHandler("create_open_competition", bot.create_open_competition))
    app.add_handler(CommandHandler("attach_competition", bot.attach_competition))
    app.add_handler(CommandHandler("competitions", bot.competitions))    
    app.add_handler(CommandHandler("mycompetitions", bot.mycompetitions))
    app.add_handler(CallbackQueryHandler(bot.file_menu_handler, pattern="file_\\S+"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_text))
    
    app.add_handler(MessageHandler(filters.Document.ALL, bot.downloader))    

    app.run_polling()

#https://docs-python.ru/packages/biblioteka-python-telegram-bot-python/planirovschik-soobschenij/