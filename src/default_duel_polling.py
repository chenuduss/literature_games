from competition_polling import ICompetitionPolling
from db_worker import DbWorkerService, FileInfo, CompetitionInfo, CompetitionStat, ChatInfo
from telegram import Update, User, Chat, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler


class DefaultDuelPolling(ICompetitionPolling):
    Name:str = "default_duel"

    def __init__(self, db:DbWorkerService):
        ICompetitionPolling.__init__(self, db)

    async def PollingMessageHandler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, comp:CompetitionInfo):
        raise NotImplementedError("DefaultDuelPolling.PollingMessageHandler")