ALTER TABLE doctors
ADD COLUMN account_was_active_before_deactivation INTEGER
CHECK (
    account_was_active_before_deactivation IS NULL
    OR account_was_active_before_deactivation IN (0, 1)
);
