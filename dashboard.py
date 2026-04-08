from flask import Flask, render_template, jsonify
import json, os

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/paper')
def api_paper():
    try:
        with open('data_paper.json', 'r') as f:
            return jsonify(json.load(f))
    except:
        return jsonify({})

@app.route('/api/real')
def api_real():
    try:
        with open('data_real.json', 'r') as f:
            return jsonify(json.load(f))
    except:
        return jsonify({})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
