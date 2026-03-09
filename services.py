"""Business logic — audit orchestration, competitor analysis, recommendations."""

from concurrent.futures import ThreadPoolExecutor, as_completed

from config import (
    openai_client, anthropic_client, gemini_model, perplexity_client,
    CHATGPT_MODEL,
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
- If competitor focuses on socialization/daycare → your advantage might be outdoor hiking or cat care
- If competitor focuses on dogs → your advantage might be cat care services
- If competitor focuses on training → your advantage might be boarding or adventure activities
- If competitor is a large chain → your advantage might be local/personalized service

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

    def check_single_competitor(competitor):
        comp_name = competitor.get('name', '')
        comp_website = competitor.get('website', '')
        if not comp_name:
            return None

        print(f"[COMPETITOR AUDIT] Checking: {comp_name}")

        comp_totals = {p: 0 for p in PLATFORMS}

        for q in queries:
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
        max_score = len(queries) * 12
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
            "queries_tested": len(queries),
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
        "api_calls_made": len(competitors) * len(queries) * 4,
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
    """Generate tailored recommendations based on audit results and package type."""
    recommendations = []

    failed_local = [r for r in local_queries if r['score'] < 4] if local_queries else []
    failed_info = [r for r in info_queries if r['score'] < 4] if info_queries else []
    failed_brand = [r for r in brand_queries if r['score'] < 8] if brand_queries else []

    is_premium = package_type.lower() == "premium"

    # 1: Local visibility
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
                "Build relationships with local bloggers and news sites for backlinks",
                "Add location-based testimonials mentioning specific areas served"
            ])
        recommendations.append({
            "title": "Improve Local Search Visibility",
            "priority": "high",
            "issue": f"Not appearing in local searches like {local_query_examples}",
            "actions": actions
        })

    # 2: Content/thought leadership
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
                "Create comparison content (e.g., 'X vs Y: Which is right for you?')",
                "Add expert quotes and data citations to boost authority signals"
            ])
        recommendations.append({
            "title": "Build Thought Leadership Content",
            "priority": "high" if len(failed_info) > 1 else "medium",
            "issue": f"Not being cited for informational queries like {info_query_examples}",
            "actions": actions
        })

    # 3: Brand visibility
    if failed_brand:
        actions = [
            "Ensure consistent NAP (Name, Address, Phone) across all web properties",
            "Build backlinks from authoritative industry sites",
            "Claim and optimize Google Business Profile",
            "Get mentioned in industry publications and local news"
        ]
        if is_premium:
            actions.extend([
                "Create a Wikipedia page or ensure accurate information on relevant wiki pages",
                "Pursue PR opportunities for brand mentions in authoritative publications",
                "Develop co-marketing partnerships for cross-promotional brand exposure"
            ])
        recommendations.append({
            "title": "Strengthen Brand Recognition",
            "priority": "high",
            "issue": "Brand name not consistently recognized across AI platforms",
            "actions": actions
        })

    # 4: Platform-specific
    if worst_platform and best_platform and worst_platform != best_platform:
        platform_tips = {
            "ChatGPT": "Ensure content is well-structured with clear headings and summaries",
            "Claude": "Add detailed, factual content with citations and sources",
            "Gemini": "Optimize Google Business Profile and ensure site is indexed properly",
            "Perplexity": "Build more backlinks and citations from authoritative sources"
        }
        actions = [
            platform_tips.get(worst_platform, "Review platform-specific optimization strategies"),
            "Ensure website loads quickly and is mobile-friendly",
            "Add more specific, factual information about your services"
        ]
        if is_premium:
            platform_premium_tips = {
                "ChatGPT": "Structure content with clear Q&A format that GPT can easily parse",
                "Claude": "Add primary source citations and research-backed claims",
                "Gemini": "Ensure Google Search Console shows no indexing issues",
                "Perplexity": "Focus on earning citations from .edu and .gov domains"
            }
            actions.append(platform_premium_tips.get(worst_platform, "Conduct platform-specific content audit"))
        recommendations.append({
            "title": f"Optimize for {worst_platform}",
            "priority": "medium",
            "issue": f"Lower visibility on {worst_platform} compared to {best_platform}",
            "actions": actions
        })

    # 5: General improvement
    if percentage < 70:
        actions = [
            "Add clear, factual 'About' page with company history and credentials",
            "Include team bios with qualifications and expertise",
            "Publish case studies or testimonials with specific details",
            "Ensure all pages have descriptive meta titles and descriptions"
        ]
        if is_premium:
            actions.extend([
                "Implement comprehensive schema markup across all page types",
                "Create a resource hub or knowledge base for your industry"
            ])
        recommendations.append({
            "title": "Enhance Overall AI Discoverability",
            "priority": "medium",
            "issue": "Room for improvement in overall AI visibility",
            "actions": actions
        })

    # Premium-only recommendations
    if is_premium:
        recommendations.append({
            "title": "Technical Optimization for AI Crawlers",
            "priority": "medium",
            "issue": "AI platforms may not be extracting all available information",
            "actions": [
                "Implement comprehensive JSON-LD structured data (Organization, LocalBusiness, FAQPage)",
                "Ensure clean HTML semantics with proper heading hierarchy",
                "Add descriptive alt text to all images",
                "Create an XML sitemap and submit to search engines",
                "Optimize page load speed to under 3 seconds"
            ]
        })
        recommendations.append({
            "title": "Maintain Content Freshness",
            "priority": "low",
            "issue": "AI models favor recently updated, relevant content",
            "actions": [
                "Establish a regular blog posting schedule (minimum 2x/month)",
                "Update service pages quarterly with new information",
                "Add 'Last Updated' dates to key pages",
                "Create seasonal or timely content relevant to your industry",
                "Monitor and update outdated statistics or information"
            ]
        })
        recommendations.append({
            "title": "Strengthen Competitive Positioning",
            "priority": "low",
            "issue": "Opportunity to differentiate from competitors in AI responses",
            "actions": [
                "Create comparison pages highlighting your unique advantages",
                "Develop case studies with measurable results",
                "Highlight awards, certifications, and unique qualifications",
                "Build a reviews strategy to increase positive sentiment signals",
                "Create 'Why Choose Us' content addressing common decision factors"
            ]
        })

    return recommendations
