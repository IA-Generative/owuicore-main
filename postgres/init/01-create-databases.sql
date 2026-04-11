-- Create additional databases for services sharing this PostgreSQL instance.
-- The default database (POSTGRES_DB / owui) is created automatically by the
-- postgres entrypoint; only extra databases need to be listed here.

CREATE DATABASE keycloak;
CREATE DATABASE bootstrap;
CREATE DATABASE myvault;

-- Create a dedicated application user with limited privileges.
-- Services should connect with this user, not the superuser.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app') THEN
    CREATE ROLE app WITH LOGIN PASSWORD 'app';
  END IF;
END $$;

GRANT ALL PRIVILEGES ON DATABASE keycloak  TO app;
GRANT ALL PRIVILEGES ON DATABASE bootstrap TO app;
GRANT ALL PRIVILEGES ON DATABASE myvault   TO app;
