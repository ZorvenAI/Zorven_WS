---
name: manage-surveys
version: "1.0"
description: Create, list, and analyze surveys and their responses
target_personas:
  - marketing_manager
  - hr_manager
  - general_assistant
triggers:
  - "survey"
  - "surveys"
  - "questionnaire"
  - "feedback form"
  - "survey response"
  - "survey results"
mcp_tools:
  - odoo_search
  - odoo_read
  - odoo_create
  - odoo_write
priority: 7
max_tokens: 400
---
# Manage Surveys

## Workflow — List Surveys
1. Search `survey.survey` with fields `["title", "state", "answer_count", "answer_done_count"]`
2. Return survey titles, their state (draft/open/closed), and response counts

## Workflow — View Survey Responses
1. Search `survey.user_input` filtered by `[["survey_id", "=", <survey_id>]]`
2. Read fields `["partner_id", "state", "scoring_total", "create_date"]`
3. Return respondent info and completion status

## Workflow — Create a Survey
1. Create record on `survey.survey` with title and description
2. Create questions on `survey.question` with `survey_id`, `title`, and `question_type`
3. Return the new survey ID and access URL

## Important
- Use model `survey.survey` for surveys, `survey.question` for questions, `survey.user_input` for responses
- Valid question_type values: free_text, numerical_box, date, simple_choice, multiple_choice, matrix
- Survey states: draft, open, closed
- Always check if the survey module is installed before attempting operations
