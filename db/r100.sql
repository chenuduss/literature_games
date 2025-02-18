CREATE TABLE sd_user (
    id bigint NOT NULL PRIMARY KEY,
    title varchar(200) NOT NULL   
);

CREATE TABLE chat (
    id bigint NOT NULL PRIMARY KEY,
    title varchar(200) NOT NULL   
);

CREATE TABLE self_contrib_record (
    user_id bigint NOT NULL,
    ts timestamp with time zone NOT NULL DEFAULT (current_timestamp AT TIME ZONE 'UTC'),
    chat_id bigint NOT NULL,
    amount int NOT NULL,
    PRIMARY KEY (user_id, ts),
    FOREIGN KEY (user_id) REFERENCES sd_user (id),
    FOREIGN KEY (chat_id) REFERENCES chat (id)
);

CREATE INDEX idx_self_contrib_record_chat_id on self_contrib_record ("chat_id");
CREATE INDEX idx_self_contrib_record_ts on self_contrib_record ("ts");



