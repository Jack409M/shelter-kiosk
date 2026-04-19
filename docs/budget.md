# Budget and Financial Coaching Module

## DWC Shelter Kiosk System

---

## Core Purpose

This module exists to help residents learn how to manage money in real life, not just fill out a form.

It transforms a static paper budget worksheet into a living system that connects:

* what a resident plans to spend
* what they actually spend
* what support they receive
* how they move toward stability

This is not accounting software.
This is a case management tool with a resident-facing behavior layer.

---

## Core Philosophy

A budget only matters if it is used during real life decisions.

* Case managers create structure
* Residents record real behavior
* The system shows truth immediately
* Conversations are based on data, not memory

---

## System Architecture Overview

The module has two tightly connected layers.

### Case Manager Layer (Source of Truth)

This is where the budget is created and owned.

Each resident has a monthly budget session tied to their program enrollment.

A budget session includes:

* income plan
* expense plan
* projected versus actual values
* benefits and assistance
* savings tracking
* financial and personal goals

This is the official version of reality.

---

### Resident Layer (Behavior Layer)

This lives in the resident portal.

Residents do not build budgets.
They interact with them.

They can:

* view their current budget
* see what is left in each category
* log purchases in real time
* immediately see if they are within or over budget

This is where behavior happens.

---

## Core Data Model

Everything centers around one concept.

### Budget Session

A monthly, enrollment scoped financial plan.

From that, everything flows:

* line items represent planned categories
* transactions represent real spending
* assistance represents support and barriers
* goals represent direction and accountability

---

## Key Components

### Budget Session

The monthly financial container.

Represents:

* the plan
* the totals
* the official worksheet

---

### Budget Line Items

The structure of the plan.

Examples:

* Rent
* Food
* Hygiene
* Transportation
* Phone
* Savings

Each line item holds:

* projected amount
* actual amount

---

### Budget Transactions

The real world actions.

Each purchase includes:

* amount
* category
* date
* note

This is what makes the system alive.

---

### Budget Assistance

Captures external reality:

* HUD rent split
* food stamps
* Medicaid or clinic access
* warrants
* unpaid tickets
* other assistance

This explains why a budget succeeds or fails.

---

### Goals

Two levels:

* system level goals
* budget specific goals

Includes:

* target dates
* action steps
* barriers
* rewards

---

## User Experience

### Case Manager Experience

The case manager:

* builds the monthly budget
* sets category limits
* reviews spending patterns
* identifies problem areas
* coaches the resident

This replaces a paper worksheet with a living coaching tool.

---

### Resident Experience

The resident:

* opens Budget from the menu
* sees simple category cards
* sees how much is left
* logs purchases quickly
* gets immediate feedback

No clutter. No complexity.

---

## Color System

Each category shows status:

* Green means within budget
* Yellow means close to limit
* Red means over budget

This is the most important behavioral signal.

---

## Product Design Rules

### Case manager owns the plan

Residents do not control budget structure.

---

### Residents own behavior

They log spending, not budgets.

---

### One source of truth

Budget session is the anchor.

---

### No duplication of data

Reuse:

* income support
* employment
* enrollment
* goals

---

### Mobile first

Residents must be able to log a purchase in seconds.

---

### Home page is not a tool hub

Resident home shows status only.

Tools live in the menu:

* Budget
* Daily Log

---

### No shame based language

The system must remain:

* clear
* factual
* supportive

Never punitive or judgmental.

---

## Integration with Existing System

This module integrates with:

* program enrollments
* intake income support
* resident employment data
* goals system
* resident portal
* case management workspace

---

## Long Term Vision

This module becomes:

* a financial literacy engine
* a behavior tracking system
* a coaching tool
* a measurable success indicator

Future expansions may include:

* savings tracking
* habit tracking
* trend analysis
* readiness scoring
* program success metrics

---

## What This System Replaces

It replaces:

* paper budget sheets
* memory based conversations
* inconsistent coaching
* delayed awareness

With:

* real time feedback
* structured planning
* consistent tracking
* measurable progress

---

## Final Ground Truth

This is not a budgeting app.

This is a structured financial behavior system embedded inside case management, designed to help residents move from instability to control.
