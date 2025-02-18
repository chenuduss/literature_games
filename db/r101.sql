ALTER TABLE self_contrib_record ALTER COLUMN ts DROP DEFAULT;
ALTER TABLE self_contrib_record ALTER COLUMN ts SET DEFAULT now();