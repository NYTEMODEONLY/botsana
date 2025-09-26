"""
Flask application for Botsana webhook handling.
This runs the web server for receiving Asana webhooks.
"""

from flask import Flask, request, jsonify
import os
import logging
from bot import process_webhook_events, audit_manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Handle incoming Asana webhooks."""
    try:
        # Verify webhook secret if provided
        secret = request.headers.get('X-Hook-Secret')
        if secret:
            # This is a webhook registration request
            response = jsonify({'status': 'ok'})
            response.headers['X-Hook-Secret'] = secret
            return response

        # Get webhook data
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No data received'}), 400

        # Process webhook events asynchronously
        import asyncio
        asyncio.run(process_webhook_events(data))

        return jsonify({'status': 'ok'}), 200

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Heroku."""
    return jsonify({'status': 'healthy', 'service': 'botsana-webhook'}), 200

@app.route('/', methods=['GET'])
def index():
    """Root endpoint."""
    return jsonify({
        'service': 'Botsana Webhook Handler',
        'status': 'running',
        'endpoints': ['/webhook', '/health']
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
