-- ============================================================
-- Sony Music M&A Catalog Valuation Workbench
-- Full schema setup for catalogue_valuation.lai_app
--
-- Databases used:
--   1. catalogue_valuation.lai_app                    (app tables)
--   2. catalogue_valuation.extract_s                  (Luminate source tables)
-- ============================================================

-- ==========================
-- PRIMARY DATABASE & SCHEMA
-- ==========================
CREATE SCHEMA IF NOT EXISTS lai_app;
SET search_path TO lai_app;

-- ============================================================
-- TRACKS
-- ============================================================
DROP TABLE IF EXISTS TRACKS;
CREATE TABLE TRACKS (
    TRACK_ID VARCHAR(10),
    TRACK_NAME VARCHAR(200),
    ISRC VARCHAR(20),
    RELEASE_YEAR INT,
    FIRST_STREAM_DATE DATE,
    CONTENT_TYPE VARCHAR(20),
    PRIMARY_ALBUM_ID VARCHAR(10)
);

INSERT INTO TRACKS VALUES
('TRK001','Hips Don''t Lie','USRC11700001',2002,'2002-12-22','Audio','ALB005'),
('TRK002','Waka Waka','USRC11700002',2023,'2023-11-06','Audio','ALB010'),
('TRK003','Te Felicito','USRC11700003',2005,'2005-08-13','Audio','ALB003'),
('TRK004','Chantaje','USRC11700004',2011,'2011-11-23','Audio','ALB015'),
('TRK005','La Tortura','USRC11700005',2022,'2022-06-27','Audio','ALB011'),
('TRK006','Ojos Asi','USRC11700006',2011,'2011-01-26','Audio','ALB004'),
('TRK007','Loba','USRC11700007',2023,'2023-05-03','Audio','ALB007'),
('TRK008','Rabiosa','USRC11700008',2011,'2011-10-23','Audio','ALB015'),
('TRK009','Antologia','USRC11700009',2011,'2011-11-16','Video','ALB004'),
('TRK010','Suerte','USRC11700010',2011,'2011-11-15','Audio','ALB015'),
('TRK011','Underneath Your Clothes','USRC11700011',2002,'2002-03-08','Audio','ALB005'),
('TRK012','Objection (Tango)','USRC11700012',2010,'2010-10-14','Video','ALB012'),
('TRK013','Whenever, Wherever','USRC11700013',2020,'2020-04-05','Video','ALB006'),
('TRK014','Empire','USRC11700014',2005,'2005-01-28','Audio','ALB002'),
('TRK015','Perro Fiel','USRC11700015',2005,'2005-11-06','Video','ALB003'),
('TRK016','Girl Like Me','USRC11700016',2023,'2023-02-13','Video','ALB010'),
('TRK017','Don''t Wait Up','USRC11700017',2023,'2023-08-17','Audio','ALB010'),
('TRK018','Me Enamore','USRC11700018',2022,'2022-01-22','Audio','ALB009'),
('TRK019','Nada','USRC11700019',2022,'2022-09-25','Audio','ALB011'),
('TRK020','Monotonia','USRC11700020',2002,'2002-11-11','Audio','ALB013');

-- ============================================================
-- ALBUMS
-- ============================================================
DROP TABLE IF EXISTS ALBUMS;
CREATE TABLE ALBUMS (
    ALBUM_ID VARCHAR(10),
    ALBUM_NAME VARCHAR(200),
    RELEASE_TYPE VARCHAR(50),
    IS_COMPILATION BOOLEAN,
    RELEASE_YEAR INT,
    TRACK_COUNT INT,
    CURRENT_REVENUE_USD FLOAT,
    TOTAL_CONSUMPTION_STREAMS INT
);

