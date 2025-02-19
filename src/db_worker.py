import psycopg2
import psycopg2.extras
from psycopg2 import pool
from datetime import datetime

def ConnectionPool(function_to_decorate):    
    def wrapper(*args, **kwargs):
        obj = args[0]
        conn = obj.Pool.getconn()
        kwargs['connection'] = conn
        try:
            return function_to_decorate(*args, **kwargs)
        finally:
            obj.Pool.putconn(conn)     
        
    return wrapper

class ChatRelatedUserSelfContrib:
    def __init__(self, ts:datetime, amount:int):
        self.TS = ts
        self.Amount = amount

class ChatTopItem:
    def __init__(self, title:str, amount:int):
        self.Title = title
        self.Amount = amount        

class UserInfo:
    def __init__(self, id:int, title:str):
        self.Id = id
        self.Title = title

class FileInfo:
    def __init__(self, id: int, title:str, size:int, text_size:int, locked:bool, loaded:datetime, file_path:str|None, owner:int):
        self.Id = id
        self.Title = title
        self.Size = size             
        self.TextSize = text_size
        self.Locked = locked
        self.Loaded = loaded
        self.FilePath = file_path
        self.Owner = owner

class CompetitionInfo:
    def __init__(self, 
            id: int, 
            chat_id:int, 
            created:datetime, 
            created_by:int, 
            confirmed:datetime|None, 
            started:datetime|None, 
            accept_files_deadline:datetime,
            polling_deadline:datetime,
            entry_token:str,
            min_text_size:int,
            max_text_size:int,
            declared_member_count:int|None,
            subject:str,
            subject_ext:str|None,
            max_files_per_member:int,
            polling_started:datetime|None = None,
            finished:datetime|None = None,
            canceled:bool = False):
        self.Id = id
        self.ChatId = chat_id
        self.Created = created             
        self.CreatedBy = created_by
        self.Confirmed = confirmed
        self.Started = started
        self.AcceptFilesDeadline = accept_files_deadline
        self.PollingDeadline = polling_deadline
        self.EntryToken = entry_token
        self.MinTextSize = min_text_size
        self.MaxTextSize = max_text_size
        self.DeclaredMemberCount = declared_member_count
        self.Subject = subject
        self.SubjectExt = subject_ext
        self.MaxFilesPerMember = max_files_per_member
        self.PollingStarted = polling_started
        self.Finished = finished
        self.Canceled = canceled

class CompetitionStat:
    def __init__(self, 
            comp_id:int,             
            registered_members:list[UserInfo], 
            submitted_member_count:int, 
            submitted_file_count:int, 
            total_submitted_text_size:int):
        self.CompId = comp_id
        self.RegisteredMembers = registered_members
        self.SubmittedMemberCount:int = submitted_member_count
        self.SubmittedFileCount:int = submitted_file_count
        self.TotalSubmittedTextSize = total_submitted_text_size


