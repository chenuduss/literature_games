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

    def __eq__(self, other):
        return self.Id == other.Id

    def __ne__(self, other):
        return not self.__eq__(other) 
    
    def __hash__(self):
        return hash(self.Id)    

class ChatInfo:
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
            entry_token:str|None,
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

    def IsOpenType(self) -> bool:
        return self.DeclaredMemberCount is None

    def IsClosedType(self) -> bool:
        return not self.IsOpenType()
    
    def IsPollingStarted(self) -> bool:
        return not (self.PollingStarted is None)
    
    def __eq__(self, other):
        return self.Id == other.Id

    def __ne__(self, other):
        return not self.__eq__(other)         

class CompetitionStat:
    def __init__(self, 
            comp_id:int,             
            registered_members:list[UserInfo], 
            submitted_members:list[UserInfo], 
            submitted_files:dict[int, list[FileInfo]], 
            total_submitted_text_size:int):
        self.CompId = comp_id
        self.RegisteredMembers = registered_members
        self.SubmittedMembers = submitted_members
        self.SubmittedFiles = submitted_files
        self.SubmittedFileCount = 0
        for user_files in self.SubmittedFiles.values():
            self.SubmittedFileCount += len(user_files)
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
    def FindChat(self, id:int, connection=None) -> int:
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT title FROM chat WHERE id = %s", (id, ))        
        rows = ps_cursor.fetchall()
        if len(rows) > 0:            
            return ChatInfo(id, rows[0][0])
                
        return None    

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

    
    @staticmethod
    def SelectCompFields(obname:str|None = None) -> str:
        if obname is None:
            return "id, chat_id, created, created_by, confirmed, started, accept_files_deadline, polling_deadline, entry_token, min_text_size, max_text_size, declared_member_count, subject, subject_ext, max_files_per_member, polling_started, finished, canceled"
        
        result = ""
        result += obname+".id, "
        result += obname+".chat_id, "
        result += obname+".created, "
        result += obname+".created_by, "
        result += obname+".confirmed, "
        result += obname+".started, "
        result += obname+".accept_files_deadline, "
        result += obname+".polling_deadline, "
        result += obname+".entry_token, "
        result += obname+".min_text_size, "
        result += obname+".max_text_size, "
        result += obname+".declared_member_count, "
        result += obname+".subject, "
        result += obname+".subject_ext, "
        result += obname+".max_files_per_member, "
        result += obname+".polling_started, "
        result += obname+".finished, "
        result += obname+".canceled "
        return result
    
    @staticmethod
    def MakeCompetitionInfoFromRow(row) -> CompetitionInfo:
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
    
    @ConnectionPool    
    def SelectActiveCompetitionsInChat(self, chat_id:int, after:datetime, before:datetime, connection=None) -> list[CompetitionInfo]:
        """ return sorted list"""
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT "+self.SelectCompFields()+" FROM competition WHERE chat_id = %s AND finished IS NULL AND polling_deadline > %s AND accept_files_deadline < %s ORDER BY accept_files_deadline", (chat_id, after, before))        
        rows = ps_cursor.fetchall()

        result = []
        for row in rows: 
            result.append(self.MakeCompetitionInfoFromRow(row))

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
    def ConfirmCompetition(self, comp_id:int,connection=None) -> CompetitionInfo:
        ps_cursor = connection.cursor()  
        ps_cursor.execute("UPDATE competition SET confirmed = (current_timestamp AT TIME ZONE 'UTC') WHERE id = %s ", (comp_id, )) 
        connection.commit() 

        return self.FindCompetition(comp_id)

    @ConnectionPool    
    def AttachCompetition(self, comp_id:int, chat_id:int, connection=None) -> CompetitionInfo:
        ps_cursor = connection.cursor()  
        ps_cursor.execute("UPDATE competition SET chat_id = %s WHERE id = %s ", (chat_id, comp_id)) 
        connection.commit() 

        return self.FindCompetition(comp_id) 
    
    @ConnectionPool    
    def SetCompetitionTextLimits(self, id:int, min:int, max:int, max_files_per_member:int, connection=None) -> FileInfo:
        ps_cursor = connection.cursor()  
        ps_cursor.execute("UPDATE competition SET min_text_size = %s, max_text_size = %s, max_files_per_member = %s WHERE id = %s ", (min, max, max_files_per_member, id)) 
        connection.commit() 

        return self.FindCompetition(id)      

    @ConnectionPool
    def SetCompetitionSubject(self, comp_id:int, subject:str, connection=None) -> CompetitionInfo:            
        ps_cursor = connection.cursor()  
        ps_cursor.execute("UPDATE competition SET subject = %s WHERE id = %s ", (subject, comp_id)) 
        connection.commit() 

        return self.FindCompetition(comp_id)  

    @ConnectionPool
    def SetCompetitionSubjectExt(self, comp_id:int, subject_ext:str, connection=None) -> CompetitionInfo:            
        ps_cursor = connection.cursor()  
        ps_cursor.execute("UPDATE competition SET subject_ext = %s WHERE id = %s ", (subject_ext, comp_id)) 
        connection.commit() 

        return self.FindCompetition(comp_id)        
    
    @ConnectionPool
    def StartCompetition(self, comp_id:int, connection=None) -> CompetitionInfo:
        ps_cursor = connection.cursor()  
        ps_cursor.execute("UPDATE competition SET started = (current_timestamp AT TIME ZONE 'UTC') WHERE id = %s ", (comp_id, )) 
        connection.commit() 

        return self.FindCompetition(comp_id)    


    @ConnectionPool
    def FinishCompetition(self, comp_id:int, canceled:bool = False, connection=None) -> CompetitionInfo:
        ps_cursor = connection.cursor() 
        ps_cursor.execute("UPDATE competition SET finished = (current_timestamp AT TIME ZONE 'UTC'), canceled = %s WHERE id = %s ", (canceled, comp_id))
        ps_cursor.execute("UPDATE uploaded_file SET locked = FALSE WHERE id IN (SELECT file_id FROM competition_member WHERE file_id IS NOT NULL AND comp_id = %s) ", (comp_id, ))
        connection.commit() 
        return self.FindCompetition(comp_id)    

    @ConnectionPool    
    def GetCompetitionStat(self, comp_id:int, connection=None) -> CompetitionStat:
        ps_cursor = connection.cursor()          
        ps_cursor.execute(
            "SELECT u.id, u.title, uf.text_size, uf.Id, uf.title, uf.file_size, uf.locked, uf.ts, uf.file_path FROM "+
            "competition_member as cm "+
            "INNER JOIN sd_user AS u ON cm.user_id = u.id "+
            "LEFT OUTER JOIN uploaded_file AS uf ON cm.file_id = uf.id "
            "WHERE comp_id = %s", (comp_id, ))
        rows = ps_cursor.fetchall()

        registered_users = set()
        total_text_size = 0
        submitted_files:dict[int, list[FileInfo]] = {}
        submitted_members = set()
        for row in rows:
            usr = UserInfo(row[0], row[1])
            registered_users.add(usr)
            if not (row[2] is None):
                
                submitted_members.add(usr)
                if not (usr.Id in submitted_files):
                    submitted_files[usr.Id] = []

                submitted_files[usr.Id].append(
                    FileInfo(row[3], row[4], row[5], row[2], row[6], row[7], row[8], usr.Id))
                total_text_size += row[2]

        return CompetitionStat(comp_id, list(registered_users), list(submitted_members), submitted_files, total_text_size)
        
    
    @ConnectionPool    
    def JoinToCompetition(self, comp_id:int, user_id:int, connection=None) -> CompetitionStat:
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT comp_id FROM competition_member WHERE comp_id = %s AND user_id = %s", (comp_id, user_id))        
        rows = ps_cursor.fetchall()

        if len(rows) == 0:
            ps_cursor.execute("INSERT INTO competition_member (comp_id, user_id) VALUES(%s, %s)", (comp_id, user_id)) 
            connection.commit()  

        return self.GetCompetitionStat(comp_id)    
    
    @ConnectionPool    
    def SelectChatRelatedCompetitions(self, chat_id:int, after:datetime, before:datetime, connection=None) -> list[CompetitionInfo]:
        """ return sorted list"""
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT "+self.SelectCompFields()+" FROM competition WHERE chat_id = %s AND polling_deadline > %s AND accept_files_deadline < %s ORDER BY accept_files_deadline", (chat_id, after, before))        
        rows = ps_cursor.fetchall()

        result = []
        for row in rows: 
            result.append(self.MakeCompetitionInfoFromRow(row))

        return result         
    
    @ConnectionPool    
    def SelectActiveCompetitions(self, after:datetime, before:datetime, connection=None) -> list[CompetitionInfo]:
        """ return sorted list"""
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT "+self.SelectCompFields()+" FROM competition WHERE finished IS NULL AND polling_deadline > %s AND accept_files_deadline < %s ORDER BY accept_files_deadline", (after, before))        
        rows = ps_cursor.fetchall()

        result = []
        for row in rows: 
            result.append(self.MakeCompetitionInfoFromRow(row))

        return result       
    
    
    @ConnectionPool    
    def SelectUserCreatedCompetitions(self, user_id:int, after:datetime, before:datetime, connection=None) -> list[CompetitionInfo]:
        """ return sorted list"""
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT "+self.SelectCompFields()+" FROM competition WHERE created_by = %s AND polling_deadline > %s AND accept_files_deadline < %s ORDER BY accept_files_deadline", (user_id, after, before))        
        rows = ps_cursor.fetchall()

        result = []
        for row in rows: 
            result.append(self.MakeCompetitionInfoFromRow(row))

        return result 

    @ConnectionPool    
    def SelectUserRegisteredCompetitions(self, user_id:int, after:datetime, before:datetime, connection=None) -> list[CompetitionInfo]:
        """ return sorted list"""
        ps_cursor = connection.cursor()  
        ps_cursor.execute("SELECT "+self.SelectCompFields("c")+" FROM competition as c INNER JOIN competition_member as cm ON c.id = cm.comp_id WHERE cm.user_id = %s AND polling_deadline > %s AND accept_files_deadline < %s ORDER BY accept_files_deadline", (user_id, after, before))        
        rows = ps_cursor.fetchall()
                                    
        result = []
        for row in rows: 
            result.append(self.MakeCompetitionInfoFromRow(row))

        return result 
    
    @staticmethod
    def MergeCompetitionLists(list1:list[CompetitionInfo], list2:list[CompetitionInfo]) -> list[CompetitionInfo]:
        total_set = set(list1).union(set(list2))
        return list(total_set)
    
    def SelectUserRelatedCompetitions(self, user_id:int, after:datetime, before:datetime) -> list[CompetitionInfo]:
        created = self.SelectUserCreatedCompetitions(user_id, after, before)
        registered = self.SelectUserRegisteredCompetitions(user_id, after, before)
        result = self.MergeCompetitionLists(created, registered)
        result.sort(key=lambda x: x.Сreated)
        return result  
    