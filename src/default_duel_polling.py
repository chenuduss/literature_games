from competition_polling import ICompetitionPolling
from db_worker import DbWorkerService, FileInfo, CompetitionInfo, CompetitionStat, ChatInfo
from telegram import Update, User, Chat, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
import re
from litgb_exception import LitGBException

class DefaultDuelPolling(ICompetitionPolling):
    Name:str = "default_duel"
    MenuQueryRegex = re.compile("vote:(\\d+)")

    def __init__(self, db:DbWorkerService):
        ICompetitionPolling.__init__(self, db)

    @staticmethod
    def MakeQueryString(comp_id:int, query:str) -> str:
        return ICompetitionPolling.MakeMenuQuery(DefaultDuelPolling.Name, comp_id, query)

    async def PollingMessageHandler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, comp:CompetitionInfo, send_reply:bool):
        schema = self.Db.GetPollingSchema(comp.PollingScheme)
        msgtext = ICompetitionPolling.MakePollingMessageHeader(comp, schema)

        msgtext += "\n\n\nВ разработке (default_duel)"

        keyboard = []
        if send_reply:
            await update.message.reply_text(msgtext, reply_markup=InlineKeyboardMarkup(keyboard))        
        else:        
            await context.bot.send_message(update.effective_chat.id, msgtext, reply_markup=InlineKeyboardMarkup(keyboard))

    @staticmethod
    def ParseMenuQuery(query:str) -> int:
        try:
            m = DefaultDuelPolling.MenuQueryRegex.match(query)
            return int(m.group(1))
        except BaseException as ex:
            raise LitGBException("DefaultDuelPolling: invalid polling menu query")             

    async def MenuHandler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, comp_id:int, qdata:str):
        file_id = self.ParseMenuQuery(qdata)        
        self.Db.InsertOrUpdateBallots([(comp_id, update.effective_user.id, file_id, 1)])
