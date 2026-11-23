--
-- PostgreSQL database dump
--

\restrict FJ2ATba4kReLcerO1eh73J19pAAaxrabUruuW3eDNtFzqSQvCeBSaXsRoW87dwK

-- Dumped from database version 16.16 (Debian 16.16-1.pgdg13+1)
-- Dumped by pg_dump version 16.16 (Debian 16.16-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: hc_labs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.hc_labs (
    patient_id integer NOT NULL,
    result_value numeric(10,2)
);


ALTER TABLE public.hc_labs OWNER TO postgres;

--
-- Name: hc_patients; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.hc_patients (
    patient_id integer NOT NULL,
    index_date date,
    age_years integer,
    consent_flag integer
);


ALTER TABLE public.hc_patients OWNER TO postgres;

--
-- Name: hc_treatments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.hc_treatments (
    patient_id integer NOT NULL,
    start_date date,
    end_date date
);


ALTER TABLE public.hc_treatments OWNER TO postgres;

--
-- Data for Name: hc_labs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.hc_labs (patient_id, result_value) FROM stdin;
1	8.50
2	\N
3	13.25
4	0.00
\.


--
-- Data for Name: hc_patients; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.hc_patients (patient_id, index_date, age_years, consent_flag) FROM stdin;
1	2026-01-15	35	1
2	2026-02-01	17	1
3	2026-03-12	62	0
4	2026-04-05	40	1
\.


--
-- Data for Name: hc_treatments; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.hc_treatments (patient_id, start_date, end_date) FROM stdin;
1	2026-01-15	2026-01-22
2	2026-02-01	2026-02-01
3	2026-03-12	2026-03-21
4	2026-04-05	2026-04-10
\.


--
-- Name: hc_labs hc_labs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.hc_labs
    ADD CONSTRAINT hc_labs_pkey PRIMARY KEY (patient_id);


--
-- Name: hc_patients hc_patients_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.hc_patients
    ADD CONSTRAINT hc_patients_pkey PRIMARY KEY (patient_id);


--
-- Name: hc_treatments hc_treatments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.hc_treatments
    ADD CONSTRAINT hc_treatments_pkey PRIMARY KEY (patient_id);


--
-- PostgreSQL database dump complete
--

\unrestrict FJ2ATba4kReLcerO1eh73J19pAAaxrabUruuW3eDNtFzqSQvCeBSaXsRoW87dwK

