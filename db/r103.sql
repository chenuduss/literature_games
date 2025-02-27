CREATE TABLE competition_ballot (
    comp_id int NOT NULL,
    user_id bigint NOT NULL,
    file_id bigint NOT NULL,
    points integer NOT NULL DEFAULT 0,
    FOREIGN KEY (comp_id) REFERENCES competition (id),
    FOREIGN KEY (user_id) REFERENCES sd_user (id),
    FOREIGN KEY (file_id) REFERENCES uploaded_file (id)
);

CREATE INDEX idx_competition_ballot_comp_id on competition_ballot ("comp_id");
CREATE INDEX idx_competition_ballot_user_id on competition_ballot ("user_id");
CREATE INDEX idx_competition_ballot_file_id on competition_ballot ("file_id");

CREATE TABLE competition_ballot_draft (
    comp_id int NOT NULL,
    user_id bigint NOT NULL,    
    ballot text,
    FOREIGN KEY (comp_id) REFERENCES competition (id),
    FOREIGN KEY (user_id) REFERENCES sd_user (id)
);

CREATE INDEX idx_competition_ballot_draft_comp_id on competition_ballot_draft ("comp_id");
CREATE INDEX idx_competition_ballot_draft_user_id on competition_ballot_draft ("user_id");