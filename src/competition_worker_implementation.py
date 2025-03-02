
from competition_worker import CompetitionWorker
from default_duel_polling import DefaultDuelPolling
from db_worker import DbWorkerService

class CompetitionWorkerImplementation(CompetitionWorker):
    def __init__(self, db:DbWorkerService):        
        CompetitionWorker.__init__(self, db)
        
        poll_schemas = self.Db.FetchAllPollingSchemas()
        for poll_schema in poll_schemas:
            if poll_schema.HandlerName == DefaultDuelPolling.Name:        
                self.PollingHandlers[poll_schema.Id] = DefaultDuelPolling(self.Db, poll_schema, self)           