class DbWorkerService:   
    def __init__(self, config:dict):
        psycopg2.extras.register_uuid()
        self.Pool = psycopg2.pool.ThreadedConnectionPool(
            5, 20,
            user = config["username"],
            password = config["password"],
            host = config["host"],
            port = config["port"],
            database = config["db"])       

        
    @ConnectionPool    
    def EnsureUserExists(self, user_id:int, title:str,  connection=None) -> None:
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT id FROM sd_user WHERE id = %s", (user_id, ))        
        rows = ps_cursor.fetchall()
        if len(rows) < 1:            
            ps_cursor.execute("INSERT INTO sd_user (id, title) VALUES (%s, %s)", (user_id, title)) 
            connection.commit()

    @ConnectionPool    
    def GetUserFileLimit(self, user_id:int, connection=None) -> int:
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT file_limit FROM sd_user WHERE id = %s", (user_id, ))        
        rows = ps_cursor.fetchall()
        if len(rows) > 0:            
            return rows[0][0] 
                
        return 0

    @ConnectionPool    
    def IsUploadAllowedForUser(self, user_id:int, connection=None) -> bool:
        return self.GetUserFileLimit(user_id) > 0
        

    @ConnectionPool    
    def EnsureChatExists(self, chat_id:int, title:str, connection=None) -> None:
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT id FROM chat WHERE id = %s", (chat_id, ))        
        rows = ps_cursor.fetchall()
        if len(rows) < 1:            
            ps_cursor.execute("INSERT INTO chat (id, title) VALUES (%s, %s)", (chat_id, title)) 
            connection.commit()
    
    @ConnectionPool    
    def GetFileCount(self, user_id:int, connection=None) -> int:
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT COUNT(*) FROM uploaded_file WHERE user_id = %s AND file_path IS NOT NULL", (user_id, ))        
        rows = ps_cursor.fetchall()
        return rows[0][0]    

    @ConnectionPool    
    def GetFilesTotalSize(self, connection=None) -> int:
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT SUM(file_size) FROM uploaded_file WHERE file_path IS NOT NULL")        
        rows = ps_cursor.fetchall()
        if rows[0][0] is None:
            return 0
        return rows[0][0]
    
    @ConnectionPool    
    def GetFileTotalCount(self, connection=None) -> int:
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT COUNT(*) FROM uploaded_file WHERE file_path IS NOT NULL")        
        rows = ps_cursor.fetchall()
        if rows[0][0] is None:
            return 0
        return rows[0][0]    

    @ConnectionPool    
    def GetNotLockedFileListBefore(self, loaded_before:datetime, connection=None) -> list[FileInfo]:
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT id, title, file_size, text_size, locked, ts, file_path, user_id FROM uploaded_file WHERE ts < %s AND file_path IS NOT NULL LIMIT %s", (loaded_before, ))        
        rows = ps_cursor.fetchall()

        result = []
        for row in rows:
            result.append(FileInfo(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7]))

        return result


    @ConnectionPool    
    def GetFileList(self, user_id:int, limit:int, connection=None) -> list[FileInfo]:
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT id, title, file_size, text_size, locked, ts, file_path FROM uploaded_file WHERE user_id = %s AND file_path IS NOT NULL LIMIT %s", (user_id, limit))        
        rows = ps_cursor.fetchall()

        result = []
        for row in rows:
            result.append(FileInfo(row[0], row[1], row[2], row[3], row[4], row[5], row[6], user_id))

        return result
    
    @ConnectionPool    
    def GetNotLockedFileList(self, user_id:int, connection=None) -> list[FileInfo]:
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT id, title, file_size, text_size, ts, file_path, user_id FROM uploaded_file WHERE user_id = %s AND file_path IS NOT NULL AND locked = false", (user_id, ))        
        rows = ps_cursor.fetchall()

        result = []
        for row in rows:
            result.append(FileInfo(row[0], row[1], row[2], row[3], False, row[4], row[5], row[6]))

        return result    
    
    @ConnectionPool    
    def FindFile(self, id:int, connection=None) -> FileInfo|None:
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT id, title, file_size, text_size, locked, ts, file_path, user_id FROM uploaded_file WHERE id = %s", (id, ))        
        rows = ps_cursor.fetchall()

        if len(rows) > 0: 
            return FileInfo(rows[0][0], rows[0][1], rows[0][2], rows[0][3], rows[0][4], rows[0][5], rows[0][6], rows[0][7])

        return None    
    
    @ConnectionPool    
    def ClearFilePath(self, id:int, connection=None) -> FileInfo:
        ps_cursor = connection.cursor()  
        ps_cursor.execute("UPDATE uploaded_file SET file_path = NULL WHERE id = %s ", (id, )) 
        connection.commit() 

        return self.FindFile(id)
    
    @ConnectionPool    
    def SetFileTitle(self, id:int, title:str, connection=None) -> FileInfo:
        ps_cursor = connection.cursor()  
        ps_cursor.execute("UPDATE uploaded_file SET title = %s WHERE id = %s ", (title, id)) 
        connection.commit() 

        return self.FindFile(id)    
        

    @ConnectionPool    
    def InsertFile(self, user_id:int, title:str,file_size:int, text_size:int, file_path:str, connection=None) -> FileInfo:
        file_id = None
        ps_cursor = connection.cursor() 
        ps_cursor.execute(
            "INSERT INTO uploaded_file (user_id, title, file_size, text_size, file_path) VALUES (%s, %s, %s, %s, %s) RETURNING id", 
            (user_id, title, file_size, text_size, file_path)) 
        rows = ps_cursor.fetchall()
        if len(rows) > 0:
            file_id = rows[0][0]
        connection.commit()

        return self.FindFile(file_id)
    
    @ConnectionPool    
    def FindCompetition(self, id:int, connection=None) -> CompetitionInfo|None:
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT id, chat_id, created, created_by, confirmed, started, accept_files_deadline, polling_deadline, entry_token, min_text_size, max_text_size, declared_member_count, subject, subject_ext, max_files_per_member, polling_started, finished, canceled FROM competition WHERE id = %s", (id, ))        
        rows = ps_cursor.fetchall()

        if len(rows) > 0: 
            return CompetitionInfo(
                rows[0][0], 
                rows[0][1], 
                rows[0][2], 
                rows[0][3], 
                rows[0][4], 
                rows[0][5],
                rows[0][6], 
                rows[0][7],
                rows[0][8],
                rows[0][9],
                rows[0][10],
                rows[0][11],
                rows[0][12],
                rows[0][13],
                rows[0][14],
                rows[0][15],
                rows[0][16],
                rows[0][17])

        return None   
    
    @ConnectionPool    
    def SelectActiveCompetitionsInChat(self, chat_id:int, after:datetime, before:datetime, connection=None) -> list[CompetitionInfo]:
        """ return sorted list"""
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT id, created, created_by, confirmed, started, accept_files_deadline, polling_deadline, entry_token, min_text_size, max_text_size, declared_member_count, subject, subject_ext, max_files_per_member, polling_started, finished, canceled FROM competition WHERE chat_id = %s AND finished IS NULL AND polling_deadline > %s AND accept_files_deadline < %s ORDER BY accept_files_deadline", (chat_id, after, before))        
        rows = ps_cursor.fetchall()

        result = []
        for row in rows: 
            return CompetitionInfo(
                row[0], 
                chat_id,
                row[1], 
                row[2], 
                row[3], 
                row[4], 
                row[5],
                row[6], 
                row[7],
                row[8],
                row[9],
                row[10],
                row[11],
                row[12],
                row[13],
                row[14],
                row[15],
                row[16])

        return result
    
    @ConnectionPool    
    def SelectActiveCompetitionsInChat(self, chat_id:int, after:datetime, before:datetime, connection=None) -> list[CompetitionInfo]:
        """ return sorted list"""
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT id, chat_id, created, created_by, confirmed, started, accept_files_deadline, polling_deadline, entry_token, min_text_size, max_text_size, declared_member_count, subject, subject_ext, max_files_per_member, polling_started, finished, canceled FROM competition WHERE chat_id = %s AND finished IS NULL AND polling_deadline > %s AND accept_files_deadline < %s ORDER BY accept_files_deadline", (chat_id, after, before))        
        rows = ps_cursor.fetchall()

        result = []
        for row in rows: 
            return CompetitionInfo(
                row[0], 
                row[1], 
                row[2], 
                row[3], 
                row[4], 
                row[5],
                row[6], 
                row[7],
                row[8],
                row[9],
                row[10],
                row[11],
                row[12],
                row[13],
                row[14],
                row[15],
                row[16],
                row[17])

        return result      

    @ConnectionPool    
    def CreateCompetition(self, 
            user_id:int, 
            chat_id:int|None,
            accept_files_deadline:datetime, 
            polling_deadline:datetime, 
            entry_token:str, 
            min_text_size:int,
            max_text_size:int,
            declared_member_count:int|None,
            subject:str,            
            connection=None) -> CompetitionInfo:
        comp_id = None
        ps_cursor = connection.cursor() 
        ps_cursor.execute(
            "INSERT INTO competition (chat_id, created_by, accept_files_deadline, polling_deadline, entry_token, min_text_size, max_text_size, declared_member_count, subject) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id", 
            (chat_id, user_id, accept_files_deadline, polling_deadline, entry_token, min_text_size, max_text_size, declared_member_count, subject)) 
        rows = ps_cursor.fetchall()
        if len(rows) > 0:
            comp_id = rows[0][0]
        connection.commit()

        return self.FindCompetition(comp_id)   

    @ConnectionPool    
    def GetCompetitionStat(self, comp_id:int, connection=None) -> CompetitionStat:
        pass
    
    @ConnectionPool    
    def JoinToCompetition(self, comp_id:int, user_id:int, connection=None) -> CompetitionStat:
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT comp_id FROM competition_member WHERE comp_id = %s AND user_id = %s", (comp_id, user_id))        
        rows = ps_cursor.fetchall()

        if len(rows) == 0:
            ps_cursor.execute("INSERT INTO competition_member (comp_id, user_id) VALUES(%s, %s)", (comp_id, user_id)) 
            connection.commit()  

        return self.GetCompetitionStat(comp_id)