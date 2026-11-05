CREATE TABLE owner_accounts (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    user_id INTEGER NOT NULL UNIQUE
        REFERENCES users(user_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            created_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(created_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', created_at)
                = substr(created_at, 1, 19)
        )
);

CREATE TRIGGER owner_account_requires_first_active_admin
BEFORE INSERT ON owner_accounts
FOR EACH ROW
WHEN NEW.singleton_id <> 1
    OR (SELECT COUNT(*) FROM users) <> 1
    OR NOT EXISTS (
        SELECT 1
        FROM users
        WHERE user_id = NEW.user_id
            AND role = 'Admin'
            AND is_active = 1
    )
BEGIN
    SELECT RAISE(ABORT, 'The Owner must be the first active Admin account.');
END;

CREATE TRIGGER owner_account_identity_immutable
BEFORE UPDATE ON owner_accounts
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'The Owner identity requires a separately approved recovery process.');
END;

CREATE TRIGGER owner_account_no_delete
BEFORE DELETE ON owner_accounts
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'The Owner identity cannot be deleted.');
END;

CREATE TRIGGER owner_user_must_remain_active_admin
BEFORE UPDATE OF role, is_active ON users
FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM owner_accounts WHERE user_id = OLD.user_id
)
    AND (NEW.role <> 'Admin' OR NEW.is_active <> 1)
BEGIN
    SELECT RAISE(ABORT, 'The Owner account must remain active and administrative.');
END;
