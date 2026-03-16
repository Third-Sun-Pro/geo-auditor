"""Business logic — audit orchestration, competitor analysis, recommendations, FAQ generation."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import (
    openai_client, anthropic_client, gemini_model, perplexity_client,
    CHATGPT_MODEL, CLAUDE_MODEL,
)
from llm import query_platform


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------

PLATFORM_NAMES = {
    'chatgpt': 'ChatGPT',
    'claude': 'Claude',
    'gemini': 'Gemini',
    'perplexity': 'Perplexity',
}
PLATFORMS = list(PLATFORM_NAMES.keys())


def run_full_audit(client_name, client_website, queries, package_type="basic"):
    """Run a GEO audit: query all platforms for each search term in parallel.

    Returns a dict ready to be jsonify'd by the route handler.
    """
    print("=" * 50)
    print(f"[AUDIT] Starting audit for: {client_name}")
    print(f"[AUDIT] Website: {client_website}")
    print(f"[AUDIT] Number of queries: {len(queries)}")
    print(f"[AUDIT] APIs available - OpenAI: {bool(openai_client)}, Anthropic: {bool(anthropic_client)}, Gemini: {bool(gemini_model)}, Perplexity: {bool(perplexity_client)}")
    print("=" * 50)

    results = []
    totals = {p: 0 for p in PLATFORMS}

    def run_single_query(q):
        query_text = q.get('query', '')
        query_type = q.get('type', 'Brand')
        if not query_text:
            return None

        with ThreadPoolExecutor(max_workers=4) as platform_executor:
            futures = {
                platform_executor.submit(query_platform, p, query_text, client_name, client_website): p
                for p in PLATFORMS
            }
            platform_results = {}
            for future in as_completed(futures):
                pname = futures[future]
                try:
                    platform_results[pname] = future.result()
                except Exception as e:
                    platform_results[pname] = {"error": str(e), "score": 0, "finding": f"Error: {e}"}

        query_score = sum(platform_results.get(p, {}).get('score', 0) for p in PLATFORMS)

        mentioned_on = [PLATFORM_NAMES[p] for p in PLATFORMS if platform_results.get(p, {}).get('score', 0) >= 1]
        not_mentioned_on = [PLATFORM_NAMES[p] for p in PLATFORMS if platform_results.get(p, {}).get('score', 0) < 1]

        if query_score >= 9:
            finding = f"Strong presence - mentioned on {', '.join(mentioned_on)}"
        elif query_score >= 5:
            finding = f"Mentioned on {', '.join(mentioned_on)}; missing from {', '.join(not_mentioned_on)}"
        elif query_score >= 1:
            finding = f"Only found on {', '.join(mentioned_on)}; not on {', '.join(not_mentioned_on)}"
        else:
            finding = "Not mentioned on any platform"

        return {
            "query": query_text,
            "type": query_type,
            "score": query_score,
            "finding": finding,
            "details": platform_results,
        }

    # Run all queries in parallel (up to 3 at a time to avoid rate limits)
    print("[AUDIT] Running queries in parallel...")
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_query = {executor.submit(run_single_query, q): q for q in queries}
        for future in as_completed(future_to_query):
            result = future.result()
            if result:
                results.append(result)
                for p in PLATFORMS:
                    totals[p] += result['details'].get(p, {}).get('score', 0)
                print(f"[AUDIT] Completed: {result['query'][:40]}... Score: {result['score']}/12")

    # Sort results to match original query order
    query_order = {q.get('query', ''): i for i, q in enumerate(queries)}
    results.sort(key=lambda r: query_order.get(r['query'], 999))

    max_per_platform = len(results) * 3
    total_score = sum(r['score'] for r in results)
    max_total = len(results) * 12
    percentage = (total_score / max_total * 100) if max_total > 0 else 0

    visibility_level = _visibility_level(percentage)
    key_findings = _generate_key_findings(results, totals, max_per_platform)

    # Categorize queries for recommendation engine
    brand_queries = [r for r in results if r['type'] == 'Brand']
    local_queries = [r for r in results if r['type'] == 'Local']
    info_queries = [r for r in results if r['type'] == 'Info']

    platforms_tested = [(PLATFORM_NAMES[p], totals[p], max_per_platform) for p in PLATFORMS]
    best_platform = max(platforms_tested, key=lambda x: x[1])
    worst_platform = min(platforms_tested, key=lambda x: x[1])

    recommendations = generate_recommendations(
        client_name, results, brand_queries, local_queries, info_queries,
        percentage,
        best_platform[0] if platforms_tested else None,
        worst_platform[0] if platforms_tested else None,
        package_type
    )

    return {
        "success": True,
        "results": results,
        "total_score": total_score,
        "max_score": max_total,
        "percentage": round(percentage, 1),
        "visibility_level": visibility_level,
        "key_findings": key_findings,
        "recommendations": recommendations,
        "platforms": {
            p: {
                "score": totals[p],
                "max": max_per_platform,
                "note": _platform_note(p),
            }
            for p in PLATFORMS
        },
    }


def _visibility_level(percentage):
    if percentage >= 70:
        return "excellent"
    elif percentage >= 50:
        return "strong"
    elif percentage >= 30:
        return "moderate"
    elif percentage >= 15:
        return "low"
    return "very low"


def _platform_note(platform):
    notes = {
        "chatgpt": "OpenAI GPT-4o-mini" if openai_client else "Not configured",
        "claude": "Anthropic Claude Haiku" if anthropic_client else "Not configured",
        "gemini": "Google Gemini Flash" if gemini_model else "Not configured",
        "perplexity": "Perplexity Sonar" if perplexity_client else "Not configured",
    }
    return notes.get(platform, "Unknown")


# ---------------------------------------------------------------------------
# Key findings generation
# ---------------------------------------------------------------------------

def _get_mentioning_platforms(query_result):
    platforms = []
    details = query_result.get('details', {})
    for p, data in details.items():
        if data.get('score', 0) >= 2:
            platforms.append(PLATFORM_NAMES.get(p, p))
    return platforms


def _get_missing_platforms(query_result):
    platforms = []
    details = query_result.get('details', {})
    for p, data in details.items():
        if data.get('score', 0) == 0:
            platforms.append(PLATFORM_NAMES.get(p, p))
    return platforms


def _generate_key_findings(results, totals, max_per_platform):
    key_findings = []

    # Brand queries
    brand_queries = [r for r in results if r['type'] == 'Brand']
    if brand_queries:
        brand_avg = sum(r['score'] for r in brand_queries) / len(brand_queries)
        failed_brand = [r for r in brand_queries if r['score'] < 4]

        if brand_avg >= 8:
            all_mentioning = set()
            for q in brand_queries:
                all_mentioning.update(_get_mentioning_platforms(q))
            platforms_str = ", ".join(sorted(all_mentioning)) if all_mentioning else "all platforms"
            key_findings.append(f"Strong brand recognition: Direct brand searches consistently return the business on {platforms_str}")
        elif brand_avg >= 4:
            missing_platforms = set()
            for q in brand_queries:
                missing_platforms.update(_get_missing_platforms(q))
            missing_str = ", ".join(sorted(missing_platforms)) if missing_platforms else "some platforms"
            key_findings.append(f"Moderate presence-mentioned on some platforms; not appearing on {missing_str}")
        else:
            missing_platforms = set()
            for q in brand_queries:
                missing_platforms.update(_get_missing_platforms(q))
            missing_str = ", ".join(sorted(missing_platforms)) if missing_platforms else "most platforms"
            key_findings.append(f"Weak brand recognition: Brand is not being surfaced on {missing_str} - critical issue")

    # Local queries
    local_queries = [r for r in results if r['type'] == 'Local']
    if local_queries:
        local_avg = sum(r['score'] for r in local_queries) / len(local_queries)
        failed_local = [r for r in local_queries if r['score'] < 4]

        if local_avg >= 8:
            mentioning = set()
            for q in local_queries:
                mentioning.update(_get_mentioning_platforms(q))
            platforms_str = ", ".join(sorted(mentioning)) if mentioning else "multiple platforms"
            key_findings.append(f"Excellent Local Visibility: Appears prominently on {platforms_str} for local service searches")
        elif local_avg >= 4:
            weak_query_names = [f'"{q["query"]}"' for q in failed_local[:2]]
            missing_platforms = set()
            for q in failed_local:
                missing_platforms.update(_get_missing_platforms(q))
            weak_str = ", ".join(weak_query_names) if weak_query_names else "some local queries"
            missing_str = ", ".join(sorted(missing_platforms)) if missing_platforms else "some platforms"
            key_findings.append(f"Local Visibility Gap: Not appearing for {weak_str}; missing on {missing_str}")
        else:
            weak_query_names = [f'"{q["query"]}"' for q in failed_local[:2]]
            missing_platforms = set()
            for q in failed_local:
                missing_platforms.update(_get_missing_platforms(q))
            weak_str = ", ".join(weak_query_names) if weak_query_names else "local searches"
            missing_str = ", ".join(sorted(missing_platforms)) if missing_platforms else "most platforms"
            key_findings.append(f"Critical Local Gap: Not appearing for {weak_str}; absent on {missing_str}")

    # Info queries
    info_queries = [r for r in results if r['type'] == 'Info']
    if info_queries:
        info_avg = sum(r['score'] for r in info_queries) / len(info_queries)
        failed_info = [r for r in info_queries if r['score'] < 4]

        if info_avg >= 8:
            mentioning = set()
            for q in info_queries:
                mentioning.update(_get_mentioning_platforms(q))
            platforms_str = ", ".join(sorted(mentioning)) if mentioning else "multiple platforms"
            key_findings.append(f"Strong Thought Leadership: Cited as authority on {platforms_str}")
        elif info_avg >= 4:
            weak_query_names = [f'"{q["query"]}"' for q in failed_info[:2]]
            weak_str = ", ".join(weak_query_names) if weak_query_names else "informational queries"
            key_findings.append(f"Content Opportunity: Not being cited for {weak_str}; needs content strategy")
        else:
            weak_query_names = [f'"{q["query"]}"' for q in failed_info[:2]]
            missing_platforms = set()
            for q in failed_info:
                missing_platforms.update(_get_missing_platforms(q))
            weak_str = ", ".join(weak_query_names) if weak_query_names else "informational queries"
            missing_str = ", ".join(sorted(missing_platforms)) if missing_platforms else "all platforms"
            key_findings.append(f"Content Gap: Not being cited for {weak_str}; absent on {missing_str}")

    # Platform comparison
    platforms_tested = [(name, totals.get(key, 0), max_per_platform)
                        for key, name in PLATFORM_NAMES.items()]
    if platforms_tested:
        best = max(platforms_tested, key=lambda x: x[1])
        worst = min(platforms_tested, key=lambda x: x[1])
        if best[1] > worst[1]:
            best_pct = round((best[1] / best[2]) * 100) if best[2] > 0 else 0
            worst_pct = round((worst[1] / worst[2]) * 100) if worst[2] > 0 else 0
            key_findings.append(f"Platform Variance: Best visibility on {best[0]} ({best_pct}%), weakest on {worst[0]} ({worst_pct}%)")

    return key_findings


# ---------------------------------------------------------------------------
# Competitor audit
# ---------------------------------------------------------------------------

def run_competitor_audit(competitors, queries, client_visibility, client_name,
                         industry, location, client_services):
    """Run visibility checks for competitors using the same queries."""
    print("=" * 50)
    print(f"[COMPETITOR AUDIT] Starting competitor visibility check")
    print(f"[COMPETITOR AUDIT] Number of competitors: {len(competitors)}")
    print(f"[COMPETITOR AUDIT] Number of queries: {len(queries)}")
    print(f"[COMPETITOR AUDIT] Industry: {industry}, Location: {location}")
    print("=" * 50)

    used_advantages = []

    def analyze_competitor_strengths(comp_name):
        if not openai_client:
            return f"Established {industry or 'business'} provider"
        try:
            industry_desc = industry or 'business'
            location_desc = location or 'their area'
            prompt = f"""In 10 words or less, what is "{comp_name}" known for as a {industry_desc} in {location_desc}?

