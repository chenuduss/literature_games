import psycopg2
import psycopg2.extras
from psycopg2 import pool
from datetime import datetime
from litgb_exception import YSDBException

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
        return rows[0][0] 


    @ConnectionPool    
    def GetFileList(self, user_id:int, limit:int, connection=None) -> list[FileInfo]:
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT id, title, file_size, text_size, locked, ts, file_path FROM uploaded_file WHERE user_id = %s AND file_path IS NOT NULL LIMIT %s", (user_id, limit))        
        rows = ps_cursor.fetchall()

        result = []
        for row in rows:
            result.append(FileInfo(row[0], row[1], row[2], row[3], row[4], row[5], row[6]))

        return result
    
    @ConnectionPool    
    def GetNotLockedFileList(self, user_id:int, connection=None) -> list[FileInfo]:
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT id, title, file_size, text_size, ts, file_path FROM uploaded_file WHERE user_id = %s AND file_path IS NOT NULL AND locked = false", (user_id, ))        
        rows = ps_cursor.fetchall()

        result = []
        for row in rows:
            result.append(FileInfo(row[0], row[1], row[2], row[3], False, row[5], row[6]))

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