INSERT INTO ALBUMS VALUES
('ALB001','Pies Descalzos','Album',false,2010,1,724484.89,802531),
('ALB002','Donde Estan Los Ladrones','Album',false,2005,14,333134.23,11235435),
('ALB003','Laundry Service','Album',false,2005,7,909994.22,5617717),
('ALB004','Fijacion Oral Vol.1','Album',false,2011,4,101717.36,3210124),
('ALB005','Sale el Sol','Album',false,2002,12,807407.23,9630373),
('ALB006','El Dorado','Album',false,2020,9,769664.94,32959974),
('ALB007','Grandes Exitos','Greatest Hits',true,2023,15,516373.27,53182564),
('ALB008','Loba (Deluxe)','Compilation',true,2014,3,531157.99,2407593),
('ALB009','Vivir la Vida - Live','Compilation',true,2022,12,554824.26,40711941),
('ALB010','Waka Waka - Single','Single',false,2023,1,80034.06,3545504),
('ALB011','Hips Don''t Lie - Single','Single',false,2022,1,228084.89,3392662),
('ALB012','Te Felicito - Video Release','Video Release',false,2010,3,814722.07,2407593),
('ALB013','Duele El Corazon - Single','Single',false,2002,1,370418.02,802531),
('ALB014','Antologia','Greatest Hits',true,2016,12,167081.58,63887554),
('ALB015','Sonora - Single','Single',false,2011,1,210889.07,802531);

-- ============================================================
-- TRACK_ALBUM_BRIDGE
-- ============================================================
DROP TABLE IF EXISTS TRACK_ALBUM_BRIDGE;
CREATE TABLE TRACK_ALBUM_BRIDGE (
    TRACK_ID VARCHAR(10),
    ALBUM_ID VARCHAR(10),
    IS_PRIMARY BOOLEAN
);

INSERT INTO TRACK_ALBUM_BRIDGE VALUES
('TRK001','ALB005',true),
('TRK001','ALB008',false),
('TRK002','ALB010',true),
('TRK003','ALB003',true),
('TRK004','ALB015',true),
('TRK005','ALB011',true),
('TRK005','ALB008',false),
('TRK006','ALB004',true),
('TRK007','ALB007',true),
('TRK007','ALB009',false),
('TRK008','ALB015',true),
('TRK009','ALB004',true),
('TRK010','ALB015',true),
('TRK010','ALB009',false),
('TRK011','ALB005',true),
('TRK012','ALB012',true),
('TRK013','ALB006',true),
('TRK014','ALB002',true),
('TRK015','ALB003',true),
('TRK015','ALB009',false),
('TRK016','ALB010',true),
('TRK017','ALB010',true),
('TRK017','ALB009',false),
('TRK018','ALB009',true),
('TRK019','ALB011',true),
('TRK020','ALB013',true);

-- ============================================================
-- CONSUMPTION_MATRIX
-- ============================================================
DROP TABLE IF EXISTS CONSUMPTION_MATRIX;
CREATE TABLE CONSUMPTION_MATRIX (
    BUCKET VARCHAR(50),
    AUDIO_PREMIUM INT,
    AUDIO_AD_SUPPORTED INT,
    VIDEO_PREMIUM INT,
    VIDEO_AD_SUPPORTED INT
);

INSERT INTO CONSUMPTION_MATRIX VALUES
('Older than 10 years',4065932,2189348,860101,703719),
('2017-2020',4520534,2434134,956267,782400),
('2021',2252144,1212693,476415,389794),
('2022',2845269,1532068,601884,492450),
('2023',3493849,1881304,739084,604705),
('2024',4925126,2651991,1041854,852426),
('2025',2876256,1548753,608439,497814);

-- ============================================================
-- GROWTH_TREND
-- ============================================================
DROP TABLE IF EXISTS GROWTH_TREND;
CREATE TABLE GROWTH_TREND (
    YEAR INT,
    YOY_GROWTH_PCT FLOAT
);

INSERT INTO GROWTH_TREND VALUES
(2021,9.1),
(2022,16.4),
(2023,19.8),
(2024,24.0),
(2025,14.0);