Give a SPECIFIC strength or specialty — what they actually DO or OFFER.
Good examples: "Large facility with 24/7 care", "Premium grooming services", "Affordable rates and convenient locations", "Wide service area with fast response times"
BAD examples: "Market competitor", "Established business", "Known company" — these are too vague.

Do not include the company name. Do not say "competitor" or "market player". Just describe their specific strength."""

            response = openai_client.chat.completions.create(
                model=CHATGPT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50
            )
            strength = response.choices[0].message.content.strip().replace('"', '').replace("'", "")
            if len(strength) > 80:
                strength = strength[:77] + "..."
            vague_phrases = ['market competitor', 'established competitor', 'known company', 'market player', 'business competitor']
            if any(vague in strength.lower() for vague in vague_phrases):
                return f"Established {industry_desc} provider in {location_desc}"
            return strength
        except Exception as e:
            print(f"[COMPETITOR AUDIT] Strength analysis failed for {comp_name}: {e}")
            return f"Established {industry or 'business'} provider"

    def analyze_your_advantage(comp_name, comp_strength):
        if not openai_client or not client_services:
            return "Personalized attention and local expertise"
        try:
            already_used = ", ".join(used_advantages) if used_advantages else "none yet"
            prompt = f"""COMPETITOR: "{comp_name}"
