# Earnings Document Retrieval Prompt — ChatGPT Validated

Source: ChatGPT, 2026-05-10. Validated by Ced.

## Priority order for document retrieval

### Press Release
1. Official IR news release
2. SEC 8-K EX-99.1
3. Company newsroom

### Presentation
1. Official IR presentations/events page
2. SEC 8-K EX-99.2 / EX-99.3
3. Official webcast materials
4. NOT_FOUND if absent

### Transcript
1. Official company transcript
2. Motley Fool
3. AlphaStreet
4. Investing.com
5. API transcript provider if configured
6. NOT_FOUND if unavailable

## Anti-hallucination rule (CRITICAL)

Before accepting a document as valid:
- Open the URL and verify content contains company name, ticker, quarter, and document type
- If URL cannot be opened or content cannot be verified → mark confidence as low or NOT_FOUND
- Never fabricate URLs, PDF names, exhibit numbers, or document availability
- Seeking Alpha is EXCLUDED (requires account)

## Key insight
> "Force the LLM to PROVE documents exist. If it can't, it must admit NOT_FOUND.
> This is exactly what's needed to avoid fake PDFs, wrong quarters, and invented links."
