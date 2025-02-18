# Бот самодисциплины

Бот: @your_self_discipline_bot

## Подготовка системы

    apt install postgresql
    apt install build-essential autoconf libtool pkg-config 
    apt install libpq-dev

## БД
    
Создание:

    python3 dbtool.py --host 127.0.0.1 --db ysdb_db2 --user postgres --action create --password ****

Обновление:

    python3 dbtool.py --host 127.0.0.1 --db ysdb_db2 --user postgres --password **** --action update    


## Запуск


    python3 src/ysdb.py --conf test/conf.json