COMPETITOR'S STRENGTH: "{comp_strength}"

CLIENT: "{client_name}"
CLIENT'S SERVICES: {client_services}

What does {client_name} offer that "{comp_name}" likely does NOT, based on their strength being "{comp_strength}"?

IMPORTANT RULES:
1. The advantage must CONTRAST with the competitor's strength - what GAP does {client_name} fill?
2. ONLY reference services from this list: {client_services}
3. Be SPECIFIC to this competitor - do not give generic advantages
4. AVOID these already-used advantages: {already_used}

Think step by step:
- What specific service does {client_name} offer that this competitor does NOT?
- If competitor is a large chain or franchise → advantage might be personalized, local service
- If competitor focuses on one niche → advantage might be a complementary service they lack
- If competitor is generalist → advantage might be a specialized expertise

Write ONE specific advantage (under 10 words). No quotes, no client name."""

            response = openai_client.chat.completions.create(
                model=CHATGPT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=40
            )
            advantage = response.choices[0].message.content.strip().replace('"', '').replace("'", "")
            if len(advantage) > 100:
                advantage = advantage[:97] + "..."
            used_advantages.append(advantage[:30])
            return advantage
        except Exception as e:
            print(f"[COMPETITOR AUDIT] Advantage analysis failed for {comp_name}: {e}")
            return "Personalized attention and local expertise"

    # Filter out brand queries — they test the CLIENT's name recognition,
    # not whether competitors appear for the same searches.
    non_brand_queries = [q for q in queries if q.get('type', '') != 'Brand']
    if not non_brand_queries:
        non_brand_queries = queries  # fallback if all are brand
    print(f"[COMPETITOR AUDIT] Using {len(non_brand_queries)} non-brand queries (skipped {len(queries) - len(non_brand_queries)} brand queries)")

    def check_single_competitor(competitor):
        comp_name = competitor.get('name', '')
        comp_website = competitor.get('website', '')
        if not comp_name:
            return None

        print(f"[COMPETITOR AUDIT] Checking: {comp_name}")

        comp_totals = {p: 0 for p in PLATFORMS}

        for q in non_brand_queries:
            query_text = q.get('query', '')
            if not query_text:
                continue

            with ThreadPoolExecutor(max_workers=4) as platform_executor:
                futures = {
                    platform_executor.submit(query_platform, p, query_text, comp_name, comp_website): p
                    for p in PLATFORMS
                }
                for future in as_completed(futures):
                    pname = futures[future]
                    try:
                        result = future.result()
                        comp_totals[pname] += result.get('score', 0)
                    except Exception:
                        pass

        total_score = sum(comp_totals.values())
        max_score = len(non_brand_queries) * 12
        percentage = (total_score / max_score * 100) if max_score > 0 else 0

        strengths = analyze_competitor_strengths(comp_name)
        your_advantage = analyze_your_advantage(comp_name, strengths)

        return {
            "name": comp_name,
            "website": comp_website,
            "visibility_score": total_score,
            "visibility_max": max_score,
            "visibility_percentage": round(percentage, 1),
            "visibility_display": f"{round(percentage, 1)}%",
            "queries_tested": len(non_brand_queries),
            "strengths": strengths,
            "your_advantage": your_advantage,
            "platform_breakdown": comp_totals,
        }

    # Run all competitor checks in parallel
    competitor_results = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_comp = {executor.submit(check_single_competitor, c): c for c in competitors}
        for future in as_completed(future_to_comp):
            result = future.result()
            if result:
                competitor_results.append(result)

    # Sort by original order
    name_to_result = {r['name']: r for r in competitor_results}
    sorted_results = [name_to_result[c.get('name')] for c in competitors if c.get('name') in name_to_result]

    # Comparison stats
    all_visibilities = [r['visibility_percentage'] for r in sorted_results]
    all_visibilities.append(client_visibility)

    leader = "Client"
    max_visibility = client_visibility
    for r in sorted_results:
        if r['visibility_percentage'] > max_visibility:
            max_visibility = r['visibility_percentage']
            leader = r['name']

    sorted_all = sorted(all_visibilities, reverse=True)
    client_rank = sorted_all.index(client_visibility) + 1 if client_visibility in sorted_all else len(sorted_all)

    print(f"[COMPETITOR AUDIT] Complete. Leader: {leader} at {max_visibility}%")

    return {
        "success": True,
        "competitors": sorted_results,
        "api_calls_made": len(competitors) * len(non_brand_queries) * 4,
        "comparison": {
            "client_visibility": client_visibility,
            "leader": leader,
            "client_rank": client_rank,
            "total_compared": len(sorted_results) + 1,
        },
    }


# ---------------------------------------------------------------------------
# Recommendation engine
# ---------------------------------------------------------------------------

def generate_recommendations(client_name, results, brand_queries, local_queries,
                             info_queries, percentage, best_platform, worst_platform,
                             package_type="basic"):
    """Generate AI-personalized recommendations based on actual audit results.

    Falls back to template-based recommendations if the AI call fails.
    """
    if not openai_client:
        print("[RECS] No OpenAI client — using template fallback")
        return _template_recommendations(
            client_name, results, brand_queries, local_queries,
            info_queries, percentage, best_platform, worst_platform, package_type
        )

    try:
        recs = _ai_recommendations(
            client_name, results, brand_queries, local_queries,
            info_queries, percentage, best_platform, worst_platform, package_type
        )
        if recs:
            return recs
    except Exception as e:
        print(f"[RECS] AI recommendations failed: {e} — using template fallback")

    return _template_recommendations(
        client_name, results, brand_queries, local_queries,
        info_queries, percentage, best_platform, worst_platform, package_type
    )


def _ai_recommendations(client_name, results, brand_queries, local_queries,
                         info_queries, percentage, best_platform, worst_platform,
                         package_type):
    """Call OpenAI to generate personalized recommendations from audit data."""
    import json

    is_premium = package_type.lower() == "premium"
    num_recs = "5-7" if is_premium else "3-4"

    # Build a summary of failed queries by category
    def _failed_summary(queries, threshold=4):
        failed = [r for r in queries if r['score'] < threshold] if queries else []
        if not failed:
            return "All queries performed well."
        lines = []
        for r in failed[:4]:
            missed = [PLATFORM_NAMES[p] for p in PLATFORMS
                      if r['details'].get(p, {}).get('score', 0) == 0]
            missed_str = ", ".join(missed) if missed else "partial on all"
            lines.append(f'  - "{r["query"]}" (score {r["score"]}/12, missing on: {missed_str})')
        return "\n".join(lines)

    brand_summary = _failed_summary(brand_queries, threshold=8)
    local_summary = _failed_summary(local_queries)
    info_summary = _failed_summary(info_queries)

    # Extract client services from query context
    all_services = set()
    for r in results:
        q = r.get('query', '').lower()
        # The queries themselves reveal the services being tested
        all_services.add(r.get('query', ''))

    prompt = f"""You are a GEO (Generative Engine Optimization) consultant writing recommendations
