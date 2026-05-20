"""
AgentBay Platform Backend - Simple Version
For Render.com deployment
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import uuid
from datetime import datetime

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
    """Run an agent"""
    if agent_id not in agents_db:
        return jsonify({'error': 'Agent not found'}), 404

    data = request.json
    user_input = data.get('input')

    if not user_input:
        return jsonify({'error': 'No input provided'}), 400

    agent = agents_db[agent_id]

    # Update usage
    usage_db[agent_id]['total_calls'] += 1

    return jsonify({
        'success': True,
        'agent_name': agent['name'],
        'user_input': user_input,
        'message': 'Agent ready to execute. Connect to Claude API to process.'
    }), 200


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
