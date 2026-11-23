-- SYNTHETIC DATA ONLY; execute in a disposable MySQL test database.
DROP TABLE IF EXISTS hc_labs;
DROP TABLE IF EXISTS hc_treatments;
DROP TABLE IF EXISTS hc_patients;
CREATE TABLE hc_patients (patient_id INTEGER PRIMARY KEY, index_date DATE, age_years INTEGER, consent_flag INTEGER);
CREATE TABLE hc_treatments (patient_id INTEGER PRIMARY KEY, start_date DATE, end_date DATE);
CREATE TABLE hc_labs (patient_id INTEGER PRIMARY KEY, result_value DECIMAL(10,2));
INSERT INTO hc_patients VALUES (1,'2026-01-15',35,1),(2,'2026-02-01',17,1),(3,'2026-03-12',62,0),(4,'2026-04-05',40,1);
INSERT INTO hc_treatments VALUES (1,'2026-01-15','2026-01-22'),(2,'2026-02-01','2026-02-01'),(3,'2026-03-12','2026-03-21'),(4,'2026-04-05','2026-04-10');
INSERT INTO hc_labs VALUES (1,8.50),(2,NULL),(3,13.25),(4,0.00);
