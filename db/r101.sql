CREATE TABLE uploaded_file (
    id bigint NOT NULL PRIMARY KEY,
    ts timestamp with time zone NOT NULL DEFAULT (current_timestamp AT TIME ZONE 'UTC'),
    title varchar(300) NOT NULL,
    file_size bigint NOT NULL,
    text_size bigint NOT NULL,
    user_id bigint NOT NULL,
    file_path text,
    locked boolean NOT NULL DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES sd_user (id),
);