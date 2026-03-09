# GEO Audit Webapp - Implementation Notes

**Last Updated:** January 27, 2026

This document captures important implementation decisions and logic that should be preserved in future updates.

---

## 1. Competitor Field Preservation

**Location:** `templates/index.html` - `analyzeWebsite()` function (~line 636)

**Rule:** Never overwrite user-entered competitors when analyzing a website.

**Logic:**
```javascript
// Fill in competitors ONLY if user hasn't already entered their own
const currentCompetitors = document.getElementById('client-competitors').value.trim();
const isDefaultOrEmpty = !currentCompetitors ||
    currentCompetitors === 'Competitor 1, Competitor 2, Competitor 3';

if (data.competitors && data.competitors.length > 0 && isDefaultOrEmpty) {
    // Only auto-fill if field is empty or has default placeholder
    document.getElementById('client-competitors').value = competitorNames;
}
```

**Why:** Users often know their competitors better than AI detection. If they've entered competitors before clicking "Analyze Website", those should be preserved.

---

## 2. Automatic Competitor Visibility Checking

**Location:** `templates/index.html` - `runAudit()` function (~line 930)

**Rule:** When running an audit, automatically check competitor visibility using the MANUALLY ENTERED competitor names from the input field.

**Logic:**
```javascript
// ALWAYS use the manually entered competitor names from the input field
let competitorsToCheck = competitorNames.map(name => ({
    name: name,
    website: ''
}));
```

**Why:** Previously, the code prioritized `window.competitorData` (AI-detected competitors) over user entries. Users should have full control over which competitors are analyzed.

---

## 3. Realistic Query Generation from Intake

**Location:** `templates/index.html` - `runAudit()` function (~line 783)

**Rules:**
1. Generate queries that people actually search for
2. Never create nonsensical queries like "[service] for [audience]"
3. Transform vague terms into specific, searchable terms for known industries

**Pet Care Industry Transformations:**
```javascript
if (isPetCare) {
    if (searchTerm === 'hiking' || searchTerm === 'hikes') {
        searchTerm = 'dog hiking services';
    } else if (searchTerm === 'boarding' || searchTerm === 'boarding facility') {
        searchTerm = 'dog boarding';
    } else if (searchTerm === 'cat care') {
        searchTerm = 'cat sitting services';
    }
}
```

**Why:**
- "hiking near me" returns hiking trails, not pet services
- "Boarding facility for young urban professionals" is not a real search
- Queries should reflect what actual customers would type into Google or ask AI assistants

**Good Query Examples:**
- "best dog boarding in Salt Lake City, Utah"
- "dog hiking services near me"
- "how much does dog boarding cost"
- "Aarf Pet Care vs Camp Bow Wow"

**Bad Query Examples (avoid):**
- "hiking near me" (too vague for pet care)
- "Boarding facility for young urban professionals" (nonsensical)
- "[service] for [target audience]" pattern (not how people search)

---

## 4. Competitor Visibility Endpoint

**Location:** `app.py` - `/run-competitor-audit` endpoint (~line 1006)

**Purpose:** Run the same AI platform queries for competitors to get their actual visibility scores instead of estimates.

**Request:**
```json
{
    "competitors": [{"name": "Competitor Name", "website": ""}],
    "queries": [{"query": "search term", "type": "Local"}],
    "client_visibility": 45.8
}
```

**Response:**
```json
{
    "success": true,
    "competitors": [
        {
            "name": "Competitor Name",
            "visibility_percentage": 25.0,
            "visibility_display": "25.0%",
            "platform_breakdown": {"chatgpt": 4, "claude": 3, "gemini": 1, "perplexity": 4}
        }
    ],
    "comparison": {
        "client_rank": 1,
        "leader": "Client",
        "total_compared": 4
    }
}
```

---

## 5. Client Intake Questions

**Location:** `templates/index.html` (~line 452)

**Fields:**
1. "How do people typically find you right now?" - Discovery patterns
2. "Specific services or offerings you want to be known for?" - Key services (comma-separated)
3. "Target audience you're trying to reach?" - Audience info (for context, NOT for query generation)

**Important:** The target audience field should inform understanding but should NOT be used to generate queries like "[service] for [audience]".

---

## Summary of Key Principles

1. **User input takes priority** over AI-detected data
2. **Queries must be realistic** - what real people actually search
3. **Competitor visibility is automatic** - runs after main audit completes
4. **Industry-aware transformations** - vague terms get context (e.g., "hiking" → "dog hiking services" for pet care)
