from db_worker import DbWorkerService, CompetitionInfo
from telegram import Update, User, Chat, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
import re
from litgb_exception import LitGBException

class ICompetitionPolling:
    PollingMenuQueryRegex = re.compile("poll:(\\S+):(\\d+):(\S*)")

    def __init__(self, db:DbWorkerService):
        self.Db = db

    @staticmethod
    def ParsePollingMenuQuery(query:str) -> tuple[str, int, str]:
        try:
            m = ICompetitionPolling.PollingMenuQueryRegex.match(query)
            return (m.group(1), m.group(2), int(m.group(3)))
        except BaseException as ex:
            raise LitGBException("invalid polling menu query")          

    @staticmethod
    def GetMenuPattern() -> str:
        return "poll:\\S+:\\d+:\S*"
    
    async def PollingMessageHandler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, comp:CompetitionInfo):
        raise NotImplementedError("ICompetitionPolling.PollingMessageHandler")

    async def MenuHandler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, comp_id:int, qdata:str):
        raise NotImplementedError("ICompetitionPolling.MenuHandler")