-- ============================================================
-- RELEASE_YEAR_ANALYSIS
-- ============================================================
DROP TABLE IF EXISTS RELEASE_YEAR_ANALYSIS;
CREATE TABLE RELEASE_YEAR_ANALYSIS (
    BUCKET VARCHAR(50),
    CONSUMPTION_STREAMS INT,
    REVENUE_USD FLOAT,
    YOY_GROWTH_PCT FLOAT
);

INSERT INTO RELEASE_YEAR_ANALYSIS VALUES
('Older than 10 years',36916428,158468.06,31.8),
('2017-2020',32959974,119518.92,-5.1),
('2021',40550692,166335.63,-2.6),
('2022',44104603,164715.97,3.1),
('2023',56728068,199645.05,0.9),
('2024',63515471,256658.58,0.4),
('2025',63887554,286967.17,19.3);

-- ============================================================
-- NEW_RELEASE_TRACKS
-- ============================================================
DROP TABLE IF EXISTS NEW_RELEASE_TRACKS;
CREATE TABLE NEW_RELEASE_TRACKS (
    TRACK_ID VARCHAR(10),
    TRACK_NAME VARCHAR(200),
    RELEASE_YEAR INT,
    FIRST_12M_STREAMS_MILLIONS FLOAT,
    MONTHS_OF_DATA INT,
    FLAG VARCHAR(50)
);

INSERT INTO NEW_RELEASE_TRACKS VALUES
('NR001','New Release Track 1',2020,1.66,12,NULL),
('NR002','New Release Track 2',2020,0.92,12,NULL),
('NR003','New Release Track 3',2022,3.07,6,NULL),
('NR004','New Release Track 4',2024,3.19,9,'Duplicate'),
('NR005','New Release Track 5',2023,1.77,6,NULL),
('NR006','New Release Track 6',2023,1.05,12,'Duplicate'),
('NR007','New Release Track 7',2020,2.57,12,NULL),
('NR008','New Release Track 8',2022,2.53,12,NULL),
('NR009','New Release Track 9',2024,1.52,6,NULL),
('NR010','New Release Track 10',2022,2.63,6,NULL),
('NR011','New Release Track 11',2020,4.80,6,'Incomplete Data'),
('NR012','New Release Track 12',2024,4.73,12,NULL);

-- ============================================================
-- AMBIGUITY_MATCHES
-- ============================================================
DROP TABLE IF EXISTS AMBIGUITY_MATCHES;
CREATE TABLE AMBIGUITY_MATCHES (
    SEARCH_TERM VARCHAR(100),
    MATCH_ID VARCHAR(10),
    MATCH_NAME VARCHAR(200),
    CONFIDENCE VARCHAR(20),
    TRACK_COUNT INT,
    RECOMMENDED BOOLEAN
);

