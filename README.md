# Бот "Литературные игры"

Бот: @literature_games_bot

## Подготовка системы

    apt install postgresql
    apt install build-essential autoconf libtool pkg-config 
    apt install libpq-dev

## БД
    
Создание:

    python3 dbtool.py --host 127.0.0.1 --db litgb_db2 --user postgres --action create --password ****

Обновление:

    python3 dbtool.py --host 127.0.0.1 --db litgb_db2 --user postgres --password **** --action update --all_access_for <user>


## Запуск

    pip3 install -r requirements.txt


    python3 src/litgb.py --conf test/conf.json


