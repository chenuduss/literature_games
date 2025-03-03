from competition_polling import ICompetitionPolling, PollingResults
from db_worker import DbWorkerService, FileInfo, CompetitionInfo, CompetitionStat, UserStub, PollingSchemaInfo
from telegram import Update, User, Chat, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, filters, CallbackQueryHandler
import re
from litgb_exception import LitGBException, OnlyPrivateMessageAllowed
from competition_worker import CompetitionWorker
import json

class DefaultTrielPolling(ICompetitionPolling):
    Name:str = "default_triel"
    MenuQueryRegex = re.compile("(\\S+):(\\d+)")
    MaxBallotsPerPolling = 500

    Pos1Points = 2
    Pos2Points = 1
    MemberPoints = 2

    @staticmethod
    def ParseMenuQuery(query:str) -> tuple[str, int]:
        try:
            m = DefaultTrielPolling.MenuQueryRegex.match(query)
            return (m.group(1), int(m.group(2)))
        except BaseException as ex:
            raise LitGBException("DefaultTrielPolling: invalid polling menu query")     

    def __init__(self, db:DbWorkerService, schema_config:PollingSchemaInfo, comp_worker:CompetitionWorker):
        ICompetitionPolling.__init__(self, db, schema_config)
        self.CompWorker = comp_worker

    def GetMinimumMemberCount(self) -> int:
        return 3   
    def GetMaximumMemberCount(self) -> int:
        return 3        

    def GetPollingMessageText(self, comp:CompetitionInfo, comp_stat:CompetitionStat, update: Update, polling_draft:dict|None) -> str:
        msgtext = ICompetitionPolling.MakePollingMessageHeader(comp, self.Config)

        ballots = self.Db.SelectCompetitionBallots(comp.Id)
        
        if len(ballots.keys()) >= self.MaxBallotsPerPolling:
            msgtext += "\n\n❗️ Достигнут лимит количества проголосовавших!"

        members_polled = 0
        for u in ballots.keys():
            if comp_stat.IsUserSubmitted(u.Id):
                members_polled += 1

        msgtext += "\n\nКол-во проголосовавших: "+str(len(ballots.keys()))
        if members_polled > 0:            
            if members_polled >= comp_stat.SubmittedMemberCount():
                msgtext += "\n✅ Все участники проголосовали."
            else:
                msgtext += "\nПроголосовавших участников: "+str(members_polled)


        if update.effective_user.id != update.effective_chat.id:
            msgtext += "\n\n⚠️ Голосование может происходить только в личных сообщениях бота."
        else:
            user_ballots = ballots.get(UserStub(update.effective_user.id), [])
            if len(user_ballots) > 0:    
                msgtext += "\n\nВаше голосование:"
                msgtext += "\n\n(в разработке)"
            else:
                msgtext += "\n\nВы не голосовали."    

            if not (polling_draft is None):
                msgtext += "\n\nВаш черновик голосования"

        return msgtext

    def MakeKeyboard(self, update: Update, comp:CompetitionInfo, comp_stat:CompetitionStat) -> InlineKeyboardMarkup:
        keyboard = []
        if update.effective_user.id != update.effective_chat.id:
            return InlineKeyboardMarkup(keyboard)


                

        return InlineKeyboardMarkup(keyboard) 
    
    async def PollingMessageHandler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, comp:CompetitionInfo, send_reply:bool):
        
        comp_info = self.CompWorker.GetCompetitionFullInfo(comp)    

        msgtext = self.GetPollingMessageText(comp, comp_info.Stat, update)
        
        if send_reply:
            await update.message.reply_text(msgtext, reply_markup=self.MakeKeyboard(update, comp, comp_info.Stat))        
        else:        
            await context.bot.send_message(update.effective_chat.id, msgtext, reply_markup=self.MakeKeyboard(update, comp, comp_info.Stat))    

    def GetPollingDraft(self, comp_id:int, user_id:int) -> dict:
        draft_str = self.Db.ReadUserPollingDraft(comp_id, user_id)
        if len(draft_str) > 3:            
            result = json.loads(draft_str)
            if "pos1" in result:
                return result
        return None
    

    def SavePollingDraft(self, comp_id:int, user_id:int, draft:dict):
        self.Db.SaveUserPollingDraft(comp_id, user_id, json.dumps(draft))   

    @staticmethod
    def ValidatePollingDraft(draft:dict, user_info:UserStub, comp_stat:CompetitionStat) -> bool:
        if not ('pos1' in draft):
            return False
        author = comp_stat.GetFileSubmitter(draft['pos1'])
        if author is None:
            return False
        if author.Id == user_info.Id:
            return False
        
        if 'pos2' in draft:
            author = comp_stat.GetFileSubmitter(draft['pos2'])
            if author is None:
                return False

            if comp_stat.IsUserSubmitted(user_info.Id):            
                return False

        return True

    def SaveBallotsFromDraft(self, comp:CompetitionInfo, user_id:int, draft:dict):
        ballots = []
        if 'pos2' in draft:
            ballots.append((comp.Id, user_id, draft['pos1'], self.Pos1Points))    
            ballots.append((comp.Id, user_id, draft['pos2'], self.Pos2Points))    
        else:
            ballots.append((comp.Id, user_id, draft['pos1'], self.MemberPoints))    
        self.Db.InsertOrUpdateBallots(ballots)
        raise NotImplementedError("DefaultTrielPolling.SaveBallotsFromDraft")

    async def MenuHandler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, comp_id:int, qdata:str):
        if update.effective_user.id != update.effective_chat.id:
            raise OnlyPrivateMessageAllowed()
        
        query = update.callback_query 
        comp = self.CompWorker.FindCompetitionInPollingState(comp_id)
        comp_info = self.CompWorker.GetCompetitionFullInfo(comp.Id)
        action, file_id = self.ParseMenuQuery(qdata)
        if action == "apply":
            poll_draft = self.GetPollingDraft(comp.Id, update.effective_user.id)
            if not ("pos2" in poll_draft):
                raise LitGBException("try apply incomplete poll draft")
            if not self.ValidatePollingDraft(poll_draft):
                raise LitGBException("invalid polling draft")
            
            voted_user_count = self.Db.DeleteUserBallots(comp.Id,  update.effective_user.id)
            if voted_user_count >= self.MaxBallotsPerPolling:
                await query.answer("Достигнут лимит количества проголосовавших")
                return  
            self.SaveBallotsFromDraft(comp_info.Comp, update.effective_user.id, poll_draft)
        elif action == "discard_draft":
            self.Db.SaveUserPollingDraft(comp.Id, update.effective_user.id, "")
        elif action == "select1":
            poll_draft = self.GetPollingDraft(comp.Id, update.effective_user.id)
            if not (poll_draft is None):
                raise LitGBException("select1 action not allowed on not empty draft")
            self.SavePollingDraft(comp.Id, update.effective_user.id, {'pos1': file_id})
        elif action == "select2":
            poll_draft = self.GetPollingDraft(comp.Id, update.effective_user.id)
            if poll_draft is None:
                raise LitGBException("select1 action not allowed on empty draft")
            if poll_draft['pos1'] == file_id:
                raise LitGBException("duplecate pos1 and pos2")
            poll_draft['pos2'] = file_id
            self.SavePollingDraft(comp.Id, update.effective_user.id, poll_draft)
        else:
            raise LitGBException("unknown action: "+action)
        
        updated_msgtext, _ = self.GetPollingMessageText(comp, comp_info.Stat, update)

        
        await query.answer("")
        await query.edit_message_text(
            text = updated_msgtext,
            reply_markup = self.MakeKeyboard(update, comp, comp_info.Stat))
        
    def CalcPollingResults(self, comp:CompetitionInfo, comp_stat:CompetitionStat) -> PollingResults:
        return PollingResults([], [], [], [])
    
    def ForOpenType(self) -> bool:
        return False    
    