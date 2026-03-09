"""UI routes — serve the form page, preview reports, download PDFs."""

import os
import tempfile
import subprocess

from flask import Blueprint, request, render_template, send_file

from report import generate_report_html

ui_bp = Blueprint('ui', __name__)


@ui_bp.route('/')
def index():
    """Serve the main form page."""
    return render_template('index.html')


@ui_bp.route('/preview', methods=['POST'])
def preview():
    """Generate HTML preview."""
    data = request.json
    html = generate_report_html(data)
    return html


@ui_bp.route('/download-pdf', methods=['POST'])
def download_pdf():
    """Generate and download PDF."""
    data = request.json
    html = generate_report_html(data)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write(html)
        html_path = f.name

    pdf_path = html_path.replace('.html', '.pdf')

    try:
        chrome_paths = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Chromium.app/Contents/MacOS/Chromium'
        ]

        for chrome_path in chrome_paths:
            if os.path.exists(chrome_path):
                subprocess.run([
                    chrome_path,
                    '--headless',
                    '--disable-gpu',
                    '--print-to-pdf=' + pdf_path,
                    'file://' + html_path
                ], check=True, capture_output=True, timeout=30)
                break
        else:
            subprocess.run(
                ['wkhtmltopdf', '--enable-local-file-access', html_path, pdf_path],
                check=True,
                capture_output=True
            )

        client_name = data.get('client', {}).get('name', 'Client').replace(' ', '_')

        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'{client_name}_GEO_Audit_Report.pdf'
        )

    finally:
        if os.path.exists(html_path):
            os.unlink(html_path)
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)
