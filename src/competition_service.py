from competition_worker import ComepetitionWorker
from db_worker import DbWorkerService, CompetitionInfo, CompetitionStat, UserInfo
import logging
from telegram.ext import ContextTypes
from litgb_exception import LitGBException
from fb2_tool import SectionsToFb2
from utils import DatetimeToString
from file_service import FileService
from file_storage import FileStorage

class CompetitionService(ComepetitionWorker, FileService):
    def __init__(self, db:DbWorkerService, file_stor:FileStorage):
        ComepetitionWorker.__init__(self, db)
        FileService.__init__(self, file_stor)
      

    async def ReportCompetitionStateToAttachedChat(self, 
            comp:CompetitionInfo, 
            context: ContextTypes.DEFAULT_TYPE, 
            message:str|None = None):
        
        if comp.ChatId is None:
            return
        
        if not (comp.Finished is None):
            if comp.Canceled:
                message_text = "❌ Конкурс #"+str(comp.Id)+" отменён"
                if not (message is None):
                    message_text += "\n\n⁉️ Причина: "+ message                   
                await context.bot.send_message(comp.ChatId, message_text)
            else:    
                await context.bot.send_message(comp.ChatId, "✅ Конкурс #"+str(comp.Id)+" завершён")

            return
        
        if comp.IsPollingStarted():
            await context.bot.send_message(comp.ChatId, "🔔 Конкурс #"+str(comp.Id)+" перешёл в стадию голосования. Дедлайн: "+DatetimeToString(comp.PollingDeadline))
            return
        
        if comp.IsStarted():
            await context.bot.send_message(comp.ChatId, "🔔Конкурс #"+str(comp.Id)+" стартовал. Дедлайн приёма файлов: "+DatetimeToString(comp.AcceptFilesDeadline))
            return       
        

        if not (comp.Confirmed is None):
            await context.bot.send_message(comp.ChatId, "✅ Конкурс #"+str(comp.Id)+" подтверждён")
            return

        await context.bot.send_message(comp.ChatId, "☑️ Конкурс #"+str(comp.Id)+" привязан к этому чату")

    async def SendSubmittedFiles(self, chat_id:int, comp_stat:CompetitionStat, context: ContextTypes.DEFAULT_TYPE):
        for files in comp_stat.SubmittedFiles.values():
            for file in files:                
                await self.SendFB2(file, chat_id, context)

    async def SendMergedSubmittedFiles(self, chat_id:int, comp_id:str, comp_stat:CompetitionStat, context: ContextTypes.DEFAULT_TYPE):
        section_filenames = []

        for files in comp_stat.SubmittedFiles.values():
            for file in files:                
                section_filenames.append(file.FilePath)

        merged_fb2_filepath = None
        try:
            file_name = "comp_"+str(comp_id)+"_all.fb2"
            merged_fb2_filepath = self.FileStorage.GetFileFullPath(file_name)
            SectionsToFb2(section_filenames, merged_fb2_filepath, "Конкурс #"+str(comp_id))
            file_obj = open(merged_fb2_filepath, "rb")
            await context.bot.send_document(chat_id, file_obj, filename=file_name)
        finally:
            if not (merged_fb2_filepath is None):
                self.FileStorage.DeleteFileFullPath(merged_fb2_filepath)  

    async def AfterConfirmCompetition(self, comp:CompetitionInfo, context: ContextTypes.DEFAULT_TYPE):
        await self.ReportCompetitionStateToAttachedChat(comp, context)

        if comp.IsClosedType():
            if comp.ChatId is None:
                return
        
        comp = self.Db.StartCompetition(comp.Id)
        await self.AfterStartCompetition(comp, context)                

    async def CheckClosedCompetitionConfirmation(self, 
            comp:CompetitionInfo, comp_stat:CompetitionStat, context: ContextTypes.DEFAULT_TYPE) -> CompetitionInfo:
         
         if (len(comp_stat.RegisteredMembers) >= comp.DeclaredMemberCount) and (not (comp.ChatId is None)):
            comp = self.Db.ConfirmCompetition(comp.Id)
            await self.AfterConfirmCompetition(comp, context)
            
         return comp
    
    async def AfterCompetitionAttach(self, comp:CompetitionInfo, context: ContextTypes.DEFAULT_TYPE) -> CompetitionInfo:
        await self.ReportCompetitionStateToAttachedChat(comp, context)
        if comp.IsOpenType():
            comp = self.Db.ConfirmCompetition(comp.Id)
            await self.AfterConfirmCompetition(comp, context)
            return comp
        else:
            stat = self.Db.GetCompetitionStat(comp.Id)
            return await self.CheckClosedCompetitionConfirmation(comp, stat, context)      

    async def AfterJoinMember(self, comp:CompetitionInfo, comp_stat:CompetitionStat, context: ContextTypes.DEFAULT_TYPE) -> CompetitionInfo:
        if comp.IsClosedType():
            return await self.CheckClosedCompetitionConfirmation(comp, comp_stat, context)
        
        return comp        

    async def AfterStartCompetition(self, comp:CompetitionInfo, context: ContextTypes.DEFAULT_TYPE):
        await self.ReportCompetitionStateToAttachedChat(comp, context)

    async def AfterPollingStarted(self, comp:CompetitionInfo, comp_stat:CompetitionStat, context: ContextTypes.DEFAULT_TYPE):
        await self.ReportCompetitionStateToAttachedChat(comp, context) 
        
        await self.SendSubmittedFiles(comp.ChatId, comp_stat, context)
        await self.SendMergedSubmittedFiles(comp.ChatId, comp.Id, comp_stat, context) 

    async def ProcessLosedMember(self, comp:CompetitionInfo, user:UserInfo, context: ContextTypes.DEFAULT_TYPE):
        self.Db.IncreaseUserLosses(user.Id)
        await context.bot.send_message(comp.ChatId, "Пользователь "+user.Title+" проиграл в конкурсе #"+str(comp.Id))        

    async def ProcessFailedMembers(self, comp:CompetitionInfo, context: ContextTypes.DEFAULT_TYPE):
        comp_stat = self.Db.GetCompetitionStat(comp.Id)        
        for user in comp_stat.RegisteredMembers:
            user_files = comp_stat.SubmittedFiles.get(user.Id, [])
            if len(user_files) == 0:
                await self.ProcessLosedMember(comp, user, context)        

    async def ShowFileAuthors(self, comp:CompetitionInfo, comp_stat:CompetitionStat, context: ContextTypes.DEFAULT_TYPE):        
        message_text = "Авторы работ в конкурсе #"+str(comp.Id)+"\n\n"
        if comp.IsClosedType():
            for user_id, files in comp_stat.SubmittedFiles.items():
                user_title = "!ОШИБКА!"
                for u in comp_stat.SubmittedMembers:
                    if u.Id == user_id:
                        user_title = u.Title
                        break
                    
                for f in files:
                    message_text +=  user_title + ": " + f.Title
        else:
            for user_id, files in comp_stat.SubmittedFiles.items():
                user_title = "!ОШИБКА!"
                for u in comp_stat.SubmittedMembers:
                    if u.Id == user_id:
                        user_title = u.Title
                        break
                    
                for f in files:
                    message_text +=  user_title + ": " + f.Title            
            message_text += "\n\nВопрос: в открытом конкурсе (самосуд) выводить всех или выводить только победителей? Имеет ли проигравший право сохранить свою анонимность?"

        await context.bot.send_message(comp.ChatId, message_text)                 

    async def ProcessWinnedMember(self, comp:CompetitionInfo, user:UserInfo, context: ContextTypes.DEFAULT_TYPE):
        self.Db.IncreaseUserWins(user.Id)
        await context.bot.send_message(comp.ChatId, "Пользователь "+user.Title+" победил в конкурсе #"+str(comp.Id))           

    async def FinalizeSuccessCompetition(self, comp:CompetitionInfo, comp_stat:CompetitionStat, context: ContextTypes.DEFAULT_TYPE):
        comp = self.Db.FinishCompetition(comp.Id)

        if comp.IsClosedType():
            if len(comp_stat.SubmittedMembers) == 1:
                await self.ProcessWinnedMember(comp, comp_stat.SubmittedMembers[0], context)

        await self.ReportCompetitionStateToAttachedChat(comp, context)
        await self.ShowFileAuthors(comp, comp_stat, context)

    async def SwitchToPollingStage(self, comp:CompetitionInfo, context: ContextTypes.DEFAULT_TYPE):
        if comp.Confirmed is None:
            LitGBException("У конкурса наступил дедлайн приёма файлов, но он не перешёл в стадию \"подтверждён\"")
        if comp.Started is None:
            LitGBException("У конкурса наступил дедлайн приёма файлов, но он не перешёл в стадию \"стартовал\"")
        if comp.IsPollingStarted():
            LitGBException("Конкурса наступил дедлайн приёма файлов, но он уже перешёл в стадию \"голосование\"")

        comp = self.Db.SwitchToPollingStage(comp.Id)        
        if comp.IsClosedType():
            await self.ProcessFailedMembers(comp, context)

        comp_stat = self.Db.RemoveMembersWithoutFiles(comp.Id)
        if self.CheckCompetitionEndCondition(comp, comp_stat):
            await self.FinalizeSuccessCompetition(comp, comp_stat, context)
            return
        
        await self.AfterPollingStarted(comp, comp_stat, context)

    async def CancelCompetitionWithError(self, comp: CompetitionInfo, error:str, context: ContextTypes.DEFAULT_TYPE):
        self.Db.FinishCompetition(comp.Id, True)
        await self.ReportCompetitionStateToAttachedChat(comp, context) 
            
    async def CheckPollingStageStart(self, context: ContextTypes.DEFAULT_TYPE):
        logging.info("CheckPollingStageStart:")
        comp_list = self.Db.SelectReadyToPollingStageCompetitions()
        for comp in comp_list:
            try:
                await self.SwitchToPollingStage(comp, context)
            except LitGBException as ex:
                logging.error("CheckPollingStageStart: ERROR on CheckPollingStageStart competition #"+str(comp.Id)+ ": "+str(ex))
                logging.error("CheckPollingStageStart: cancel competition #"+str(comp.Id)+ " due error on switch to polling stage")
                await self.CancelCompetitionWithError(comp, str(ex), context)
            except BaseException as ex:
                logging.error("CheckPollingStageStart: EXCEPTION on CheckPollingStageStart competition #"+str(comp.Id)+ ": "+str(ex))       

    async def FinalizeCompetitionPolling(self, comp:CompetitionInfo, context: ContextTypes.DEFAULT_TYPE):              
        if not comp.IsPollingStarted():
            LitGBException("У конкурса наступил дедлайн голосования, но он не перешёл в стадию \"голосование\"")
        if comp.Confirmed is None:
            LitGBException("У конкурса наступил дедлайн приёма файлов, но он не перешёл в стадию \"подтверждён\"")
        if not comp.IsStarted():
            LitGBException("У конкурса наступил дедлайн приёма файлов, но он не перешёл в стадию \"стартовал\"")            

        comp_stat = self.Db.GetCompetitionStat(comp.Id)
        await self.FinalizeSuccessCompetition(comp, comp_stat, context)     

    async def CheckPollingStageEnd(self, context: ContextTypes.DEFAULT_TYPE):
        logging.info("CheckPollingStageEnd:")
        comp_list = self.Db.SelectPollingDeadlinedCompetitions()
        for comp in comp_list:
            try:
                await self.FinalizeCompetitionPolling(comp, context)
            except LitGBException as ex:
                logging.error("CheckPollingStageEnd: ERROR on FinalizeCompetitionPolling competition #"+str(comp.Id)+ ": "+str(ex))
                logging.error("CheckPollingStageEnd: cancel competition #"+str(comp.Id)+ " due error on finalize polling stage")
                await self.CancelCompetitionWithError(comp, str(ex), context)
            except BaseException as ex:
                logging.error("CheckPollingStageEnd: EXCEPTION on FinalizeCompetitionPolling competition #"+str(comp.Id)+ ": "+str(ex))          
            
    async def CheckCompetitionStates(self, context: ContextTypes.DEFAULT_TYPE):
        await self.CheckPollingStageStart(context)    
        await self.CheckPollingStageEnd(context)