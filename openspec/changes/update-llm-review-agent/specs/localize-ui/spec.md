## MODIFIED Requirements

### Requirement: Review UI wording must describe the actual review path
The system MUST describe the review feature as model-backed when it uses the AI
provider and as local fallback validation when it does not.

#### Scenario: Review button label and help text
- **WHEN** the settings UI renders the review section
- **THEN** the button label and help text clearly indicate whether the review is
  model-backed or local fallback

#### Scenario: Review result message
- **WHEN** review completes or falls back
- **THEN** the UI shows a message that matches the actual execution path
- **AND** it does not imply model-backed review when only local fallback ran
