---
name: odoo-recruitment
version: "1.0"
description: Recruitment pipeline and applicant tracking
target_agents:
  - odoo_mcp
triggers:
  - "recruit"
  - "applicant"
  - "hiring"
  - "interview"
  - "job posting"
priority: 7
max_tokens: 400
---
# Recruitment Pipeline Management

## Job Posting
- Create job positions linked to departments with detailed descriptions
- Publish openings to the Odoo website careers page with a single click
- Syndicate postings to external job boards via integration connectors
- Set application deadlines and expected start dates on each posting
- Track the number of applications received per posting for channel effectiveness

## Applicant Stage Management
- Default stages: New, Initial Screening, First Interview, Second Interview, Offer, Hired
- Customize stages per department to match specific hiring workflows
- Move applicants through stages via drag-and-drop on the Kanban board
- Require stage-specific actions (e.g., phone screen notes before advancing past Screening)
- Archive refused applicants with a rejection reason for future talent pool review

## Interview Scheduling
- Schedule interviews directly from the applicant record using the calendar integration
- Assign interviewers from the hiring team and send calendar invitations automatically
- Use interview evaluation forms with structured scoring criteria per competency
- Collect interviewer feedback as logged notes or survey responses on the applicant card
- Compare candidate scores across interviewers for objective decision-making

## Offer Management
- Generate offer letters from templates with salary, start date, and contract terms
- Send offers via email with digital signature for remote acceptance
- Track offer status: Draft, Sent, Accepted, Refused, Expired
- Upon acceptance, convert the applicant to an employee record with pre-filled data
- Notify HR and the hiring manager automatically when an offer is accepted
