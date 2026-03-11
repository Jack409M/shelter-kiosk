# DWC Program Operations Platform
System Architecture

This document defines the architecture for the DWC Program Operations platform.

The platform extends the Shelter Operations system into a full program management and outcomes tracking system for residents.

The design follows several principles.

1. No monolithic route files
2. No monolithic database tables
3. Modular blueprints
4. Normalized activity records
5. Centralized metrics engine
6. Clear source of truth for every data concept

The system is divided into several modules.

Resident Core  
Stores identity and contact information.

Program Enrollment  
Tracks entry and exit from the program and anchors all other records.

Outcomes and Case Management  
Tracks intake assessments, services delivered, case manager updates, exit assessments, and follow up outcomes.

Weekly Accountability  
Tracks weekly productive hours and work hours through plan and actual submissions.

Recovery Engagement  
Tracks sponsor relationships, recovery program participation, step work, and recovery meeting attendance.

Weekly Case Management Check In  
Captures weekly operational needs such as transportation support, case manager meetings, and open needs.

Appointments  
Stores structured appointment records that support reminders and printed appointment slips.

Goals  
Stores structured resident goals which can persist across case management meetings.

Reporting and Metrics  
Calculates program impact metrics such as graduation rate, income improvement, recovery engagement, and weekly compliance.

Reminder Engine  
Uses appointment data to generate SMS reminders and future app notifications.

The architecture is designed to support long term program evaluation, grant reporting, and operational dashboards while remaining maintainable and modular.

