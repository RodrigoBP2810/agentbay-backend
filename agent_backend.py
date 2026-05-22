"""
AgentBay Platform Backend - With Claude API Integration
For Render.com deployment
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import uuid
from datetime import datetime
import requests

app = Flask(__name__)
CORS(app)

# In-memory storage
agents_db = {}
users_db = {}
usage_db = {}


@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    }), 200


@app.route('/api/info', methods=['GET'])
def info():
    """Platform info"""
    return jsonify({
        'platform': 'AgentBay',
        'version': '1.0.0',
        'status': 'running'
    }), 200


@app.route('/api/register', methods=['POST'])
def register_user():
    """Register a new creator"""
    data = request.json
    username = data.get('username')
    email = data.get('email')
    api_key = data.get('anthropic_api_key')

    if not all([username, email, api_key]):
        return jsonify({'error': 'Missing fields'}), 400

    user_id = str(uuid.uuid4())
    users_db[user_id] = {
        'id': user_id,
        'username': username,
        'email': email,
        'api_key': api_key,
        'created_at': datetime.now().isoformat(),
        'agents': [],
        'total_earnings': 0.0
    }

    return jsonify({
        'success': True,
        'user_id': user_id,
        'message': f'Welcome {username}!'
    }), 201


@app.route('/api/agents', methods=['POST'])
def create_agent():
    """Create a new agent"""
    data = request.json
    user_id = data.get('user_id')

    if user_id not in users_db:
        return jsonify({'error': 'User not found'}), 404

    agent_config = {
        'id': str(uuid.uuid4()),
        'creator_id': user_id,
        'name': data.get('name'),
        'description': data.get('description'),
        'system_prompt': data.get('system_prompt'),
        'created_at': datetime.now().isoformat(),
        'status': 'active',
        'price_per_call': data.get('price_per_call', 0.01)
    }

    if not all([agent_config['name'], agent_config['description'], agent_config['system_prompt']]):
        return jsonify({'error': 'Missing required fields'}), 400

    agents_db[agent_config['id']] = agent_config
    users_db[user_id]['agents'].append(agent_config['id'])
    usage_db[agent_config['id']] = {'total_calls': 0, 'total_tokens': 0}

    return jsonify({
        'success': True,
        'agent': agent_config
    }), 201


@app.route('/api/agents', methods=['GET'])
def list_agents():
    """List all agents"""
    agents_list = list(agents_db.values())
    return jsonify({
        'agents': agents_list,
        'total': len(agents_list)
    }), 200


@app.route('/api/agents/<agent_id>', methods=['GET'])
def get_agent(agent_id):
    """Get agent details"""
    if agent_id not in agents_db:
        return jsonify({'error': 'Agent not found'}), 404

    agent = agents_db[agent_id]
    usage = usage_db.get(agent_id, {})

    return jsonify({
        'agent': agent,
        'usage': usage
    }), 200


@app.route('/api/agents/<agent_id>/run', methods=['POST'])
def run_agent(agent_id):
    """Run an agent - Call Claude API and return response"""
    data = request.json
    user_input = data.get('input')
    api_key = data.get('api_key')
    system_prompt = data.get('system_prompt')

    if not user_input:
        return jsonify({'error': 'No input provided'}), 400

    if not api_key:
        return jsonify({'error': 'No API key provided'}), 400

    try:
        # Call Claude API
        response = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'Content-Type': 'application/json',
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01'
            },
            json={
                'model': 'claude-opus',
                'max_tokens': 1024,
                'system': system_prompt if system_prompt else 'You are a helpful assistant.',
                'messages': [{
                    'role': 'user',
                    'content': user_input
                }]
            }
        )

        response_data = response.json()

        if response.status_code != 200:
            error_msg = response_data.get('error', {}).get('message', 'Unknown error')
            return jsonify({
                'success': False,
                'error': error_msg
            }), response.status_code

        # Extract response
        assistant_message = response_data['content'][0]['text']
        input_tokens = response_data['usage']['input_tokens']
        output_tokens = response_data['usage']['output_tokens']
        total_tokens = input_tokens + output_tokens

        # Track usage if agent exists
        if agent_id in agents_db:
            usage_db[agent_id]['total_calls'] += 1
            usage_db[agent_id]['total_tokens'] += total_tokens

        return jsonify({
            'success': True,
            'response': assistant_message,
            'tokens': total_tokens,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/user/<user_id>', methods=['GET'])
def get_user(user_id):
    """Get user profile"""
    if user_id not in users_db:
        return jsonify({'error': 'User not found'}), 404

    user = users_db[user_id]
    return jsonify({
        'user': {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'agent_count': len(user['agents']),
            'total_earnings': user['total_earnings']
        }
    }), 200


@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Server error'}), 500


if __name__ == '__main__':
    app.run(debug=False, port=5000)
