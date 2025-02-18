from telegram import Update, User, Chat
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
import argparse
from db_worker import DbWorkerService
import logging
import json
import time
from datetime import timedelta, datetime
from ysdb_exception import YSDBException
from zoneinfo import ZoneInfo
from file_worker import FileStorage
    
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

class YSDBot:
    def __init__(self, db_worker:DbWorkerService, file_stor:FileStorage):
        self.Db = db_worker
        self.StartTS = int(time.time())
        
        self.PushLimits = CommandLimits(0.3, 0.5)
        self.PopLimits = CommandLimits(0.4, 1.0)
        self.MyStatLimits = CommandLimits(0.7, 1.25)
        self.StatLimits = CommandLimits(1, 3)    
        self.MaxFileSize = 1024*1024*256
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
    def ParsePushMessage(msg:str) -> int:
        try:
            parts = msg.strip().split(" ", 1)
            second_part = parts[1].strip()
            koeff = 1
            if second_part[-1] in ['k', 'K', 'к', 'К']:
                second_part = second_part[:-1]
                koeff = 1000
            return int(second_part)*koeff
        except BaseException as ex:
            raise YSDBException("Некорректный формат команды /push")     

    @staticmethod
    def ParseTopParamsAndValidate(msg:str) -> int:
        result = None
        try:
            parts = msg.strip().split(" ", 1)
            if len(parts) < 2:
                return 7
            else:
                second_part = parts[1].strip()
                result = int(second_part)
        except BaseException as ex:
            raise YSDBException("Некорректный формат команды /top")    
        
        if result < 2:
            raise YSDBException("🚫 Топ меньше чем за 2 дня считать нельзя")            
        if result > 180:
            raise YSDBException("🚫 Топ больше чем за 180 дней считать нельзя") 
        return result
               
    @staticmethod
    def ParseStatParamsAndValidate(msg:str) -> int:

        result = None
        try:
            parts = msg.strip().split(" ", 1)
            if len(parts) < 2:
                return 7
            else:
                second_part = parts[1].strip()
                result = int(second_part)
        except BaseException as ex:
            raise YSDBException("Некорректный формат команды /stat")    
        
        if result < 2:
            raise YSDBException("🚫 Стаститику меньше, чем за 1 день считать нельзя") 
        return result

    @staticmethod
    def ParseMyStatType(msg:str) -> str:
        try:
            parts = msg.strip().split(" ", 1)            
            return parts[1].strip().lower()
        except BaseException as ex:
            return ""

    def MakeLastPushingInfo(self, user_id:int, chat_id:int, count:int) -> str:
        user_contribs = self.Db.SelectLastUserSelfContribs(user_id, chat_id, count)
        result = ""
        cc = 1
        for uc in user_contribs:
            if cc > 1:
                result += "\n"

            result += "№"+str(cc) +" " + uc.TS.strftime("%d.%m.%Y %H:%M")+" 📓 "+MakeHumanReadableAmount(uc.Amount)
            cc += 1

        return result
    
    def MakeShortStatBlock(self, user_id:int, chat_id:int) -> str:
        result = "Количество за сутки: " + MakeHumanReadableAmount(self.Db.GetAmountSum(user_id, chat_id, datetime.now() - timedelta(days=1), datetime.now()))
        result += "\nКоличество за неделю: " + MakeHumanReadableAmount(self.Db.GetAmountSum(user_id, chat_id, datetime.now() - timedelta(days=7), datetime.now()))
        return result

    def MakeLastPushingInfoBlock(self, user_id:int, chat_id:int, count:int) -> str:
        result = "📑 Последние записи:\n"

        result += self.MakeLastPushingInfo(user_id, chat_id, count)

        return result
    
    def MakeTopBlock(self, chat_id:int, day_count:int) -> str:
        result = "🏆 TОП за последние "+str(day_count)+" дней:\n"

        top = self.Db.GetTop(chat_id, datetime.now() - timedelta(days=day_count), datetime.now())
        
        cc = 1
        for item in top:
            if cc > 1:
                result += "\n"

            result += "№"+str(cc) +" " + item.Title+" : "+MakeHumanReadableAmount(item.Amount)
            cc += 1

        return result        

    @staticmethod
    def MakeErrorMessage(ex: YSDBException) -> str:
        return "⛔️ Ошибка!\n\n"+str(ex)
    
    @staticmethod
    def MakeExternalErrorMessage(ex: BaseException) -> str:
        return "❗️ Ошибка при выполнении команды: "+str(ex)

    async def push(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logging.info("[PUSH] user id "+YSDBot.GetUserTitleForLog(update.effective_user)+", chat id "+YSDBot.GetChatTitleForLog(update.effective_chat) + ", text: "+update.message.text)    
        if self.PushLimits.Check(update.effective_user.id, update.effective_chat.id):
            logging.warning("[PUSH] Ignore command from user id "+YSDBot.GetUserTitleForLog(update.effective_user)+", chat id "+YSDBot.GetChatTitleForLog(update.effective_chat) + ", text: "+update.message.text)
            return
        self.LastHandledPushCommand = time.time()

        try:
            self.Db.EnsureUserExists(update.effective_user.id, YSDBot.MakeUserTitle(update.effective_user))
            self.Db.EnsureChatExists(update.effective_chat.id, YSDBot.MakeChatTitle(update.effective_chat))            
        
            amount = YSDBot.ParsePushMessage(update.message.text)            

            if amount < 1:
                raise YSDBException("🚫 Меньше одного символа пушить нельзя") 
            if amount > 80000:
                raise YSDBException("🚫 Больше 80k пушить нельзя")
            current_day_counter = self.Db.GetAmountSum(update.effective_user.id, update.effective_chat.id, datetime.now() - timedelta(days=1), datetime.now())     
            if current_day_counter > 100000:
                raise YSDBException("🥴 Мне кажется, что ты за сегодня уже много написал. Тебе надо бы отдохнуть")
            
            self.Db.InsertSelfContribRecord(update.effective_user.id, update.effective_chat.id, amount)

            reply_message = "✅ Сохранено "+MakeHumanReadableAmount(amount)+" символов."
            reply_message += "\n\n"+self.MakeShortStatBlock(update.effective_user.id, update.effective_chat.id)
            #reply_message += "\n\n"+self.MakeLastPushingInfoBlock(update.effective_user.id, update.effective_chat.id, 3)

            await update.message.reply_text(reply_message) 
        except YSDBException as ex:
            await update.message.reply_text(YSDBot.MakeErrorMessage(ex)) 
        except BaseException as ex:    
            logging.error("[PUSH] user id "+YSDBot.GetUserTitleForLog(update.effective_user)+", chat id "+YSDBot.GetChatTitleForLog(update.effective_chat) + ", text: "+update.message.text + ". EXCEPTION: "+str(ex))       
            await update.message.reply_text(YSDBot.MakeExternalErrorMessage(ex))
    

    async def pop(self,update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:                

        logging.info("[POP] user id "+YSDBot.GetUserTitleForLog(update.effective_user)+", chat id "+YSDBot.GetChatTitleForLog(update.effective_chat)+ ", text: "+update.message.text)    
        if self.PopLimits.Check(update.effective_user.id, update.effective_chat.id):
            logging.warning("[POP] Ignore command from user id "+YSDBot.GetUserTitleForLog(update.effective_user)+", chat id "+YSDBot.GetChatTitleForLog(update.effective_chat)+ ", text: "+update.message.text)
            return
        self.LastHandledPopCommand = time.time()

        if not update.message.text.strip().lower().endswith("yes"):
            reply_message = "⚠️ Чтобы выполнить операцию, введите команду вручную:\n\n/pop yes"
            reply_message += "\n\n"+self.MakeLastPushingInfoBlock(update.effective_user.id, update.effective_chat.id, 5)
            await update.message.reply_text(reply_message) 

            return

        try:
            self.Db.DeleteLastSelfContribRecords(update.effective_user.id, update.effective_chat.id, 1)
            reply_message = "☑️ Выполнена попытка удаления последней записи.\n\n"+self.MakeLastPushingInfoBlock(update.effective_user.id, update.effective_chat.id, 5)
            await update.message.reply_text(reply_message) 
        except YSDBException as ex:
            await update.message.reply_text(YSDBot.MakeErrorMessage(ex)) 
        except BaseException as ex:    
            logging.error("[PUSH] user id "+YSDBot.GetUserTitleForLog(update.effective_user)+", chat id "+YSDBot.GetChatTitleForLog(update.effective_chat) + ", text: "+update.message.text + ". EXCEPTION: "+str(ex))       
            await update.message.reply_text(YSDBot.MakeExternalErrorMessage(ex))
           

    async def mystat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logging.info("[MYSTAT] user id "+YSDBot.GetUserTitleForLog(update.effective_user)+", chat id "+YSDBot.GetChatTitleForLog(update.effective_chat))    
        if self.MyStatLimits.Check(update.effective_user.id, update.effective_chat.id):
            logging.warning("[MYSTAT] Ignore command from user id "+YSDBot.GetUserTitleForLog(update.effective_user)+", chat id "+YSDBot.GetChatTitleForLog(update.effective_chat))        
            return
        self.LastHandledMyStatCommand = time.time()

        t = YSDBot.ParseMyStatType(update.message.text)
        full = (t == "full")

        try:
            stat_message = "Привет, " + YSDBot.MakeUserTitle(update.effective_user) + "!\n\n"
            stat_message += self.MakeLastPushingInfoBlock(update.effective_user.id, update.effective_chat.id, 10 if full else 5)

            stat_message += "\n\n📊 Данные по знакам"
            stat_message += "\nЗа последние сутки: "+MakeHumanReadableAmount(self.Db.GetAmountSum(update.effective_user.id, update.effective_chat.id, datetime.now() - timedelta(days=1), datetime.now()))
            #stat_message += "\nЗа последние 3 суток: "+MakeHumanReadableAmount(self.Db.GetAmountSum(update.effective_user.id, update.effective_chat.id, datetime.now() - timedelta(days=3), datetime.now()))
            stat_message += "\nЗа последние 7 суток: "+MakeHumanReadableAmount(self.Db.GetAmountSum(update.effective_user.id, update.effective_chat.id, datetime.now() - timedelta(days=7), datetime.now()))
            if full:
                stat_message += "\nЗа последние 15 суток: "+MakeHumanReadableAmount(self.Db.GetAmountSum(update.effective_user.id, update.effective_chat.id, datetime.now() - timedelta(days=15), datetime.now()))
            stat_message += "\nЗа последние 30 суток: "+MakeHumanReadableAmount(self.Db.GetAmountSum(update.effective_user.id, update.effective_chat.id, datetime.now() - timedelta(days=30), datetime.now()))
            if full:
                stat_message += "\nЗа всё время: "+MakeHumanReadableAmount(self.Db.GetAmountSum(update.effective_user.id, update.effective_chat.id, datetime.now() - timedelta(days=3600), datetime.now()))

            if update.effective_user.id == update.effective_chat.id:
                stat_message += "\n\n((Тут будет статистика по всем чатам))"

            await update.message.reply_text(stat_message)     
        except YSDBException as ex:
            await update.message.reply_text(YSDBot.MakeErrorMessage(ex)) 
        except BaseException as ex:    
            logging.error("[MYSTAT] user id "+YSDBot.GetUserTitleForLog(update.effective_user)+", chat id "+YSDBot.GetChatTitleForLog(update.effective_chat) + ", text: "+update.message.text + ". EXCEPTION: "+str(ex))       
            await update.message.reply_text(YSDBot.MakeExternalErrorMessage(ex))



    

    async def stat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:        
        logging.info("[STAT] user id "+YSDBot.GetUserTitleForLog(update.effective_user)+", chat id "+YSDBot.GetChatTitleForLog(update.effective_chat))    
        if self.StatLimits.Check(update.effective_user.id, update.effective_chat.id):
            logging.warning("[STAT] Ignore command from user id "+YSDBot.GetUserTitleForLog(update.effective_user)+", chat id "+YSDBot.GetChatTitleForLog(update.effective_chat))                
            return

        try:
            day_count = YSDBot.ParseStatParamsAndValidate(update.message.text)            
            stat_message = "📊 Статистика за "+str(day_count)+" дней (чат " + YSDBot.MakeChatTitle(update.effective_chat) + ")\n"
            total_amount = self.Db.GetChatAmountSum(update.effective_chat.id, datetime.now() - timedelta(days=day_count), datetime.now())
            stat_message += "\nКоличество знаков по всем пользователям: "+MakeHumanReadableAmount(total_amount)
            stat_message += "\nВ среднем за сутки: " + MakeHumanReadableAmount(total_amount/day_count)                     
            stat_message += "\nПишуших участников: "+str(self.Db.GetChatActiveUserCount(update.effective_chat.id, datetime.now() - timedelta(days=day_count), datetime.now()))                     
            stat_message += "\n\nℹ️ Чтобы получить топ по юзерам, введите команду /top (или /top <кол-во дней>, например, /top 25)"
            await update.message.reply_text(stat_message)     
        except YSDBException as ex:
            await update.message.reply_text(YSDBot.MakeErrorMessage(ex)) 
        except BaseException as ex:    
            logging.error("[STAT] user id "+YSDBot.GetUserTitleForLog(update.effective_user)+", chat id "+YSDBot.GetChatTitleForLog(update.effective_chat) + ", text: "+update.message.text + ". EXCEPTION: "+str(ex))       
            await update.message.reply_text(YSDBot.MakeExternalErrorMessage(ex))  

    async def top(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:        
        logging.info("[TOP] user id "+YSDBot.GetUserTitleForLog(update.effective_user)+", chat id "+YSDBot.GetChatTitleForLog(update.effective_chat))    
        if self.StatLimits.Check(update.effective_user.id, update.effective_chat.id):
            logging.warning("[TOP] Ignore command from user id "+YSDBot.GetUserTitleForLog(update.effective_user)+", chat id "+YSDBot.GetChatTitleForLog(update.effective_chat))                
            return
        self.LastHandledStatCommand = time.time()

        try:
            day_count = YSDBot.ParseTopParamsAndValidate(update.message.text)
            stat_message = self.MakeTopBlock(update.effective_chat.id, day_count)
            #stat_message+= "\n\nДанные по чату: " + YSDBot.MakeChatTitle(update.effective_chat)         

            await update.message.reply_text(stat_message)     
        except YSDBException as ex:
            await update.message.reply_text(YSDBot.MakeErrorMessage(ex)) 
        except BaseException as ex:    
            logging.error("[TOP] user id "+YSDBot.GetUserTitleForLog(update.effective_user)+", chat id "+YSDBot.GetChatTitleForLog(update.effective_chat) + ", text: "+update.message.text + ". EXCEPTION: "+str(ex))       
            await update.message.reply_text(YSDBot.MakeExternalErrorMessage(ex))              

    @staticmethod
    def get_help() -> str:
        result = "Команды: "
        result +="\n📈 Моя статиcтика: /mystat [full]"
        result +="\n➕ Добавление знаков: /push <количеcтво знаков>"
        result +="\n❕ Примеры:"
        result +="\n❕▫️ /push 190"
        result +="\n❕▫️ /push 5k"
        result +="\n❌ Удаление последней записи о знаках: /pop yes"
        result +="\n🏆 Топ юзеров за период: /top [<кол-во дней>]"        
        result +="\n❕ Примеры:"
        result +="\n❕▫️ /top 15"
        result +="\n❕▫️ /top"        
        result +="\n❕ Значение по-умолчанию: 7"
        result +="\n📊 Статистика чата: /stat [<кол-во дней>]"
        result +="\n❕ Значение по-умолчанию: 7"

        return result

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        ut = YSDBot.GetUserTitleForLog(update.effective_user)
        logging.info("[STATUS] user id "+ut+", chat id "+YSDBot.GetChatTitleForLog(update.effective_chat))    
        status_msg = "Привет, "+YSDBot.MakeUserTitle(update.effective_user)+"! ("+ut+")"
        status_msg +="\nЭто чат: "+YSDBot.MakeChatTitle(update.effective_chat)
        uptime_sec = time.time() - self.StartTS
        uptime = timedelta(seconds = uptime_sec)
        status_msg +="\nАптайм "+ str(uptime)
        status_msg += "\n\n"+ YSDBot.get_help()

        #status_msg +="\nВерсия "+ str(uptime)
        await update.message.reply_text(status_msg)

    async def downloader(self, update, context):            
        logging.info("[DOWNLOADER] user id "+YSDBot.GetUserTitleForLog(update.effective_user))    

        try:
            if not self.Db.IsUploadAllowedForUser(update.effective_user.id):
                raise YSDBException("Вам не разрешена загрузка файлов")

            file = await context.bot.get_file(update.message.document)       
            
            if file.file_size > self.MaxFileSize:
                raise YSDBException("Файл слишком большой. Максимальный разрешённый размер: "+MakeHumanReadableAmount(self.MaxFileSize))
            
            file_full_path = self.FileStorage.GetFileFullPath(file.file_path)
            logging.info("[DOWNLOADER] user id "+YSDBot.GetUserTitleForLog(update.effective_user)+" file size "+str(file.file_size)+" downloading...") 
            await file.download_to_drive(file_full_path) 
            logging.info("[DOWNLOADER] user id "+YSDBot.GetUserTitleForLog(update.effective_user)+" file size "+str(file.file_size)+" download success") 

            await update.message.reply_text("☑️ Файл успешно загружен. Имя файла: "+file.file_path)
        except YSDBException as ex:
            await update.message.reply_text(YSDBot.MakeErrorMessage(ex)) 
        except BaseException as ex:    
            logging.error("[DOWNLOADER] user id "+YSDBot.GetUserTitleForLog(update.effective_user)+ ". EXCEPTION: "+str(ex))       
            await update.message.reply_text(YSDBot.MakeExternalErrorMessage(ex))         


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    parser = argparse.ArgumentParser(
        prog = 'YSDB', description = '''Your self-discipline bot''', epilog = '''(c) 2024''')   


    parser.add_argument ('--conf', dest='conf', action="store", type=str, required=True)

    args = parser.parse_args()

    
    with open(args.conf, 'r') as file:
        conf = json.load(file)

       
    file_str = FileStorage(conf['files_dir'])

    db = DbWorkerService(conf['db'])

    app = ApplicationBuilder().token(conf['bot_token']).build()

    bot = YSDBot(db, file_str)

    app.add_handler(CommandHandler("status", bot.status))
    app.add_handler(CommandHandler("push", bot.push))
    app.add_handler(CommandHandler("pop", bot.pop))
    app.add_handler(CommandHandler("mystat", bot.mystat))
    app.add_handler(CommandHandler("stat", bot.stat))
    app.add_handler(CommandHandler("top", bot.top))
    app.add_handler(MessageHandler(filters.Document.ALL, bot.downloader))

    app.run_polling()