for a client audit report. Generate {num_recs} personalized, actionable recommendations.

CLIENT: {client_name}
OVERALL VISIBILITY: {percentage:.0f}%
BEST PLATFORM: {best_platform or 'N/A'}
WORST PLATFORM: {worst_platform or 'N/A'}
PACKAGE: {"Premium" if is_premium else "Standard"}

BRAND QUERY RESULTS (scored poorly = not recognized by name):
{brand_summary}

LOCAL QUERY RESULTS (scored poorly = not appearing for local service searches):
{local_summary}

INFO QUERY RESULTS (scored poorly = not cited as an authority):
{info_summary}

RULES FOR YOUR RECOMMENDATIONS:
1. REFERENCE ACTUAL FAILED QUERIES — In the "issue" field, mention the specific queries
   that scored poorly. Don't be vague — say exactly what searches they're missing.

2. INDUSTRY-SPECIFIC ACTIONS — Tailor every action to this specific business.
   BAD: "Create content about your services"
   GOOD: "Write a comprehensive guide: 'How to Choose a Retirement Planner in Westlake Village'"

3. QUICK WINS FIRST — Order actions within each recommendation from easiest/fastest
   to most involved. Schema markup and Google Business Profile come before "build a content hub."

4. CONCRETE AND HANDOFF-READY — Each action should be specific enough that a web developer
   or content writer could execute it without further clarification.
   BAD: "Improve your website"
   GOOD: "Add LocalBusiness JSON-LD schema to your homepage with your business name, address, phone number, and service area"

