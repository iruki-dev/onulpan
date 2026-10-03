-- 0004: 웹(app_reader)이 탈퇴 처리와 수신 재개에 필요한 최소 권한
GRANT UPDATE (user_id, anon_id) ON events TO app_reader;
GRANT DELETE ON email_suppressions TO app_reader;
