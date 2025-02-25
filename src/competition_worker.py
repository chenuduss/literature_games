from db_worker import DbWorkerService, CompetitionInfo
from litgb_exception import LitGBException, CompetitionNotFound

class ComepetitionWorker:
    def __init__(self, db:DbWorkerService):
        self.Db = db
                 
    def FindCompetition(self, comp_id:int) -> CompetitionInfo:     
        comp = self.Db.FindCompetition(comp_id)
        if comp is None:
            raise CompetitionNotFound(comp_id)
        return comp                 