5. PRIORITY LEVELS:
   - high: Directly addresses the biggest visibility gaps
   - medium: Important improvements with moderate impact
   - low: Nice-to-haves and long-term strategy

6. 3-5 ACTIONS per recommendation. Each action is one sentence.

Respond ONLY with a JSON array. Each item:
{{"title": "Short title", "priority": "high|medium|low", "issue": "Why this matters — reference the failed queries", "actions": ["Action 1", "Action 2", ...]}}"""

    print(f"[RECS] Generating AI recommendations for {client_name}...")

    response = openai_client.chat.completions.create(
        model=CHATGPT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
        temperature=0.7,
    )

    result_text = response.choices[0].message.content.strip()
    if result_text.startswith('```'):
        result_text = result_text.split('```')[1]
        if result_text.startswith('json'):
            result_text = result_text[4:]
    result_text = result_text.strip()

    recommendations = json.loads(result_text)

    # Validate structure
    if not isinstance(recommendations, list) or len(recommendations) == 0:
        print("[RECS] AI returned empty or invalid recommendations")
        return None

    # Ensure each rec has the expected fields
    valid_recs = []
    for rec in recommendations:
        if isinstance(rec, dict) and 'title' in rec and 'actions' in rec:
            valid_recs.append({
                "title": rec.get("title", ""),
                "priority": rec.get("priority", "medium"),
                "issue": rec.get("issue", ""),
                "actions": rec.get("actions", []),
            })

    if not valid_recs:
        print("[RECS] AI response had no valid recommendations")
        return None

    print(f"[RECS] Generated {len(valid_recs)} AI-personalized recommendations")
    return valid_recs


def _template_recommendations(client_name, results, brand_queries, local_queries,
                              info_queries, percentage, best_platform, worst_platform,
                              package_type="basic"):
    """Fallback: template-based recommendations when AI is unavailable."""
    recommendations = []

    failed_local = [r for r in local_queries if r['score'] < 4] if local_queries else []
    failed_info = [r for r in info_queries if r['score'] < 4] if info_queries else []
    failed_brand = [r for r in brand_queries if r['score'] < 8] if brand_queries else []

    is_premium = package_type.lower() == "premium"

    if failed_local:
        local_query_examples = ", ".join([f'"{q["query"]}"' for q in failed_local[:2]])
        actions = [
            f"Add '{client_name}' + location keywords to homepage title and H1",
            "Create location-specific landing pages with city name in URL",
            "Build local citations on directories (Yelp, Google Business, industry directories)",
            "Add LocalBusiness schema markup with address and service area"
        ]
        if is_premium:
            actions.extend([
                "Create neighborhood-specific content pages targeting micro-local searches",
                "Build relationships with local bloggers and news sites for backlinks"
            ])
        recommendations.append({
            "title": "Improve Local Search Visibility",
            "priority": "high",
            "issue": f"Not appearing in local searches like {local_query_examples}",
            "actions": actions
        })

    if failed_info:
        info_query_examples = ", ".join([f'"{q["query"]}"' for q in failed_info[:2]])
        actions = [
            "Create comprehensive FAQ page with industry questions",
            "Publish blog posts answering common questions in your field",
            "Add structured data (FAQ schema) to help AI extract answers",
            "Create 'How it works' or 'What to expect' educational content"
        ]
        if is_premium:
            actions.extend([
                "Develop in-depth guides and whitepapers on industry topics",
                "Create comparison content (e.g., 'X vs Y: Which is right for you?')"
            ])
        recommendations.append({
            "title": "Build Thought Leadership Content",
            "priority": "high" if len(failed_info) > 1 else "medium",
            "issue": f"Not being cited for informational queries like {info_query_examples}",
            "actions": actions
        })

    if failed_brand:
        actions = [
            "Ensure consistent NAP (Name, Address, Phone) across all web properties",
            "Claim and optimize Google Business Profile",
            "Build backlinks from authoritative industry sites",
            "Get mentioned in industry publications and local news"
        ]
        recommendations.append({
            "title": "Strengthen Brand Recognition",
            "priority": "high",
            "issue": "Brand name not consistently recognized across AI platforms",
            "actions": actions
        })

    if worst_platform and best_platform and worst_platform != best_platform:
        platform_tips = {
            "ChatGPT": "Ensure content is well-structured with clear headings and summaries",
            "Claude": "Add detailed, factual content with citations and sources",
            "Gemini": "Optimize Google Business Profile and ensure site is indexed properly",
            "Perplexity": "Build more backlinks and citations from authoritative sources"
        }
        recommendations.append({
            "title": f"Optimize for {worst_platform}",
            "priority": "medium",
            "issue": f"Lower visibility on {worst_platform} compared to {best_platform}",
            "actions": [
                platform_tips.get(worst_platform, "Review platform-specific optimization strategies"),
                "Ensure website loads quickly and is mobile-friendly",
                "Add more specific, factual information about your services"
            ]
        })

    if percentage < 70:
        recommendations.append({
            "title": "Enhance Overall AI Discoverability",
            "priority": "medium",
            "issue": "Room for improvement in overall AI visibility",
            "actions": [
                "Add clear, factual 'About' page with company history and credentials",
                "Include team bios with qualifications and expertise",
                "Publish case studies or testimonials with specific details",
                "Ensure all pages have descriptive meta titles and descriptions"
            ]
        })

    return recommendations


# ---------------------------------------------------------------------------
# FAQ generation
# ---------------------------------------------------------------------------

def generate_faqs(client_name, client_website, industry, location, queries,
                  visibility_percentage, key_findings, recommendations,
                  competitors=None, num_faqs=8):
    """Generate website-ready FAQs using Claude, informed by audit results.

    Returns a dict with 'faqs' (list of Q&A dicts), 'html' (ready-to-paste),
    and 'schema' (JSON-LD FAQ schema markup).
    """
    if not anthropic_client:
        return {"error": "Anthropic API key not configured"}

    # Build context from audit data
    weak_queries = [q for q in queries if q.get('score', 0) < 6]
    strong_queries = [q for q in queries if q.get('score', 0) >= 6]

    weak_summary = "\n".join(
        f'  - "{q["query"]}" (score {q["score"]}/12, type: {q.get("type", "Unknown")})'
        for q in weak_queries[:8]
    ) or "  None — all queries performed well."

    strong_summary = "\n".join(
        f'  - "{q["query"]}" (score {q["score"]}/12)'
        for q in strong_queries[:5]
    ) or "  None."

    findings_text = "\n".join(f"  - {f}" for f in (key_findings or [])) or "  None."

    rec_text = "\n".join(
        f'  - {r.get("title", "")}: {r.get("issue", "")}'
        for r in (recommendations or [])[:5]
    ) or "  None."

    competitor_text = ""
    if competitors:
        competitor_text = "\nCOMPETITORS:\n" + "\n".join(
            f'  - {c.get("name", "")} ({c.get("visibility_display", "?")} visibility)'
            f' — Strength: {c.get("strengths", "N/A")}'
            for c in competitors[:5]
        )

    num_faqs = max(5, min(num_faqs, 10))

    prompt = f"""You are a GEO (Generative Engine Optimization) specialist creating FAQ content
