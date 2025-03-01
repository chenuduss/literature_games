from competition_polling import ICompetitionPolling
from db_worker import DbWorkerService, FileInfo, CompetitionInfo, CompetitionStat, ChatInfo
from telegram import Update, User, Chat, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler


class DefaultDuelPolling(ICompetitionPolling):
    Name:str = "default_duel"

    def __init__(self, db:DbWorkerService):
        ICompetitionPolling.__init__(self, db)

    async def PollingMessageHandler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, comp:CompetitionInfo, send_reply:bool):
        msgtext = "В разработке (default_duel)"
        keyboard = []

        if send_reply:
            await update.message.reply_text(msgtext, reply_markup=InlineKeyboardMarkup(keyboard))        
        else:        
            await context.bot.send_message(update.effective_chat.id, msgtext, reply_markup=InlineKeyboardMarkup(keyboard))

    async def PollingMessageHandler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, comp:CompetitionInfo, send_reply:bool):
        raise NotImplementedError("DefaultDuelPolling.PollingMessageHandler")