-- MySQL dump 10.13  Distrib 8.0.46, for Linux (aarch64)
--
-- Host: localhost    Database: healthcare_bench
-- ------------------------------------------------------
-- Server version	8.0.46

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `hc_labs`
--

DROP TABLE IF EXISTS `hc_labs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `hc_labs` (
  `patient_id` int NOT NULL,
  `result_value` decimal(10,2) DEFAULT NULL,
  PRIMARY KEY (`patient_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `hc_labs`
--

LOCK TABLES `hc_labs` WRITE;
/*!40000 ALTER TABLE `hc_labs` DISABLE KEYS */;
INSERT INTO `hc_labs` VALUES (1,8.50),(2,NULL),(3,13.25),(4,0.00);
/*!40000 ALTER TABLE `hc_labs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `hc_patients`
--

DROP TABLE IF EXISTS `hc_patients`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `hc_patients` (
  `patient_id` int NOT NULL,
  `index_date` date DEFAULT NULL,
  `age_years` int DEFAULT NULL,
  `consent_flag` int DEFAULT NULL,
  PRIMARY KEY (`patient_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `hc_patients`
--

LOCK TABLES `hc_patients` WRITE;
/*!40000 ALTER TABLE `hc_patients` DISABLE KEYS */;
INSERT INTO `hc_patients` VALUES (1,'2026-01-15',35,1),(2,'2026-02-01',17,1),(3,'2026-03-12',62,0),(4,'2026-04-05',40,1);
/*!40000 ALTER TABLE `hc_patients` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `hc_treatments`
--

DROP TABLE IF EXISTS `hc_treatments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `hc_treatments` (
  `patient_id` int NOT NULL,
  `start_date` date DEFAULT NULL,
  `end_date` date DEFAULT NULL,
  PRIMARY KEY (`patient_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `hc_treatments`
--

LOCK TABLES `hc_treatments` WRITE;
/*!40000 ALTER TABLE `hc_treatments` DISABLE KEYS */;
INSERT INTO `hc_treatments` VALUES (1,'2026-01-15','2026-01-22'),(2,'2026-02-01','2026-02-01'),(3,'2026-03-12','2026-03-21'),(4,'2026-04-05','2026-04-10');
/*!40000 ALTER TABLE `hc_treatments` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-11-22 23:11:14
