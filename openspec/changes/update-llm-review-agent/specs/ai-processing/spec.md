## MODIFIED Requirements

### Requirement: AI text processing should support model-backed review suggestions
The system MUST support a review workflow that uses the configured AI provider
to inspect recent transcript history and generate actionable suggestions.

#### Scenario: Manual review uses the selected AI provider
- **WHEN** the user triggers review from the settings UI
- **THEN** the system uses the configured AI provider to analyze recent history
- **AND** the returned suggestions are shown in the review UI

#### Scenario: LLM path is unavailable
- **WHEN** the configured AI provider cannot be reached or returns an invalid
  review response
- **THEN** the system falls back to local safety validation for obvious
  contract violations
- **AND** it records that the model-backed review path was unavailable
