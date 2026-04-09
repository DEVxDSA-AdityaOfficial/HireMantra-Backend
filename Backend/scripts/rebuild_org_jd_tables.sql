-- Run against MySQL when upgrading from the older schema (onboarding.user_id, JD without organization_id).
-- This removes tenant and JD data. Back up first. Then restart the API so SQLAlchemy create_all can recreate tables.

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS job_descriptions;
DROP TABLE IF EXISTS onboarding;
DROP TABLE IF EXISTS organizations;
SET FOREIGN_KEY_CHECKS = 1;
