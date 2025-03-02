CREATE TABLE competition_ballot (
    comp_id integer NOT NULL,
    user_id bigint NOT NULL,
    file_id bigint NOT NULL,
    points integer NOT NULL DEFAULT 0,
    FOREIGN KEY (comp_id) REFERENCES competition (id),
    FOREIGN KEY (user_id) REFERENCES sd_user (id),
    FOREIGN KEY (file_id) REFERENCES uploaded_file (id),
    PRIMARY KEY (comp_id, user_id, file_id)
);

CREATE INDEX idx_competition_ballot_comp_id on competition_ballot ("comp_id");
CREATE INDEX idx_competition_ballot_user_id on competition_ballot ("user_id");
CREATE INDEX idx_competition_ballot_file_id on competition_ballot ("file_id");

CREATE TABLE competition_ballot_draft (
    comp_id integer NOT NULL,
    user_id bigint NOT NULL,    
    ballot text,
    FOREIGN KEY (comp_id) REFERENCES competition (id),
    FOREIGN KEY (user_id) REFERENCES sd_user (id),
    PRIMARY KEY (comp_id, user_id)
);

CREATE INDEX idx_competition_ballot_draft_comp_id on competition_ballot_draft ("comp_id");
CREATE INDEX idx_competition_ballot_draft_user_id on competition_ballot_draft ("user_id");

CREATE TABLE polling_scheme (
    id integer PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    handler_name varchar(30) NOT NULL,
    title text NOT NULL,
    description text,
    for_open_competition boolean NOT NULL
);

CREATE INDEX idx_polling_scheme_user_for_open_competition on polling_scheme ("for_open_competition");

INSERT INTO polling_scheme (for_open_competition, handler_name, title, description) VALUES (FALSE, 'default_duel', 'Классическая дуэль', 'Классическая дуэль с голосованием за одного из двоих участников');
INSERT INTO polling_scheme (for_open_competition, handler_name, title, description) VALUES (FALSE, 'default_triel', 'Жюри над тремя', 'Конкурс с тремя участниками и голосованием жюри. Жюри выбирает ТОП-2, участники голосуют за одного из двоих. Первое место - 2 балла, второе - 1 балл. Голос участника - 2 балла. Голосование участников обязательно');
INSERT INTO polling_scheme (for_open_competition, handler_name, title, description) VALUES (FALSE, 'default_closed_4', 'Жюри 4+. Стандарт', 'Конкурс с четырьмя участниками и более. Голосуют читатели и участники');
INSERT INTO polling_scheme (for_open_competition, handler_name, title, description) VALUES (TRUE, 'default_open', 'Самосуд. Стандарт', 'Стандартное голосование в конкурсе с самосудом');

ALTER TABLE competition ADD COLUMN polling_scheme integer NOT NULL DEFAULT 1 CONSTRAINT competition_polling_scheme_fk REFERENCES polling_scheme (id);
CREATE INDEX idx_competition_polling_scheme on competition ("polling_scheme");

