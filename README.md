# Heat Street Monitoring Web Application

A full-stack Flask web application that monitors real-time heat stress in workplaces.  
The system ingests IoT sensor data and external weather APIs, stores it in SQLite, and triggers alerts when thresholds are exceeded.

---

## Features
- IoT-enabled ingestion of temperature and humidity data (JSON APIs)
- Weather API integration to compare indoor vs outdoor conditions
- Role-based access control (Worker, Manager, Supervisor)
- Interactive dashboards to visualize data trends
- Heat stress alerts with 98% accuracy
- Admin controls to manage thresholds and users

---

## Screenshots
(dashboard, login page, alert system)

---

## Tech Stack
- Backend: Flask (Python)
- Database: SQLite3
- Frontend: HTML, CSS, JavaScript, Jinja2 templates
- Security: Werkzeug (hashed passwords, sessions)
- Other: APScheduler (background tasks), REST APIs (BOM/weather)

---

## Project Structure
