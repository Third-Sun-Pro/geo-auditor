"""Report generation — HTML report builder for PDF export."""

from config import get_logo_base64


def get_score_class(score):
    """Return CSS class based on score (max 12 per query with 4 platforms)."""
    if score >= 9:
        return "score-3"
    elif score >= 5:
        return "score-2"
    elif score >= 2:
        return "score-1"
    else:
        return "score-0"


def get_score_icon(score):
    """Return icon based on score (max 12 per query with 4 platforms)."""
    if score >= 9:
        return "&#10003;"
    elif score >= 4:
        return "&#9888;"
    else:
        return "&#10007;"


def _visibility_label(percentage):
    """Return a human-readable visibility label for the score summary."""
    if percentage >= 70:
        return "Excellent"
    elif percentage >= 50:
        return "Strong"
    elif percentage >= 30:
        return "Moderate"
    elif percentage >= 15:
        return "Low"
    return "Very Low"


def _platform_fill_class(percentage):
    """Return CSS class for platform progress bar fill color."""
    if percentage >= 50:
        return "fill-strong"
    elif percentage >= 25:
        return "fill-moderate"
    return "fill-low"


def _executive_context(percentage, num_queries):
    """Return contextual sentence for the executive summary based on score level."""
    if percentage >= 70:
        return (
            "This is a strong position — the business is being actively recommended "
            "by AI search tools. The recommendations below focus on maintaining this "
            "advantage and closing any remaining gaps."
        )
    elif percentage >= 50:
        return (
            "The business has a solid foundation in AI search, but there are clear "
            "opportunities to improve. Implementing the high-priority recommendations "
            "below could significantly increase visibility."
        )
    elif percentage >= 30:
        return (
            "There is room for meaningful improvement. AI search tools are aware of the "
            "business but aren't consistently recommending it. The recommendations below "
            "outline specific steps to strengthen this presence."
        )
    elif percentage >= 15:
        return (
            "AI search tools are largely not surfacing this business in their responses. "
            "This represents both a challenge and an opportunity — competitors who invest "
            "in GEO now will gain a significant advantage. See the recommendations below "
            "for actionable next steps."
        )
    return (
        "The business is currently not visible in AI-generated search results. As more "
        "consumers turn to AI tools for recommendations, addressing this gap is critical. "
        "The recommendations below provide a roadmap to build visibility from the ground up."
    )


