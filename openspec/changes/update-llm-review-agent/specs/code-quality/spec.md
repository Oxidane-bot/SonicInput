## MODIFIED Requirements

### Requirement: Review heuristics must be explicit about their fallback role
The system MUST keep heuristic review logic clearly labeled as fallback safety
validation and MUST NOT present it as a model-backed review engine.

#### Scenario: Fallback path is used
- **WHEN** review falls back to local heuristics
- **THEN** the system labels the result as fallback validation
- **AND** the UI and logs do not claim that a model review ran

#### Scenario: Heuristic detection still protects output
- **WHEN** local validation detects malformed or unsafe AI output
- **THEN** the system blocks that output from becoming the final inserted text
- **AND** it records a concrete fallback reason
