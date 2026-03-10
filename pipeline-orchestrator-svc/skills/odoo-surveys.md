---
name: odoo-surveys
version: "1.0"
description: Survey and feedback management for Odoo Surveys module
target_agents:
  - odoo_worker
triggers:
  - "survey"
  - "questionnaire"
  - "feedback"
  - "survey response"
  - "survey results"
priority: 8
max_tokens: 400
---
# Odoo Surveys Management

## Survey Lifecycle
- Create surveys with a title, description, and question pages
- Add question types: free text, numerical, date, single choice, multiple choice, matrix
- Organize questions into pages (sections) for logical grouping
- Set scoring and certification rules if surveys are used for assessments
- Publish surveys to make them available to respondents

## Odoo Models
- `survey.survey` — The survey itself (title, state, pages, access mode)
- `survey.question` — Individual questions within a survey
- `survey.user_input` — Completed survey responses (one per respondent attempt)
- `survey.user_input.line` — Individual answer lines within a response

## Access Modes
- `public` — Anyone with the link can respond (no login required)
- `token` — Requires a unique token per respondent (trackable invitations)

## Common Operations
- List all surveys: search `survey.survey` with fields `[title, state, answer_count]`
- View responses: search `survey.user_input` filtered by `survey_id`
- Get survey questions: search `survey.question` filtered by `survey_id`
- Check completion stats: read `answer_count`, `answer_done_count` from `survey.survey`

## Key Fields
- `survey.survey`: title, description, state (draft/open/closed), access_mode, answer_count
- `survey.question`: title, question_type, sequence, survey_id, page_id
- `survey.user_input`: survey_id, partner_id, state (new/done), scoring_total
