from competition_polling import ICompetitionPolling, PollingResults
from db_worker import DbWorkerService, FileInfo, CompetitionInfo, CompetitionStat, UserStub, PollingSchemaInfo, PollingFileResults, FileBallot
from telegram import Update, User, Chat, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, filters, CallbackQueryHandler
import re
from litgb_exception import LitGBException
from competition_worker import CompetitionWorker

class DefaultDuelPolling(ICompetitionPolling):
    Name:str = "default_duel"
    MenuQueryRegex = re.compile("vote:(\\d+)")
    MaxBallotsPerPolling = 500

    def __init__(self, db:DbWorkerService, schema_config:PollingSchemaInfo, comp_worker:CompetitionWorker):
        ICompetitionPolling.__init__(self, db, schema_config)
        self.CompWorker = comp_worker

    def GetMinimumMemberCount(self) -> int:
        return 2
    def GetMaximumMemberCount(self) -> int:
        return 2          

    
    def MakeQueryString(self, comp_id:int, query:str) -> str:
        return ICompetitionPolling.MakeMenuQuery(self.Config.Id, comp_id, query)
    
    def GetPollingMessageText(self, comp:CompetitionInfo, comp_stat:CompetitionStat, update: Update) -> tuple[str, int]:
        msgtext = ICompetitionPolling.MakePollingMessageHeader(comp, self.Config)

        voted_user_count = self.Db.GetVotedUserCount(comp.Id)

        msgtext += "\n\nКол-во проголосовавших: "+str(voted_user_count)
        if voted_user_count >= self.MaxBallotsPerPolling:
            msgtext += "\n❗️ Достигнут лимит количества проголосовавших!"
        
        if update.effective_user.id == update.effective_chat.id:
            competition_ballots = self.Db.SelectCompetitionBallots(comp.Id)
            user_ballots = competition_ballots.get(UserStub(update.effective_user.id), [])
            if len(user_ballots) > 0:
                file = self.Db.FindFile(user_ballots[0].FileId)
                if file is None:
                    msgtext += "\n\nВаш голос за рассказ: ОШИБКА! Файл не найден"    
                else:    
                    msgtext += "\n\nВаш голос за рассказ: #"+str(file.Id)+" "+file.NameForMessage()
            else:
                if not comp_stat.IsUserSubmitted(update.effective_user.id):
                    msgtext += "\n\nВы ещё не голосовали в этом конкурсе."
                else:
                    msgtext += "\n\nВам нельзя голосовать, потому что вы автор одного из рассказов."    

        return (msgtext, voted_user_count)

    def MakeKeyboard(self, update: Update, comp:CompetitionInfo, comp_stat:CompetitionStat) -> InlineKeyboardMarkup:
        keyboard = []

        vote_buttons_allowed = False
        if update.effective_chat.id != update.effective_user.id:
            vote_buttons_allowed = True
        else:
            vote_buttons_allowed = not comp_stat.IsUserSubmitted(update.effective_chat.id)

        if vote_buttons_allowed:
            for files in comp_stat.SubmittedFiles.values():
                for f in files:
                    keyboard.append([InlineKeyboardButton("👍 #"+str(f.Id)+": "+f.NameForButtonCaption(), callback_data=self.MakeQueryString(comp.Id, "vote:"+str(f.Id)) )]) 

        return InlineKeyboardMarkup(keyboard)

    async def PollingMessageHandler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, comp:CompetitionInfo, send_reply:bool):
        comp_info = self.CompWorker.GetCompetitionFullInfo(comp)        

        comp_stat = self.Db.GetCompetitionStat(comp.Id)
        msgtext, voted_user_count = self.GetPollingMessageText(comp, comp_stat, update)

        keybd =InlineKeyboardMarkup([])
        if voted_user_count < self.MaxBallotsPerPolling:
            keybd = self.MakeKeyboard(update, comp, comp_info.Stat)
            
        if send_reply:
            await update.message.reply_text(msgtext, reply_markup=keybd)        
        else:        
            await context.bot.send_message(update.effective_chat.id, msgtext, reply_markup=keybd)

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

        self.Db.EnsureUserExists(update.effective_user.id)
        voted_user_count = self.Db.DeleteUserBallots(comp.Id, update.effective_user.id)
        if voted_user_count >= self.MaxBallotsPerPolling:
            await query.answer("Достигнут лимит количества проголосовавших")
            return
        self.Db.InsertOrUpdateBallots([(comp.Id, update.effective_user.id, file_id, 1)])        
        
        updated_msgtext, _ = self.GetPollingMessageText(comp, comp_stat, update)                     
        await query.answer("Голос принят")
        await query.edit_message_text(
            text = updated_msgtext,
            reply_markup = self.MakeKeyboard(comp))
        
    def CalcPollingResults(self, comp:CompetitionInfo, comp_stat:CompetitionStat) -> PollingResults:
        
        file_scores:dict[int, int] = {}
        for files in comp_stat.SubmittedFiles.values():
            for file in files:
                file_scores[file.Id] = 0

        ballots = self.Db.SelectCompetitionBallots(comp.Id)
        for fballots in ballots.values():
            for ballot in fballots:
                file_scores[ballot.FileId] += ballot.Points

        file_ids = list(file_scores.keys())
        if len(file_ids) != 2:
            raise LitGBException("actual file count in duel not eqaul to 2, file count: "+str(len(file_ids)))
        
        f1_author = comp_stat.GetFileSubmitter(file_ids[0])
        f2_author = comp_stat.GetFileSubmitter(file_ids[1])

        f1 = PollingFileResults(0, file_ids[0], file_scores[file_ids[0]])
        f2 = PollingFileResults(0, file_ids[1], file_scores[file_ids[1]])
        if f1.Score > f2.Score:
            f1.RatingPos = 1
            f2.RatingPos = 2
            return PollingResults([f1_author], [], [f2_author], [f1,f2])
        elif f1.Score < f2.Score:
            f1.RatingPos = 2
            f2.RatingPos = 1
            return PollingResults([f2_author], [], [f1_author], [f1,f2])
        else:                        
            f1.RatingPos = 1
            f2.RatingPos = 1
            half_winners = []
            if f1.Score > 0:
                half_winners = [f1_author, f2_author]
            return PollingResults([], half_winners, [], [f1,f2])

    def ForOpenType(self) -> bool:
        return False
