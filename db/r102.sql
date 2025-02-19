CREATE TABLE competition (
    id int GENERATED BY DEFAULT AS IDENTITY,
    chat_id bigint ,
    created timestamp with time zone NOT NULL DEFAULT (current_timestamp AT TIME ZONE 'UTC'),
    created_by bigint NOT NULL,
    confirmed timestamp with time zone,
    started timestamp with time zone,
    accept_files_deadline timestamp with time zone NOT NULL,
    polling_deadline timestamp with time zone NOT NULL,
    entry_token text,
    min_text_size int NOT NULL,
    max_text_size int NOT NULL,
    declared_member_count int,
    subject text NOT NULL,
    subject_ext text,
    max_files_per_member int NOT NULL DEFAULT 1;
    polling boolean NOT NULL DEFAULT FALSE,
    finished boolean NOT NULL DEFAULT FALSE,
    FOREIGN KEY (chat_id) REFERENCES chat (id),
    FOREIGN KEY (created_by) REFERENCES sd_user (id),
);

CREATE TABLE competition_member (
    comp_id int NOT NULL,
    user_id bigint NOT NULL,
    file_id bigint,
    result_place int,
    result_score int,
    FOREIGN KEY (comp_id) REFERENCES competition (id),
    FOREIGN KEY (user_id) REFERENCES sd_user (id),
    FOREIGN KEY (file_id) REFERENCES uploaded_file (id)
);

CREATE INDEX idx_uploaded_file_ts on uploaded_file ("ts");
CREATE INDEX idx_uploaded_file_user_id on uploaded_file ("user_id");
CREATE INDEX idx_uploaded_file_locked on uploaded_file ("locked");
CREATE INDEX idx_uploaded_file_file_size on uploaded_file ("file_size");
CREATE INDEX idx_uploaded_file_file_path on uploaded_file (file_path IS NOT NULL);

CREATE INDEX idx_competition_chat_id on competition ("chat_id");
CREATE INDEX idx_competition_created on competition ("created");
CREATE INDEX idx_competition_created_by on competition ("created_by");


CREATE INDEX idx_competition_member_comp_id on competition_member ("comp_id");
CREATE INDEX idx_competition_member_user_id on competition_member ("user_id");
CREATE INDEX idx_competition_member_file_id on competition_member ("file_id");