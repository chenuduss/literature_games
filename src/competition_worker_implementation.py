
from competition_worker import CompetitionWorker
from default_duel_polling import DefaultDuelPolling
from default_triel_polling import DefaultTrielPolling
from db_worker import DbWorkerService

class CompetitionWorkerImplementation(CompetitionWorker):
    def __init__(self, db:DbWorkerService):        
        CompetitionWorker.__init__(self, db)
        
        poll_schemas = self.Db.FetchAllPollingSchemas()
        for poll_schema in poll_schemas:
            if poll_schema.HandlerName == DefaultDuelPolling.Name:        
                self.PollingHandlers[poll_schema.Id] = DefaultDuelPolling(self.Db, poll_schema, self)
            elif poll_schema.HandlerName == DefaultTrielPolling.Name:
                self.PollingHandlers[poll_schema.Id] = DefaultTrielPolling(self.Db, poll_schema, self)
