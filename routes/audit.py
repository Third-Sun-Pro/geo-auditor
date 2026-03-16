"""Audit routes — run audits, competitor checks, website analysis, API status."""

from flask import Blueprint, request, jsonify

from config import openai_client, anthropic_client, gemini_model, perplexity_client, any_api_configured
from services import run_full_audit, run_competitor_audit, generate_faqs, revise_faqs
from scraper import scrape_website, analyze_website_with_ai, generate_from_intake

audit_bp = Blueprint('audit', __name__)


@audit_bp.route('/run-audit', methods=['POST'])
def run_audit():
    """Run automated GEO audit against AI platforms."""
    data = request.json

    client_name = data.get('client_name', '')
    client_website = data.get('client_website', '')
    queries = data.get('queries', [])
    package_type = data.get('package_type', 'basic')

    if not client_name:
        return jsonify({"error": "Client name is required"}), 400
    if not queries:
        return jsonify({"error": "At least one query is required"}), 400
    if not any_api_configured():
        return jsonify({"error": "No API keys configured. Add at least one to .env file"}), 400

    result = run_full_audit(client_name, client_website, queries, package_type)
    return jsonify(result)


@audit_bp.route('/run-competitor-audit', methods=['POST'])
def run_competitor_audit_route():
    """Run visibility checks for competitors using the same queries."""
    data = request.json

    competitors = data.get('competitors', [])
    queries = data.get('queries', [])

    if not competitors:
        return jsonify({"error": "At least one competitor is required"}), 400
    if not queries:
        return jsonify({"error": "At least one query is required"}), 400
    if not any_api_configured():
        return jsonify({"error": "No API keys configured. Add at least one to .env file"}), 400

    result = run_competitor_audit(
        competitors=competitors,
        queries=queries,
        client_visibility=data.get('client_visibility', 0),
        client_name=data.get('client_name', ''),
        industry=data.get('industry', ''),
        location=data.get('location', ''),
        client_services=data.get('client_services', ''),
    )
    return jsonify(result)


@audit_bp.route('/analyze-website', methods=['POST'])
def analyze_website():
    """Analyze a website URL and return business info + suggested queries."""
    data = request.json
    url = data.get('url', '').strip()

    if not url:
        return jsonify({"error": "URL is required"}), 400

    scraped = scrape_website(url)
    if not scraped.get('success'):
        return jsonify({"error": f"Failed to fetch website: {scraped.get('error')}"}), 400

    analysis = analyze_website_with_ai(scraped)
    if not analysis.get('success'):
        return jsonify({"error": f"Failed to analyze website: {analysis.get('error')}"}), 400

    return jsonify({
        "success": True,
        "url": url,
        "data": analysis.get('data')
    })


@audit_bp.route('/generate-from-intake', methods=['POST'])
def generate_from_intake_route():
    """Parse pasted questionnaire answers and generate queries + client details."""
    data = request.json
    intake_text = data.get('intake_text', '').strip()

    if not intake_text:
        return jsonify({"error": "Intake text is required"}), 400

    result = generate_from_intake(
        intake_text=intake_text,
        client_name=data.get('client_name', ''),
        location=data.get('location', ''),
        industry=data.get('industry', ''),
    )

    if not result.get('success'):
        return jsonify({"error": result.get('error', 'Failed to process intake')}), 400

    return jsonify(result)


@audit_bp.route('/generate-faqs', methods=['POST'])
def generate_faqs_route():
    """Generate website-ready FAQs from audit data using Claude."""
    data = request.json

    client_name = data.get('client_name', '')
    if not client_name:
        return jsonify({"error": "Client name is required"}), 400

    if not anthropic_client:
        return jsonify({"error": "Anthropic API key not configured"}), 400

    result = generate_faqs(
        client_name=client_name,
        client_website=data.get('client_website', ''),
        industry=data.get('industry', ''),
        location=data.get('location', ''),
        queries=data.get('queries', []),
        visibility_percentage=data.get('visibility_percentage', 0),
        key_findings=data.get('key_findings', []),
        recommendations=data.get('recommendations', []),
        competitors=data.get('competitors', []),
        num_faqs=data.get('num_faqs', 8),
    )

    if 'error' in result:
        return jsonify(result), 400

    return jsonify(result)


@audit_bp.route('/revise-faqs', methods=['POST'])
def revise_faqs_route():
    """Revise previously generated FAQs based on user feedback."""
    data = request.json

    client_name = data.get('client_name', '')
    if not client_name:
        return jsonify({"error": "Client name is required"}), 400

    faqs = data.get('faqs', [])
    feedback = data.get('feedback', '').strip()
    if not faqs or not feedback:
        return jsonify({"error": "FAQs and feedback are required"}), 400

    if not anthropic_client:
        return jsonify({"error": "Anthropic API key not configured"}), 400

    result = revise_faqs(
        faqs=faqs,
        feedback=feedback,
        client_name=client_name,
        client_website=data.get('client_website', ''),
        industry=data.get('industry', ''),
        location=data.get('location', ''),
    )

    if 'error' in result:
        return jsonify(result), 400

    return jsonify(result)


@audit_bp.route('/check-api-keys')
def check_api_keys():
    """Check which API keys are configured."""
    return jsonify({
        "openai": bool(openai_client),
        "anthropic": bool(anthropic_client),
        "perplexity": bool(perplexity_client),
        "google": bool(gemini_model)
    })
