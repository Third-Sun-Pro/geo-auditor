"""Website scraping — fetch and analyze sites with AI for audit intake."""

import json
import requests
from bs4 import BeautifulSoup

from config import openai_client, CHATGPT_MODEL


def scrape_website(url):
    """Scrape a website and extract key information."""
    try:
        if not url.startswith('http'):
            url = 'https://' + url

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        title = soup.title.string if soup.title else ""

        meta_desc = ""
        meta_tag = soup.find('meta', attrs={'name': 'description'})
        if meta_tag:
            meta_desc = meta_tag.get('content', '')

        og_title = ""
        og_tag = soup.find('meta', attrs={'property': 'og:title'})
        if og_tag:
            og_title = og_tag.get('content', '')

        og_desc = ""
        og_desc_tag = soup.find('meta', attrs={'property': 'og:description'})
        if og_desc_tag:
            og_desc = og_desc_tag.get('content', '')

        schema_data = []
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                schema_data.append(data)
            except Exception:
                pass

        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        page_text = soup.get_text(separator=' ', strip=True)[:3000]

        return {
            "success": True,
            "url": url,
            "title": title,
            "meta_description": meta_desc,
            "og_title": og_title,
            "og_description": og_desc,
            "schema_data": schema_data,
            "page_text": page_text
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def generate_from_intake(intake_text, client_name, location, industry):
    """Parse pasted questionnaire answers and generate queries + client details."""
    if not openai_client:
        return {"error": "OpenAI API key required for intake analysis"}

    prompt = f"""A client filled out a questionnaire for a GEO (Generative Engine Optimization) audit.
Here are their answers (may be formatted as Q&A, bullet points, or free-form text):

---
{intake_text[:3000]}
---

Known details:
- Client Name: {client_name or 'Extract from answers if possible'}
- Location: {location or 'Extract from answers if possible'}
- Industry: {industry or 'Extract from answers if possible'}

From their answers, provide a JSON response with:
1. "client_name": Business name (use known detail if provided, otherwise extract)
2. "industry": Industry description
3. "location": City, State
4. "services": Array of 3-5 main services/offerings they EXPLICITLY mention
5. "discovery": How people currently find them (one sentence summary)
6. "audience": Their target audience (one sentence summary)
7. "queries": Array of 10 search queries to test their AI visibility

CRITICAL QUERY RULES:
1. NATURAL LANGUAGE — Write queries the way real people talk to AI assistants.
   People ask ChatGPT/Claude questions in full sentences, not Google-style keywords.
   GOOD: "Can you recommend a retirement planner in Westlake Village, California?"
   BAD: "retirement planning Westlake Village" (keyword-style, not how people talk to AI)

2. USE ONLY THEIR ACTUAL SERVICES — Only reference services the client explicitly
   mentions. Do NOT invent related services or adjacent professions.
   If they say "retirement planning and investment management", do NOT generate
   queries about "estate planning attorneys" or "tax preparation" unless they said that.

3. SPECIFIC LOCATION — Always use the full city name, not just the state.
   GOOD: "financial planner in Westlake Village California"
   BAD: "financial planner Utah" (too broad)

4. PURCHASE INTENT — Info queries should reflect someone actively looking to hire/buy,
   not casual curiosity.
   GOOD: "how do I choose a financial planner for my retirement savings?"
   BAD: "what is retirement planning" (too basic, no intent)

Query breakdown:
- 2 Brand queries: Questions specifically about this business by name
  Example: "What do people say about [Business Name]?", "Is [Business Name] a good choice for [service]?"
- 4 Local queries: Natural questions combining their city + specific services they offer
  Example: "Who's the best [specific service] in [City]?", "Can you recommend a [service] near [City]?"
- 3 Informational queries: Decision-stage questions their expertise answers
  Example: "How much does [service] typically cost in [State]?", "What should I look for when choosing a [profession]?"
- 1 Comparison/niche query: How they stack up against alternatives
  Example: "What's the difference between [their niche] and [alternative]?"

Each query: {{"query": "search text", "type": "Brand|Local|Info|Compare"}}

Respond ONLY with valid JSON, no other text."""

    try:
        response = openai_client.chat.completions.create(
            model=CHATGPT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500
        )

        result_text = response.choices[0].message.content.strip()
        if result_text.startswith('```'):
            result_text = result_text.split('```')[1]
            if result_text.startswith('json'):
                result_text = result_text[4:]
        result_text = result_text.strip()

        result = json.loads(result_text)
        return {"success": True, "data": result}

    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Failed to parse AI response: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def analyze_website_with_ai(scraped_data):
    """Use AI to analyze the website and generate audit info."""
    if not openai_client:
        return {"error": "OpenAI API key required for website analysis"}

    prompt = f"""Analyze this website and extract business information for a GEO (Generative Engine Optimization) audit.

Website URL: {scraped_data.get('url', '')}
Page Title: {scraped_data.get('title', '')}
Meta Description: {scraped_data.get('meta_description', '')}
Page Content Preview: {scraped_data.get('page_text', '')[:2000]}
Structured Data: {json.dumps(scraped_data.get('schema_data', []))[:1000]}

Please provide a JSON response with:
1. "business_name": The name of the business (clean, no taglines)
2. "industry": A brief industry description (e.g., "Specialty Coffee Roaster & Cafe")
3. "location": City, State if mentioned, otherwise "Unknown"
4. "services": Array of 3-5 main services/offerings EXPLICITLY shown on the website
5. "unique_value": What makes this business unique or different (one sentence)
6. "competitors": Array of 3 real competitor businesses in their area/industry. Each should have:
   - "name": Real business name (search for actual competitors in their city/industry)
   - "type": Brief description (e.g., "National chain daycare")
   - "strength": What they're known for
7. "queries": An array of 10 search queries to test their AI visibility

CRITICAL QUERY RULES:
1. NATURAL LANGUAGE — Write queries the way real people talk to AI assistants like
   ChatGPT, Claude, or Perplexity. People ask full questions, not Google keywords.
   GOOD: "Can you recommend a good plumber in Southeast Portland?"
   BAD: "plumber Southeast Portland" (keyword-style, not how people talk to AI)

2. USE ONLY THEIR ACTUAL SERVICES — Only reference services explicitly shown on the
   website. Do NOT invent related services or adjacent professions.
   If the website shows "water heater repair" and "drain cleaning", do NOT generate
   queries about "HVAC" or "electrical work" unless the website mentions them.

3. SPECIFIC LOCATION — Use the city name (or neighborhood if available), not just state.
   GOOD: "emergency plumber in Southeast Portland"
   BAD: "plumber in Oregon" (too broad)

4. PURCHASE INTENT — Info queries should reflect someone actively looking to hire/buy.
   GOOD: "How much does a tankless water heater installation cost in Portland?"
   BAD: "what is plumbing" (too basic, no buying intent)

Query breakdown:
- 2 Brand queries: Questions specifically about this business by name
  GOOD: "What do people say about Acme Plumbing?", "Is Acme Plumbing in Portland any good?"
  BAD: "plumbing company" (no name, too vague)

- 4 Local queries: Natural questions combining their city + specific services they offer
  GOOD: "Who's the best emergency plumber in Southeast Portland?", "Can you recommend someone for water heater repair near Hawthorne District?"
  BAD: "best plumber in Portland" (too broad, would match hundreds)

- 3 Informational queries: Decision-stage questions their expertise could answer
  GOOD: "How much does tankless water heater installation cost in Oregon?", "What are the signs my sewer line needs replacement?"
  BAD: "what is plumbing" (too basic, not decision-stage)

- 1 Comparison query: How they compare to a specific alternative
  GOOD: "How does Acme Plumbing compare to Roto-Rooter in Portland?"
  BAD: "local plumber vs chain" (too generic)

Each query: {{"query": "search text", "type": "Brand|Local|Info|Compare"}}

IMPORTANT: For competitors, provide REAL businesses that operate in the same city/region and industry. Do not use placeholder names.

Respond ONLY with valid JSON, no other text."""

    try:
        response = openai_client.chat.completions.create(
            model=CHATGPT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500
        )

        result_text = response.choices[0].message.content

        # Clean up markdown code blocks if present
        result_text = result_text.strip()
        if result_text.startswith('```'):
            result_text = result_text.split('```')[1]
            if result_text.startswith('json'):
                result_text = result_text[4:]
        result_text = result_text.strip()

        result = json.loads(result_text)
        return {"success": True, "data": result}

    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Failed to parse AI response: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
