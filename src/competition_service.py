from competition_worker_implementation import CompetitionWorkerImplementation
from db_worker import DbWorkerService, CompetitionInfo, CompetitionStat, UserInfo, PollingSchemaInfo, PollingFileResults, UserStub
import logging
from telegram.ext import ContextTypes
from litgb_exception import LitGBException
from fb2_tool import SectionsToFb2
from utils import DatetimeToString
from file_service import FileService
from file_storage import FileStorage

from competition_polling import ICompetitionPolling, PollingResults


class CompetitionService(CompetitionWorkerImplementation, FileService):
    def __init__(self, db:DbWorkerService, file_stor:FileStorage):
        CompetitionWorkerImplementation.__init__(self, db)
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
            user_files = comp_stat.SubmittedFiles.get(UserStub(user.Id), [])
            if len(user_files) == 0:
                await self.ProcessLosedMember(comp, user, context)        

    async def ShowFileAuthors(self, comp:CompetitionInfo, comp_stat:CompetitionStat, context: ContextTypes.DEFAULT_TYPE):        

        if comp.IsClosedType():
            if comp_stat.SubmittedMemberCount() < 2:
                return
        else:
            if comp_stat.SubmittedMemberCount() < 3:
                return

        message_text = "Авторы работ в конкурсе #"+str(comp.Id)+"\n\n"
        
        if comp.IsClosedType():
            for user, files in comp_stat.SubmittedFiles.items():                   
                for f in files:
                    message_text +=  user.Title + ": " + f.Title
        else:            
            for user, files in comp_stat.SubmittedFiles.items():                    
                for f in files:
                    message_text +=  user.Title + ": " + f.Title            
            message_text += "\n\nВопрос: в открытом конкурсе (самосуд) выводить всех или выводить только победителей? Имеет ли проигравший право сохранить свою анонимность?"

        await context.bot.send_message(comp.ChatId, message_text)                 


    async def ProcessHalfWinnedMember(self, comp:CompetitionInfo, user:UserInfo, context: ContextTypes.DEFAULT_TYPE):
        self.Db.IncreaseUserWins(user.Id)
        await context.bot.send_message(comp.ChatId, "Пользователь "+user.Title+" полупобедил в конкурсе #"+str(comp.Id))

    async def ProcessWinnedMember(self, comp:CompetitionInfo, user:UserInfo, context: ContextTypes.DEFAULT_TYPE):
        self.Db.IncreaseUserWins(user.Id)
        await context.bot.send_message(comp.ChatId, "Пользователь "+user.Title+" победил в конкурсе #"+str(comp.Id))

    async def ShowBallots(self, comp:CompetitionInfo, context: ContextTypes.DEFAULT_TYPE):
        pass    

    async def ShowResults(self, comp:CompetitionInfo, comp_results:PollingResults, context: ContextTypes.DEFAULT_TYPE): 
        comp_results.RatingTable.sort(key=lambda x: x.RatingPos)
        await context.bot.send_message(comp.ChatId, "ShowResults... under constructing")

    async def ProcessResults(self, comp:CompetitionInfo, comp_stat:CompetitionStat, context: ContextTypes.DEFAULT_TYPE):

        comp_results = None        
        if comp.IsClosedType():            
            if comp_stat.SubmittedMemberCount() == 1:
                winner = comp_stat.GetSubmittedMembers()[0]
                winner_files = comp_stat.SubmittedFiles[winner]
                polling_results:list[PollingFileResults] = []
                for f in winner_files:
                    polling_results.append(self.Db.SetFileResults(comp.Id, f.Id, 1, 1))
                await self.ProcessWinnedMember(comp, winner, context)                

                comp_results = PollingResults([winner.Id], [], [], polling_results)

        if comp_results is None:
            polling_handler = self.GetCompetitionPollingHandler(comp)
            comp_results = polling_handler.GetPollingResults(comp)
            for winner_id in comp_results.Winners:
                await self.ProcessWinnedMember(comp, comp_stat.GetUserInfo(winner_id), context)
            for half_winner_id in comp_results.HalfWinners:
                await self.ProcessHalfWinnedMember(comp, comp_stat.GetUserInfo(half_winner_id), context)                  
            for loser_id in comp_results.Winners:
                await self.ProcessLosedMember(comp, comp_stat.GetUserInfo(loser_id), context)            

            for file_res in comp_results.RatingTable:    
                self.Db.SetFileResults(comp.Id, file_res.FileId, file_res.Score, file_res.RatingPos)

        await self.ShowResults(comp, comp_results, context)

        

    async def FinalizeSuccessCompetition(self, comp:CompetitionInfo, comp_stat:CompetitionStat, context: ContextTypes.DEFAULT_TYPE):
        comp = self.Db.FinishCompetition(comp.Id)
        await self.ReportCompetitionStateToAttachedChat(comp, context)


        await self.ProcessResults(comp, comp_stat, context)
        await self.ShowFileAuthors(comp, comp_stat, context)
        await self.ShowBallots(comp, context)
        
    def ChooseNewPollingSchema(self, comp:CompetitionInfo, comp_stat:CompetitionStat) -> ICompetitionPolling:        
        for handler in self.PollingHandlers.values():
            if comp.IsOpenType() == handler.Config.ForOpenType:
                if comp_stat.SubmittedMemberCount() >= handler.GetMinimumMemberCount():
                    new_comp = self.Db.SetPollingSchema(comp.Id, handler.Config.Id)
                    comp.PollingScheme = new_comp.PollingScheme
                    return handler

    async def RecheckPollingSchema(self, comp:CompetitionInfo, comp_stat:CompetitionStat, context: ContextTypes.DEFAULT_TYPE): 

        polling_handler = self.GetCompetitionPollingHandler(comp)    
        if comp_stat.SubmittedMemberCount() < polling_handler.GetMinimumMemberCount():
            new_polling_handler = self.ChooseNewPollingSchema(comp, comp_stat)
            if new_polling_handler is None:
                raise LitGBException("Конкурс не может продолжаться, потому что выбранная схема голосования не подходит для текущего количества участников ("+str(comp_stat.SubmittedFileCount())+"), а новая схема не была найдена.")
            message_text = "Для конкурса #"+str(comp.Id)+" установлена новая схема голосования, так как старая схема не подходит для текущего количества участников."
            message_text+= "\n\nНовая схема голосования: "+new_polling_handler.Config.Title+" (id:"+str(new_polling_handler.Config.Id)+")"
            await context.bot.send_message(comp.ChatId, message_text)

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
        
        if comp.IsClosedType():
            if comp_stat.SubmittedMemberCount() == 1:                
                await self.FinalizeSuccessCompetition(comp, comp_stat, context)
                return
        
        await self.RecheckPollingSchema(comp, comp_stat, context)
        await self.AfterPollingStarted(comp, comp_stat, context)

    async def CancelCompetitionWithError(self, comp: CompetitionInfo, error:str, context: ContextTypes.DEFAULT_TYPE):
        self.Db.FinishCompetition(comp.Id, True)
        await self.ReportCompetitionStateToAttachedChat(comp, context, error) 
            
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
