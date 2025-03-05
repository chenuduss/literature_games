from competition_polling import ICompetitionPolling, PollingResults
from db_worker import DbWorkerService, FileInfo, CompetitionInfo, CompetitionStat, UserStub, PollingSchemaInfo, UserInfo, PollingFileResults
from telegram import Update, User, Chat, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, filters, CallbackQueryHandler
import re
from litgb_exception import LitGBException, OnlyPrivateMessageAllowed
from competition_worker import CompetitionWorker
import json
import logging

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
                msgtext += "\n\n🗳 Ваше голосование:"
                user_ballots.sort(key=lambda x: x.Points)
                i = 0
                for b in reversed(user_ballots):
                    i += 1
                    f = self.Db.FindFile(b.FileId)
                    msgtext += "\n"+str(i)+". #"+str(f.Id)+" "+f.NameForMessage()
            else:
                msgtext += "\n\nВы не голосовали."

            if not (polling_draft is None):
                msgtext += "\n\n📄 Ваш черновик голосования:"
                f = comp_stat.GetFileInfo(polling_draft['pos1'])
                msgtext += "\n1. #"+str(f.Id)+" "+f.NameForMessage()
                if 'pos2' in polling_draft:
                    f = comp_stat.GetFileInfo(polling_draft['pos2'])
                    msgtext += "\n2. #"+str(f.Id)+" "+f.NameForMessage()

        return msgtext
    
    def MakeQueryString(self, comp_id:int, query:str) -> str:
        return ICompetitionPolling.MakeMenuQuery(self.Config.Id, comp_id, query)  

    def MakeKeyboard(self, update: Update, comp:CompetitionInfo, comp_stat:CompetitionStat, polling_draft:dict|None) -> InlineKeyboardMarkup:
        keyboard = []
        if update.effective_user.id != update.effective_chat.id:
            return InlineKeyboardMarkup(keyboard)

        if polling_draft is None:
            for au, files in comp_stat.SubmittedFiles.items():
                for f in files:
                    if au.Id != update.effective_user.id:
                        keyboard.append([InlineKeyboardButton("#"+str(f.Id)+" "+f.NameForButtonCaption(), callback_data=self.MakeQueryString(comp.Id, "select1:"+str(f.Id)))]) 
        else:
            pos1_id = polling_draft['pos1']
            for au, files in comp_stat.SubmittedFiles.items():
                for f in files:
                    if (au.Id != update.effective_user.id) and (f.id != pos1_id):
                        keyboard.append([InlineKeyboardButton("#"+str(f.Id)+" "+f.NameForButtonCaption(), callback_data=self.MakeQueryString(comp.Id, "select2:"+str(f.Id)))])
            if self.ValidatePollingDraft(polling_draft, UserStub(update.effective_user.id), comp_stat):
                keyboard.append([InlineKeyboardButton("Проголосовать", callback_data=self.MakeQueryString(comp.Id, "apply:0"))]) 

            keyboard.append([InlineKeyboardButton("Очистить черновик", callback_data=self.MakeQueryString(comp.Id, "discard_draft:0"))])     
                

        return InlineKeyboardMarkup(keyboard) 
    
    async def PollingMessageHandler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, comp:CompetitionInfo, send_reply:bool):
        
        comp_info = self.CompWorker.GetCompetitionFullInfo(comp)    
        polling_draft = None
        if update.effective_user.id != update.effective_chat.id:
            polling_draft = self.Db.ReadUserPollingDraft(comp.Id, update.effective_user.id)
        msgtext = self.GetPollingMessageText(comp, comp_info.Stat, update, polling_draft)
        

        kbd = self.MakeKeyboard(update, comp, comp_info.Stat, polling_draft)

        if send_reply:
            await update.message.reply_text(msgtext, reply_markup=kbd)        
        else:        
            await context.bot.send_message(update.effective_chat.id, msgtext, reply_markup=kbd)    

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
        poll_draft = None
        if action == "apply":
            poll_draft = self.GetPollingDraft(comp.Id, update.effective_user.id)            
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
            reply_markup = self.MakeKeyboard(update, comp, comp_info.Stat, poll_draft))
        
    def CalcPollingResults(self, comp:CompetitionInfo, comp_stat:CompetitionStat) -> PollingResults:        

        file_scores:dict[int, int] = {}  #  file_id -> total score 
        for files in comp_stat.SubmittedFiles.values():
            for file in files:
                file_scores[file.Id] = 0

        ballots = self.Db.SelectCompetitionBallots(comp.Id)
        for fballots in ballots.values():
            for ballot in fballots:
                file_scores[ballot.FileId] += ballot.Points

        losers:list[UserInfo] = []

        for u in comp_stat.GetSubmittedMembers():
            if not (u in ballots):
                logging.info("[CALCRES] user "+ u.Title+" is losed because not polled")
                losers.append(u)
                for f in comp_stat.SubmittedFiles[u]:
                    file_scores.pop(f.Id)

        if len(file_scores.keys()) == 0:
            return PollingResults([], [], losers, [])
        
        if len(file_scores.keys()) == 1:
            file_id = list(file_scores.keys())[0]
            f1_author = comp_stat.GetFileSubmitter(file_id)
            f1 = PollingFileResults(1, file_id, file_scores[file_id])
            return PollingResults([f1_author], [], losers, [f1])

        file_ids = list(file_scores.keys())
        if len(file_scores.keys()) == 2:
            f1_author = comp_stat.GetFileSubmitter(file_ids[0])
            f2_author = comp_stat.GetFileSubmitter(file_ids[1])

            f1 = PollingFileResults(0, file_ids[0], file_scores[file_ids[0]])
            f2 = PollingFileResults(0, file_ids[1], file_scores[file_ids[1]])
            if f1.Score > f2.Score:
                f1.RatingPos = 1
                f2.RatingPos = 2
                losers.append(f2_author)
                return PollingResults([f1_author], [], losers, [f1,f2])
            elif f1.Score < f2.Score:
                f1.RatingPos = 2
                f2.RatingPos = 1
                losers.append(f1_author)
                return PollingResults([f2_author], [], losers, [f1,f2])
            else:                        
                f1.RatingPos = 1
                f2.RatingPos = 1
                winners = []
                half_winners = []
                if f1.Score > 0:
                    winners = [f1_author, f2_author]
                else:
                    half_winners = [f1_author, f2_author]
                return PollingResults(winners, half_winners, losers, [f1,f2])            


        # CASE WITH 3 MEMBERS
        file_table = [
            PollingFileResults(0, file_ids[0], file_scores[file_ids[0]]),
            PollingFileResults(0, file_ids[1], file_scores[file_ids[1]]),
            PollingFileResults(0, file_ids[2], file_scores[file_ids[2]])
        ]
        file_table.sort(key=lambda x: x.Score)
        file_table.reverse()        
        file_table[0].RatingPos = 1
        if file_table[0].Score == file_table[1].Score:
            file_table[1].RatingPos = 1
        else:
            file_table[1].RatingPos = 2

        if file_table[1].Score == file_table[2].Score:
            file_table[2].RatingPos = file_table[1].RatingPos
        else:
            file_table[2].RatingPos = file_table[1].RatingPos + 1 

        winners = []
        if file_table[2].RatingPos == 3:
            losers.append(comp_stat.GetFileSubmitter(file_table[2].FileId).Id)

        if file_table[1].RatingPos > file_table[0].RatingPos:
            winners.append(comp_stat.GetFileSubmitter(file_table[0].FileId).Id)

        raise NotImplementedError("DefaultTrielPolling.CalcPollingResults")    


        return PollingResults(winners, [], losers, file_table)
    
    def ForOpenType(self) -> bool:
        return False    
    