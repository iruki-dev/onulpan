-- 0005: 이후 마이그레이션이 만드는 테이블·시퀀스도 기본으로 읽을 수 있게 한다 (쓰기 권한은 마이그레이션마다 명시)
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO app_writer, app_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO app_writer, app_reader;