for a client's website. The goal is to create FAQs that AI search engines will pick up and cite
when users ask questions related to this business.

CLIENT: {client_name}
WEBSITE: {client_website or 'N/A'}
INDUSTRY: {industry or 'N/A'}
LOCATION: {location or 'N/A'}
OVERALL VISIBILITY: {visibility_percentage:.1f}%

QUERIES WHERE THE CLIENT IS NOT BEING FOUND (these are the gaps to fill):
{weak_summary}

QUERIES WHERE THE CLIENT IS VISIBLE (leverage these):
{strong_summary}

KEY FINDINGS FROM AUDIT:
{findings_text}

TOP RECOMMENDATIONS:
{rec_text}
{competitor_text}

GENERATE EXACTLY {num_faqs} FAQs following these rules:

1. PRIORITIZE VISIBILITY GAPS — The FAQs should directly answer the types of questions
   where the client is NOT being found. If they're missing from "best {industry} in {location}"
   queries, create FAQs that establish them as a top choice in that area.

2. ENTITY-RICH ANSWERS — Include the business name, location, specific services, and
   concrete details in every answer. AI engines cite content that is factually dense.
   Mention "{client_name}" by name in most answers.

3. NATURAL QUESTION FORMAT — Write questions the way a real person would ask them.
   Good: "What makes {client_name} different from other {industry} providers in {location}?"
   Bad: "Why choose us?"

