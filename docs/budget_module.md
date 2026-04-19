# Budget and Financial Coaching Module

## Purpose
This module adds structured budgeting to the case management system.

## Design
- Case manager defines monthly budget
- Resident logs spending in real time
- System compares plan vs actual

## Core Tables
- resident_budget_sessions (extended)
- resident_budget_line_items
- resident_budget_transactions
- resident_budget_assistance
- resident_budget_goal_details

## Behavior
- Green: within budget
- Yellow: near limit
- Red: over budget

## Integration
Tied to program_enrollments, intake income, and resident portal.
