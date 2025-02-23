from telegram import Update, User, Chat, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler, ConversationHandler
import argparse
from db_worker import DbWorkerService, FileInfo, CompetitionInfo, CompetitionStat, ChatInfo
import logging
import json
import time
import os
from datetime import timedelta, datetime, timezone
from litgb_exception import LitGBException, FileNotFound, CompetitionNotFound, OnlyPrivateMessageAllowed
from zoneinfo import ZoneInfo
from file_worker import FileStorage
from fb2_tool import FileToFb2Section, SectionToFb2
import string
import random
import re
import traceback
import pytz
    
def GetRandomString(length:int) -> str:    
    letters = string.ascii_lowercase+string.ascii_uppercase    
    return ''.join(random.choice(letters) for i in range(length))

def DatetimeToString(v:datetime) -> str:
    return v.strftime("%d.%m.%Y %H:%M %Z")

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

    def Check(self, user_id:int, chat_id:int):
        t = time.time() 
        if t - self.LastHandled < self.GlobalMinimumInterval:            
            raise CommandRateLimitReached(self)
        if chat_id in self.ChatLimits:
            if t - self.ChatLimits[chat_id] < self.ChatMinimumInterval: 
                raise CommandRateLimitReached(self)
            self.ChatLimits[chat_id] = t
        else:
            self.ChatLimits[chat_id] = t    
        
        self.LastHandled = t         


class CommandRateLimitReached(LitGBException):
    def __init__(self, src_limit: CommandLimits):
        LitGBException.__init__(self, "Команда выполняется слишком часто. Минимальный интервал в чате "+str(src_limit.ChatMinimumInterval)+" сек, минимальный интервал глобально "+str(src_limit.GlobalMinimumInterval)+" сек")      

class UserConversation:
    def __init__(self): 
        self.SetTitleFor = None
        self.SetSubjectFor = None
        self.SetSubjectExtFor = None
        self.InputEntryTokenFor = None
        self.SetDeadlinesFor = None

class CompetitionFullInfo:
    def __init__(self, comp:CompetitionInfo, stat:CompetitionStat|None = None, chat:ChatInfo|None = None): 
        self.Comp = comp
        self.Stat = stat
        self.Chat = chat

