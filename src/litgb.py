from telegram import Update, User, Chat, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
import argparse
from db_worker import DbWorkerService, FileInfo, CompetitionInfo, CompetitionStat, ChatInfo, UserInfo
import logging
import json
import time
import os
from datetime import timedelta, datetime, timezone
from litgb_exception import LitGBException, FileNotFound, OnlyPrivateMessageAllowed
from zoneinfo import ZoneInfo
from file_storage import FileStorage
from fb2_tool import FileToFb2Section
from utils import GetRandomString, MakeHumanReadableAmount, DatetimeToString, TimedeltaToString
import re
import traceback
import pytz
from competition_worker import ComepetitionWorker, CompetitionFullInfo
from competition_service import CompetitionService

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

class LitGBot(CompetitionService):
    def __init__(self, db_worker:DbWorkerService, file_stor:FileStorage, admin:dict, defaults:dict):
        CompetitionService.__init__(self, db_worker, file_stor)
        self.StartTS = int(time.time())       
        
        self.CompetitionChangeLimits = CommandLimits(1, 3)
        self.CompetitionViewLimits = CommandLimits(0.7, 3)
        self.CompetitionPollViewLimits = CommandLimits(2, 4)
        self.CreateCompetitionLimits = CommandLimits(10, 30)
        self.UploadFilesLimits = CommandLimits(3, 10)
        self.FilesViewLimits = CommandLimits(1, 3)
        self.MyStatLimits = CommandLimits(0.7, 1.25)
        self.StatLimits = CommandLimits(1, 3)
        self.CompetitionFilesLimits = CommandLimits(2, 5)       
         
        self.MaxFileNameSize = 280
        self.MaxSubjectLength = 1024
        self.MaxSubjectExtLength = 2048
        self.UserConversations:dict[int, UserConversation] = {}

        self.JoinToCompetitionCommandRegex = re.compile("/join\\s+(\\d+)\\s+(\\S+)")
        self.CompetitionMenuQueryRegex = re.compile("comp_(\\S+)_(\\S+)_(\\d+)")

        self.DefaultAcceptDeadlineTimedelta = timedelta(minutes=defaults.get('default_accept_deadline_min', 60*4))
        if 'default_polling_stage_min' in defaults:
            self.DefaultPollingStageTimedelta = timedelta(minutes=defaults['default_polling_stage_min'])
        else:
            self.DefaultPollingStageTimedelta = timedelta(hours=defaults.get('default_polling_stage_h', 48))
        self.MinimumPollingStageInterval = timedelta(minutes=defaults.get('minimum_polling_stage_min', 60*2))

        self.DefaultMinTextSize = defaults.get('minimum_text_size', 12000)
        self.DefaultMaxTextSize = defaults.get('maximum_text_size', 40000)        

        self.MaxCompetitionDeadlineFutureInterval = timedelta(days=60)        
        self.MinTextSize = 5000
        self.MaxTextSize = 120000
        self.TextLimitChangeStep = 2500

        if self.DefaultMaxTextSize < self.MinTextSize:
            raise LitGBException("invalid minimum_text_size default value: "+str(self.DefaultMinTextSize))
        if self.DefaultMaxTextSize > self.MaxTextSize:
            raise LitGBException("invalid maximum_text_size default value: "+str(self.DefaultMaxTextSize))

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

        self.Db.EnsureUserExists(update.effective_user.id, self.MakeUserTitle(update.effective_user))        
        user_info = self.Db.FindUser(update.effective_user.id)
        stat_message = "Статистика пользователя "+user_info.Title
        stat_message += "\nПобед: "+str(user_info.Wins)
        stat_message += "\nПоражений: "+str(user_info.Losses)

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
        result = "Команды:\n"
        
        result += "\n/my_stat - моя статистика"       
        result += "\n📗 Загрузка файлов - просто отправьте файл в личные сообщения бота. Поддерживаемые форматы: docx и txt"
        result += "\n/files - ваши файлы. Работает только в личных сообщениях"
        result += "\n/create_open_competition - создание открытого конкурса (с самосудом). Работает только в личных сообщениях"
        result += "\n/create_closed_competition <кол-во участников> - создание закрытого конкурса (дуэль или конкурс с жюри). При вызове в групповом чате, сразу привязывается к нему"
        result += "\n/attach_competition <id> - привязывание конкурса к групповому чату"
        result += "\n/competition <id> - карточка конкурса"
        result += "\n/competition_polling <id> - карточка голосования конкурса"
        result += "\n/current_competition - карточка конкурса текущего чата в стадии голосования"
        result += "\n/current_polling - состояние голосования конкурса текущего чата в стадии голосования"
        result += "\n/results <id> - результаты конкурса"
        result += "\n/competitions - список конкурсов, которые привязаны к текущему чату. В личных сообщениях - список активных конкурсов"
        result += "\n/joinable_competitions - список конкурсов, к которым можно присоединиться"
        result += "\n/mycompetitions (только в личке) - список активных конкурсов, которые создал текущий пользователь или в которых он участвует"
        
        return result
    
    async def SendHelpAfterCreateCompetition(self, comp:CompetitionInfo, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

        help_msg = "ℹ️ "
        if comp.IsClosedType():
            help_msg += "Вы создали конкурс закрытого типа. Это означает, что список его участников ограничен и он начнётся только подтверждения заявленного количество участников. "
            help_msg += "У данного конкурса заявленное количество участников равно "+str(comp.DeclaredMemberCount)+"."                        
            help_msg += "\n\n⚠️ После того, как конкурс стартует, изменить его свойства уже нельзя. Поэтому перед тем, как раздавать участникам входные токены или привязывать конкурс к чату, задайте всего его параметры.\n"
        else:
            help_msg += "Вы создали конкурс открытого типа. Это означает, что список его участников неограничен и заранее неизвестен. Он стартует сразу после привязки его в групповому чату."
            help_msg += "\n\n⚠️ После того, как конкурс стартует, изменить его свойства уже нельзя. Поэтому перед тем, как привязывать конкурс к чату, задайте всего его параметры.\n"    

        if comp.CreatedBy == update.effective_chat.id:
            help_msg += "\n🔐 Быстрая команда для подтверждения участия в конкурсе:\n<pre>/join "+str(comp.Id)+" "+comp.EntryToken+"</pre>"
        

        if comp.ChatId is None:    
            help_msg += "\n\n❗️ Конкурс может стартовать только после привязки его к групповому чату. "
            help_msg += "\nЧтобы привязать конкурс к групповом чату, введите следующую команду в целевом групповом чате:\n<pre>/attach_competition "+str(comp.Id)+"</pre>"

        await update.message.reply_html(help_msg)

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
        status_msg += "\n\n"+ self.get_help()

        #status_msg +="\nВерсия "+ str(uptime)
        await update.message.reply_text(status_msg)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        status_msg ="Это бот \"Литературные игры\""
        status_msg += "\n\n"+ self.get_help()
        await update.message.reply_text(self.get_help())        

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
                    file_title = update.message.caption.strip(" \t")
            if file_title is None:
                file_title = "f_"+GetRandomString(14) 
                
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



    async def getfb2(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:            
        logging.info("[GETFB2] user id "+LitGBot.GetUserTitleForLog(update.effective_user))         
        self.FilesViewLimits.Check(update.effective_user.id, update.effective_chat.id)

        self.DeleteOldFiles() 
        self.CheckPrivateOnly(update) 
        
        file_id = self.ParseSingleIntArgumentCommand(update.message.text, "/getfb2", 1, None)
        file = self.GetFileAndCheckAccess(file_id, update.effective_user.id)

        await self.SendFB2(file, update.effective_chat.id, context)


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
    def CheckSimilarityOfTitles(t1:str, t2:str) -> bool:
        return t1.lower() == t2.lower()
    
    @staticmethod
    def IsFileAcceptableFromUser(comp:CompetitionInfo, comp_stat:CompetitionStat, user_id:int, file:FileInfo) -> bool:
        if not comp.IsStarted():
            return False
        submitted_files = comp_stat.SubmittedFiles.get(user_id, [])
        if len(submitted_files) >= comp.MaxFilesPerMember:
            return False
        
        stripped_title = file.Title.strip(" \t")
        for f in submitted_files:            
            if f.Id == file.Id:
                return False
            if LitGBot.CheckSimilarityOfTitles(f.Title, stripped_title):
                return False
        
        return True            

    def file_menu_keyboard(self, file_index:int, files:list[FileInfo], user_id:int):
        if len(files) == 0:
            return InlineKeyboardMarkup([])

        file = files[file_index]
        file_id_str = str(file.Id)
        keyboard = []   
        

        keyboard.append([InlineKeyboardButton('FB2', callback_data='file_fb2_'+file_id_str)])

        if not file.Locked:
            keyboard.append([InlineKeyboardButton('Удалить', callback_data='file_delete_'+file_id_str)])
            keyboard.append([InlineKeyboardButton('Установить название', callback_data='file_settitle_'+file_id_str)])

            joined_competitions = self.Db.SelectUserRegisteredCompetitions(user_id, datetime.now(timezone.utc), datetime.now(timezone.utc)+timedelta(days=40))
            if len(joined_competitions) > 0:    
                added_buttons = 0            
                for comp in joined_competitions:
                    comp_stat = self.Db.GetCompetitionStat(comp.Id)
                    if self.IsFileAcceptableFromUser(comp, comp_stat, user_id, file):
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
                    text="✏️ Введите новое название файла", reply_markup=InlineKeyboardMarkup([]))                
            elif params[0] == "fb2":
                file_id = int(params[1])
                f = self.GetFileAndCheckAccess(file_id, update.effective_user.id)
                await self.SendFB2(f, update.effective_chat.id, context)
            elif params[0] == "use":
                file_id = int(params[1])
                comp_id = int(params[2])
                f = self.GetFileAndCheckAccess(file_id, update.effective_user.id)
                comp = self.FindFileAcceptableCompetition(comp_id)
                if (f.TextSize < comp.MinTextSize) or (f.TextSize > comp.MaxTextSize):
                    raise LitGBException("file not acceptable for competition")
                comp_stat = self.Db.GetCompetitionStat(comp.Id)
                if not self.IsFileAcceptableFromUser(comp, comp_stat, update.effective_user.id, f):
                    raise LitGBException("file not acceptable for competition from this user")
                
                comp_stat = self.Db.UseFileInCompetition(comp.Id, update.effective_user.id, f.Id)            
                await query.edit_message_text(
                    text="✅ Файл задействован в конкурсе #"+str(comp_id), reply_markup=InlineKeyboardMarkup([]))            
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
        limit = self.ParseSingleIntArgumentCommand(update.message.text, "/set_allusers_filelimit", 0, 30) 
        affected_users = self.Db.SetAllUsersFileLimit(limit)
        await update.message.reply_text("Лимит "+str(affected_users)+" пользователей установлен в значение "+str(limit))

    async def set_newusers_file_limit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logging.warning("[ADMIN] user id "+LitGBot.GetUserTitleForLog(update.effective_user))     
        if update.effective_user.id != update.effective_chat.id:
            return
        if not (update.effective_user.id in self.Admins):
            return        
        self.Db.DefaultNewUsersFileLimit = self.ParseSingleIntArgumentCommand(update.message.text, "/set_newusers_file_limit", 0, 30) 
        await update.message.reply_text("Лимит файлов для всех новых пользователей установлен в значение "+str(self.Db.DefaultNewUsersFileLimit))
        

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
        self.Db.EnsureUserExists(update.effective_user.id, self.MakeUserTitle(update.effective_user)) 

        files = self.Db.GetFileList(update.effective_user.id, 30)
        if len(files) > 0:
            files.sort(key=lambda x: x.Loaded)                
            await update.message.reply_text(self.file_menu_message(files[0]), reply_markup=self.file_menu_keyboard(0, files, update.effective_user.id))   
        else:
            await update.message.reply_text("✖️ У вас нет файлов", reply_markup=InlineKeyboardMarkup([]))   
   
    def ParseDeadlines(self, v:str, tz:timezone) -> tuple[datetime, datetime]:
        deadlines = v.strip().split("/", 1)
        if len(deadlines) != 2:
            raise LitGBException("неправильный формат дедлайнов")
        d1 = datetime.strptime(deadlines[0].strip(), '%d.%m.%Y %H:%M')
        d2 = datetime.strptime(deadlines[1].strip(), '%d.%m.%Y %H:%M')

        d1 = tz.localize(d1)
        d2 = tz.localize(d2) 
        if d2 <= d1 + self.MinimumPollingStageInterval:
            raise LitGBException("Слишком короткий период голосования")
        
        return (d1, d2)

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:                
        logging.info("[HANDLE_TEXT] user id "+LitGBot.GetUserTitleForLog(update.effective_user))        

        if update.effective_user.id in self.UserConversations:            
            if update.effective_user.id != update.effective_chat.id:
                return
            self.Db.EnsureUserExists(update.effective_user.id, self.MakeUserTitle(update.effective_user))     
            convers = self.UserConversations.pop(update.effective_user.id)
            if not (convers.SetTitleFor is None):
                logging.info("[FILE_SETTITLE] new title for file #"+str(convers.SetTitleFor)+": "+update.message.text) 
                if len(update.message.text) > self.MaxFileNameSize:
                    raise LitGBException("Имя файла слишком длинное. Максимальная разрешённая длина: "+str(self.MaxFileNameSize))
                self.Db.SetFileTitle(convers.SetTitleFor, update.message.text.strip(" \t"))
                await update.message.reply_text("Новое имя файла #"+str(convers.SetTitleFor)+" установлено: "+update.message.text)            
            elif not (convers.SetSubjectFor is None):
                new_subj = update.message.text.strip()
                logging.info("[COMP_SETSUBJ] new subject for competition #"+str(convers.SetSubjectFor)+": "+new_subj) 
                if len(new_subj) < 3:
                    raise LitGBException("Тема не может быть меньше трёх символов")
                if len(new_subj) > self.MaxSubjectLength:
                    raise LitGBException("Тема не может быть больше "+str(self.MaxSubjectLength)+" символов")
                comp = self.FindPropertyChangableCompetition(convers.SetSubjectFor, update.effective_user.id)
                self.Db.SetCompetitionSubject(comp.Id, new_subj)
                await update.message.reply_text("✅ Новая тема для конкурса #"+str(comp.Id)+" установлена: "+new_subj)
            elif not (convers.SetSubjectExtFor is None):
                new_subjext = update.message.text.strip()
                logging.info("[COMP_SETSUBJEXT] new subject for competition #"+str(convers.SetSubjectExtFor)+": "+new_subjext) 
                if len(new_subjext) < 3:
                    raise LitGBException("Пояснение не может быть меньше трёх символов")
                if len(new_subj) > self.MaxSubjectExtLength:
                    raise LitGBException("Тема не может быть больше "+str(self.MaxSubjectExtLength)+" символов")                
                comp = self.FindPropertyChangableCompetition(convers.SetSubjectExtFor, update.effective_user.id)
                self.Db.SetCompetitionSubjectExt(comp.Id, new_subjext)
                await update.message.reply_text("✅ Новое пояснение для конкурса #"+str(comp.Id)+" установлено:\n\n"+new_subjext)                
            elif  not (convers.InputEntryTokenFor is None):    
                token = update.message.text.strip()
                logging.info("[INPUT_TOKEN] input entry token for competition #"+str(convers.SetSubjectFor)+": "+token) 

                comp = self.FindJoinableCompetition(convers.InputEntryTokenFor)
                if comp.EntryToken != token:
                    raise LitGBException("неправильный входной токен")
                
                comp_stat = self.Db.JoinToCompetition(comp.Id, update.effective_user.id)
                comp = await self.AfterJoinMember(comp, comp_stat, context)
                await update.message.reply_text("✅ Заявлено участие в конкурсе #"+str(comp.Id))
            elif  not (convers.SetDeadlinesFor is None):
                new_deadlines = update.message.text.strip()
                logging.info("[COMP_SETSUBJEXT] new deadlines for competition #"+str(convers.SetDeadlinesFor)+": "+new_deadlines) 
                accept_files_deadline, polling_deadline = self.ParseDeadlines(new_deadlines, self.Timezone)
                comp = self.FindPropertyChangableCompetition(convers.SetDeadlinesFor, update.effective_user.id)
                if not (comp.ChatId is None):
                    if not self.CheckCompetitionDeadlines(comp.ChatId,):
                        raise LitGBException("новые дедлайны пересекаются с дедлайнами других конкурсов")
                    
                comp = self.Db.SetDeadlines(comp.Id, accept_files_deadline, polling_deadline)
                await update.message.reply_text("✅ Дедлайны для конкурса #"+str(comp.Id)+" установлены: "+DatetimeToString(comp.AcceptFilesDeadline)+" / "+DatetimeToString(comp.PollingDeadline))
    
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
        await update.message.reply_text("✔️ Создан новый закрытый конкурс #"+str(comp.Id)) 
        
        comp_info = self.GetCompetitionFullInfo(comp)
        await update.message.reply_text(
            self.comp_menu_message(comp_info, update.effective_user.id, update.effective_chat.id), 
            reply_markup=self.comp_menu_keyboard("singlemode", 0, comp_info.Stat, [comp], update.effective_user.id, update.effective_chat.id))            
        await self.SendHelpAfterCreateCompetition(comp, update, context)
        
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
        await update.message.reply_text("✔️ Создан новый открытый конкурс #"+str(comp.Id)) 

        comp_info = self.GetCompetitionFullInfo(comp)
        await update.message.reply_text(
            self.comp_menu_message(comp_info, update.effective_user.id, update.effective_chat.id), 
            reply_markup=self.comp_menu_keyboard("singlemode", 0, comp_info.Stat, [comp], update.effective_user.id, update.effective_chat.id))       
        await self.SendHelpAfterCreateCompetition(comp, update, context)
        
    async def attach_competition(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[ATTACH] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        self.CompetitionChangeLimits.Check(update.effective_user.id, update.effective_chat.id)
        if update.effective_user.id == update.effective_chat.id:
            await update.message.reply_text("⛔️ Выполнение команды в личных сообщениях бота лишено смысла")
            return
        self.Db.EnsureUserExists(update.effective_user.id, self.MakeUserTitle(update.effective_user))
        self.Db.EnsureChatExists(update.effective_chat.id, self.MakeChatTitle(update.effective_chat))    

        comp_id = self.ParseSingleIntArgumentCommand(update.message.text, "/attach_competition")
        comp = self.FindNotAttachedCompetition(comp_id)
        if comp.CreatedBy != update.effective_user.id:
            raise LitGBException("Привязывать конкурс к чату может только создатель конкурса")
        if not self.CheckCompetitionDeadlines(update.effective_chat.id, comp):
            raise LitGBException("Нельзя привязать конкурс к чату, если его период голосования пересекается с периодами голосования других конкурсов в чате")
        comp = self.Db.AttachCompetition(comp.Id, update.effective_chat.id)
        await self.AfterCompetitionAttach(comp, context)
        
        comp_info = self.GetCompetitionFullInfo(comp)                      
        await update.message.reply_text(
            self.comp_menu_message(comp_info, update.effective_user.id, update.effective_chat.id), 
            reply_markup=self.comp_menu_keyboard("singlemode", 0, comp_info.Stat, [comp], update.effective_user.id, update.effective_chat.id))
                    
        
    async def competitions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[COMPS] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        self.CompetitionViewLimits.Check(update.effective_user.id, update.effective_chat.id)
        
        list_type = "allactiveattached"
        if update.effective_user.id != update.effective_chat.id:            
            list_type = "chatrelated"

        comp_list = self.GetCompetitionList(list_type, update.effective_user.id, update.effective_chat.id)        
        if len(comp_list) == 0:
            await update.message.reply_text("✖️ Нет конкурсов")
            return  
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
        
    async def competition_polling(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[COMPPOLL] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        self.CompetitionViewLimits.Check(update.effective_user.id, update.effective_chat.id)
        
        comp_id = self.ParseSingleIntArgumentCommand(update.message.text, "/competition_polling")    

        comp = self.FindCompetitionInPollingState(comp_id)
        comp_info = self.GetCompetitionFullInfo(comp)
        await update.message.reply_text(
            self.comp_poll_menu_message(comp_info, update.effective_user.id, update.effective_chat.id), 
            reply_markup=self.comp_poll_menu_keyboard(comp_info, update.effective_user.id, update.effective_chat.id))        
        
    async def results(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:     
        logging.info("[RESULT] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        self.CompetitionViewLimits.Check(update.effective_user.id, update.effective_chat.id)
        comp_id = self.ParseSingleIntArgumentCommand(update.message.text, "/results")  
        comp = self.FindFinishedCompetition(comp_id)
        comp_info = self.GetCompetitionFullInfo(comp)
        await update.message.reply_text("В разработке")
        
    async def competition_files(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logging.info("[COMPFILES] user id "+self.GetUserTitleForLog(update.effective_user)) 
        self.CompetitionFilesLimits.Check(update.effective_user.id, update.effective_chat.id)      

        comp_id = self.ParseSingleIntArgumentCommand(update.message.text, "/competition_files")  
        comp = self.FindCompetitionInPollingState(comp_id)
        if update.effective_chat.id != comp.ChatId:
            raise LitGBException("Команду можно выполнить только в чате, к которому привязан конкурс")
        comp_info = self.GetCompetitionFullInfo(comp)
        await self.SendSubmittedFiles(comp.ChatId, comp_info.Stat, context)
        await self.SendMergedSubmittedFiles(comp.ChatId, comp.Id, comp_info.Stat, context)

        
    async def current_competition(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[CURRENT] user id "+LitGBot.GetUserTitleForLog(update.effective_user))     
        self.CompetitionViewLimits.Check(update.effective_user.id, update.effective_chat.id)
        if update.effective_user.id == update.effective_chat.id:
            await update.message.reply_text("⛔️ Выполнение команды в личных сообщениях бота лишено смысла")
            return

        comp = self.Db.GetCurrentPollingCompetitionInChat(update.effective_chat.id)    
        if comp is None:
            await update.message.reply_text("✖️ Нет конкурсов")
            return
        comp_info = self.GetCompetitionFullInfo(comp)                      
        await update.message.reply_text(
            self.comp_menu_message(comp_info, update.effective_user.id, update.effective_chat.id), 
            reply_markup=self.comp_menu_keyboard("singlemode", 0, comp_info.Stat, [comp], update.effective_user.id, update.effective_chat.id))

    async def current_polling(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:     
        logging.info("[CURPOLL] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        self.CompetitionPollViewLimits.Check(update.effective_user.id, update.effective_chat.id)
        if update.effective_user.id == update.effective_chat.id:
            await update.message.reply_text("⛔️ Выполнение команды в личных сообщениях бота лишено смысла")
            return
        comp = self.Db.GetCurrentPollingCompetitionInChat(update.effective_chat.id)    
        if comp is None:
            await update.message.reply_text("✖️ Нет конкурсов")
            return
        comp_info = self.GetCompetitionFullInfo(comp) 
        await update.message.reply_text(
            self.comp_poll_menu_message(comp_info, update.effective_user.id, update.effective_chat.id), 
            reply_markup=self.comp_poll_menu_keyboard(comp_info, update.effective_user.id, update.effective_chat.id))        
        
    async def mycompetitions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[MYCOMPS] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        self.CompetitionViewLimits.Check(update.effective_user.id, update.effective_chat.id)
        self.CheckPrivateOnly(update)
        self.Db.EnsureUserExists(update.effective_user.id, self.MakeUserTitle(update.effective_user))

        comp_list = self.GetCompetitionList("my", update.effective_user.id, update.effective_chat.id)        
        if len(comp_list) == 0:
            await update.message.reply_text("✖️ Нет конкурсов")
            return
        comp = comp_list[0]
        comp_info = self.GetCompetitionFullInfo(comp)
        await update.message.reply_text(
            self.comp_menu_message(comp_info, update.effective_user.id, update.effective_chat.id), 
            reply_markup=self.comp_menu_keyboard("my", 0, comp_info.Stat, comp_list, update.effective_user.id, update.effective_chat.id))

    async def joinable_competitions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[JCOMPS] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        self.CompetitionViewLimits.Check(update.effective_user.id, update.effective_chat.id)
        
        comp_list = self.GetCompetitionList("joinable", update.effective_user.id, update.effective_chat.id)        
        if len(comp_list) == 0:
            await update.message.reply_text("✖️ Нет конкурсов")
            return
        comp = comp_list[0]
        comp_info = self.GetCompetitionFullInfo(comp)
        await update.message.reply_text(
            self.comp_menu_message(comp_info, update.effective_user.id, update.effective_chat.id), 
            reply_markup=self.comp_menu_keyboard("joinable", 0, comp_info.Stat, comp_list, update.effective_user.id, update.effective_chat.id))
    
    def ParseJoinToCompetitionCommand(self, msg:str) -> tuple[int, str]:        
        try:
            m = self.JoinToCompetitionCommandRegex.match(msg)
            return (int(m.group(1)), m.group(2))
        except BaseException as ex:
            raise LitGBException("Некорректный формат команды /join") 


    async def join_to_competition(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:         
        logging.info("[JOIN] user id "+LitGBot.GetUserTitleForLog(update.effective_user)) 
        self.CompetitionViewLimits.Check(update.effective_user.id, update.effective_chat.id)        

        comp_id, token = self.ParseJoinToCompetitionCommand(update.message.text)        
        comp = self.FindJoinableCompetition(comp_id)
        self.Db.EnsureUserExists(update.effective_user.id, self.MakeUserTitle(update.effective_user))
        if comp.CreatedBy != update.effective_user.id:
            if not (comp.EntryToken is None):
                if len(comp.EntryToken) > 0:
                    if comp.EntryToken != token:
                        raise LitGBException("неправильный входной токен: введено ")
        comp_stat = self.Db.JoinToCompetition(comp_id, update.effective_user.id)
        comp = await self.AfterJoinMember(comp, comp_stat, context)
        await update.message.reply_text("✅ Заявлено участие в конкурсе #"+str(comp.Id))

    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update is None:
            logging.warning("Exception: "+ str(context.error))
        else:    
            logging.info("Exception: user id "+LitGBot.GetUserTitleForLog(update.effective_user)+", chat id "+LitGBot.GetChatTitleForLog(update.effective_chat), exc_info=context.error)

        message_text = "impossible case (lol)"
        if isinstance(context.error, OnlyPrivateMessageAllowed):
            message_text = str(context.error)
        elif isinstance(context.error, CommandRateLimitReached):
            message_text = str(context.error)
        elif isinstance(context.error, LitGBException): 
            logging.warning("LitGBException: "+str(context.error))          
            message_text = self.MakeErrorMessage(context.error)
        else:
            logging.error("EXCEPTION: "+str(context.error))
            tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
            tb_string = "".join(tb_list)
            logging.warning("Exception traceback:" + tb_string)            
            message_text = self.MakeExternalErrorMessage(context.error)
        
        if update is None:
            pass
        else:    
            await update.message.reply_text(message_text)
        

    def ParseCompetitionMenuQuery(self, query:str) -> tuple[str, str, int]:
        try:
            m = self.CompetitionMenuQueryRegex.match(query)
            return (m.group(1), m.group(2), int(m.group(3)))
        except BaseException as ex:
            raise LitGBException("invalid comp menu query")  

    def comp_poll_menu_keyboard(self, comp_info:CompetitionFullInfo, user_id:str, chat_id:int):
        keyboard = []
        return InlineKeyboardMarkup(keyboard)
    
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
                if self.CheckCompetitionPropertyChangable(comp) is None:            
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


                if self.IsCompetitionСancelable(comp) is None:            
                    keyboard.append([InlineKeyboardButton('Отменить', callback_data='comp_'+list_type+'_cancel_'+str(comp.Id))])
        
            if self.CheckCompetitionJoinable(comp) is None:
                if not comp_stat.IsUserRegistered(user_id):
                    keyboard.append([InlineKeyboardButton('Присоединиться', callback_data='comp_'+list_type+'_join_'+str(comp.Id))])

            if ComepetitionWorker.CheckCompetitionLeaveable(comp) is None:
                if comp_stat.IsUserRegistered(user_id):   
                    if len(comp_stat.SubmittedFiles.get(user_id, [])) > 0:    
                        keyboard.append([InlineKeyboardButton('Снять все свои файлы', callback_data='comp_'+list_type+'_releasefiles_'+str(comp.Id))])
                    keyboard.append([InlineKeyboardButton('Выйти', callback_data='comp_'+list_type+'_leave_'+str(comp.Id))])

        return InlineKeyboardMarkup(keyboard)
  
    def comp_poll_menu_message(self, comp_info:CompetitionFullInfo, user_id:int, chat_id:int) -> str:        
        return "В разработке"
    
    def comp_menu_message(self, comp_info:CompetitionFullInfo, user_id:int, chat_id:int) -> str:        
        result = "#" + str(comp_info.Comp.Id)
        if comp_info.Comp.Canceled:
            result += " ОТМЕНЁН"
        if not (comp_info.Comp.Finished is None):
            result += " ЗАВЕРШЁН"

        result +="\nТип: "
        if comp_info.Comp.IsClosedType():
            result +="дуэль/жюри"
        else:
            result +="🔫 самосуд"    

        result +="\n\nСоздан: " + DatetimeToString(comp_info.Comp.Created)
        if not (comp_info.Comp.Confirmed is None):
            result +="\nПодтверждён: " + DatetimeToString(comp_info.Comp.Confirmed)
        if not (comp_info.Comp.Started is None):
            result +="\nЗапущен: " + DatetimeToString(comp_info.Comp.Started)    
        if not (comp_info.Comp.PollingStarted is None):
            result +="\nГолосование начато: " + DatetimeToString(comp_info.Comp.PollingStarted)
        if not (comp_info.Comp.Finished is None):
            result +="\nЗавершён: " + DatetimeToString(comp_info.Comp.Finished)            
        

        if not (comp_info.Chat is None):
            result +="\nКонфа: " + comp_info.Chat.Title
        else:
            result +="⚠️ Конкурс будет запущен только после привязки в групповому чату"
        result +="\n\n🏷 Тема: " + comp_info.Comp.Subject
        if not (comp_info.Comp.SubjectExt is None):
            result +="\n📃 Пояснение:\n\n" + comp_info.Comp.SubjectExt
        result +="\n🕟 Дедлайн приёма работ: " + DatetimeToString(comp_info.Comp.AcceptFilesDeadline)
        result +="\n🕓 Дедлайн голосования: " + DatetimeToString(comp_info.Comp.PollingDeadline)
        now = datetime.now(timezone.utc)
        if now < comp_info.Comp.AcceptFilesDeadline:
            result +="\n⏳ До окончания приёма работ: " + TimedeltaToString(comp_info.Comp.AcceptFilesDeadline - now)
            result +="\n⏱️ Время на голосование: " + TimedeltaToString(comp_info.Comp.PollingDeadline - comp_info.Comp.AcceptFilesDeadline)
        elif now < comp_info.Comp.PollingDeadline:  
            result +="\n⏳ До окончания голосования: " + TimedeltaToString(comp_info.Comp.PollingDeadline - now)
        result +="\nМинимальный размер текста: " + str(comp_info.Comp.MinTextSize)
        result +="\nМаксимальный размер текста: " + str(comp_info.Comp.MaxTextSize)        
        result +="\nМаксимум работ с одного участника: " + str(comp_info.Comp.MaxFilesPerMember)
        if comp_info.Comp.CreatedBy == chat_id:
            result +="\n🔐 Входной токен: " + comp_info.Comp.EntryToken

        if user_id == chat_id:
            if comp_info.Stat.IsUserRegistered(user_id):
                result +="\n\n‼️ ВЫ УЧАСТВУЕТЕ В ЭТОМ КОНКУРСЕ"

                user_files = comp_info.Stat.SubmittedFiles.get(user_id, [])
                if len(user_files) > 0:
                    result +="\n✅ Ваши файлы на этом конкурсе:"
                    i = 0
                    for f in user_files:
                        i += 1
                        result +="\n✔️ "+str(i)+". ("+str(MakeHumanReadableAmount(f.TextSize))+") "+f.Title
                else:
                    result +="\n🔘 Вы ещё не прикрепляли файлы к конкурсу"

        
        result +="\n\n📉 Зарегистрированных участников : " + str(len(comp_info.Stat.RegisteredMembers))        

        if comp_info.Comp.IsClosedType() and (len(comp_info.Stat.RegisteredMembers) > 0):
            result +="\n📋 Список участников:"
            i = 0
            for m in comp_info.Stat.RegisteredMembers:
                i += 1
                result +="\n🔹 "+str(i)+": "+m.Title
        else:
            result +="\n📈 Кол-во участников приславших рассказы: " + str(len(comp_info.Stat.SubmittedMembers))    
            result +="\n📚 Кол-во присланных рассказов: " + str(comp_info.Stat.SubmittedFileCount)  


        if comp_info.Comp.IsOpenType() or comp_info.Comp.IsPollingStarted():
            result +="\n🖨 Суммарно присланный текст: " + MakeHumanReadableAmount(comp_info.Stat.TotalSubmittedTextSize)
        

        return result
 
     
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
                        text="🔓 Введите токен для входа в конкурс", reply_markup=InlineKeyboardMarkup([]))  
            elif action == "leave":
                comp = self.FindLeavableCompetition(comp_id)
                comp_stat = self.Db.GetCompetitionStat(comp.Id)
                if comp_stat.IsUserRegistered(update.effective_user.id):
                    if comp.IsClosedType():
                        if comp.IsStarted():
                            if comp_stat.IsUserRegistered(update.effective_user.id):
                                LitGBException("Из закрытого стартовавшего конкурса нельзя выйти")
                else:
                    LitGBException("can not leave from competition, because current user not registered in them")            
                        
                comp_info = self.ReleaseUserFilesFromCompetition(update.effective_user.id, comp, True)    
                await query.edit_message_text(
                    text="Вы вышли из конкурса #"+str(comp_info.Comp.Id), reply_markup=InlineKeyboardMarkup([]))
            elif action == "releasefiles":
                comp = self.FindFileAcceptableCompetition(comp_id)
                comp_info = self.ReleaseUserFilesFromCompetition(update.effective_user.id, comp, False)
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
        
             
    async def competition_service_event(self, context: ContextTypes.DEFAULT_TYPE):
        logging.info("competition_service_event:")
        await self.CheckCompetitionStates(context)


if __name__ == '__main__':    

    parser = argparse.ArgumentParser(
        prog = 'LitGBot', description = '''Literature games bot''', epilog = '''(c) 2025''')   
    parser.add_argument ('--conf', dest='conf', action="store", type=str, required=True)
    args = parser.parse_args()    

    with open(args.conf, 'r') as file:
        conf = json.load(file)
     
    logging.basicConfig(level=conf.get('log_level', 'WARNING'), format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
       
    file_str = FileStorage(conf['file_storage'])

    db = DbWorkerService(conf['db'])

    app = ApplicationBuilder().token(conf['bot_token']).build()

    bot = LitGBot(db, file_str, conf['admin'], conf.get('competition_defaults', {}))   

    app.add_handler(CommandHandler("start", bot.help))
    app.add_handler(CommandHandler("help", bot.help))
    app.add_handler(CommandHandler("status", bot.status))
    app.add_handler(CommandHandler("filelist", bot.filelist))
    app.add_handler(CommandHandler("files", bot.files))
    app.add_handler(CommandHandler("getfb2", bot.getfb2))
    app.add_handler(CommandHandler("my_stat", bot.mystat))
    app.add_handler(CommandHandler("stat", bot.stat))
    app.add_handler(CommandHandler("top", bot.top))
    app.add_handler(CommandHandler("create_closed_competition", bot.create_closed_competition))
    app.add_handler(CommandHandler("create_open_competition", bot.create_open_competition))
    app.add_handler(CommandHandler("attach_competition", bot.attach_competition))
    app.add_handler(CommandHandler("competitions", bot.competitions))  
    app.add_handler(CommandHandler("competition", bot.competition))  
    app.add_handler(CommandHandler("competition_polling", bot.competition_polling)) 
    app.add_handler(CommandHandler("competition_files", bot.competition_files))  
    app.add_handler(CommandHandler("current_competition", bot.current_competition))  
    app.add_handler(CommandHandler("current_polling", bot.current_polling)) 
    app.add_handler(CommandHandler("joinable_competitions", bot.joinable_competitions))
    app.add_handler(CommandHandler("join", bot.join_to_competition))
    app.add_handler(CommandHandler("mycompetitions", bot.mycompetitions))
    app.add_handler(CommandHandler("results", bot.results))
    

    #ADMINS
    app.add_handler(CommandHandler("set_filelimit", bot.set_file_limit))    
    app.add_handler(CommandHandler("set_allusers_filelimit", bot.set_allusers_file_limit))   
    app.add_handler(CommandHandler("set_newusers_filelimit", bot.set_newusers_file_limit))  
    app.add_handler(CommandHandler("kill", bot.kill_competition))

    app.add_handler(CallbackQueryHandler(bot.file_menu_handler, pattern="file_\\S+"))
    app.add_handler(CallbackQueryHandler(bot.comp_menu_handler, pattern="comp_\\S+"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_text))
    
    app.add_handler(MessageHandler(filters.Document.ALL, bot.downloader))    

    job_minute = app.job_queue.run_repeating(bot.competition_service_event, interval=100, first=5)

    app.add_error_handler(bot.error_handler)

    app.run_polling()
    