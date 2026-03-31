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


def _platform_score_cell(score):
    """Return styled HTML for a single platform score (0-3) in the query table."""
    if score >= 3:
        return f'<td style="text-align:center; color:#1E8449; font-weight:600;">{score}</td>'
    elif score >= 2:
        return f'<td style="text-align:center; color:#1E8449;">{score}</td>'
    elif score >= 1:
        return f'<td style="text-align:center; color:#9A7D0A;">{score}</td>'
    return '<td style="text-align:center; color:#ccc;">0</td>'


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


def _reaudit_executive_context(prev_pct, cur_pct, pct_change, queries_improved, queries_declined):
    """Return contextual narrative for re-audit executive summary focused on progress."""
    if pct_change > 10:
        progress_line = (
            "This represents significant progress. The GEO strategy is clearly working, "
            "and the business is gaining meaningful traction across AI search platforms."
        )
    elif pct_change > 0:
        progress_line = (
            "This is positive movement in the right direction. AI platforms are beginning "
            "to surface the business more consistently as optimization efforts take hold."
        )
    elif pct_change == 0:
        progress_line = (
            "Visibility has held steady since the last audit. While the score hasn't "
            "changed, maintaining position in a shifting AI landscape is still meaningful. "
            "The recommendations below target areas with the most room for growth."
        )
    else:
        progress_line = (
            "Visibility has dipped slightly since the last audit. This can happen as AI "
            "models update and competitors invest in their own optimization. The "
            "recommendations below are calibrated to regain and surpass the previous baseline."
        )

    movement_line = ""
    if queries_improved > 0 or queries_declined > 0:
        parts = []
        if queries_improved > 0:
            parts.append(f"{queries_improved} search queries showed improvement")
        if queries_declined > 0:
            parts.append(f"{queries_declined} declined")
        movement_line = " ".join(parts) + " — see the detailed comparison below."

    return f"{progress_line} {movement_line}"