4. COMPREHENSIVE ANSWERS — Each answer should be 2-4 sentences. Include specific details,
   not vague marketing language. Mention services, credentials, experience, location details.

5. DIFFERENTIATION — If competitors exist, subtly address what makes this client unique
   without naming competitors.

6. MIX OF QUESTION TYPES:
   - 2-3 "What/Who" questions (establish identity and services)
   - 2-3 "How/Why" questions (demonstrate expertise)
   - 1-2 location-specific questions (local visibility)
   - 1-2 comparison/selection questions (capture comparison searches)

Respond ONLY with a JSON array. Each item: {{"question": "...", "answer": "..."}}"""

    print(f"[FAQ] Generating {num_faqs} FAQs for {client_name} via Claude...")

    response = anthropic_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=3000,
        temperature=0.7,
        messages=[{"role": "user", "content": prompt}],
    )

    result_text = response.content[0].text.strip()

    # Strip markdown code fences if present
    if result_text.startswith('```'):
        result_text = result_text.split('```')[1]
        if result_text.startswith('json'):
            result_text = result_text[4:]
    result_text = result_text.strip()

    faqs = json.loads(result_text)

    if not isinstance(faqs, list) or len(faqs) == 0:
        return {"error": "AI returned empty or invalid FAQ data"}

    # Validate structure
    valid_faqs = []
    for faq in faqs:
        if isinstance(faq, dict) and 'question' in faq and 'answer' in faq:
            valid_faqs.append({
                "question": faq["question"].strip(),
                "answer": faq["answer"].strip(),
            })

    if not valid_faqs:
        return {"error": "AI response contained no valid Q&A pairs"}

    # Generate ready-to-paste HTML
    html = _faqs_to_html(valid_faqs, client_name)

    # Generate JSON-LD FAQ schema
    schema = _faqs_to_schema(valid_faqs)

    print(f"[FAQ] Generated {len(valid_faqs)} FAQs for {client_name}")

    return {
        "success": True,
        "faqs": valid_faqs,
        "html": html,
        "schema": schema,
        "count": len(valid_faqs),
    }


def _faqs_to_html(faqs, client_name):
    """Convert FAQ list to ready-to-paste HTML for a Joomla article."""
    lines = [f'<h2>Frequently Asked Questions About {client_name}</h2>', '']
    for faq in faqs:
        q = faq['question'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        a = faq['answer'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        lines.append(f'<h3>{q}</h3>')
        lines.append(f'<p>{a}</p>')
        lines.append('')
    return '\n'.join(lines)


def _faqs_to_schema(faqs):
    """Convert FAQ list to JSON-LD FAQ schema markup."""
    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": faq["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": faq["answer"],
                },
            }
            for faq in faqs
        ],
    }
    return json.dumps(schema, indent=2)