INSERT INTO AMBIGUITY_MATCHES VALUES
('CHI Records','LBL001','CHI Records','High',482,true),
('CHI Records','LBL002','CHI Records MC','Medium',61,false),
('CHI Records','LBL003','CHI Power Records','Low',19,false),
('Shakira','ART001','Shakira','High',214,true),
('Shakira','ART002','Shakira ft.','Low',8,false),
('Karol G','ART005','Karol G','High',213,true),
('Karol G','ART006','Karol G ft.','Low',12,false),
('Bad Bunny','ART007','Bad Bunny','High',56,true),
('Bad Bunny','ART008','Bad Bunny ft.','Low',22,false),
('Harry Styles','ART009','Harry Styles','High',112,true),
('Harry Styles','ART010','Harry Styles ft.','Low',19,false),
('Camila Cabello','ART011','Camila Cabello','High',85,true),
('Camila Cabello','ART012','Camila Cabello ft.','Low',11,false),
('Manuel Turizo','ART013','Manuel Turizo','High',223,true),
('Manuel Turizo','ART014','Manuel Turizo ft.','Low',39,false),
('Rauw Alejandro','ART015','Rauw Alejandro','High',72,true),
('Rauw Alejandro','ART016','Rauw Alejandro ft.','Low',42,false),
('Sebastian Yatra','ART017','Sebastian Yatra','High',158,true),
('Sebastian Yatra','ART018','Sebastian Yatra ft.','Low',7,false),
('RCA Records','LBL007','RCA Records','High',115,true),
('RCA Records','LBL008','RCA Records MC','Medium',31,false),
('RCA Records','LBL009','RCA Records Power','Low',11,false),
('Columbia Records','LBL010','Columbia Records','High',219,true),
('Columbia Records','LBL011','Columbia Records MC','Medium',84,false),
('Columbia Records','LBL012','Columbia Records Power','Low',24,false),
('Arista Records','LBL013','Arista Records','High',113,true),
('Arista Records','LBL014','Arista Records MC','Medium',45,false),
('Arista Records','LBL015','Arista Records Power','Low',27,false),
('Nashville West Records','LBL016','Nashville West Records','High',432,true),
('Nashville West Records','LBL017','Nashville West Records MC','Medium',89,false),
('Nashville West Records','LBL018','Nashville West Records Power','Low',18,false),
('Sony Music Latin','LBL019','Sony Music Latin','High',212,true),
('Sony Music Latin','LBL020','Sony Music Latin MC','Medium',77,false),
('Sony Music Latin','LBL021','Sony Music Latin Power','Low',23,false);

-- ============================================================
-- CONFIG (JSONB store for nested/config data)
-- ============================================================
DROP TABLE IF EXISTS CONFIG;
CREATE TABLE CONFIG (
    CONFIG_KEY VARCHAR(100),
    CONFIG_VALUE JSONB
);

