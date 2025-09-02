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
<img width="404" height="736" alt="image" src="https://github.com/user-attachments/assets/0c9387ea-e845-4a6b-9f4b-c5f032fab8f7" />
<img width="411" height="367" alt="image" src="https://github.com/user-attachments/assets/eeda7a2f-0e85-414d-b8aa-6d54aa5a81db" />
<img width="1796" height="765" alt="image" src="https://github.com/user-attachments/assets/8146788b-3e2c-401a-97e8-5d42bae41ee4" />
<img width="1822" height="789" alt="image" src="https://github.com/user-attachments/assets/597ab8f4-6432-45c8-a0e9-04e927a62ab2" />
<img width="1747" height="653" alt="image" src="https://github.com/user-attachments/assets/47c27b14-b89d-4b76-9e4f-c904a2fd7426" />



---

## Tech Stack
- Backend: Flask (Python)
- Database: SQLite3
- Frontend: HTML, CSS, JavaScript, Jinja2 templates
- Security: Werkzeug (hashed passwords, sessions)
- Other: APScheduler (background tasks), REST APIs (BOM/weather)

---

## Project Structure