def generate_report_html(data):
    """Generate the HTML report from form data."""

    color = data.get('brand_color', 'E77206')
    logo_html = get_logo_base64()

    # Calculate totals
    queries = data.get('queries', [])
    total_score = sum(q.get('score', 0) for q in queries)
    max_score = len(queries) * 12
    percentage = (total_score / max_score) * 100 if max_score > 0 else 0

    # Build comparison data lookups for use across the report
    comparison = data.get('comparison_data')
    is_reaudit = comparison is not None
    prev_query_scores = {}
    if comparison:
        for qc in comparison.get('query_changes', []):
            prev_query_scores[qc.get('query', '')] = qc.get('previous_score', 0)

    # Check if per-platform details exist (new audits have them, old ones don't)
    has_details = any(q.get('details') for q in queries)

    # Generate query rows
    query_rows = ""
    for i, q in enumerate(queries, 1):
        score = q.get('score', 0)
        score_class = get_score_class(score)
        icon = get_score_icon(score)
        details = q.get('details', {})

        # Build change cell for re-audits
        change_cell = ""
        if is_reaudit:
            query_text = q.get('query', '')
            if query_text in prev_query_scores:
                prev_score = prev_query_scores[query_text]
                delta = score - prev_score
                if delta > 0:
                    change_cell = f'<td style="text-align: center; color: #1E8449; font-weight: 600; font-size: 9pt;">&#9650; +{delta}</td>'
                elif delta < 0:
                    change_cell = f'<td style="text-align: center; color: #922B21; font-weight: 600; font-size: 9pt;">&#9660; {delta}</td>'
                else:
                    change_cell = '<td style="text-align: center; color: #888; font-size: 9pt;">&mdash;</td>'
            else:
                change_cell = '<td style="text-align: center; color: #888; font-size: 8pt;">new</td>'

        if has_details:
            chatgpt_cell = _platform_score_cell(details.get('chatgpt', {}).get('score', 0))
            claude_cell = _platform_score_cell(details.get('claude', {}).get('score', 0))
            gemini_cell = _platform_score_cell(details.get('gemini', {}).get('score', 0))
            perplexity_cell = _platform_score_cell(details.get('perplexity', {}).get('score', 0))
            query_rows += f"""
            <tr>
                <td>{i}</td>
                <td>{q.get('query', '')}</td>
                <td>{q.get('type', '')}</td>
                {chatgpt_cell}{claude_cell}{gemini_cell}{perplexity_cell}
                <td class="{score_class}">{score}/12</td>
                {change_cell}
                <td>{icon} {q.get('finding', '')}</td>
            </tr>"""
        else:
            query_rows += f"""
            <tr>
                <td>{i}</td>
                <td>{q.get('query', '')}</td>
                <td>{q.get('type', '')}</td>
                <td class="{score_class}">{score}/12</td>
                {change_cell}
                <td>{icon} {q.get('finding', '')}</td>
            </tr>"""

    # Build query table header (conditional on per-platform details and re-audit)
    change_header = '<th style="width: 6%; text-align: center;">+/-</th>' if is_reaudit else ''
    if has_details:
        findings_width = '26%' if is_reaudit else '32%'
        query_table_header = f"""
            <tr>
                <th style="width: 4%">#</th>
                <th style="width: 22%">QUERY</th>
                <th style="width: 8%">TYPE</th>
                <th style="width: 6%; text-align: center;" title="ChatGPT">GPT</th>
                <th style="width: 6%; text-align: center;" title="Claude">CL</th>
                <th style="width: 6%; text-align: center;" title="Gemini">GEM</th>
                <th style="width: 6%; text-align: center;" title="Perplexity">PPX</th>
                <th style="width: 8%">TOTAL</th>
                {change_header}
                <th style="width: {findings_width}">KEY FINDINGS</th>
            </tr>"""
    else:
        findings_width = '39%' if is_reaudit else '45%'
        query_table_header = f"""
            <tr>
                <th style="width: 5%">#</th>
                <th style="width: 28%">QUERY</th>
                <th style="width: 10%">TYPE</th>
                <th style="width: 10%">SCORE</th>
                {change_header}
                <th style="width: {findings_width}">KEY FINDINGS</th>
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

        # Build before/after comparison for re-audits
        platform_prev_html = ""
        if is_reaudit and comparison:
            p_changes = comparison.get('platform_changes', {}).get(platform, {})
            p_prev_pct = p_changes.get('previous', 0)
            p_delta = p_changes.get('change', 0)
            if p_delta > 0:
                delta_html = f'<span style="color: #1E8449; font-weight: 600;">&#9650; +{p_delta:.1f}%</span>'
            elif p_delta < 0:
                delta_html = f'<span style="color: #922B21; font-weight: 600;">&#9660; {p_delta:.1f}%</span>'
            else:
                delta_html = '<span style="color: #888;">no change</span>'
            prev_fill = _platform_fill_class(p_prev_pct)
            platform_prev_html = f"""
            <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #eee;">
                <div style="font-size: 8pt; color: #999; margin-bottom: 3px;">Previous: {p_prev_pct:.0f}%</div>
                <div class="progress-bar" style="margin: 0 0 6px 0;"><div class="progress-fill {prev_fill}" style="width: {p_prev_pct:.0f}%; opacity: 0.4;"></div></div>
                <div style="font-size: 10pt;">{delta_html}</div>
            </div>"""

        platform_cards += f"""
        <div class="platform-card">
            <h3>{platform_names.get(platform, platform)}</h3>
            <div class="platform-score">{pct:.0f}%</div>
            <div class="progress-bar"><div class="progress-fill {fill_class}" style="width: {pct:.0f}%"></div></div>
            <p class="platform-visibility">{score}/{max_p} points</p>
            <p class="platform-model">{pdata.get('note', '')}</p>
            {platform_prev_html}
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

    comparison_html = ""
    if comparison:
        pct_change = comparison.get('percentage_change', 0)
        prev_pct = comparison.get('previous_percentage', 0)
        cur_pct = comparison.get('current_percentage', 0)
        prev_date = comparison.get('previous_audit_date', 'Previous')
        change_sign = '+' if pct_change >= 0 else ''
        change_color = '#1E8449' if pct_change >= 0 else '#922B21'
        arrow = '&#9650;' if pct_change >= 0 else '&#9660;'

        # Platform change cards
        platform_names_cmp = {
            'chatgpt': 'ChatGPT', 'claude': 'Claude',
            'gemini': 'Gemini', 'perplexity': 'Perplexity'
        }
        platform_changes_html = ""
        for p_key, p_data in comparison.get('platform_changes', {}).items():
            p_change = p_data.get('change', 0)
            p_sign = '+' if p_change >= 0 else ''
            p_color = '#1E8449' if p_change > 0 else '#922B21' if p_change < 0 else '#888'
            platform_changes_html += f"""
                <div style="text-align: center; background: white; padding: 12px; border-radius: 8px; border: 1px solid #eee;">
                    <div style="font-size: 9pt; font-weight: 600; color: #555;">{platform_names_cmp.get(p_key, p_key)}</div>
                    <div style="font-size: 16pt; font-weight: 700; color: {p_color};">{p_sign}{p_change:.1f}%</div>
                    <div style="font-size: 8pt; color: #999;">{p_data.get('previous', 0):.0f}% &rarr; {p_data.get('current', 0):.0f}%</div>
                </div>
            """

        # Top query changes
        query_changes = comparison.get('query_changes', [])
        improved = [q for q in query_changes if q.get('change', 0) > 0][:3]
        declined = [q for q in query_changes if q.get('change', 0) < 0][:2]

        query_rows_cmp = ""
        for q in improved:
            query_rows_cmp += f"""
                <tr style="background: #f0fdf4;">
                    <td>{q.get('query', '')}</td>
                    <td style="text-align: center; color: #1E8449; font-weight: 600;">+{q['change']} pts</td>
                    <td style="text-align: center; color: #888;">{q.get('previous_score', 0)} &rarr; {q.get('current_score', 0)}</td>
                </tr>
            """
        for q in declined:
            query_rows_cmp += f"""
                <tr style="background: #fef2f2;">
                    <td>{q.get('query', '')}</td>
                    <td style="text-align: center; color: #922B21; font-weight: 600;">{q['change']} pts</td>
                    <td style="text-align: center; color: #888;">{q.get('previous_score', 0)} &rarr; {q.get('current_score', 0)}</td>
                </tr>
            """

        queries_improved = comparison.get('queries_improved', 0)
        queries_declined = comparison.get('queries_declined', 0)
        queries_unchanged = comparison.get('queries_unchanged', 0)

        # Build query table separately (Python 3.9 can't have backslashes in f-strings)
        query_table_cmp = ""
        if query_rows_cmp:
            query_table_cmp = (
                "<table style='font-size: 9pt; margin: 0;'><thead><tr>"
                "<th>Query</th><th style='width: 80px;'>Change</th>"
                "<th style='width: 80px;'>Score</th></tr></thead><tbody>"
                + query_rows_cmp +
                "</tbody></table>"
            )

        # Build side-by-side platform bar charts
        platform_bars_html = ""
        for p_key in ['chatgpt', 'claude', 'gemini', 'perplexity']:
            p_data = comparison.get('platform_changes', {}).get(p_key, {})
            p_prev = p_data.get('previous', 0)
            p_cur = p_data.get('current', 0)
            p_change = p_data.get('change', 0)
            p_sign = '+' if p_change >= 0 else ''
            p_color = '#1E8449' if p_change > 0 else '#922B21' if p_change < 0 else '#888'
            prev_fill = _platform_fill_class(p_prev)
            cur_fill = _platform_fill_class(p_cur)
            platform_bars_html += f"""
                <div style="background: white; padding: 16px 20px; border-radius: 10px; border: 1px solid #e5e7eb;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <span style="font-weight: 600; font-size: 11pt; color: #333;">{platform_names_cmp.get(p_key, p_key)}</span>
                        <span style="font-weight: 700; font-size: 12pt; color: {p_color};">{p_sign}{p_change:.1f}%</span>
                    </div>
                    <div style="margin-bottom: 6px;">
                        <div style="display: flex; justify-content: space-between; font-size: 8pt; color: #999; margin-bottom: 2px;">
                            <span>Previous: {p_prev:.0f}%</span>
                        </div>
                        <div style="width: 100%; height: 6px; background: #eee; border-radius: 3px; overflow: hidden;">
                            <div class="{prev_fill}" style="width: {p_prev:.0f}%; height: 100%; border-radius: 3px; opacity: 0.4;"></div>
                        </div>
                    </div>
                    <div>
                        <div style="display: flex; justify-content: space-between; font-size: 8pt; color: #555; margin-bottom: 2px;">
                            <span>Current: {p_cur:.0f}%</span>
                        </div>
                        <div style="width: 100%; height: 6px; background: #eee; border-radius: 3px; overflow: hidden;">
                            <div class="{cur_fill}" style="width: {p_cur:.0f}%; height: 100%; border-radius: 3px;"></div>
                        </div>
                    </div>
                </div>
            """

        # Build FULL query-by-query comparison table (all queries, not just top 3/2)
        full_query_rows_cmp = ""
        for q in query_changes:
            q_change = q.get('change', 0)
            q_sign = '+' if q_change > 0 else ''
            if q_change > 0:
                row_bg = '#f0fdf4'
                change_html = f'<span style="color: #1E8449; font-weight: 600;">&#9650; {q_sign}{q_change}</span>'
            elif q_change < 0:
                row_bg = '#fef2f2'
                change_html = f'<span style="color: #922B21; font-weight: 600;">&#9660; {q_change}</span>'
            else:
                row_bg = '#fff'
                change_html = '<span style="color: #888;">&mdash;</span>'

            full_query_rows_cmp += f"""
                <tr style="background: {row_bg};">
                    <td style="font-size: 9pt;">{q.get('query', '')}</td>
                    <td style="text-align: center; font-size: 9pt; color: #999;">{q.get('type', '')}</td>
                    <td style="text-align: center; font-size: 9pt;">{q.get('previous_score', 0)}/12</td>
                    <td style="text-align: center; font-size: 9pt; font-weight: 600;">{q.get('current_score', 0)}/12</td>
                    <td style="text-align: center; font-size: 9pt;">{change_html}</td>
                </tr>
            """

        comparison_html = f"""
    <div class="page-break"></div>

    <!-- ===== PROGRESS REPORT PAGE ===== -->
    <div class="section-header">
        <h2>Progress Since Last Audit</h2>
    </div>
    <p style="font-size: 10pt; color: #888; margin-bottom: 25px;">Compared to audit from {prev_date}</p>

    <!-- Big score change hero -->
    <div style="background: linear-gradient(135deg, #f0fdf4, #ecfdf5); border: 1px solid #86efac; border-radius: 16px; padding: 35px 40px; margin-bottom: 30px; text-align: center; page-break-inside: avoid;">
        <div style="font-size: 48pt; font-weight: 800; color: {change_color}; line-height: 1;">{arrow} {change_sign}{pct_change:.1f}%</div>
        <div style="font-size: 14pt; color: #555; margin-top: 10px; font-weight: 500;">{prev_pct:.1f}% &rarr; {cur_pct:.1f}% overall visibility</div>
        <div style="font-size: 11pt; color: #888; margin-top: 8px;">{queries_improved} queries improved &middot; {queries_declined} declined &middot; {queries_unchanged} unchanged</div>
    </div>

    <!-- Platform comparison with before/after bars -->
    <h3 style="color: #333; font-size: 13pt; margin: 25px 0 15px 0;">Platform-by-Platform Progress</h3>
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 30px; page-break-inside: avoid;">
        {platform_bars_html}
    </div>

    <!-- Query-by-query detail is shown in the Detailed Query Results table with +/- column -->
        """

    # Build sections that are excluded from re-audits
    score_interpretation_html = ""
    if not is_reaudit:
        score_interpretation_html = """<div class="score-interpretation">
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
    </div>"""

    geo_explainer_html = ""
    if not is_reaudit:
        geo_explainer_html = f"""<div class="geo-explainer">
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
    </div>"""

    competitor_section_html = ""
    if not is_reaudit:
        competitor_section_html = f"""<div class="section-header">
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
    </table>"""

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
            --brand-orange: #{color};
            --dark-primary: #2C3E50;
            --dark-secondary: #34495E;
            --warm-gray: #6B7280;
            --red-accent: #A93226;
            --maroon-accent: #7B241C;
            --cream-bg: #F9FAFB;
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
            color: var(--brand-orange);
            letter-spacing: -1px;
        }}

        .header {{
            border-bottom: none;
            padding-bottom: 20px;
            margin-bottom: 30px;
            text-align: center;
        }}

        h1 {{
            color: var(--dark-primary);
            font-size: 28pt;
            font-weight: 800;
            margin: 0 0 5px 0;
        }}

        .subtitle {{
            font-size: 14pt;
            color: var(--warm-gray);
            font-style: italic;
            margin: 0;
        }}

        h2 {{
            color: var(--dark-primary);
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
            background: var(--brand-orange);
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
            border-left: 5px solid var(--dark-secondary);
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
            background: var(--dark-primary);
            color: white;
            padding: 35px 40px;
            border-radius: 16px;
            margin: 30px 0;
            text-align: center;
        }}

        .score-summary h2 {{
            color: rgba(255,255,255,0.8);
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
            color: var(--brand-orange);
        }}

        .score-label {{
            font-size: 20pt;
            font-weight: 600;
            color: rgba(255,255,255,0.9);
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
            background: var(--dark-primary);
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
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 25px;
            border-top: 4px solid var(--dark-primary);
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            text-align: center;
        }}

        .platform-card h3 {{
            margin: 0 0 15px 0;
            color: var(--dark-primary);
            font-size: 13pt;
            font-weight: 600;
        }}

        .platform-score {{
            font-size: 36pt;
            font-weight: 800;
            color: var(--dark-primary);
            font-style: italic;
            margin: 10px 0;
        }}

        .platform-visibility {{
            font-size: 11pt;
            color: var(--dark-secondary);
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
            border-left: 5px solid #d1d5db;
            border-radius: 0 12px 12px 0;
            padding: 20px 25px;
            margin: 20px 0;
        }}

        .recommendation h4 {{
            margin: 0 0 15px 0;
            color: var(--dark-primary);
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
            border-left-color: var(--brand-orange);
            background: #FEF5F0;
        }}
        .priority-medium {{
            border-left-color: var(--dark-secondary);
            background: #F3F4F6;
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
            height: 6px;
            background: linear-gradient(90deg,
                var(--dark-primary) 0%,
                var(--brand-orange) 50%,
                var(--dark-primary) 100%
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

        /* Cover page prepared-by line */
        .prepared-by {{
            text-align: center;
            font-size: 9pt;
            color: #999;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }}

        .prepared-by strong {{
            color: #666;
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
            .key-findings,
            .footer {{
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
            border-left: 5px solid var(--dark-secondary);
        }}

        .geo-explainer h3 {{
            color: var(--dark-primary);
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
    <!-- ===== PAGE 1: COVER ===== -->
    <div class="logo-area">
        {logo_html}
    </div>

    <div class="header">
        <h1>GENERATIVE ENGINE OPTIMIZATION AUDIT</h1>
        <p class="subtitle">AI Visibility Analysis Report</p>
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
        {"<p class='score-note' style='margin-top: 10px; font-size: 13pt; font-weight: 600;'>" + ("&#9650; +" if comparison.get("percentage_change", 0) >= 0 else "&#9660; ") + f"{comparison.get('percentage_change', 0):.1f}% since last audit</p>" if is_reaudit else ""}
    </div>

    {score_interpretation_html}

    <div class="prepared-by">
        Prepared by <strong>Third Sun Productions</strong> &middot; thirdsunproductions.com
    </div>

    <div class="page-break"></div>

    <!-- ===== PAGE 2: CONTEXT + ANALYSIS ===== -->
    {geo_explainer_html}

    <div class="section-header">
        <h2>Executive Summary</h2>
    </div>
    <div class="executive-summary">
        {"" if not is_reaudit else "<p><em>This is a follow-up audit measuring progress since the previous assessment.</em></p>"}
        <p>
            {client.get('name', 'The client')} {"now demonstrates" if is_reaudit else "demonstrates"} <strong>{_visibility_label(percentage).lower()} visibility</strong>
            across AI-powered search engines, scoring {percentage:.0f}% overall{(", up from " + str(comparison['previous_percentage']) + "%.") if is_reaudit and comparison.get('percentage_change', 0) > 0 else (", down from " + str(comparison['previous_percentage']) + "%.") if is_reaudit and comparison.get('percentage_change', 0) < 0 else "."}
            {_reaudit_executive_context(comparison.get('previous_percentage', 0), percentage, comparison.get('percentage_change', 0), comparison.get('queries_improved', 0), comparison.get('queries_declined', 0)) if is_reaudit else _executive_context(percentage, len(queries))}
        </p>

        <p><strong>KEY FINDINGS</strong></p>
        <ul class="key-findings">
            {findings_html}
        </ul>
    </div>

    {comparison_html}

    <div class="page-break"></div>

    <!-- ===== PAGE 3+: DETAILED DATA ===== -->
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
            {query_table_header}
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

    <!-- ===== RECOMMENDATIONS ===== -->
    <div class="section-header">
        <h2>Top Recommendations</h2>
    </div>
    <p style="font-size: 10pt; color: #888; margin-bottom: 20px;">
        {len(recommendations)} prioritized actions to improve your AI visibility
    </p>

    {recommendation_html}

    {competitor_section_html}

    <!-- ===== NEXT STEPS ===== -->
    <div class="section-header">
        <h2>Next Steps</h2>
    </div>
    <div class="geo-explainer" style="border-left-color: var(--brand-orange);">
        <p style="font-size: 11pt; margin: 0 0 12px 0;"><strong>Your path forward:</strong></p>
        {"<ul class='key-findings' style='margin: 0;'><li><strong>Review the updated recommendations</strong> — these account for progress made since the last audit and focus on what still needs attention</li><li><strong>Continue implementation</strong> — some changes may not yet be reflected in AI responses due to indexing delays (typically 4–8 weeks)</li><li><strong>Schedule another follow-up audit in 30–60 days</strong> to continue tracking momentum</li></ul>" if is_reaudit else f"<ul class='key-findings' style='margin: 0;'><li><strong>Review the {len(recommendations)} recommendations</strong> in this report, starting with the high-priority items</li><li><strong>Implement changes</strong> — focus on structured data, content optimization, and authority signals first</li><li><strong>Schedule a re-audit in 30–60 days</strong> to measure improvement and track progress over time</li></ul>"}
    </div>

    <div class="footer">
        <p><strong>GEO Audit Report</strong> &middot; {client.get('name', '')} &middot; {client.get('audit_date', '')}</p>
        <p>Prepared by Third Sun Productions &middot; thirdsunproductions.com</p>
    </div>

    <!-- Gradient Footer Bar -->
    <div class="gradient-footer"></div>
</body>
</html>
    """

    return html
