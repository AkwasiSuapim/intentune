# Trade-offs

## Status

**Living Document**

A trade-off records what the project gains and what it accepts in return.

## Modular Monolith Instead of Microservices

### Gain

- Simpler development
- Easier local debugging
- One deployment
- Fewer distributed-system failures

### Cost

- Strong module boundaries depend on discipline
- Independent scaling is limited

### Revisit When

Clear modules need separate ownership, scaling, or deployment.

## CSV Catalog Before a Database

### Gain

- Simple baseline
- Easy inspection
- No migration or database setup

### Cost

- Limited querying and concurrent updates
- Not suitable for persistent users and feedback

### Revisit When

The product stores profiles, feedback, or recommendation history.

## Deterministic Scoring Before Machine Learning

### Gain

- Explainability
- Easier testing
- Lower cost
- Easier debugging

### Cost

- Limited ability to learn complex preference patterns
- Manual feature and weight design

### Revisit When

Enough quality feedback data exists to evaluate a learned model responsibly.

## Streamlit Before a Separate Frontend

### Gain

- Faster browser MVP
- Python-only development
- Easy result visualization

### Cost

- Less UI flexibility
- Tighter coupling to Python application execution

### Revisit When

The application needs polished custom interaction, a mobile client, or a separately deployed frontend.

## External AI Provider

### Gain

- Strong natural-language interpretation without training a model

### Cost

- API cost
- Latency
- Provider availability
- Privacy considerations
- Output variability

### Mitigation

Structured output, validation, timeouts, fallback behavior, and provider abstraction.

## YouTube as the First External Catalog

### Gain

- Broad visible catalog
- Thumbnails, links, channels, and embeddable videos

### Cost

- API quota
- Search metadata may not include precise audio features
- Availability and regional restrictions

### Mitigation

Use official APIs, normalize metadata, avoid unsupported claims, and keep the internal catalog available.

## Trade-off Entry Template

```text
## Trade-off Title

Date:
Related Decision:

Gain:

Cost:

Mitigation:

Revisit When:
```