-- ============================================================
-- CATALOG_ACTIVITY_LOG (tracks who created which catalog table)
-- ============================================================
CREATE TABLE IF NOT EXISTS CATALOG_ACTIVITY_LOG (
    ACTIVITY_ID BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    USER_EMAIL VARCHAR(320) NOT NULL,
    ACTIVITY_TYPE VARCHAR(50) NOT NULL,
    ENTITY_NAME VARCHAR(200) NOT NULL,
    ENTITY_TYPE VARCHAR(50) NOT NULL,
    SEARCH_MODE VARCHAR(50),
    CATALOG_TABLE_NAME VARCHAR(500),
    TRACK_COUNT NUMERIC,
    ALBUM_COUNT NUMERIC,
    TOTAL_STREAMS NUMERIC,
    TOTAL_REVENUE_USD FLOAT,
    STATUS VARCHAR(20) DEFAULT 'SUCCESS',
    ERROR_MESSAGE VARCHAR(2000),
    CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- USER_PROGRESS (session step tracking per user)
-- ============================================================
CREATE TABLE IF NOT EXISTS USER_PROGRESS (
    USER_EMAIL VARCHAR(320) NOT NULL,
    CURRENT_STEP INT DEFAULT 1,
    VISITED_STEPS VARCHAR(200) DEFAULT '[]',
    LAST_UPDATED TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT PK_USER_PROGRESS PRIMARY KEY (USER_EMAIL)
);

-- ============================================================
-- SESSION_PROGRESS (session-based workflow state tracking)
-- ============================================================
CREATE TABLE IF NOT EXISTS SESSION_PROGRESS (
    SESSION_ID VARCHAR DEFAULT UUID_STRING(),
    USER_EMAIL VARCHAR NOT NULL,
    STATUS VARCHAR DEFAULT 'IN_PROGRESS',
    CURRENT_STEP NUMERIC DEFAULT 1,
    STEP_DATA JSONB DEFAULT '{}'::jsonb,
    CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UPDATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- ARTISTS (dropdown autocomplete source)
-- ============================================================
CREATE TABLE IF NOT EXISTS ARTISTS (
    NAME VARCHAR(200) NOT NULL
);

INSERT INTO ARTISTS VALUES
('Shakira'),
('Karol G'),
('Bad Bunny'),
('Harry Styles'),
('Camila Cabello'),
('Manuel Turizo'),
('Rauw Alejandro'),
('Sebastian Yatra');

-- ============================================================
-- DYNAMIC STEP TABLES (created at runtime per user session)
-- ============================================================
-- STEP1_{entity}_{user}_{session_id}
--   Stores user's selected entities with MRELG_IDs from Luminate.
--   Columns: MRELG_ID, ENTITY_NAME, SEARCH_TERM, SEARCH_MODE,
--            SELECTED_BY, SESSION_ID, CREATED_AT

-- STEP2_{entity}_{user}_{session_id}
--   Release group details joined from Luminate for confirmed selections.
--   Columns: MRELG_ID, TITLE, DISPLAY_ARTIST, IMPRINT, RELEASE_DATE,
--            RELEASE_YEAR, PRODUCT_FORMAT, RELEASE_TYPE, GENRES,
--            COMPILATION_TYPE, DURATION, ENTITY_NAME, SEARCH_TERM,
--            SEARCH_MODE, SELECTED_BY, SESSION_ID

-- ============================================================
-- EXTERNAL DATABASES & VIEWS (Luminate data share)
-- These source tables are provided by the PostgreSQL data load and must be
-- mounted before the app can perform live catalog searches.
-- ============================================================

-- Database/schema: catalogue_valuation.extract_s (loaded from Luminate)
-- Schema:   EXTRACT_S
-- Key views:
--   VW_MUSICAL_RELEASE_GROUP_DS
--     Columns: MRELG_ID, TITLE, DISPLAY_ARTIST, IMPRINT,
--              RELEASE_DATE, RELEASE_YEAR, PRODUCT_FORMAT,
--              RELEASE_TYPE, GENRES, COMPILATION_TYPE, DURATION
--
--   VW_MUSICAL_RECORDING_DS
--     Columns: MR_ID, TITLE, DISPLAY_ARTIST, RELEASE_DATE
--
--   VW_SONG_MRELG_MAP_DS
--     Columns: SONG_ID, MRELG_ID
--
--   VW_SONG_DS
--     Columns: SONG_ID, TITLE, DISPLAY_ARTIST

-- Source: catalogue_valuation.extract_s (monthly streaming models)
-- Schema:   PROD
-- Key tables:
--   MONTHLY_MR_SUMMARY
--     Columns: MONTH_START_DATE, MR_ID, COUNTRY_CODE,
--              COMMERCIAL_MODEL, CONTENT_TYPE, QUANTITY
--
--   PRODUCT_CATALOG
--     Columns: RECORDING_ID, RELEASE_GROUP_ID, RELEASE_GROUP_TITLE

-- ============================================================
-- DATA PIPELINE: extract_s -> lai_app
-- (Requires a real share. Replace PROVIDER_ACCOUNT.SHARE_NAME
--  with actual values when ready.)
-- ============================================================

-- The source schema is configured with LUMINATE_DATABASE/LUMINATE_SCHEMA.
--
-- CREATE TABLE IF NOT EXISTS lai_app.MONTHLY_MR_SUMMARY (
--     MONTH_START_DATE             DATE,
--     RELEASE_GROUP_DISPLAY_ARTIST VARCHAR(500),
--     RELEASE_GROUP_ID             VARCHAR(100),
--     RELEASE_GROUP_TITLE          VARCHAR(500),
--     FIRST_STREAM_DATE            DATE,
--     RECORDING_ID                 VARCHAR(100),
--     RECORDING_TITLE              VARCHAR(500),
--     CONTENT_TYPE                 VARCHAR(100),
--     QUANTITY                     NUMERIC(38,0)
-- );
