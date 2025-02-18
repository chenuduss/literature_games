import psycopg2
import psycopg2.extras
from psycopg2 import pool
from datetime import datetime
from ysdb_exception import YSDBException

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
    def InsertSelfContribRecord(self, user_id:int, chat_id:int, amount:int, connection=None) -> None:
        ps_cursor = connection.cursor() 
        ps_cursor.execute("INSERT INTO self_contrib_record (user_id, chat_id, amount) VALUES (%s, %s, %s)", (user_id, chat_id, amount)) 
        connection.commit() 

    @ConnectionPool    
    def DeleteLastSelfContribRecords(self, user_id:int, chat_id:int, limit:int, connection=None) -> None:
        ps_cursor = connection.cursor() 

        ps_cursor.execute("SELECT ts FROM self_contrib_record WHERE user_id = %s AND chat_id = %s ORDER BY ts DESC LIMIT %s", (user_id, chat_id, limit))        
        rows = ps_cursor.fetchall()                
        if len(rows) < 1:
            return
        
        row = rows[-1]
        ps_cursor.execute("DELETE FROM self_contrib_record WHERE user_id = %s AND chat_id = %s AND ts >= %s", (user_id, chat_id, row[0])) 
        connection.commit()         

    @ConnectionPool    
    def SelectLastUserSelfContribs(self, user_id:int, chat_id:int, limit:int,  connection=None) -> list[ChatRelatedUserSelfContrib]:
        ps_cursor = connection.cursor()          
        ps_cursor.execute("SELECT ts, amount FROM self_contrib_record WHERE user_id = %s AND chat_id = %s ORDER BY ts DESC LIMIT %s", (user_id, chat_id, limit))        
        rows = ps_cursor.fetchall()        
        result = []
        for row in rows:
            result.append(ChatRelatedUserSelfContrib(row[0], row[1]))

        return result    


    
    @ConnectionPool    
    def GetAllAmountSum(self, user_id:int, connection=None) -> None:
        raise NotImplementedError("DbWorkerService.CalcAllUserStat")   

    @ConnectionPool    
    def GetAmountSum(self, user_id:int, chat_id:int, start_ts:datetime, end_ts:datetime, connection=None) -> int:
        ps_cursor = connection.cursor()          
        ps_cursor.execute(
            "SELECT sum(amount) FROM self_contrib_record WHERE user_id = %s AND chat_id = %s AND ts >= %s AND ts <= %s", 
            (user_id, chat_id, start_ts, end_ts))        
        rows = ps_cursor.fetchall()    
        if len(rows) == 1:               
            if rows[0][0] is None:
                return 0
            return rows[0][0]
        elif len(rows) > 1:
            raise YSDBException("corrupted DB table")
        return 0
    
    @ConnectionPool    
    def GetChatAmountSum(self, chat_id:int, start_ts:datetime, end_ts:datetime, connection=None) -> int:
        ps_cursor = connection.cursor()          
        ps_cursor.execute(
            "SELECT sum(amount) FROM self_contrib_record WHERE chat_id = %s AND ts >= %s AND ts <= %s", 
            (chat_id, start_ts, end_ts))        
        rows = ps_cursor.fetchall()    
        if len(rows) == 1:            
            return rows[0][0] or 0
        elif len(rows) > 1:
            raise YSDBException("corrupted DB table")
        return 0
    
    @ConnectionPool    
    def GetChatActiveUserCount(self, chat_id:int, start_ts:datetime, end_ts:datetime, connection=None) -> int:
        ps_cursor = connection.cursor()          
        ps_cursor.execute(
            "SELECT COUNT(DISTINCT user_id) FROM self_contrib_record WHERE chat_id = %s AND ts >= %s AND ts <= %s GROUP BY chat_id", 
            (chat_id, start_ts, end_ts))        
        rows = ps_cursor.fetchall()    
        if len(rows) == 1:            
            return rows[0][0] or 0
        elif len(rows) > 1:
            raise YSDBException("corrupted DB table")
        return 0    

    @ConnectionPool    
    def GetTop(self, chat_id:int, start_ts:datetime, end_ts:datetime, connection=None) -> list[ChatTopItem]:
        ps_cursor = connection.cursor() 
        query = "SELECT u.id, u.title, sum(scr.amount) "
        query+= "FROM self_contrib_record as scr INNER JOIN sd_user as u ON scr.user_id = u.id "
        query+= "WHERE ts >= %s AND ts <= %s AND chat_id = %s "
        query+= "GROUP BY u.id ORDER BY sum(scr.amount) DESC LIMIT 30 OFFSET 0"
        ps_cursor.execute(query, (start_ts, end_ts, chat_id))
        rows = ps_cursor.fetchall() 
        result = []
        for row in rows:
            result.append(ChatTopItem(row[1], row[2]))

        return result    






