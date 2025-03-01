from competition_polling import ICompetitionPolling
from db_worker import DbWorkerService, FileInfo, CompetitionInfo, CompetitionStat, ChatInfo, PollingSchemaInfo
from telegram import Update, User, Chat, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
import re
from litgb_exception import LitGBException
from competition_worker import CompetitionWorker

class DefaultDuelPolling(ICompetitionPolling):
    Name:str = "default_duel"
    MenuQueryRegex = re.compile("vote:(\\d+)")

    def __init__(self, db:DbWorkerService, schema_config:PollingSchemaInfo, comp_worker:CompetitionWorker):
        ICompetitionPolling.__init__(self, db, schema_config)
        self.CompWorker = comp_worker

    def GetMinimumMemberCount(self) -> int:
        return 2    

    @staticmethod
    def MakeQueryString(comp_id:int, query:str) -> str:
        return ICompetitionPolling.MakeMenuQuery(DefaultDuelPolling.Name, comp_id, query)
    
    def GetPollingMessageText(self, comp:CompetitionInfo, poll_schema:PollingSchemaInfo, update: Update) -> str:
        msgtext = ICompetitionPolling.MakePollingMessageHeader(comp, poll_schema)

        competition_ballots = self.Db.SelectCompetitionBallots(comp.Id)

        msgtext += "\n\nКол-во проголосовавших: "+str(len(competition_ballots.keys()))
        
        if update.effective_user.id == update.effective_chat.id:
            user_ballots = competition_ballots.get(update.effective_user.id, [])
            if len(user_ballots) > 0:
                file = self.Db.FindFile(user_ballots[0].FileId)
                if file is None:
                    msgtext += "\n\nВаш голос за рассказ: ОШИБКА! Файл не найден"    
                else:    
                    msgtext += "\n\nВаш голос за рассказ: #"+str(file.Id)+" "+file.Title
            else:
                msgtext += "\n\nВы ещё не голосовали в этом конкурсе"

    def MakeKeyboard(self, comp:CompetitionInfo) -> InlineKeyboardMarkup:
        keyboard = []
        InlineKeyboardMarkup(keyboard)

    async def PollingMessageHandler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, comp:CompetitionInfo, send_reply:bool):
        schema = self.Db.GetPollingSchema(comp.PollingScheme)
        msgtext = self.GetPollingMessageText(comp, schema, update)

        
        if send_reply:
            await update.message.reply_text(msgtext, reply_markup=self.MakeKeyboard(comp))        
        else:        
            await context.bot.send_message(update.effective_chat.id, msgtext, reply_markup=self.MakeKeyboard(comp))

    @staticmethod
    def ParseMenuQuery(query:str) -> int:
        try:
            m = DefaultDuelPolling.MenuQueryRegex.match(query)
            return int(m.group(1))
        except BaseException as ex:
            raise LitGBException("DefaultDuelPolling: invalid polling menu query")             

    async def MenuHandler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, comp_id:int, qdata:str):
        file_id = self.ParseMenuQuery(qdata)
        comp = self.CompWorker.FindCompetitionInPollingState(comp_id)
        comp_stat = self.Db.GetCompetitionStat(comp.Id)

        query = update.callback_query 
        if comp_stat.IsUserSubmitted(update.effective_user.id):
            await query.answer("Участникам нельзя голосовать в дуэли")
            return

        self.Db.InsertOrUpdateBallots([(comp.Id, update.effective_user.id, file_id, 1)])
        
        schema = self.Db.GetPollingSchema(comp.PollingScheme)
        updated_msgtext = self.GetPollingMessageText(comp, schema, update)                     
        await query.answer("Голос принят")
        await query.edit_message_text(
            text = updated_msgtext,
            reply_markup = self.MakeKeyboard(comp))        