class LitGBot:
    def __init__(self, db_worker:DbWorkerService, file_stor:FileStorage, admin:dict):
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

        self.JoinToCompetitionCommandRegex = re.compile("/join\\s+(\\d+)\\s+(\\S+)")
        self.CompetitionMenuQueryRegex = re.compile("comp_(\\S+)_(\\S+)_(\\d+)")

        self.DefaultAcceptDeadlineTimedelta = timedelta(minutes=15)
        self.DefaultPollingStageTimedelta = timedelta(minutes=15)

        self.DefaultMinTextSize = 15000
        self.DefaultMaxTextSize = 40000
        self.CompetitionsListDefaultFutureInterval = timedelta(days=40)
        self.CompetitionsListDefaultPastInterval = timedelta(days=3)
        self.MaxCompetitionDeadlineFutureInterval = timedelta(days=60)
        self.MinTextSize = 5000
        self.MaxTextSize = 120000
        self.TextLimitChangeStep = 2500

        self.Admins = set(admin["user_ids"])
        self.Timezone = pytz.timezone("Europe/Moscow")


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
        self.MyStatLimits.Check(update.effective_user.id, update.effective_chat.id)

        stat_message = "в разработке"        

        await update.message.reply_text(stat_message)
    

    async def stat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:        
        logging.info("[STAT] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat))    
        self.StatLimits.Check(update.effective_user.id, update.effective_chat.id)

        stat_message = "в разработке"        

        await update.message.reply_text(stat_message)      


    async def top(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:        
        logging.info("[TOP] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat))    
        self.StatLimits.Check(update.effective_user.id, update.effective_chat.id)
          
        stat_message = "в разработке"        

        await update.message.reply_text(stat_message)     
              

    @staticmethod
    def get_help() -> str:
        result = "Команды: "
        result += "\n/competition - карточка конкурса"
        result += "\n/competitions - список конкурсов, которые привязаны к текущему чату. В личке - список активных конкурсов"
        result += "\n/joinable_competitions - список конкурсов, к которым можно присоединиться"
        result += "\n/mycompetitions (только в личке) - список активных конкурсов, которые создал текущий пользователь или в которых он участвует"
        
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
            file_list = self.Db.GetNotLockedFileListBefore(datetime.now(timezone.utc) - self.FileStorage.RetentionPeriod)
            for file in file_list:                
                self.DeleteFile(file)
        except BaseException as ex:
            logging.error("[FILESTORAGE] exception on delete file: "+str(ex)) 


    @staticmethod
    def MakeFileTitle(filename:str) -> str:
        return filename
    
    def CheckPrivateOnly(self, update: Update):
        if update.effective_user.id != update.effective_chat.id:
            raise OnlyPrivateMessageAllowed()

    async def downloader(self, update: Update, context: ContextTypes.DEFAULT_TYPE):            
        logging.info("[DOWNLOADER] user id "+LitGBot.GetUserTitleForLog(update.effective_user))    
        self.UploadFilesLimits.Check(update.effective_user.id, update.effective_chat.id)           
        self.CheckPrivateOnly(update) 

        self.DeleteOldFiles()

        file_full_path = None
        file_full_path_tmp = None
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
            file_full_path_tmp = self.FileStorage.GetFileFullPath(file_title+ext)            
            file_full_path = self.FileStorage.GetFileFullPath(file_title+".fb2_section")
            
            logging.info("[DOWNLOADER] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+" file size "+str(file.file_size)+" downloading...") 
            await file.download_to_drive(file_full_path_tmp)
            
            text_size = FileToFb2Section(file_full_path_tmp, file_full_path, file_title)         
            self.FileStorage.DeleteFileFullPath(file_full_path_tmp)
            file_full_path_tmp = None
            file_size = self.FileStorage.GetFileSize(file_full_path)
            logging.info("[DOWNLOADER] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+" fb2 section file size "+str(file_size)+" download success. Text size: "+str(text_size)) 

            _ = self.Db.InsertFile(update.effective_user.id, file_title, file_size, text_size, file_full_path)
            file_full_path = None

            logging.info("[DOWNLOADER] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+" fb2 section file size "+str(file_size)+", text size: "+str(text_size)+". Insert to DB success") 

            reply_text = "☑️ Файл успешно загружен. Имя файла: "+file_title+". Текст: "+ MakeHumanReadableAmount(text_size)
            if not (deleted_file_name is None):
                reply_text += "\nБыл удалён файл "+ deleted_file_name
            await update.message.reply_text(reply_text)      
        finally:
            if not (file_full_path_tmp is None):
                self.FileStorage.DeleteFileFullPath(file_full_path_tmp)
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
        self.FilesViewLimits.Check(update.effective_user.id, update.effective_chat.id)

        self.DeleteOldFiles()
        self.CheckPrivateOnly(update) 


        files = self.Db.GetFileList(update.effective_user.id, 30)
        files.sort(key=lambda x: x.Loaded)

        reply_text = "Список файлов\n"
        for file in files:
            reply_text += "\n"+self.MakeFileListItem(file)

        await update.message.reply_text(reply_text)   

    @staticmethod
    def ParseTwoIntArgumentCommand(msg:str, command:str, min:int|None = 1, max:int|None = None) -> tuple[int, int]: 
        try:
            parts = msg.strip().split(" ", 2)
            if len(parts) < 3:
                raise LitGBException("Некорректный формат команды "+command)
            else:
                second_part = parts[1].strip()
                result1 = int(second_part) 
                if not (min is None):
                    if result1 < min:
                        raise LitGBException("Разрешённое минимальное значение команды "+str(min))
                if not (max is None):    
                    if  result1 > max:
                        raise LitGBException("Разрешённое максимальное значение команды "+str(min))
                third_part = parts[2].strip()
                result2 = int(third_part) 
                if not (min is None):
                    if result2 < min:
                        raise LitGBException("Разрешённое минимальное значение команды "+str(min))
                if not (max is None):    
                    if  result2 > max:
                        raise LitGBException("Разрешённое максимальное значение команды "+str(min))                    
                    
                return (result1, result2    )
        except BaseException as ex:
            raise LitGBException("Некорректный формат команды "+command)

    @staticmethod
    def ParseSingleIntArgumentCommand(msg:str, command:str, min:int|None = 1, max:int|None = None) -> int: 
        result = None
        try:
            parts = msg.strip().split(" ", 1)
            if len(parts) < 2:
                raise LitGBException("Некорректный формат команды "+command)
            else:
                second_part = parts[1].strip()
                result = int(second_part) 
                if not (min is None):
                    if result < min:
                        raise LitGBException("Разрешённое минимальное значение команды "+str(min))
                if not (max is None):    
                    if  result > max:
                        raise LitGBException("Разрешённое максимальное значение команды "+str(min))
                return result    
        except BaseException as ex:
            raise LitGBException("Некорректный формат команды "+command)


    def GetFileAndCheckAccess(self, file_id:int, user_id:int) -> FileInfo:
        result = self.Db.FindFile(file_id)
        if result is None:
            raise FileNotFound(file_id)
        if (result.Owner != user_id) or (result.FilePath is None):
            raise FileNotFound(file_id)
        return result
    
    async def SendFB2(self, f:FileInfo, update: Update, context: ContextTypes.DEFAULT_TYPE):
        fb2_filepath = None

        try:
            fb2_name = f.Title+".fb2"
            fb2_filepath = self.FileStorage.GetFileFullPath(fb2_name) 
            SectionToFb2(f.FilePath, fb2_filepath, f.Title)

            file_obj = open(fb2_filepath, "rb")
            await context.bot.send_document(update.effective_chat.id, file_obj, filename=fb2_name)
        finally:
            if not (fb2_filepath is None):
                self.FileStorage.DeleteFileFullPath(fb2_filepath)


    async def getfb2(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:            
        logging.info("[GETFB2] user id "+LitGBot.GetUserTitleForLog(update.effective_user))         
        self.FilesViewLimits.Check(update.effective_user.id, update.effective_chat.id)

        self.DeleteOldFiles() 
        self.CheckPrivateOnly(update) 
        
        file_id = self.ParseSingleIntArgumentCommand(update.message.text, "/getfb2", 1, None)
        file = self.GetFileAndCheckAccess(file_id, update.effective_user.id)

        await self.SendFB2(file, update, context)
           


    @staticmethod
    def file_menu_message(f:FileInfo|None) -> str:        
        result = LitGBot.LockedMark(f.Locked) + "#" + str(f.Id)
        result +="\nНазвание: " + f.Title
        result +="\n"+LitGBot.FileSizeCaption(f)
        result +="\nЗагружено: " + DatetimeToString(f.Loaded)

        return result

    @staticmethod
    def error_menu_message(error:LitGBException) -> str:
        return LitGBot.MakeErrorMessage(error)
    
    @staticmethod
    def MakeUseFileInCompetitionButtonCaption(comp:CompetitionInfo, chat:ChatInfo) -> str:
        return "#"+str(comp.Id)+" "+chat.Title
    
    @staticmethod
    def IsFileAcceptableFromUser(comp:CompetitionInfo, comp_stat:CompetitionStat, user_id:int, file_id:int) -> bool:
        submitted_files = comp_stat.SubmittedFiles.get(user_id, [])
        if len(submitted_files) >= comp.MaxFilesPerMember:
            return False
        
        for f in submitted_files:
            if f.Id == file_id:
                return False
        
        return True
            

    def file_menu_keyboard(self, file_index:int, files:list[FileInfo], user_id:int):
        if len(files) == 0:
            return InlineKeyboardMarkup([])

        file = files[file_index]
        file_id_str = str(file.Id)
        keyboard = []   
        


        keyboard.append([InlineKeyboardButton('Удалить', callback_data='file_delete_'+file_id_str)])
        keyboard.append([InlineKeyboardButton('Установить название', callback_data='file_settitle_'+file_id_str)])
        keyboard.append([InlineKeyboardButton('FB2', callback_data='file_fb2_'+file_id_str)])

        if not file.Locked:
            joined_competitions = self.Db.SelectUserRegisteredCompetitions(user_id, datetime.now(timezone.utc), datetime.now(timezone.utc)+timedelta(days=40))
            if len(joined_competitions) > 0:    
                added_buttons = 0            
                for comp in joined_competitions:
                    comp_stat = self.Db.GetCompetitionStat(comp.Id)
                    if self.IsFileAcceptableFromUser(comp, comp_stat, user_id, file.Id):
                        if (file.TextSize >= comp.MinTextSize) and (file.TextSize <= comp.MaxTextSize):
                            chat = self.Db.FindChat(comp.ChatId)
                            button_caption = self.MakeUseFileInCompetitionButtonCaption(comp, chat)
                            keyboard.append([InlineKeyboardButton(button_caption, callback_data='file_use_'+str(file.Id)+"_"+str(comp.Id))])
                            added_buttons += 1
                            if added_buttons >= 5:
                                break
                            



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
            params = qdata.split("_", 2)

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
                            reply_markup=self.file_menu_keyboard(file_index, files, update.effective_user.id))
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
            elif params[0] == "use":
                file_id = int(params[1])
                comp_id = int(params[2])
                f = self.GetFileAndCheckAccess(file_id, update.effective_user.id)
                comp = self.FindFileAcceptableCompetition(comp_id)
                if (f.TextSize < comp.MinTextSize) or (f.TextSize > comp.MaxTextSize):
                    raise LitGBException("file not acceptable for competition")
                comp_stat = self.Db.GetCompetitionStat(comp.Id)
                if not self.IsFileAcceptableFromUser(comp, comp_stat, update.effective_user.id, f.Id):
                    raise LitGBException("file not acceptable for competition from this user")
                
                comp_stat = self.Db.UseFileInCompetition(comp.Id, update.effective_user.id, f.Id)            
                await query.edit_message_text(
                    text="Файл задействован в конкурсе #"+str(comp_id), reply_markup=InlineKeyboardMarkup([]))            
            else:
                raise LitGBException("unknown menu action: "+params[0])
        except LitGBException as ex:
            await query.edit_message_text(
                text=self.error_menu_message(ex), reply_markup=InlineKeyboardMarkup([]))                    
        except BaseException as ex:    
            logging.error("[file_menu_handler] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+ ". EXCEPTION: "+str(ex))       
            await query.edit_message_text(
                text=LitGBot.MakeExternalErrorMessage(ex), reply_markup=InlineKeyboardMarkup([])) 

    async def set_file_limit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logging.warning("[ADMIN] user id "+LitGBot.GetUserTitleForLog(update.effective_user))     
        if update.effective_user.id != update.effective_chat.id:
            return
        if not (update.effective_user.id in self.Admins):
            return
        user_id, limit = self.ParseTwoIntArgumentCommand(update.message.text, "/set_filelimit", 0)
        self.Db.SetUserFileLimit(user_id, limit)
        await update.message.reply_text("Лимит у пользователя "+str(user_id)+" установлен в значение "+str(limit))

    async def set_allusers_file_limit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logging.warning("[ADMIN] user id "+LitGBot.GetUserTitleForLog(update.effective_user))     
        if update.effective_user.id != update.effective_chat.id:
            return
        if not (update.effective_user.id in self.Admins):
            return        
        limit = self.ParseSingleIntArgumentCommand(update.message.text, "/set_allusers_filelimit", 0) 
        affected_users = self.Db.SetAllUsersFileLimit(limit)
        await update.message.reply_text("Лимит "+str(affected_users)+" пользователей установлен в значение "+str(limit))

    async def kill_competition(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logging.warning("[ADMIN] user id "+LitGBot.GetUserTitleForLog(update.effective_user))             
        if update.effective_user.id != update.effective_chat.id:
            return
        if not (update.effective_user.id in self.Admins):
            return        
        

    async def files(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:            
        logging.info("[FILES] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        self.FilesViewLimits.Check(update.effective_user.id, update.effective_chat.id)
        self.DeleteOldFiles() 
        self.CheckPrivateOnly(update)         

        files = self.Db.GetFileList(update.effective_user.id, 30)
        if len(files) > 0:
            files.sort(key=lambda x: x.Loaded)                
            await update.message.reply_text(self.file_menu_message(files[0]), reply_markup=self.file_menu_keyboard(0, files, update.effective_user.id))   
        else:
            await update.message.reply_text(self.file_menu_message(None), reply_markup=self.file_menu_keyboard(0, [], update.effective_user.id))   
   
    @staticmethod
    def ParseDeadlines(v:str, tz:timezone) -> tuple[datetime, datetime]:
        deadlines = v.strip().split("/", 1)
        if len(deadlines) != 2:
            raise LitGBException("неправильный формат дедлайнов")
        d1 = datetime.strptime(deadlines[0].strip(), '%d.%m.%Y %H:%M')
        d2 = datetime.strptime(deadlines[1].strip(), '%d.%m.%Y %H:%M')

        d1 = tz.localize(d1)
        d2 = tz.localize(d2)        
        
        return (d1, d2)

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:                
        logging.info("[HANDLE_TEXT] user id "+LitGBot.GetUserTitleForLog(update.effective_user))        

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
            elif not (convers.SetSubjectFor is None):
                new_subj = update.message.text.strip()
                logging.info("[COMP_SETSUBJ] new subject for competition #"+str(convers.SetSubjectFor)+": "+new_subj) 
                if len(new_subj) < 3:
                    raise LitGBException("Тема не может быть меньше трёх символов")
                comp = self.FindPropertyChangableCompetition(convers.SetSubjectFor, update.effective_user.id)
                self.Db.SetCompetitionSubject(comp.Id, new_subj)
                await update.message.reply_text("Новая тема для конкурса #"+str(comp.Id)+" установлена: "+new_subj)
            elif not (convers.SetSubjectExtFor is None):
                new_subjext = update.message.text.strip()
                logging.info("[COMP_SETSUBJEXT] new subject for competition #"+str(convers.SetSubjectExtFor)+": "+new_subjext) 
                if len(new_subjext) < 3:
                    raise LitGBException("Пояснение не может быть меньше трёх символов")
                comp = self.FindPropertyChangableCompetition(convers.SetSubjectExtFor, update.effective_user.id)
                self.Db.SetCompetitionSubjectExt(comp.Id, new_subjext)
                await update.message.reply_text("Новое пояснение для конкурса #"+str(comp.Id)+" установлено:\n\n"+new_subjext)                
            elif  not (convers.InputEntryTokenFor is None):    
                token = update.message.text.strip()
                logging.info("[INPUT_TOKEN] input entry token for competition #"+str(convers.SetSubjectFor)+": "+token) 

                comp = self.FindJoinableCompetition(convers.InputEntryTokenFor)
                if comp.EntryToken != token:
                    raise LitGBException("неправильный входной токен")
                
                comp_stat = self.Db.JoinToCompetition(comp.Id, update.effective_user.id)
                comp = await self.AfterJoinMember(comp, comp_stat, context)
                await update.message.reply_text("Заявлено участие в конкурсе #"+str(comp.Id))
            elif  not (convers.SetDeadlinesFor is None):
                new_deadlines = update.message.text.strip()
                logging.info("[COMP_SETSUBJEXT] new deadlines for competition #"+str(convers.SetDeadlinesFor)+": "+new_deadlines) 
                accept_files_deadline, polling_deadline = self.ParseDeadlines(new_deadlines, self.Timezone)
                comp = self.FindPropertyChangableCompetition(convers.SetDeadlinesFor, update.effective_user.id)
                if not (comp.ChatId is None):
                    if not self.CheckCompetitionDeadlines(comp.ChatId,):
                        raise LitGBException("новые дедлайны пересекаются с дедлайнами других конкурсов")
                    
                comp = self.Db.SetDeadlines(comp.Id, accept_files_deadline, polling_deadline)
                await update.message.reply_text("Дедлайны для конкурса #"+str(comp.Id)+" установлены: "+DatetimeToString(comp.AcceptFilesDeadline)+" / "+DatetimeToString(comp.PollingDeadline))
    
    def GetDefaultAcceptDeadlineForClosedCompetition(self) -> datetime:
        return datetime.now(timezone.utc)+self.DefaultAcceptDeadlineTimedelta
    
    def SelectFirstAvailableAcceptDeadlineForChat(self, chat_id:int, min_ts:datetime, polling_stage_interval_secs:int) -> datetime:
        comps = self.Db.SelectActiveCompetitionsInChat(chat_id, min_ts, min_ts+self.MaxCompetitionDeadlineFutureInterval+timedelta(days=1))
        if len(comps) > 0:
            for i in range(0, len(comps)-1):
                if (comps[i+1].AcceptFilesDeadline - comps[i].PollingDeadline).total_seconds() >= polling_stage_interval_secs:
                    return comps[i].PollingDeadline
            
            return comps[-1].PollingDeadline
        
        return min_ts
    
    @staticmethod
    def CheckDeadlinesIntersection(comp1:CompetitionInfo, comp2:CompetitionInfo) -> bool:
        if (comp1.AcceptFilesDeadline <= comp2.PollingDeadline) and (comp1.AcceptFilesDeadline >= comp2.AcceptFilesDeadline):
            return False
        
        if (comp1.PollingDeadline <= comp2.PollingDeadline) and (comp1.PollingDeadline >= comp2.AcceptFilesDeadline):
            return False
        
        if (comp1.PollingDeadline >= comp2.PollingDeadline) and (comp1.AcceptFilesDeadline <= comp2.AcceptFilesDeadline):
            return False
        
        return True
    
    def CheckCompetitionDeadlines(self, chat_id:int, comp:CompetitionInfo) -> bool:
        comps = self.Db.SelectActiveCompetitionsInChat(chat_id, comp.AcceptFilesDeadline, comp.AcceptFilesDeadline+self.MaxCompetitionDeadlineFutureInterval+timedelta(days=1))
        for c in comps:
            if self.CheckDeadlinesIntersection(comp, c):
                return False

        return True
    
    async def AfterStartCompetition(self, comp:CompetitionInfo, context: ContextTypes.DEFAULT_TYPE):

        await self.ReportCompetitionStateToAttachedChat(comp, context)
    
    async def AfterConfirmCompetition(self, comp:CompetitionInfo, context: ContextTypes.DEFAULT_TYPE):
        await self.ReportCompetitionStateToAttachedChat(comp, context)

        if comp.IsClosedType():
            if comp.ChatId is None:
                return
        
        comp = self.Db.StartCompetition(comp.Id)
        await self.AfterStartCompetition(comp, context)
    
    async def CheckClosedCompetitionConfirmation(self, 
            comp:CompetitionInfo, comp_stat:CompetitionStat, context: ContextTypes.DEFAULT_TYPE) -> CompetitionInfo:
         
         if (len(comp_stat.RegisteredMembers) >= comp.DeclaredMemberCount) and (not (comp.ChatId is None)):
            comp = self.Db.ConfirmCompetition(comp.Id)
            await self.AfterConfirmCompetition(comp, context)
            
         return comp
    
    async def AfterJoinMember(self, comp:CompetitionInfo, comp_stat:CompetitionStat, context: ContextTypes.DEFAULT_TYPE) -> CompetitionInfo:
        if comp.IsClosedType():
            return await self.CheckClosedCompetitionConfirmation(comp, comp_stat, context)
        
        return comp
    
    async def AfterCompetitionAttach(self, comp:CompetitionInfo, context: ContextTypes.DEFAULT_TYPE) -> CompetitionInfo:
        if comp.IsOpenType():
            comp = self.Db.ConfirmCompetition(comp.Id)
            await self.AfterConfirmCompetition(comp, context)
            return comp
        else:
            stat = self.Db.GetCompetitionStat(comp.Id)
            return await self.CheckClosedCompetitionConfirmation(comp, stat, context)        

    async def create_closed_competition(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[CREATECLOSED] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        self.CreateCompetitionLimits.Check(update.effective_user.id, update.effective_chat.id)
        
        self.Db.EnsureUserExists(update.effective_user.id, self.MakeUserTitle(update.effective_user))
        
        member_count = self.ParseSingleIntArgumentCommand(update.message.text, "/create_closed_competition", 2, 15)
        chat_id = update.effective_chat.id
        if chat_id == update.effective_user.id:
            chat_id = None
        accept_deadline = self.GetDefaultAcceptDeadlineForClosedCompetition()
        if not (chat_id is None):
            self.Db.EnsureChatExists(update.effective_chat.id, self.MakeChatTitle(update.effective_chat)) 
            accept_deadline = self.SelectFirstAvailableAcceptDeadlineForChat(chat_id, accept_deadline, 172800)
        comp = self.Db.CreateCompetition(
            update.effective_user.id, 
            chat_id, 
            accept_deadline,
            accept_deadline+self.DefaultPollingStageTimedelta,
            GetRandomString(12),
            self.DefaultMinTextSize,
            self.DefaultMaxTextSize,
            member_count,
            "тема не задана")
        logging.info("[CREATECLOSED] competition created with id "+str(comp.Id))
        if not (chat_id is None):
            comp = await self.AfterCompetitionAttach(comp, context)
        await update.message.reply_text("Создан новый закрытый конкурс #"+str(comp.Id)) 
          
        
    async def create_open_competition(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[CREATEOPEN] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        self.CreateCompetitionLimits.Check(update.effective_user.id, update.effective_chat.id)
        self.CheckPrivateOnly(update)
        self.Db.EnsureUserExists(update.effective_user.id, self.MakeUserTitle(update.effective_user))

        
        accept_deadline = self.GetDefaultAcceptDeadlineForClosedCompetition()        
        comp = self.Db.CreateCompetition(
            update.effective_user.id, 
            None, 
            accept_deadline,
            accept_deadline+self.DefaultPollingStageTimedelta,
            GetRandomString(12),
            self.DefaultMinTextSize,
            self.DefaultMaxTextSize,
            None,
            "тема не задана")
        logging.info("[CREATEOPEN] competition created with id "+str(comp.Id))        
        await update.message.reply_text("Создан новый открытый конкурс #"+str(comp.Id)) 
       
        
    async def attach_competition(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[ATTACH] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        self.CompetitionChangeLimits.Check(update.effective_user.id, update.effective_chat.id)
        if update.effective_user.id == update.effective_chat.id:
            await update.message.reply_text("⛔️ Выполнение команды в личных сообщениях бота лишено смысла")
        self.Db.EnsureChatExists(update.effective_chat.id, self.MakeChatTitle(update.effective_chat))    

        comp_id = self.ParseSingleIntArgumentCommand(update.message.text, "/attach_competition")
        comp = self.FindNotAttachedCompetition(comp_id)
        if comp.CreatedBy != update.effective_user.id:
            raise LitGBException("Привязывать конкурс к чату может только создатель конкурса")
        if not self.CheckCompetitionDeadlines(update.effective_chat.id, comp):
            raise LitGBException("Нельзя привязать конкурс к чату, если его период голосования пересекается с периодами голосования других конкурсов в чате")
        comp = self.Db.AttachCompetition(comp.Id, update.effective_chat.id)
        await self.AfterCompetitionAttach(comp, context)
        await update.message.reply_text("Конкурс #"+str(comp.Id)+" привязан к текущему чату") 
                    

        
    async def competitions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[COMPS] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        self.CompetitionViewLimits.Check(update.effective_user.id, update.effective_chat.id)
        
        list_type = "allactiveattached"
        if update.effective_user.id != update.effective_chat.id:            
            list_type = "chatrelated"

        comp_list = self.GetCompetitionList(list_type, update.effective_user.id, update.effective_chat.id)        
        comp = comp_list[0]
        comp_info = self.GetCompetitionFullInfo(comp)
        await update.message.reply_text(
            self.comp_menu_message(comp_info, update.effective_user.id, update.effective_chat.id), 
            reply_markup=self.comp_menu_keyboard(list_type, 0, comp_info.Stat, comp_list, update.effective_user.id, update.effective_chat.id))


    async def competition(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[COMP] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        self.CompetitionViewLimits.Check(update.effective_user.id, update.effective_chat.id)
        
        comp_id = self.ParseSingleIntArgumentCommand(update.message.text, "/competition")    

        comp = self.FindCompetition(comp_id)
        comp_info = self.GetCompetitionFullInfo(comp)                      
        await update.message.reply_text(
            self.comp_menu_message(comp_info, update.effective_user.id, update.effective_chat.id), 
            reply_markup=self.comp_menu_keyboard("singlemode", 0, comp_info.Stat, [comp], update.effective_user.id, update.effective_chat.id))
        
    async def current_competition(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[CURRENT] user id "+LitGBot.GetUserTitleForLog(update.effective_user))     
        self.CompetitionViewLimits.Check(update.effective_user.id, update.effective_chat.id)
        if update.effective_user.id == update.effective_chat.id:
            await update.message.reply_text("⛔️ Выполнение команды в личных сообщениях бота лишено смысла")

        
    async def mycompetitions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[MYCOMPS] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        self.CompetitionViewLimits.Check(update.effective_user.id, update.effective_chat.id)
        self.CheckPrivateOnly(update)         

        comp_list = self.GetCompetitionList("my", update.effective_user.id, update.effective_chat.id)        
        if len(comp_list) == 0:
            await update.message.reply_text("нет конкурсов")
        comp = comp_list[0]
        comp_info = self.GetCompetitionFullInfo(comp)
        await update.message.reply_text(
            self.comp_menu_message(comp_info, update.effective_user.id, update.effective_chat.id), 
            reply_markup=self.comp_menu_keyboard("my", 0, comp_info.Stat, comp_list, update.effective_user.id, update.effective_chat.id))

    async def joinable_competitions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[JCOMPS] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        self.CompetitionViewLimits.Check(update.effective_user.id, update.effective_chat.id)

        # список конкурсов, в которым можно присоединиться
        raise LitGBException("команда в разработке")
    
    def ParseJoinToCompetitionCommand(self, msg:str) -> tuple[int, str]:        
        try:
            m = self.JoinToCompetitionCommandRegex.match(msg)
            return (int(m.group(1)), m.group(2))
        except BaseException as ex:
            raise LitGBException("Некорректный формат команды /join") 

    def FindCompetition(self, comp_id:int) -> CompetitionInfo:     
        comp = self.Db.FindCompetition(comp_id)
        if comp is None:
            raise CompetitionNotFound(comp_id)
        return comp


    def FindNotFinishedCompetition(self, comp_id:int) -> CompetitionInfo:
        comp = self.FindCompetition(comp_id)
        if comp.Finished is None:
            return comp
        
        raise LitGBException("Конкурс уже завершён")    


    
    def FindCompetitionBeforePollingStage(self, comp_id:int) -> CompetitionInfo:
        comp = self.FindNotFinishedCompetition(comp_id)
        if not comp.IsPollingStarted():
            return comp
        
        raise LitGBException("Конкурс в стадии голосования")
    
    @staticmethod
    def IsCompetitionСancelable(comp:CompetitionInfo) -> str|None:
        if comp.IsPollingStarted():
            return "конкурс нельзя отменить в стадии голосования"
        
        if comp.IsClosedType():
            if comp.Confirmed:
                return "Закрытый конкурс нельзя отменить после подтверждения всех участников"
            
            
        return None
            
    
    def FindCancelableCompetition(self, comp_id:int) -> CompetitionInfo:
        comp = self.FindCompetitionBeforePollingStage(comp_id)

        reason = self.IsCompetitionСancelable(comp)
        if reason is None:
            return comp
        raise LitGBException(reason)
    
    @staticmethod
    def IsCompetitionPropertyChangable(comp: CompetitionInfo) -> str|None:
        if not (comp.Started is None):
            return "Конкурс стартовал, изменить его свойства уже нельзя"
        
    @staticmethod
    def EnsureCompetitionCreator(comp: CompetitionInfo, user_id:int) -> str|None:
        if comp.CreatedBy != user_id:
            raise LitGBException("изменение свойств конкурса разрешено только его создателю")
    
    def FindPropertyChangableCompetition(self, comp_id:int, check_creator:int|None) -> CompetitionInfo:
        comp = self.FindCompetitionBeforePollingStage(comp_id)

        if not (check_creator is None):
            self.EnsureCompetitionCreator(comp, check_creator)

        reason = self.IsCompetitionPropertyChangable(comp)
        if reason is None:
            return comp
        
        raise LitGBException(reason)
    
    def FindNotAttachedCompetition(self, comp_id:int) -> CompetitionInfo:
        comp = self.FindCompetitionBeforePollingStage(comp_id)
        if not (comp.ChatId is None):
            raise LitGBException("Конкурс уже привязан ")
        if not (comp.Started is None):
            raise LitGBException("Конкурс уже стартовал, а значит его уже нельзя привязать ни к какому чату")
        return comp
    

    @staticmethod
    def IsCompetitionJoinable(comp:CompetitionInfo) -> str|None:
        if comp.IsOpenType():        
            if comp.Confirmed is None:
                return "к конкурсу нельзя присоединиться"
            if datetime.now(timezone.utc) >= comp.AcceptFilesDeadline:
                return "прошёл дедлайн отправки работ"
        else:            
            if not (comp.Confirmed is None):
                return "к конкурсу нельзя присоединиться"

        return None
    
    @staticmethod
    def CheckCompetitionLeaveable(comp:CompetitionInfo) -> str|None:
        if not (comp.PollingStarted is None):
            return "нельзя выйти из конкурса на стадии голосования"

        if comp.IsClosedType():  
            if not (comp.Started is None):
                return "из закрытого конкурса нельзя выйти в после того, как он стартовал" 

        return None       
      
    def FindJoinableCompetition(self, comp_id:int) -> CompetitionInfo:
        comp = self.FindCompetitionBeforePollingStage(comp_id)

        reason = self.IsCompetitionJoinable(comp)
        if reason is None:
            return comp
            
        raise LitGBException(reason)
    
    def FindFileAcceptableCompetition(self, id:int) -> CompetitionInfo:
        comp = self.FindCompetitionBeforePollingStage(id)
        if comp.Started is None:
            raise LitGBException("конкурс ещё не стартовал, приём файлов возможен только в стартовавший конкурс")
        return comp   


    async def join_to_competition(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[JOIN] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        self.CompetitionViewLimits.Check(update.effective_user.id, update.effective_chat.id)

        comp_id, token = self.ParseJoinToCompetitionCommand(update.message.text)
        comp = self.FindJoinableCompetition(comp_id)
        if comp.CreatedBy != update.effective_user.id:
            if not (comp.EntryToken is None):
                if len(comp.EntryToken) > 0:
                    if comp.EntryToken != token:
                        raise LitGBException("неправильный входной токен")
        comp_stat = self.Db.JoinToCompetition(comp_id, update.effective_user.id)
        comp = await self.AfterJoinMember(comp, comp_stat, context)
        await update.message.reply_text("Заявлено участие в конкурсе #"+str(comp.Id))

    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update is None:
            logging.warning("Exception: ", exc_info=context.error)
        else:    
            logging.warning("Exception: user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat), exc_info=context.error)

        
        if isinstance(context.error, OnlyPrivateMessageAllowed):
            await update.message.reply_text(str(context.error))
            return

        if isinstance(context.error, CommandRateLimitReached):
            await update.message.reply_text(str(context.error))
            return

        if isinstance(context.error, LitGBException):           
            await update.message.reply_text(self.MakeErrorMessage(context.error)) 
            return  

        if isinstance(context.error, BaseException):
            logging.error("EXCEPTION: "+str(context.error,))
            tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
            tb_string = "".join(tb_list)
            logging.warning("Exception traceback:" + tb_string)            
            await update.message.reply_text(self.MakeExternalErrorMessage(context.error))
            return
        

    def ParseCompetitionMenuQuery(self, query:str) -> tuple[str, str, int]:
        try:
            m = self.CompetitionMenuQueryRegex.match(query)
            return (m.group(1), m.group(2), int(m.group(3)))
        except BaseException as ex:
            raise LitGBException("invalid comp menu query")  
        
    @staticmethod
    def IsMemberRegisteredInCompetition(comp_stat:CompetitionStat, user_id) -> bool:    
        for m in comp_stat.RegisteredMembers:
            if m.Id == user_id:
                return True
        return False

    
    def comp_menu_keyboard(self, 
            list_type:str, 
            comp_index:int, 
            comp_stat:CompetitionStat, 
            comp_list:list[CompetitionInfo], 
            user_id:str, 
            chat_id:int):

        keyboard = []

        list_buttons_line = []
        if comp_index > 0:
            list_buttons_line.append(InlineKeyboardButton('<=', callback_data='comp_'+list_type+'_show_'+str(comp_list[comp_index-1].Id)))
        if comp_index < len(comp_list)-1:
            list_buttons_line.append(InlineKeyboardButton('=>', callback_data='comp_'+list_type+'_show_'+str(comp_list[comp_index+1].Id)))
        if len(list_buttons_line) > 0:
            keyboard.append(list_buttons_line)  
        ###
        comp = comp_list[comp_index]
        if user_id == chat_id:
            if user_id == comp.CreatedBy :
                if LitGBot.IsCompetitionPropertyChangable(comp) is None:            
                    keyboard.append([InlineKeyboardButton('Установить тему', callback_data='comp_'+list_type+'_setsubject_'+str(comp.Id))]) 
                    keyboard.append([InlineKeyboardButton('Установить пояснение', callback_data='comp_'+list_type+'_setsubjectext_'+str(comp.Id))]) 
                    keyboard.append([InlineKeyboardButton('Установить дедлайны', callback_data='comp_'+list_type+'_setdeadlines_'+str(comp.Id))])

                    min_text_size_change_kbd = []
                    if comp.MinTextSize > self.MinTextSize:
                        min_text_size_change_kbd.append(InlineKeyboardButton('MIN --', callback_data='comp_'+list_type+'_mintextdec_'+str(comp.Id)))
                    if comp.MinTextSize + self.TextLimitChangeStep < comp.MaxTextSize:
                        min_text_size_change_kbd.append(InlineKeyboardButton('MIN ++', callback_data='comp_'+list_type+'_mintextinc_'+str(comp.Id)))

                    if len(min_text_size_change_kbd) > 0:
                        keyboard.append(min_text_size_change_kbd)

                    max_text_size_change_kbd = []
                    if comp.MaxTextSize - self.TextLimitChangeStep > comp.MinTextSize:
                        max_text_size_change_kbd.append(InlineKeyboardButton('MAX --', callback_data='comp_'+list_type+'_maxtextdec_'+str(comp.Id)))                
                    if comp.MaxTextSize < self.MaxTextSize:
                        max_text_size_change_kbd.append(InlineKeyboardButton('MAX ++', callback_data='comp_'+list_type+'_maxtextinc_'+str(comp.Id)))

                    if len(max_text_size_change_kbd) > 0:
                        keyboard.append(max_text_size_change_kbd)  

                    if comp.IsOpenType():
                        max_files_change_kbd = []
                        if comp.MaxFilesPerMember > 1:
                            max_files_change_kbd.append(InlineKeyboardButton('MAXFILES --', callback_data='comp_'+list_type+'_maxfilesdec_'+str(comp.Id)))                
                        if comp.MaxFilesPerMember < 10:
                            max_files_change_kbd.append(InlineKeyboardButton('MAXFILES ++', callback_data='comp_'+list_type+'_maxfilesinc_'+str(comp.Id)))

                        if len(max_files_change_kbd) > 0:
                            keyboard.append(max_files_change_kbd)


                if LitGBot.IsCompetitionСancelable(comp) is None:            
                    keyboard.append([InlineKeyboardButton('Отменить', callback_data='comp_'+list_type+'_cancel_'+str(comp.Id))])
        
            if self.IsCompetitionJoinable(comp) is None:
                if not self.IsMemberRegisteredInCompetition(comp_stat, user_id):
                    keyboard.append([InlineKeyboardButton('Присоединиться', callback_data='comp_'+list_type+'_join_'+str(comp.Id))])

            if self.CheckCompetitionLeaveable(comp) is None:
                if self.IsMemberRegisteredInCompetition(comp_stat, user_id):
                    keyboard.append([InlineKeyboardButton('Выйти', callback_data='comp_'+list_type+'_leave_'+str(comp.Id))])

        return InlineKeyboardMarkup(keyboard)
       

    def GetCompetitionList(self, list_type:str, user_id:int, chat_id:int) -> list[CompetitionInfo]:

        after = datetime.now(timezone.utc) - self.CompetitionsListDefaultPastInterval
        before = datetime.now(timezone.utc) + self.CompetitionsListDefaultFutureInterval        

        if list_type == "chatrelated":
            return self.Db.SelectChatRelatedCompetitions(chat_id, after, before)
        elif list_type == "allactiveattached":
            return self.Db.SelectActiveAttachedCompetitions(after, before)
        elif list_type == "my":
            return self.Db.SelectUserRelatedCompetitions(user_id, after, before)        
        
        raise LitGBException("unknown competitions list type: "+list_type)    
    
    def comp_menu_message(self, comp_info:CompetitionFullInfo, user_id:int, chat_id:int) -> str:        
        result = "#" + str(comp_info.Comp.Id)
        if comp_info.Comp.Canceled:
            result += " ОТМЕНЁН"
        result +="\nТип: "
        if comp_info.Comp.IsClosedType():
            result +="дуэль/жюри"
        else:
            result +="самосуд"    

        result +="\nСоздан: " + DatetimeToString(comp_info.Comp.Created)
        if not (comp_info.Comp.Confirmed is None):
            result +="\nПодтверждён: " + DatetimeToString(comp_info.Comp.Confirmed)
        if not (comp_info.Comp.Started is None):
            result +="\nЗапущен: " + DatetimeToString(comp_info.Comp.Started)    

        if not (comp_info.Chat is None):
            result +="\nКонфа: " + comp_info.Chat.Title
        result +="\nТема: " + comp_info.Comp.Subject
        if not (comp_info.Comp.SubjectExt is None):
            result +="\nПояснение:\n\n" + comp_info.Comp.SubjectExt
        result +="\nДедлайн приёма работ: " + DatetimeToString(comp_info.Comp.AcceptFilesDeadline)
        result +="\nДедлайн голосования: " + DatetimeToString(comp_info.Comp.PollingDeadline)
        result +="\nМинимальный размер текста: " + str(comp_info.Comp.MinTextSize)
        result +="\nМаксимальный размер текста: " + str(comp_info.Comp.MaxTextSize)        
        result +="\nМаксимум работ с одного участника: " + str(comp_info.Comp.MaxFilesPerMember)
        if comp_info.Comp.CreatedBy == chat_id:
            result +="\nВходной токен: " + comp_info.Comp.EntryToken

        if user_id == chat_id:
            if self.IsMemberRegisteredInCompetition(comp_info.Stat, user_id):
                result +="\nВЫ УЧАСТВУЕТЕ В ЭТОМ КОНКУРСЕ"

                user_files = comp_info.Stat.SubmittedFiles.get(user_id, [])
                if len(user_files) > 0:
                    result +="\nВаши файлы на этом конкурсе:"
                    i = 0
                    for f in comp_info.Stat.SubmittedFiles[user_id]:
                        i += 1
                        result +="\n"+str(i)+". ("+str(MakeHumanReadableAmount(f.TextSize))+") "+f.Title
                else:
                    result +="\nВы ещё не прикрепляли файлы к конкурсу"

        
        result +="\nЗарегистрированных участников : " + str(len(comp_info.Stat.RegisteredMembers))        

        if comp_info.Comp.IsClosedType() and (len(comp_info.Stat.RegisteredMembers) > 0):
            result +="\nСписок участников:"
            i = 0
            for m in comp_info.Stat.RegisteredMembers:
                i += 1
                result +="\n"+str(i)+": "+m.Title
        else:
            result +="\nКол-во участников приславших рассказы: " + str(len(comp_info.Stat.SubmittedMembers))    
            result +="\nКол-во присланных рассказов: " + str(comp_info.Stat.SubmittedFileCount)  


        if comp_info.Comp.IsOpenType() or comp_info.Comp.IsPollingStarted():
            result +="\nСуммарно присланный текст: " + str(comp_info.Stat.TotalSubmittedTextSize)
        

        return result
    
    async def ReportCompetitionStateToAttachedChat(self, 
            comp:CompetitionInfo, 
            context: ContextTypes.DEFAULT_TYPE, 
            message:str|None = None):
        
        if comp.ChatId is None:
            return
        
        if comp.Finished:            
            if comp.Canceled:
                message_text = "Конкурс #"+str(comp.Id)+" отменён"
                if not (message is None):
                    message_text += "\n\nПричина: "+ message                   
                await context.bot.send_message(comp.ChatId, message_text)
            else:    
                await context.bot.send_message(comp.ChatId, "Конкурс #"+str(comp.Id)+" завершён")
            return
        
        if not (comp.PollingStarted) is None:
            await context.bot.send_message(comp.ChatId, "Конкурс #"+str(comp.Id)+" перешёл в стадию голосования. Дедлайн: "+DatetimeToString(comp.PollingDeadline))
            return

    
    def CancelCompetition(self, comp_id:int) -> CompetitionInfo:
        comp = self.FindCancelableCompetition(comp_id)
        return self.Db.FinishCompetition(comp.Id, True)
        
    
    def ValidateTextLimits(self, comp:CompetitionInfo):
        if comp.MinTextSize >= comp.MaxTextSize:
            raise LitGBException("минимальное размер текста должен быть меньше, чем максимальный размер")
        if comp.MinTextSize < self.MinTextSize:
            raise LitGBException("минимальный размер текста не может быть меньше, чем "+str(self.MinTextSize))
        if comp.MaxTextSize > self.MaxTextSize:
            raise LitGBException("максимальный размер текста не может быть больше, чем "+str(self.MaxTextSize))        
        if comp.MaxFilesPerMember < 1:
            raise LitGBException("максимум работ с участника не может быть меньше одного")        
        if comp.IsClosedType() and (comp.MaxFilesPerMember != 1):
            raise LitGBException("в закрытых конкурсах максимум файлов с участника должен быть всегда 1")
        if comp.MaxFilesPerMember > 10:
            raise LitGBException("максимум работ с участника не может быть больше 10")        
        
    @staticmethod
    def GetIndex(comp:CompetitionInfo, comp_list:list[CompetitionInfo]) -> int:
        comp_index = -1
        for i, v in enumerate(comp_list): 
            if v.Id == comp.Id:
                comp_index = i
                break

        if comp_index < 0:
            raise LitGBException("competition not found in competition list")
        return comp_index
    
    def GetCompetitionFullInfo(self, comp:CompetitionInfo) -> CompetitionFullInfo:
        stat = self.Db.GetCompetitionStat(comp.Id)
        chat = None
        if not (comp.ChatId is None):
            chat = self.Db.FindChat(comp.ChatId)
        return CompetitionFullInfo(comp, stat, chat)
    
    def ReleaseUserFilesFromCompetition(self, user_id: int, comp:CompetitionInfo) -> CompetitionFullInfo:
        raise NotImplementedError("ReleaseUserFilesFromCompetition")
                
    async def comp_menu_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: 
        logging.info("[comp_menu_handler] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 

        query = update.callback_query              

        await query.answer()
        try:
            (list_type, action, comp_id) = self.ParseCompetitionMenuQuery(query.data)

            if action == "show":

                comp = self.FindCompetition(comp_id)
                if list_type == "singlemode":
                    comp_list = [comp]                    
                else:    
                    comp_list = self.GetCompetitionList(list_type, update.effective_user.id, update.effective_chat.id)
                
                comp_index = self.GetIndex(comp, comp_list)                
                comp_info = self.GetCompetitionFullInfo(comp)
                
                await query.edit_message_text(
                    text=self.comp_menu_message(comp_info, update.effective_user.id, update.effective_chat.id),
                    reply_markup=self.comp_menu_keyboard(list_type, comp_index, comp_info.Stat, comp_list, update.effective_user.id, update.effective_chat.id))
            elif action == "cancel":                
                comp = self.CancelCompetition(comp_id)
                
                comp_info = self.GetCompetitionFullInfo(comp)
                await self.ReportCompetitionStateToAttachedChat(comp, context)
                await query.edit_message_text(
                    text=self.comp_menu_message(comp_info, update.effective_user.id, update.effective_chat.id), 
                    reply_markup=InlineKeyboardMarkup([]))  
                
            elif (action == "mintextdec") or (action == "mintextinc") or (action == "maxtextdec") or (action == "maxtextinc") or (action == "maxfilesdec") or (action == "maxfilesinc"):
                comp = self.FindPropertyChangableCompetition(comp_id, update.effective_user.id)

                if action == "mintextdec":
                    comp.MinTextSize -= self.TextLimitChangeStep
                elif action == "mintextinc":
                    comp.MinTextSize += self.TextLimitChangeStep
                elif action == "maxtextdec":
                    comp.MaxTextSize -= self.TextLimitChangeStep
                elif action == "maxtextinc":
                    comp.MaxTextSize += self.TextLimitChangeStep
                elif action == "maxfilesdec":
                    comp.MaxFilesPerMember -= 1
                elif action == "maxfilesinc":
                    comp.MaxFilesPerMember += 1

                self.ValidateTextLimits(comp)    
                                
                list_type = "singlemode"
                comp_list = [comp]
                comp_index = self.GetIndex(comp, comp_list)
                comp = self.Db.SetCompetitionTextLimits(comp.Id, comp.MinTextSize, comp.MaxTextSize, comp.MaxFilesPerMember)
                comp_info = self.GetCompetitionFullInfo(comp)
                await query.edit_message_text(
                    text=self.comp_menu_message(comp_info, update.effective_user.id, update.effective_chat.id),
                    reply_markup=self.comp_menu_keyboard(list_type, comp_index, comp_info.Stat, comp_list, update.effective_user.id, update.effective_chat.id))
             
            elif action == "setdeadlines":
                comp = self.FindPropertyChangableCompetition(comp_id, update.effective_user.id)
                uconv = UserConversation()
                uconv.SetDeadlinesFor = comp.Id
                self.UserConversations[update.effective_user.id] = uconv
                await query.edit_message_text(
                    text="Введите две отметки времени разделённых знаком \"/\". Первая дедлайн приёма работа, вторая дедлайн голосования. Формат отметки времени: ДД.ММ.ГГГГ Час:Минута\n Время принимается в зоне Europe/Moscow\n\nНапример: 27.11.2024 23:46/30.11.2024 22:41", reply_markup=InlineKeyboardMarkup([]))
            elif action == "setsubject":  
                comp = self.FindPropertyChangableCompetition(comp_id, update.effective_user.id)
                uconv = UserConversation()
                uconv.SetSubjectFor = comp.Id
                self.UserConversations[update.effective_user.id] = uconv
                await query.edit_message_text(
                    text="Введите новую тему", reply_markup=InlineKeyboardMarkup([]))
            elif action == "setsubjectext":  
                comp = self.FindPropertyChangableCompetition(comp_id, update.effective_user.id)
                uconv = UserConversation()
                uconv.SetSubjectExtFor = comp.Id
                self.UserConversations[update.effective_user.id] = uconv
                await query.edit_message_text(
                    text="Введите новое пояснение для конкурса", reply_markup=InlineKeyboardMarkup([]))                               
            elif action == "join":
                comp = self.FindJoinableCompetition(comp_id)
                if comp.CreatedBy == update.effective_user.id:                    
                    comp_stat = self.Db.JoinToCompetition(comp_id, update.effective_user.id)
                    comp = await self.AfterJoinMember(comp, comp_stat, context)
                    await query.edit_message_text(
                        text="Заявлено участие в конкурсе #"+str(comp.Id), reply_markup=InlineKeyboardMarkup([]))                                  
                else:
                    uconv = UserConversation()
                    uconv.InputEntryTokenFor = comp.Id
                    self.UserConversations[update.effective_user.id] = uconv
                    await query.edit_message_text(
                        text="Введите токен для входа в конкурс", reply_markup=InlineKeyboardMarkup([]))  
            elif action == "leave":
                comp = self.FindLeavableCompetition(comp_id)
                raise NotImplementedError("action == leave")
            elif action == "releasefiles":
                comp = self.FindFileAcceptableCompetition(comp_id)
                comp_info = self.ReleaseUserFilesFromCompetition(update.effective_user.id, comp)
                list_type = "singlemode"
                comp_list = [comp]
                comp_index = self.GetIndex(comp, comp_list)
                await query.edit_message_text(
                    text=self.comp_menu_message(comp_info, update.effective_user.id, update.effective_chat.id),
                    reply_markup=self.comp_menu_keyboard(list_type, comp_index, comp_info.Stat, comp_list, update.effective_user.id, update.effective_chat.id))  
            else:
                raise LitGBException("unknown menu action: "+action)
            

        except LitGBException as ex:
            await query.edit_message_text(
                text=self.error_menu_message(ex), reply_markup=InlineKeyboardMarkup([]))                    
        except BaseException as ex:    
            logging.error("[comp_menu_handler] user id "+LitGBot.GetUserTitleForLog(update.effective_user)+ ". EXCEPTION: "+str(ex))       
            await query.edit_message_text(
                text=LitGBot.MakeExternalErrorMessage(ex), reply_markup=InlineKeyboardMarkup([]))        
          
    @staticmethod      
    def CheckCompetitionEndCondition(comp:CompetitionInfo, stat:CompetitionStat) -> bool:
        if comp.IsClosedType():
            return len(stat.SubmittedMembers) < 2
        else:
            return len(stat.SubmittedMembers) < 3
        
    async def CancelCompetitionWithError(self, comp: CompetitionInfo, error:str, context: ContextTypes.DEFAULT_TYPE):
        self.Db.FinishCompetition(comp.Id, True)
        await self.ReportCompetitionStateToAttachedChat(comp, context)        

    async def FinalizeSuccessCompetition(self, comp:CompetitionInfo, context: ContextTypes.DEFAULT_TYPE):

        await self.ReportCompetitionStateToAttachedChat(comp, context)

    async def ProcessFailedMembers(self, comp:CompetitionInfo, context: ContextTypes.DEFAULT_TYPE):
        pass
            
    async def SwitchToPollingStage(self, comp:CompetitionInfo, context: ContextTypes.DEFAULT_TYPE):
        if comp.Confirmed is None:
            LitGBException("У конкурса наступил дедлайн приёма файлов, но он не перешёл в стадию \"подтверждён\"")
        if comp.Started is None:
            LitGBException("У конкурса наступил дедлайн приёма файлов, но он не перешёл в стадию \"стартовал\"")
        if comp.IsPollingStarted():
            LitGBException("Конкурса наступил дедлайн приёма файлов, но он уже перешёл в стадию \"голосование\"")

        self.Db.SwitchToPollingStage(comp.Id)
        if comp.IsClosedType():
            await self.ProcessFailedMembers(comp, context)
        com_stat = self.Db.RemoveMembersWithoutFiles(comp.Id)
        if self.CheckCompetitionEndCondition(comp, com_stat):
            await self.FinalizeSuccessCompetition(comp, context)
            return
        
        await self.ReportCompetitionStateToAttachedChat(comp, context)        

        
        # выложить файлы по отдельности
        # выложить один файл со всеми рассказами      


            
    async def CheckPollingStageStart(self, context: ContextTypes.DEFAULT_TYPE):
        logging.info("CheckPollingStageStart:")
        comp_list = self.Db.SelectReadyToPollingStageCompetitions()
        for comp in comp_list:
            try:
                self.SwitchToPollingStage(comp, context)
            except LitGBException as ex:
                logging.error("CheckPollingStageStart: ERROR on CheckPollingStageStart competition #"+str(comp.Id)+ ": "+str(ex))
                logging.error("CheckPollingStageStart: cancel competition #"+str(comp.Id)+ " due error on switch to polling stage")
                await self.CancelCompetitionWithError(comp, str(ex), context)
            except BaseException as ex:
                logging.error("CheckPollingStageStart: EXCEPTION on CheckPollingStageStart competition #"+str(comp.Id)+ ": "+str(ex))       

    def FinalizeCompetitionPolling(self, comp:CompetitionInfo, context: ContextTypes.DEFAULT_TYPE):
        if not comp.IsPollingStarted():
            LitGBException("У конкурса наступил дедлайн голосования, но он не перешёл в стадию \"голосование\"")

    async def CheckPollingStageEnd(self, context: ContextTypes.DEFAULT_TYPE):
        logging.info("CheckPollingStageEnd:")
        comp_list = self.Db.SelectPollingDeadlinedCompetitions()
        for comp in comp_list:
            try:
                self.FinalizeCompetitionPolling(comp, context)
            except LitGBException as ex:
                logging.error("CheckPollingStageEnd: ERROR on FinalizeCompetitionPolling competition #"+str(comp.Id)+ ": "+str(ex))
                logging.error("CheckPollingStageEnd: cancel competition #"+str(comp.Id)+ " due error on finalize polling stage")
                await self.CancelCompetitionWithError(comp, str(ex), context)
            except BaseException as ex:
                logging.error("CheckPollingStageEnd: EXCEPTION on FinalizeCompetitionPolling competition #"+str(comp.Id)+ ": "+str(ex))          
            
    async def CheckCompetitionStates(self, context: ContextTypes.DEFAULT_TYPE):
        await self.CheckPollingStageStart(context)    
        await self.CheckPollingStageEnd(context)  
            
    async def event_five_minutes(self, context: ContextTypes.DEFAULT_TYPE):
        logging.info("event_five_minutes:")
        await self.CheckCompetitionStates(context)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    parser = argparse.ArgumentParser(
        prog = 'LitGBot', description = '''Literature games bot''', epilog = '''(c) 2025''')   


    parser.add_argument ('--conf', dest='conf', action="store", type=str, required=True)

    args = parser.parse_args()

    
    with open(args.conf, 'r') as file:
        conf = json.load(file)

       
    file_str = FileStorage(conf['file_storage'])

    db = DbWorkerService(conf['db'])

    app = ApplicationBuilder().token(conf['bot_token']).build()

    bot = LitGBot(db, file_str, conf['admin'])   

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
    app.add_handler(CommandHandler("competition", bot.competition))  
    app.add_handler(CommandHandler("current_competition", bot.current_competition))  
    app.add_handler(CommandHandler("joinable_competitions", bot.joinable_competitions))
    app.add_handler(CommandHandler("join", bot.join_to_competition))
    app.add_handler(CommandHandler("mycompetitions", bot.mycompetitions))

    #ADMINS
    app.add_handler(CommandHandler("set_filelimit", bot.set_file_limit))    
    app.add_handler(CommandHandler("set_allusers_filelimit", bot.set_allusers_file_limit))   
    app.add_handler(CommandHandler("kill", bot.kill_competition))

    app.add_handler(CallbackQueryHandler(bot.file_menu_handler, pattern="file_\\S+"))
    app.add_handler(CallbackQueryHandler(bot.comp_menu_handler, pattern="comp_\\S+"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_text))
    
    app.add_handler(MessageHandler(filters.Document.ALL, bot.downloader))    

    job_minute = app.job_queue.run_repeating(bot.event_five_minutes, interval=60*5, first=5)

    app.add_error_handler(bot.error_handler)

    app.run_polling()
    