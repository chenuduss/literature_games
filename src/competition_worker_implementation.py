
from competition_worker import CompetitionWorker
from default_duel_polling import DefaultDuelPolling
from default_triel_polling import DefaultTrielPolling
from default_closed_4_polling import DefaultClosed4Polling
from default_open_polling import DefaultOpenPolling
from db_worker import DbWorkerService
from litgb_exception import LitGBException

class CompetitionWorkerImplementation(CompetitionWorker):
    def __init__(self, db:DbWorkerService):        
        CompetitionWorker.__init__(self, db)
        
        poll_schemas = self.Db.FetchAllPollingSchemas()
        for poll_schema in poll_schemas:
            if poll_schema.HandlerName == DefaultDuelPolling.Name:        
                self.PollingHandlers[poll_schema.Id] = DefaultDuelPolling(self.Db, poll_schema, self)
            elif poll_schema.HandlerName == DefaultTrielPolling.Name:
                self.PollingHandlers[poll_schema.Id] = DefaultTrielPolling(self.Db, poll_schema, self)
            elif poll_schema.HandlerName == DefaultClosed4Polling.Name:
                self.PollingHandlers[poll_schema.Id] = DefaultClosed4Polling(self.Db, poll_schema, self)    
            elif poll_schema.HandlerName == DefaultOpenPolling.Name:
                self.PollingHandlers[poll_schema.Id] = DefaultOpenPolling(self.Db, poll_schema, self)
            else:
                raise LitGBException("unknow polling handler name: "+poll_schema.HandlerName)            
