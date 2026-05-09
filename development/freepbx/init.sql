-- Initial database setup for the FreePBX 17 dev container.
--
-- Mirrors escomputers/freepbx-docker upstream — creates the two databases
-- FreePBX expects (asterisk + asteriskcdrdb) and grants the freepbxuser
-- access to both. The user itself is created by MariaDB's standard
-- MYSQL_USER + MYSQL_PASSWORD environment-variable hooks.

CREATE DATABASE asterisk;
GRANT ALL PRIVILEGES ON `asterisk`.* TO 'freepbxuser'@'%';

CREATE DATABASE asteriskcdrdb;
GRANT ALL PRIVILEGES ON `asteriskcdrdb`.* TO 'freepbxuser'@'%';

FLUSH PRIVILEGES;
