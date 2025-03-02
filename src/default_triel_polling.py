from competition_polling import ICompetitionPolling, PollingResults
from db_worker import DbWorkerService, FileInfo, CompetitionInfo, CompetitionStat, ChatInfo, PollingSchemaInfo
from telegram import Update, User, Chat, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, filters, CallbackQueryHandler
import re
from litgb_exception import LitGBException
from competition_worker import CompetitionWorker

class DefaultTrielPolling(ICompetitionPolling):
    Name:str = "default_triel"

    def __init__(self, db:DbWorkerService, schema_config:PollingSchemaInfo, comp_worker:CompetitionWorker):
        ICompetitionPolling.__init__(self, db, schema_config)
        self.CompWorker = comp_worker

    def GetMinimumMemberCount(self) -> int:
        return 3   
    def GetMaximumMemberCount(self) -> int:
        return 3        

    def GetPollingMessageText(self, comp:CompetitionInfo, poll_schema:PollingSchemaInfo, update: Update) -> str:
        msgtext = ICompetitionPolling.MakePollingMessageHeader(comp, poll_schema)

        msgtext += "\n\nВ разработке"

        return msgtext

    def MakeKeyboard(self, update: Update, comp:CompetitionInfo, comp_stat:CompetitionStat) -> InlineKeyboardMarkup:
        keyboard = []
        InlineKeyboardMarkup(keyboard)          
    
    async def PollingMessageHandler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, comp:CompetitionInfo, send_reply:bool):
        comp_info = self.CompWorker.GetCompetitionFullInfo(comp)        

        msgtext = self.GetPollingMessageText(comp, comp_info.PollingHandler.Config, update)

        
        if send_reply:
            await update.message.reply_text(msgtext, reply_markup=self.MakeKeyboard(update, comp, comp_info.Stat))        
        else:        
            await context.bot.send_message(update.effective_chat.id, msgtext, reply_markup=self.MakeKeyboard(update, comp, comp_info.Stat))    

    async def MenuHandler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, comp_id:int, qdata:str):
        pass
        
    def CalcPollingResults(self, comp:CompetitionInfo, comp_stat:CompetitionStat) -> PollingResults:
        return PollingResults([], [], [], [])
    
    def ForOpenType(self) -> bool:
        return False    