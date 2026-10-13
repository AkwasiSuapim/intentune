# Risks and Open Questions

## Status

**Living Document**

## Product Risks

- Recommendations may feel repetitive because the catalog is small.
- Exact labels may not represent real musical similarity.
- Users may expect the product to play music directly.
- Explanations may sound confident even when metadata is weak.

## Technical Risks

- Refactoring may change current scoring behavior.
- AI output may be malformed or inconsistent.
- YouTube results may lack precise audio features.
- External API quotas may limit usage.
- Feedback signals such as skips may be ambiguous.
- A public deployment may be abused or generate unexpected cost.

## Data Risks

- Small catalogs can over-represent certain genres or cultures.
- User prompts may contain sensitive personal information.
- Adaptive profiles may overreact to a small number of actions.

## Open Product Questions

- Should users select both current mood and desired mood manually?
- Which recommendation modes should exist first?
- How many results should be shown by default?
- Should explanations display raw point values or plain-language reasons?

## Open Backend Questions

- How should missing candidate features affect score normalization?
- How should genre and mood similarity be represented?
- How should diversity penalties interact with relevance scores?
- What is the first stable API response schema?

## Open Persistence Questions

- Do first users need accounts?
- Should anonymous sessions persist across browser visits?
- Should raw prompts be stored?
- Which feedback actions should influence profiles?

## Open AI Questions

- Which provider will be used?
- What structured schema will the model return?
- When should the chatbot ask a clarifying question?
- What deterministic fallback should exist?

## Open YouTube Questions

- How should search queries be generated?
- How many API calls should one recommendation request make?
- How should duplicates and long playlist videos be handled?
- Which metadata can be used safely for ranking?

## Review Rule

Review this file at the beginning and end of every development phase.
