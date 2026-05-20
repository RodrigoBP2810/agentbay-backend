"""
AgentBay Platform Backend Service
==================================

This is the backend infrastructure for hosting and running AI agents at scale.
It handles:
- Agent registration and storage
- User authentication and API key management
- Agent execution through Claude API
- Usage tracking and billing
- Creator payouts and analytics

Installation:
pip install flask flask-cors anthropic python-dotenv

Usage:
python agent_backend.py

The service will run on http://localhost:5000
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from anthropic import Anthropic
from datetime import datetime
import json
import os
from dotenv import load_dotenv
import uuid

load_dotenv()

app = Flask(__name__)
CORS(app)

# In-memory storage (in production, use PostgreSQL/MongoDB)
agents_db = {}
users_db = {}
usage_db = {}

# Initialize Anthropic client
client = Anthropic()


# ============================================================================
# USER & AUTHENTICATION ENDPOINTS
# ============================================================================

@app.route('/api/register', methods=['POST'])
def register_user():
    """Register a new creator account"""
    data = request.json
    username = data.get('username')
    email = data.get('email')
    api_key = data.get('anthropic_api_key')

    if not all([username, email, api_key]):
        return jsonify({'error': 'Missing required fields'}), 400

    user_id = str(uuid.uuid4())
    users_db[user_id] = {
        'id': user_id,
        'username': username,
        'email': email,
        'api_key': api_key,  # In production: encrypt this
        'created_at': datetime.now().isoformat(),
        'agents': [],
        'total_earnings': 0.0
    }

    return jsonify({
        'success': True,
        'user_id': user_id,
        'message': f'Welcome {username}!'
    }), 201


@app.route('/api/user/<user_id>', methods=['GET'])
def get_user_profile(user_id):
    """Get user profile and statistics"""
    if user_id not in users_db:
        return jsonify({'error': 'User not found'}), 404

    user = users_db[user_id]
    agent_count = len(user['agents'])

    # Calculate usage for this user's agents
    total_usage = sum(
        usage_db.get(agent_id, {}).get('total_calls', 0)
        for agent_id in user['agents']
    )

    return jsonify({
        'user': {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'created_at': user['created_at'],
            'agent_count': agent_count,
            'total_calls': total_usage,
            'total_earnings': user['total_earnings']
        }
    }), 200


# ============================================================================
# AGENT MANAGEMENT ENDPOINTS
# ============================================================================

@app.route('/api/agents', methods=['POST'])
def create_agent():
    """Create a new agent from configuration"""
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
        'capabilities': data.get('capabilities', []),
        'input_type': data.get('input_type', 'text'),
        'output_type': data.get('output_type', 'text'),
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat(),
        'status': 'active',
        'version': data.get('version', '1.0.0'),
        'price_per_call': data.get('price_per_call', 0.01),
        'monthly_subscription': data.get('monthly_subscription', 0.0),
        'call_limit_per_month': data.get('call_limit_per_month', 10000)
    }

    # Validate required fields
    if not all([agent_config['name'], agent_config['description'], agent_config['system_prompt']]):
        return jsonify({'error': 'Missing required agent fields'}), 400

    # Store agent
    agents_db[agent_config['id']] = agent_config
    users_db[user_id]['agents'].append(agent_config['id'])
    usage_db[agent_config['id']] = {
        'total_calls': 0,
        'total_tokens': 0,
        'created_at': datetime.now().isoformat()
    }

    return jsonify({
        'success': True,
        'agent': agent_config,
        'message': f'Agent "{agent_config["name"]}" created successfully!'
    }), 201


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


@app.route('/api/agents', methods=['GET'])
def list_agents():
    """List all published agents (marketplace)"""
    # In production, filter by status, categories, ratings, etc.
    agents_list = [
        {
            **agent,
            'usage_stats': usage_db.get(agent_id, {})
        }
        for agent_id, agent in agents_db.items()
        if agent.get('status') == 'active'
    ]

    return jsonify({
        'agents': agents_list,
        'total': len(agents_list)
    }), 200


@app.route('/api/agents/<agent_id>', methods=['PUT'])
def update_agent(agent_id):
    """Update agent configuration"""
    if agent_id not in agents_db:
        return jsonify({'error': 'Agent not found'}), 404

    data = request.json
    agent = agents_db[agent_id]

    # Update allowed fields
    if 'name' in data:
        agent['name'] = data['name']
    if 'description' in data:
        agent['description'] = data['description']
    if 'system_prompt' in data:
        agent['system_prompt'] = data['system_prompt']
    if 'price_per_call' in data:
        agent['price_per_call'] = data['price_per_call']

    agent['updated_at'] = datetime.now().isoformat()

    return jsonify({
        'success': True,
        'agent': agent,
        'message': 'Agent updated successfully'
    }), 200


# ============================================================================
# AGENT EXECUTION ENDPOINTS
# ============================================================================

@app.route('/api/agents/<agent_id>/run', methods=['POST'])
def run_agent(agent_id):
    """Execute an agent with user input"""
    if agent_id not in agents_db:
        return jsonify({'error': 'Agent not found'}), 404

    data = request.json
    user_input = data.get('input')
    user_id = data.get('user_id')  # Required for billing

    if not user_input:
        return jsonify({'error': 'No input provided'}), 400

    agent = agents_db[agent_id]

    # Get the creator's API key
    creator_id = agent['creator_id']
    if creator_id not in users_db:
        return jsonify({'error': 'Creator not found'}), 404

    creator = users_db[creator_id]

    # Create Anthropic client with creator's API key
    client = Anthropic(api_key=creator['api_key'])

    try:
        # Call Claude API with agent's system prompt
        response = client.messages.create(
            model='claude-3-5-sonnet-20241022',
            max_tokens=1024,
            system=agent['system_prompt'],
            messages=[
                {'role': 'user', 'content': user_input}
            ]
        )

        # Extract response
        result_text = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        total_tokens = input_tokens + output_tokens

        # Update usage statistics
        usage_db[agent_id]['total_calls'] += 1
        usage_db[agent_id]['total_tokens'] += total_tokens

        # Calculate cost (in production, integrate with billing system)
        # Using Claude pricing: approximately $0.003 per 1K input tokens, $0.015 per 1K output tokens
        cost = (input_tokens * 0.003 / 1000) + (output_tokens * 0.015 / 1000)

        # Update creator earnings (70% goes to creator, 30% to platform)
        creator_earnings = cost * 0.70
        users_db[creator_id]['total_earnings'] += creator_earnings

        return jsonify({
            'success': True,
            'agent_name': agent['name'],
            'user_input': user_input,
            'response': result_text,
            'tokens': {
                'input': input_tokens,
                'output': output_tokens,
                'total': total_tokens
            },
            'cost': {
                'total': round(cost, 6),
                'creator_earnings': round(creator_earnings, 6),
                'platform_fee': round(cost * 0.30, 6)
            }
        }), 200

    except Exception as e:
        return jsonify({
            'error': 'Failed to execute agent',
            'details': str(e)
        }), 500


# ============================================================================
# ANALYTICS & USAGE ENDPOINTS
# ============================================================================

@app.route('/api/agents/<agent_id>/analytics', methods=['GET'])
def get_agent_analytics(agent_id):
    """Get analytics for a specific agent"""
    if agent_id not in agents_db:
        return jsonify({'error': 'Agent not found'}), 404

    if agent_id not in usage_db:
        usage = {'total_calls': 0, 'total_tokens': 0}
    else:
        usage = usage_db[agent_id]

    agent = agents_db[agent_id]

    # Estimate earnings
    estimated_revenue = usage['total_calls'] * agent['price_per_call']
    creator_earnings = estimated_revenue * 0.70

    return jsonify({
        'agent_id': agent_id,
        'agent_name': agent['name'],
        'total_calls': usage['total_calls'],
        'total_tokens': usage['total_tokens'],
        'average_tokens_per_call': usage['total_tokens'] / max(usage['total_calls'], 1),
        'estimated_revenue': round(estimated_revenue, 2),
        'creator_earnings': round(creator_earnings, 2),
        'platform_fee': round(estimated_revenue * 0.30, 2)
    }), 200


@app.route('/api/user/<user_id>/earnings', methods=['GET'])
def get_user_earnings(user_id):
    """Get earnings summary for a creator"""
    if user_id not in users_db:
        return jsonify({'error': 'User not found'}), 404

    user = users_db[user_id]

    # Calculate detailed earnings per agent
    earnings_breakdown = []
    total_calls = 0
    total_tokens = 0

    for agent_id in user['agents']:
        agent = agents_db[agent_id]
        usage = usage_db.get(agent_id, {'total_calls': 0, 'total_tokens': 0})

        calls = usage['total_calls']
        tokens = usage['total_tokens']
        revenue = calls * agent['price_per_call']
        creator_share = revenue * 0.70

        earnings_breakdown.append({
            'agent_id': agent_id,
            'agent_name': agent['name'],
            'calls': calls,
            'tokens': tokens,
            'revenue': round(revenue, 2),
            'creator_earnings': round(creator_share, 2)
        })

        total_calls += calls
        total_tokens += tokens

    return jsonify({
        'user_id': user_id,
        'username': user['username'],
        'total_earnings': round(user['total_earnings'], 2),
        'total_calls': total_calls,
        'total_tokens': total_tokens,
        'agents_count': len(user['agents']),
        'earnings_breakdown': earnings_breakdown
    }), 200


# ============================================================================
# HEALTH & INFO ENDPOINTS
# ============================================================================

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'agents_count': len(agents_db),
        'users_count': len(users_db),
        'timestamp': datetime.now().isoformat()
    }), 200


@app.route('/api/info', methods=['GET'])
def platform_info():
    """Platform information"""
    return jsonify({
        'platform': 'AgentBay',
        'version': '1.0.0',
        'features': [
            'Visual agent builder',
            'No-code agent creation',
            'Claude API integration',
            'Usage tracking',
            'Creator payouts (70/30 split)',
            'Agent marketplace',
            'Real-time execution'
        ],
        'pricing': {
            'creator_share': '70%',
            'platform_fee': '30%',
            'per_agent_call': 'Variable',
            'monthly_subscription': 'Optional'
        }
    }), 200


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500


# ============================================================================
# EXAMPLE USAGE & TESTING
# ============================================================================

def example_usage():
    """Example of how to use the API"""
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║            AgentBay Platform - Example Usage               ║
    ╚════════════════════════════════════════════════════════════╝

    1. Register a creator:
    POST /api/register
    {
        "username": "jane_creator",
        "email": "jane@example.com",
        "anthropic_api_key": "sk-ant-..."
    }

    2. Create an agent:
    POST /api/agents
    {
        "user_id": "<user_id>",
        "name": "Customer Support Bot",
        "description": "Helps customers with product questions",
        "system_prompt": "You are a helpful customer support agent...",
        "price_per_call": 0.01
    }

    3. Run the agent:
    POST /api/agents/<agent_id>/run
    {
        "user_id": "<user_id>",
        "input": "What's your refund policy?"
    }

    4. Check earnings:
    GET /api/user/<user_id>/earnings

    5. View marketplace:
    GET /api/agents

    ═══════════════════════════════════════════════════════════════

    DEPLOYMENT CONSIDERATIONS:

    • Database: Replace in-memory storage with PostgreSQL
    • Authentication: Use JWT tokens instead of user_id in requests
    • API Keys: Encrypt stored Anthropic API keys
    • Rate Limiting: Implement per-agent and per-user rate limits
    • Billing: Integrate with Stripe for payments
    • Monitoring: Add logging and error tracking (Sentry)
    • Caching: Use Redis for frequently accessed agents
    • Load Balancing: Deploy multiple instances behind a load balancer
    • CDN: Serve static files through CloudFlare
    • Scaling: Use Kubernetes for container orchestration

    ═══════════════════════════════════════════════════════════════
    """)


if __name__ == '__main__':
    example_usage()
    print("Starting AgentBay Platform Backend...")
    print("Server running on http://localhost:5000")
    print("Documentation available at /api/info")
    app.run(debug=True, port=5000)
