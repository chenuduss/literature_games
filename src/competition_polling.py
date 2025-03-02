from db_worker import DbWorkerService, CompetitionInfo, PollingSchemaInfo, PollingFileResults, CompetitionStat, UserInfo
from telegram import Update, User, Chat, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
import re
from litgb_exception import LitGBException

class PollingResults:
    def __init__(self, winners:list[UserInfo], half_winners:list[UserInfo], losers:list[UserInfo], table:list[PollingFileResults]):
        self.Winners = winners
        self.HalfWinners = half_winners
        self.Losers = losers
        self.RatingTable = table

class ICompetitionPolling:
    PollingMenuQueryRegex = re.compile("poll:(\\d+):(\\d+):(\S*)")


    @staticmethod
    def GetMenuPattern() -> str:
        return "poll:\\d+:\\d+:\S*"    

    @staticmethod
    def ParsePollingMenuQuery(query:str) -> tuple[int, int, str]:
        try:
            m = ICompetitionPolling.PollingMenuQueryRegex.match(query)
            return (int(m.group(1)), int(m.group(2)), m.group(3))
        except BaseException as ex:
            raise LitGBException("invalid polling menu query")   

    @staticmethod
    def MakeMenuQuery(polling_type:str, comp_id:int, query:str) -> str:
        return "poll:"+polling_type+":"+str(comp_id)+":"+query
    
    def __init__(self, db:DbWorkerService, schema_config:PollingSchemaInfo):
        self.Db = db
        self.Config = schema_config

    def GetMinimumMemberCount(self) -> int:
        raise NotImplementedError("ICompetitionPolling.GetMinimumMemberCount")
    def GetMaximumMemberCount(self) -> int:
        raise NotImplementedError("ICompetitionPolling.GetMaximumMemberCount")    
    
    @staticmethod
    def MakePollingMessageHeader(comp:CompetitionInfo, schema:PollingSchemaInfo) -> str:
        return "ГОЛОСОВАНИЕ #"+str(comp.Id)+"\nТип: "+schema.Title
    
    async def PollingMessageHandler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, comp:CompetitionInfo, send_reply:bool):
        raise NotImplementedError("ICompetitionPolling.PollingMessageHandler")

    async def MenuHandler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, comp_id:int, qdata:str):
        raise NotImplementedError("ICompetitionPolling.MenuHandler")
    
    def CalcPollingResults(self, comp:CompetitionInfo, comp_stat:CompetitionStat) -> PollingResults:
        raise NotImplementedError("ICompetitionPolling.CalcPollingResults")   
    
    def ForOpenType(self) -> bool:
        raise NotImplementedError("ICompetitionPolling.ForOpenType")   
