CREATE TABLE sd_user (
    id bigint NOT NULL PRIMARY KEY,
    title varchar(200) NOT NULL,   
    ALTER TABLE sd_user ADD COLUMN file_limit int NOT NULL DEFAULT 0
);

CREATE TABLE chat (
    id bigint NOT NULL PRIMARY KEY,
    title varchar(200) NOT NULL   
);




