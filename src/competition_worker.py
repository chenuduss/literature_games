from db_worker import DbWorkerService, CompetitionInfo, CompetitionStat, ChatInfo
from litgb_exception import LitGBException, CompetitionNotFound
from datetime import datetime, timezone, timedelta

class CompetitionFullInfo:
    def __init__(self, comp:CompetitionInfo, stat:CompetitionStat|None = None, chat:ChatInfo|None = None): 
        self.Comp = comp
        self.Stat = stat
        self.Chat = chat

class ComepetitionWorker:
    def __init__(self, db:DbWorkerService):
        self.Db = db
        self.CompetitionsListDefaultFutureInterval = timedelta(days=40)
        self.CompetitionsListDefaultPastInterval = timedelta(days=3)        
                 
    def FindCompetition(self, comp_id:int) -> CompetitionInfo:     
        comp = self.Db.FindCompetition(comp_id)
        if comp is None:
            raise CompetitionNotFound(comp_id)
        return comp

    def FindNotFinishedCompetition(self, comp_id:int) -> CompetitionInfo:
        comp = self.FindCompetition(comp_id)
        if comp.Finished is None:
            return comp
        
        raise LitGBException("🛑 Конкурс уже завершён")                    
    
    def FindCompetitionInPollingState(self, comp_id:int) -> CompetitionInfo:
        comp = self.FindNotFinishedCompetition(comp_id)
        if not comp.IsPollingStarted():
            raise LitGBException("🚫 Конкурс не перешёл в стадию голосования")
        return comp    

    def FindCompetitionBeforePollingStage(self, comp_id:int) -> CompetitionInfo:
        comp = self.FindNotFinishedCompetition(comp_id)
        if datetime.now(timezone.utc) >= comp.AcceptFilesDeadline:
            raise LitGBException("дедлайн приёма файлов уже прошёл")    
        if not comp.IsPollingStarted():
            return comp        
        
        raise LitGBException("Конкурс в стадии голосования")
    
    @staticmethod
    def CheckCompetitionJoinable(comp:CompetitionInfo) -> str|None:
        if not (comp.Finished is None):
            return "конкурс завершён"
        if comp.IsPollingStarted():
            return "конкурс в стадии голосования"

        if comp.IsOpenType():        
            if comp.Confirmed is None:
                return "к конкурсу нельзя присоединиться"
            if datetime.now(timezone.utc) >= comp.AcceptFilesDeadline:
                return "прошёл дедлайн отправки работ"
        else:            
            if not (comp.Confirmed is None):
                return "к конкурсу нельзя присоединиться"

        return None  

    def FindJoinableCompetition(self, comp_id:int) -> CompetitionInfo:
        comp = self.FindCompetitionBeforePollingStage(comp_id)

        reason = self.CheckCompetitionJoinable(comp)
        if reason is None:
            return comp
            
        raise LitGBException(reason)         
    
    @staticmethod
    def CheckCompetitionPropertyChangable(comp: CompetitionInfo) -> str|None:
        if not (comp.Started is None):
            return "🚫 Конкурс стартовал, изменить его свойства уже нельзя"    
        return None
        
    @staticmethod
    def EnsureCompetitionCreator(comp: CompetitionInfo, user_id:int) -> str|None:
        if comp.CreatedBy != user_id:
            raise LitGBException("изменение свойств конкурса разрешено только его создателю")        
        
    def FindPropertyChangableCompetition(self, comp_id:int, check_creator:int|None) -> CompetitionInfo:
        comp = self.FindCompetitionBeforePollingStage(comp_id)

        if not (check_creator is None):
            self.EnsureCompetitionCreator(comp, check_creator)

        reason = self.CheckCompetitionPropertyChangable(comp)
        if reason is None:
            return comp
        
        raise LitGBException(reason)
    
    def FindFileAcceptableCompetition(self, id:int) -> CompetitionInfo:
        comp = self.FindCompetitionBeforePollingStage(id)
        if comp.Started is None:
            raise LitGBException("конкурс ещё не стартовал, приём файлов возможен только в стартовавший конкурс")
        return comp
    
    @staticmethod
    def CheckCompetitionLeaveable(comp:CompetitionInfo) -> str|None:
        if not (comp.PollingStarted is None):
            return "нельзя выйти из конкурса на стадии голосования"

        if comp.IsClosedType():  
            if not (comp.Started is None):
                return "из закрытого конкурса нельзя выйти в после того, как он стартовал" 

        return None  

    def FindLeavableCompetition(self, id:int) -> CompetitionInfo:
        comp = self.FindCompetitionBeforePollingStage(id)
        reason = self.CheckCompetitionLeaveable()        
        if reason is None:
            return comp
        
        raise LitGBException(reason)
    
    @staticmethod      
    def CheckCompetitionEndCondition(comp:CompetitionInfo, stat:CompetitionStat) -> bool:
        if comp.IsClosedType():
            return len(stat.SubmittedMembers) < 2
        else:
            return len(stat.SubmittedMembers) < 3

    def GetCompetitionFullInfo(self, comp:CompetitionInfo) -> CompetitionFullInfo:
        stat = self.Db.GetCompetitionStat(comp.Id)
        chat = None
        if not (comp.ChatId is None):
            chat = self.Db.FindChat(comp.ChatId)
        return CompetitionFullInfo(comp, stat, chat)            
    
    def ReleaseUserFilesFromCompetition(self, user_id: int, comp:CompetitionInfo, unreg:bool) -> CompetitionFullInfo:
        if unreg:
            self.Db.UnregUser(comp.Id, user_id)
        else:    
            self.Db.ReleaseUserFiles(comp.Id, user_id)

    @staticmethod
    def IsCompetitionСancelable(comp:CompetitionInfo) -> str|None:
        if comp.IsPollingStarted():
            return "конкурс нельзя отменить в стадии голосования"
        
        if comp.IsClosedType():
            if comp.Confirmed:
                return "Закрытый конкурс нельзя отменить после подтверждения всех участников"
            
        return None  

    def FindNotAttachedCompetition(self, comp_id:int) -> CompetitionInfo:
        comp = self.FindCompetitionBeforePollingStage(comp_id)
        if not (comp.ChatId is None):
            raise LitGBException("Конкурс уже привязан ")
        if comp.IsStarted():
            raise LitGBException("Конкурс уже стартовал, а значит его уже нельзя привязать ни к какому чату")
        return comp              

    def FindCancelableCompetition(self, comp_id:int) -> CompetitionInfo:
        comp = self.FindCompetitionBeforePollingStage(comp_id)

        reason = self.IsCompetitionСancelable(comp)
        if reason is None:
            return comp
        raise LitGBException(reason)            

    def CancelCompetition(self, comp_id:int) -> CompetitionInfo:
        comp = self.FindCancelableCompetition(comp_id)
        return self.Db.FinishCompetition(comp.Id, True)
    
    def GetCompetitionList(self, list_type:str, user_id:int, chat_id:int) -> list[CompetitionInfo]:
        after = datetime.now(timezone.utc) - self.CompetitionsListDefaultPastInterval
        before = datetime.now(timezone.utc) + self.CompetitionsListDefaultFutureInterval        

        if list_type == "chatrelated":
            return self.Db.SelectChatRelatedCompetitions(chat_id, after, before)
        elif list_type == "allactiveattached":
            return self.Db.SelectActiveAttachedCompetitions(after, before)
        elif list_type == "my":
            return self.Db.SelectUserRelatedCompetitions(user_id, after, before)        
        elif list_type == "joinable":
            return self.Db.SelectJoinableCompetitions(after, before)        
        
        
        raise LitGBException("unknown competitions list type: "+list_type)      