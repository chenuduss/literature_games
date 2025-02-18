import psycopg2
import sys
import argparse
import os
import re
import string
import random

from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def get_all_sql_files():
    pattern = re.compile("^r[0-9]+\.sql$")
    sql_files = [f for f in os.listdir('.') if pattern.match(f)]    
    result = {}
    for f in sql_files:
        result[int(f[1:-4])] = f
    return result

def get_sql_files_from_version(version):
    files = get_all_sql_files()
    result = {}
    for key, value in files.items():
        if key > version:
            result[key] = value
    return result   

def get_db_version(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM config WHERE key='db_revision'")
    recs = cursor.fetchall()
    if len(recs) > 1:
        raise Exception('database config is non-consistent, "db_revision" rows more than one')     
    cursor.close()

    return int(recs[0][0])

def set_db_version(conn, version):
    cursor = conn.cursor()
    cursor.execute("UPDATE config SET value="+str(version)+" WHERE key='db_revision'")    
    cursor.close()    

def execute_file(conn, filename):
    with open(filename, 'r') as f:
        sql_text = f.read()

    cursor = conn.cursor()
    cursor.execute(sql_text)
    cursor.close()    

def execute_file_and_update_db_version(conn, filename, version):
    try:
        execute_file(conn, filename)
        set_db_version(conn, version)
        conn.commit()
    except BaseException as e:
        print("Exception caused on update db to revision: "+str(version)+ " (file "+filename+")")
        print("Exception message: "+str(e))
        conn.rollback()
        raise e 


def create_user(conn, login, password):
        cursor = conn.cursor()
        cursor.execute("CREATE USER "+login+" WITH encrypted password '"+password+"'")
        cursor.close() 

def create_full_access_user(conn, dbname, login, password):   

    try:
        create_user(conn, login, password)
        cursor = conn.cursor()
        cursor.execute("GRANT ALL PRIVILEGES ON DATABASE "+dbname+" TO "+login)
        cursor.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "+login)
        cursor.execute("GRANT USAGE, SELECT ON ALL SEQUENCES  IN SCHEMA public TO "+login)
        cursor.close()
        conn.commit()
    except BaseException as e:
        print("Exception caused on creating full access user: "+login)
        print("Exception message: "+str(e))
        conn.rollback()
        raise e 

def grant_full_access_to_user(conn, dbname, login):   

    try:
        cursor = conn.cursor()
        cursor.execute("GRANT ALL PRIVILEGES ON DATABASE "+dbname+" TO "+login)
        cursor.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "+login)
        cursor.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "+login)
        cursor.close()
        conn.commit()
    except BaseException as e:
        print("Exception caused on updating access rights for full access user: "+login)
        print("Exception message: "+str(e))
        conn.rollback()
        raise e 

def gen_random_string(char_set, length):
    return ''.join([random.choice(char_set) for i in range(length)])
    
def generate_password():
    password_charset = string.ascii_letters + string.digits
    return gen_random_string(password_charset, 16)

def create_db(args):
    conn = psycopg2.connect(user=args.user, password = args.password, host=args.host, port = args.port)
    cursor = conn.cursor()
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT);
    cursor.execute('CREATE DATABASE '+ args.db)
    cursor.close()
    conn.close()

    conn = psycopg2.connect(user=args.user, password = args.password, host=args.host, port = args.port, database = args.db)

    cursor = conn.cursor()
    cursor.execute("CREATE TABLE config (key varchar(255) PRIMARY KEY, value text); INSERT INTO config (key, value) VALUES ('db_revision', '1');")

    files = get_all_sql_files()

    print("Creating database...")
    last_revision = 0
    for key in sorted(files):
        print("Executing file "+files[key]+ ", revision "+str(key))
        try:
            execute_file_and_update_db_version(conn, files[key], key)
            last_revision = key
        except BaseException as e:
            print("Exception: "+str(e))
            break

    print("Database created. Revision: "+str(last_revision))

    print("Creating user...")
    username = args.db+"_admin"
    password = generate_password()
    create_full_access_user(conn, args.db, username, password)
    print("User with all access to DB")
    print("    Login: " + username)
    print("    Password: " + password)

def grant_all_access_to_user(args, login):
    conn = psycopg2.connect(user=args.user, password = args.password, host=args.host, port = args.port, database = args.db)

    print("Grant all access to database "+args.db+" to user "+login)
    grant_full_access_to_user(conn, args.db, login)

    return

def update_db(args):
    conn = psycopg2.connect(user=args.user, password = args.password, host=args.host, port = args.port, database = args.db)

    files = get_sql_files_from_version(get_db_version(conn))
#    print (files)

    print("Updating database...")
    last_revision = get_db_version(conn)
    for key in sorted(files):
        print("Executing file "+files[key]+ ", revision "+str(key))
        execute_file_and_update_db_version(conn, files[key], key)
        last_revision = key

    print("Database updated. Revision: "+str(last_revision))    

    return


def truncate_db(args):
    print ("not implemented")
    return

 
def createParser():
    parser = argparse.ArgumentParser(
            prog = 'Database tool',
            description = '''YSDB database maintenance application''',
            epilog = '''(c) 2024'''
            )

    parser.add_argument ('--host', required=True)
    parser.add_argument ('--port', default=5432, type=int)
    parser.add_argument ('--db', required=True)
    parser.add_argument ('--user', required=True)
    parser.add_argument ('--password', required=True)
    parser.add_argument ('--action', choices=['create', 'update', 'truncate'], default='create')
    parser.add_argument ('--all_access_for', default='')
 
    return parser
 
 
if __name__ == '__main__':
    parser = createParser()
    namespace = parser.parse_args(sys.argv[1:])
 
    if (namespace.action == "create"):
        create_db(namespace)
    elif (namespace.action == "update"):
        update_db(namespace)
    elif (namespace.action == "truncate"):
        truncate_db(namespace)
    else:
        print ("impossible case")

    if (len(namespace.all_access_for) > 1):
        grant_all_access_to_user(namespace, namespace.all_access_for)