def generate_report_html(data):
    """Generate the HTML report from form data."""

    color = data.get('brand_color', 'E77206')
    logo_html = get_logo_base64()

    # Calculate totals
    queries = data.get('queries', [])
    total_score = sum(q.get('score', 0) for q in queries)
    max_score = len(queries) * 12
    percentage = (total_score / max_score) * 100 if max_score > 0 else 0

    # Generate query rows
    query_rows = ""
    for i, q in enumerate(queries, 1):
        score = q.get('score', 0)
        score_class = get_score_class(score)
        icon = get_score_icon(score)
        query_rows += f"""
            <tr>
                <td>{i}</td>
                <td>{q.get('query', '')}</td>
                <td>{q.get('type', '')}</td>
                <td class="{score_class}">{score}/12</td>
                <td>{icon} {q.get('finding', '')}</td>
            </tr>"""

    # Generate platform cards
    platforms = data.get('platforms', {})
    platform_cards = ""
    platform_names = {
        "chatgpt": "ChatGPT (OpenAI)",
        "perplexity": "Perplexity AI",
        "claude": "Claude (Anthropic)",
        "gemini": "Gemini (Google)"
    }
    for platform, pdata in platforms.items():
        score = pdata.get('score', 0)
        max_p = pdata.get('max', 30)
        pct = (score / max_p) * 100 if max_p > 0 else 0
        fill_class = _platform_fill_class(pct)
        platform_cards += f"""
        <div class="platform-card">
            <h3>{platform_names.get(platform, platform)}</h3>
            <div class="platform-score">{pct:.0f}%</div>
            <div class="progress-bar"><div class="progress-fill {fill_class}" style="width: {pct:.0f}%"></div></div>
            <p class="platform-visibility">{score}/{max_p} points</p>
            <p class="platform-model">{pdata.get('note', '')}</p>
        </div>"""

    # Generate recommendations
    recommendations = data.get('recommendations', [])
    recommendation_html = ""
    for i, rec in enumerate(recommendations, 1):
        priority = rec.get('priority', 'medium')
        priority_class = f"priority-{priority}"
        actions = rec.get('actions', [])
        actions_html = "".join(f"<li>{a}</li>" for a in actions if a)
        recommendation_html += f"""
    <div class="recommendation {priority_class}">
        <h4>{i}. {rec.get('title', '')} ({priority.upper()} PRIORITY)</h4>
        <p><strong>Issue:</strong> {rec.get('issue', '')}</p>
        <p><strong>Action:</strong></p>
        <ul style="margin: 10px 0; font-size: 10pt;">
            {actions_html}
        </ul>
    </div>"""

    # Generate competitor rows
    competitors = data.get('competitors', [])
    competitor_rows = ""
    for comp in competitors:
        visibility = comp.get('visibility_display', comp.get('visibility', ''))
        if not visibility or (visibility and '%' not in str(visibility)):
            visibility = 'Not tested'
        competitor_rows += f"""
            <tr>
                <td><strong>{comp.get('name', '')}</strong></td>
                <td>{visibility}</td>
                <td>{comp.get('strengths', '')}</td>
                <td>{comp.get('your_advantage', '')}</td>
            </tr>"""

    # Generate key findings
    findings = data.get('key_findings', [])
    findings_html = "".join(f"<li>{f}</li>" for f in findings if f)

    client = data.get('client', {})

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400;1,600;1,700;1,800&display=swap" rel="stylesheet">
    <style>
        @page {{
            size: letter;
            margin: 0.5in 0.75in 1.15in 0.75in;
        }}

        :root {{
            --orange-primary: #{color};
            --orange-dark: #D56A1F;
            --yellow-accent: #F5B041;
            --red-accent: #A93226;
            --maroon-accent: #7B241C;
            --cream-bg: #FDF6F0;
            --light-gray: #f8f9fa;
        }}

        body {{
            font-family: 'Visby CF', 'Poppins', 'Avenir', 'Montserrat', 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 8.5in;
            margin: 0 auto;
            position: relative;
        }}

        .logo-area {{
            text-align: center;
            margin-bottom: 30px;
        }}

        .logo-text {{
            font-size: 36pt;
            font-weight: 700;
            color: var(--orange-primary);
            letter-spacing: -1px;
        }}

        .header {{
            border-bottom: none;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}

        h1 {{
            color: #2C2C2C;
            font-size: 28pt;
            font-weight: 800;
            margin: 0 0 5px 0;
        }}

        .subtitle {{
            font-size: 14pt;
            color: var(--orange-primary);
            font-style: italic;
            margin: 0;
        }}

        h2 {{
            color: var(--orange-primary);
            font-size: 18pt;
            font-weight: 700;
            margin-top: 35px;
            margin-bottom: 15px;
            border-bottom: none;
            padding-bottom: 8px;
            display: inline-block;
            position: relative;
        }}

        h2::after {{
            content: '';
            position: absolute;
            bottom: 0;
            left: 0;
            width: 100%;
            height: 3px;
            background: var(--orange-primary);
        }}

        .section-header {{
            margin-bottom: 20px;
        }}

        h3 {{
            color: #333;
            font-size: 14pt;
            margin-top: 20px;
            margin-bottom: 10px;
        }}

        /* Client Info Card */
        .client-info {{
            background: white;
            padding: 25px 30px;
            border-radius: 12px;
            margin-bottom: 30px;
            border-left: 5px solid var(--yellow-accent);
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }}

        .client-info table {{
            width: 100%;
            border-collapse: collapse;
        }}

        .client-info td {{
            padding: 10px 0;
            border-bottom: 1px solid #eee;
            font-size: 11pt;
        }}

        .client-info tr:last-child td {{
            border-bottom: none;
        }}

        .client-info td:first-child {{
            font-weight: 600;
            width: 200px;
            color: #555;
            text-transform: uppercase;
            font-size: 9pt;
            letter-spacing: 0.5px;
        }}

        /* Score Summary Box */
        .score-summary {{
            background: var(--orange-primary);
            color: white;
            padding: 35px 40px;
            border-radius: 16px;
            margin: 30px 0;
            text-align: center;
        }}

        .score-summary h2 {{
            color: white;
            border: none;
            margin: 0 0 10px 0;
            font-size: 14pt;
            font-weight: 400;
            text-transform: uppercase;
            letter-spacing: 2px;
            display: block;
        }}

        .score-summary h2::after {{
            display: none;
        }}

        .score-number {{
            font-size: 72pt;
            font-weight: 800;
            margin: 10px 0;
            letter-spacing: -2px;
            font-style: italic;
        }}

        .score-label {{
            font-size: 20pt;
            font-weight: 600;
            color: var(--yellow-accent);
        }}

        .score-note {{
            margin-top: 20px;
            font-size: 11pt;
            opacity: 0.9;
            font-style: italic;
        }}

        /* Tables */
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 10pt;
            border-radius: 8px;
            overflow: hidden;
        }}

        th {{
            background: var(--orange-primary);
            color: white;
            padding: 14px 12px;
            text-align: left;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 9pt;
            letter-spacing: 0.5px;
        }}

        td {{
            padding: 12px;
            border-bottom: 1px solid #eee;
        }}

        tbody tr:nth-child(even) {{
            background: #fafafa;
        }}

        tbody tr:hover {{
            background: #f5f5f5;
        }}

        .score-0 {{ background: #FDEDEC; color: #922B21; font-weight: bold; text-align: center; }}
        .score-1 {{ background: #FEF9E7; color: #9A7D0A; font-weight: bold; text-align: center; }}
        .score-2 {{ background: #E8F8F5; color: #1E8449; font-weight: bold; text-align: center; }}
        .score-3 {{ background: #D5F5E3; color: #1E8449; font-weight: bold; text-align: center; }}

        /* Platform Cards */
        .platform-breakdown {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin: 25px 0;
        }}

        .platform-card {{
            background: white;
            border: 1px solid #eee;
            border-radius: 12px;
            padding: 25px;
            border-left: 5px solid var(--yellow-accent);
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            text-align: center;
        }}

        .platform-card h3 {{
            margin: 0 0 15px 0;
            color: #333;
            font-size: 13pt;
            font-weight: 600;
        }}

        .platform-score {{
            font-size: 36pt;
            font-weight: 800;
            color: var(--orange-primary);
            font-style: italic;
            margin: 10px 0;
        }}

        .platform-visibility {{
            font-size: 11pt;
            color: var(--orange-primary);
            font-weight: 600;
            margin-bottom: 5px;
        }}

        .platform-model {{
            font-size: 9pt;
            color: #888;
        }}

        /* Recommendation Cards */
        .recommendation {{
            background: var(--cream-bg);
            border-left: 5px solid var(--yellow-accent);
            border-radius: 0 12px 12px 0;
            padding: 20px 25px;
            margin: 20px 0;
        }}

        .recommendation h4 {{
            margin: 0 0 15px 0;
            color: var(--orange-primary);
            font-size: 13pt;
            font-weight: 700;
        }}

        .recommendation p {{
            margin: 8px 0;
            font-size: 10pt;
        }}

        .recommendation strong {{
            color: #444;
        }}

        .recommendation ul {{
            margin: 10px 0;
            padding-left: 20px;
            font-size: 10pt;
        }}

        .recommendation li {{
            margin: 6px 0;
        }}

        .priority-high {{
            border-left-color: var(--orange-primary);
            background: #FEF5F0;
        }}
        .priority-medium {{
            border-left-color: var(--yellow-accent);
            background: #FFFBF0;
        }}
        .priority-low {{
            border-left-color: #28a745;
            background: #F0FFF4;
        }}

        /* Gradient Footer Bar */
        .gradient-footer {{
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            height: 25px;
            background: linear-gradient(90deg,
                var(--yellow-accent) 0%,
                var(--orange-primary) 50%,
                var(--maroon-accent) 100%
            );
            z-index: 1000;
        }}

        .footer {{
            margin-top: 50px;
            padding: 20px 0 40px 0;
            font-size: 9pt;
            color: #888;
            text-align: center;
        }}

        .footer p {{
            margin: 5px 0;
        }}

        .footer strong {{
            color: #666;
        }}

        .page-break {{
            page-break-after: always;
        }}

        /* ===== Print / PDF page-break rules ===== */
        @media print {{
            body {{
                padding-bottom: 35px;
            }}
            .gradient-footer {{
                position: fixed;
                bottom: 0;
            }}
            .client-info,
            .score-summary,
            .score-interpretation,
            .score-legend,
            .geo-explainer,
            .recommendation,
            .platform-card,
            .executive-summary,
            .key-findings {{
                page-break-inside: avoid;
            }}
            .section-header,
            h2, h3 {{
                page-break-after: avoid;
            }}
            thead {{
                display: table-header-group;
            }}
            tr {{
                page-break-inside: avoid;
            }}
            .platform-breakdown {{
                page-break-inside: avoid;
            }}
        }}

        /* Key Findings List */
        .key-findings {{
            margin: 15px 0;
        }}

        .key-findings li {{
            margin: 10px 0;
            font-size: 11pt;
        }}

        /* Executive Summary styling */
        .executive-summary p {{
            font-size: 11pt;
            line-height: 1.7;
        }}

        /* GEO Explainer */
        .geo-explainer {{
            background: var(--cream-bg);
            padding: 25px 30px;
            border-radius: 12px;
            margin-bottom: 30px;
            border-left: 5px solid var(--orange-primary);
        }}

        .geo-explainer h3 {{
            color: var(--orange-primary);
            margin: 0 0 10px 0;
            font-size: 13pt;
        }}

        .geo-explainer p {{
            font-size: 10pt;
            line-height: 1.6;
            margin: 8px 0;
            color: #555;
        }}

        /* Score Interpretation */
        .score-interpretation {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr 1fr;
            gap: 12px;
            margin: 20px 0;
        }}

        .score-level {{
            text-align: center;
            padding: 12px 8px;
            border-radius: 8px;
            font-size: 9pt;
            font-weight: 600;
        }}

        .score-level .level-range {{
            font-size: 14pt;
            font-weight: 800;
            display: block;
            margin-bottom: 4px;
        }}

        .level-strong {{
            background: #D5F5E3;
            color: #1E8449;
        }}
        .level-moderate {{
            background: #E8F8F5;
            color: #1E8449;
        }}
        .level-low {{
            background: #FEF9E7;
            color: #9A7D0A;
        }}
        .level-not-found {{
            background: #FDEDEC;
            color: #922B21;
        }}

        /* Progress bar for platform cards */
        .progress-bar {{
            width: 100%;
            height: 8px;
            background: #eee;
            border-radius: 4px;
            margin: 12px 0 6px 0;
            overflow: hidden;
        }}

        .progress-fill {{
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s ease;
        }}

        .fill-strong {{ background: #27ae60; }}
        .fill-moderate {{ background: #f39c12; }}
        .fill-low {{ background: #e74c3c; }}

        /* Score legend */
        .score-legend {{
            background: #f8f9fa;
            padding: 20px 25px;
            border-radius: 12px;
            margin: 20px 0 30px 0;
        }}

        .score-legend h4 {{
            margin: 0 0 12px 0;
            font-size: 11pt;
            color: #555;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .legend-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 9pt;
        }}

        .legend-dot {{
            width: 12px;
            height: 12px;
            border-radius: 3px;
            flex-shrink: 0;
        }}
    </style>
</head>
<body>
    <div class="logo-area">
        {logo_html}
    </div>

    <div class="header">
        <h1>GENERATIVE ENGINE OPTIMIZATION AUDIT</h1>
        <p class="subtitle">AI Visibility Analysis Report</p>
    </div>

    <div class="geo-explainer">
        <h3>What is Generative Engine Optimization?</h3>
        <p>
            When people search using AI tools like ChatGPT, Claude, Gemini, and Perplexity, these
            platforms generate answers by pulling from websites across the internet. <strong>Generative
            Engine Optimization (GEO)</strong> measures whether your business is being mentioned,
            cited, or recommended in those AI-generated responses.
        </p>
        <p>
            This audit tested {len(queries)} real search queries — the kinds of questions your potential
            customers are asking — across 4 major AI platforms to see how visible
            {client.get('name', 'your business')} is in this new search landscape.
        </p>
    </div>

    <div class="client-info">
        <table>
            <tr><td>CLIENT NAME</td><td><strong>{client.get('name', '')}</strong></td></tr>
            <tr><td>WEBSITE</td><td>{client.get('website', '')}</td></tr>
            <tr><td>INDUSTRY</td><td>{client.get('industry', '')}</td></tr>
            <tr><td>LOCATION</td><td>{client.get('location', '')}</td></tr>
            <tr><td>AUDIT DATE</td><td>{client.get('audit_date', '')}</td></tr>
            <tr><td>PACKAGE TYPE</td><td>{client.get('package', '')}</td></tr>
            <tr><td>COMPETITORS ANALYZED</td><td>{client.get('competitors', '')}</td></tr>
        </table>
    </div>

    <div class="score-summary">
        <h2>OVERALL VISIBILITY SCORE</h2>
        <div class="score-number">{percentage:.0f}%</div>
        <div class="score-label">{_visibility_label(percentage)} AI Visibility</div>
        <p class="score-note">
            {total_score} out of {max_score} points across {len(queries)} queries on 4 AI platforms
        </p>
    </div>

    <div class="score-interpretation">
        <div class="score-level level-strong">
            <span class="level-range">70%+</span>
            Excellent
        </div>
        <div class="score-level level-moderate">
            <span class="level-range">50-69%</span>
            Strong
        </div>
        <div class="score-level level-low">
            <span class="level-range">30-49%</span>
            Moderate
        </div>
        <div class="score-level level-not-found">
            <span class="level-range">&lt;30%</span>
            Needs Work
        </div>
    </div>

    <div class="section-header">
        <h2>Executive Summary</h2>
    </div>
    <div class="executive-summary">
        <p>
            {client.get('name', 'The client')} demonstrates <strong>{_visibility_label(percentage).lower()} visibility</strong>
            across AI-powered search engines, scoring {percentage:.0f}% overall.
            {_executive_context(percentage, len(queries))}
        </p>

        <p><strong>KEY FINDINGS</strong></p>
        <ul class="key-findings">
            {findings_html}
        </ul>
    </div>

    <div class="page-break"></div>

    <div class="section-header">
        <h2>Detailed Query Results</h2>
    </div>

    <div class="score-legend">
        <h4>How to Read the Scores</h4>
        <p style="font-size: 9pt; color: #666; margin: 0 0 12px 0;">
            Each query is tested on 4 AI platforms. Per platform, the score reflects how the business appeared:
        </p>
        <div class="legend-grid">
            <div class="legend-item">
                <div class="legend-dot" style="background: #D5F5E3; border: 1px solid #1E8449;"></div>
                <span><strong>3 pts</strong> — URL cited directly in the response</span>
            </div>
            <div class="legend-item">
                <div class="legend-dot" style="background: #E8F8F5; border: 1px solid #1E8449;"></div>
                <span><strong>2 pts</strong> — Business mentioned by name</span>
            </div>
            <div class="legend-item">
                <div class="legend-dot" style="background: #FEF9E7; border: 1px solid #9A7D0A;"></div>
                <span><strong>1 pt</strong> — Industry/category mentioned, not the business</span>
            </div>
            <div class="legend-item">
                <div class="legend-dot" style="background: #FDEDEC; border: 1px solid #922B21;"></div>
                <span><strong>0 pts</strong> — Not mentioned at all</span>
            </div>
        </div>
        <p style="font-size: 9pt; color: #888; margin: 12px 0 0 0;">
            Maximum score per query: 12 points (3 points × 4 platforms)
        </p>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width: 5%">#</th>
                <th style="width: 30%">QUERY</th>
                <th style="width: 10%">TYPE</th>
                <th style="width: 10%">SCORE</th>
                <th style="width: 45%">KEY FINDINGS</th>
            </tr>
        </thead>
        <tbody>
            {query_rows}
        </tbody>
    </table>

    <div class="section-header">
        <h2>Performance by Platform</h2>
    </div>
    <div class="platform-breakdown">
        {platform_cards}
    </div>

    <div class="page-break"></div>

    <div class="section-header">
        <h2>Top Recommendations</h2>
    </div>
    <p style="font-size: 10pt; color: #888; margin-bottom: 20px;">
        Prioritized by impact potential
    </p>

    {recommendation_html}

    <div class="section-header">
        <h2>Competitive Landscape</h2>
    </div>
    <p style="font-size: 10pt; color: #888; margin-bottom: 15px;">Based on AI search visibility testing</p>
    <table>
        <thead>
            <tr>
                <th>COMPETITOR</th>
                <th>EST. VISIBILITY</th>
                <th>STRENGTHS</th>
                <th>YOUR ADVANTAGE</th>
            </tr>
        </thead>
        <tbody>
            {competitor_rows}
        </tbody>
    </table>

    <div class="section-header">
        <h2>Next Steps</h2>
    </div>
    <ul class="key-findings">
        <li><strong>Review Recommendations:</strong> Prioritize based on your resources and goals</li>
        <li><strong>Implement High-Priority Items:</strong> Start with the top 2-3 recommendations</li>
        <li><strong>30-Day Follow-Up:</strong> Re-run audit to measure improvement</li>
    </ul>

    <div class="footer">
        <p><strong>GEO Audit Report</strong> | Generated {client.get('audit_date', '')} | Third Sun Productions</p>
        <p>Next Steps: Review recommendations and schedule implementation</p>
    </div>

    <!-- Gradient Footer Bar -->
    <div class="gradient-footer"></div>
</body>
</html>
    """

    return html
